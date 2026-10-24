import json

import duckdb
import pytest

from scripts.build_warehouse_analysis import (
    build_warehouse_analysis,
    classify_cancellation_blocker,
    public_quality_payload,
)


def _write_test_parquet(path):
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE rows AS SELECT * FROM (VALUES
          ('a', 'hotel-a', 'official', '2026-10-18T01:00:00Z', '2026-11-02', '2026-11-03', 1, 2, 0, false, '45.0', 'included', 'Non-refundable', 10000.0, NULL, NULL, NULL, NULL),
          ('b', 'hotel-a', 'booking_com', '2026-10-18T01:01:00Z', '2026-11-02', '2026-11-03', 1, 2, 0, false, NULL, 'unknown', 'Cancellation policy is available on the official booking page', NULL, NULL, NULL, NULL, NULL),
          ('c', 'hotel-a', 'official', '2026-10-18T01:02:00Z', '2026-11-02', '2026-11-03', 1, 2, 0, true, '"45"', 'unknown', '13~4天之前 訂金的30％ 3~1天之前 訂金的70％ 當天 訂金的100％', NULL, NULL, NULL, NULL, NULL),
          ('d', 'hotel-b', 'official', '2026-10-18T01:03:00Z', '2026-11-02', '2026-11-03', 1, 2, 0, false, '45.0', 'unknown', '�N���������O��', NULL, NULL, NULL, NULL, NULL)
        ) AS t(observation_id, hotel_id, source_platform, queried_at,
               check_in, check_out, rooms, adults, children, breakfast_included,
               room_size_sqm, tax_inclusion, cancellation_policy, nightly_adr_twd,
               total_price, price_before_tax, service_charge, tax)
        """
    )
    connection.execute("COPY rows TO ? (FORMAT PARQUET)", [str(path)])
    connection.close()


def _write_manifest(path, rows):
    path.write_text(
        json.dumps(
            {
                "rows": rows,
                "natural_keys": rows,
                "partitions": [{"month": "2026-10", "sha256": "abc"}],
            }
        ),
        encoding="utf-8",
    )


def test_classify_cancellation_blocker_preserves_non_comparable_notices():
    assert (
        classify_cancellation_blocker(
            "Cancellation policy is available on the official booking page"
        )
        == "generic_placeholder"
    )
    assert classify_cancellation_blocker("將收取取消費用") == "generic_fee_notice"
    assert classify_cancellation_blocker("�N���������O��") == "encoding_corruption"
    assert classify_cancellation_blocker("special conditions apply") == "unparsed_policy"


def test_build_warehouse_analysis_profiles_parquet_deterministically(tmp_path):
    warehouse = tmp_path / "warehouse"
    rates = warehouse / "rates"
    rates.mkdir(parents=True)
    _write_test_parquet(rates / "2026-10.parquet")
    manifest = warehouse / "manifest.json"
    _write_manifest(manifest, 4)
    target = warehouse / "analysis.json"

    payload = build_warehouse_analysis(rates / "*.parquet", manifest, target)

    assert payload["schema_version"] == "1.7"
    assert payload["rows"] == 4
    assert payload["hotels"] == 2
    assert payload["quality"]["known_room_size_ratio"] == 0.75
    assert payload["quality"]["known_tax_ratio"] == 0.25
    assert payload["quality"]["known_cancellation_policy_ratio"] == 1.0
    assert payload["quality"]["known_cancellation_class_ratio"] == 0.5
    assert payload["quality"]["known_cancellation_deadline_ratio"] == 0.25
    assert payload["quality"]["known_cancellation_schedule_ratio"] == 0.25
    assert payload["quality"]["strict_metadata_ready_rows"] == 1
    assert payload["quality"]["strict_metadata_ready_ratio"] == 0.25
    assert payload["quality"]["strict_metadata_missing_fields"] == {
        "tax_inclusion": 3,
        "cancellation_class": 2,
        "cancellation_deadline": 3,
        "room_size": 1,
    }
    assert payload["quality"]["nightly_adr_ratio"] == 0.25
    assert [item["source_platform"] for item in payload["sources"]] == [
        "booking_com",
        "official",
    ]
    assert payload["hotels_by_unknown_room_size"][0]["unknown_room_size_rows"] == 1
    assert payload["hotels_by_unknown_tax"][0]["unknown_tax_rows"] == 2
    assert payload["unknown_cancellation_policies"] == [
        {
            "hotel_id": "hotel-a",
            "source_platform": "booking_com",
            "cancellation_policy": (
                "Cancellation policy is available on the official booking page"
            ),
            "rows": 1,
        },
        {
            "hotel_id": "hotel-b",
            "source_platform": "official",
            "cancellation_policy": "�N���������O��",
            "rows": 1,
        },
    ]
    assert payload["cancellation_blockers"] == [
        {
            "reason": "encoding_corruption",
            "hotel_id": "hotel-b",
            "source_platform": "official",
            "rows": 1,
        },
        {
            "reason": "generic_placeholder",
            "hotel_id": "hotel-a",
            "source_platform": "booking_com",
            "rows": 1,
        },
    ]
    assert payload["strict_metadata_gap_hotels"] == [
        {
            "hotel_id": "hotel-a",
            "source_platform": "booking_com",
            "rows": 1,
            "missing_fields": {
                "cancellation_class": 1,
                "cancellation_deadline": 1,
                "room_size": 1,
                "tax_inclusion": 1,
            },
        },
        {
            "hotel_id": "hotel-a",
            "source_platform": "official",
            "rows": 1,
            "missing_fields": {"cancellation_deadline": 1, "tax_inclusion": 1},
        },
        {
            "hotel_id": "hotel-b",
            "source_platform": "official",
            "rows": 1,
            "missing_fields": {
                "cancellation_class": 1,
                "cancellation_deadline": 1,
                "tax_inclusion": 1,
            },
        },
    ]
    official = next(
        item for item in payload["sources"] if item["source_platform"] == "official"
    )
    assert official["known_cancellation_class_rows"] == 2
    assert official["known_cancellation_deadline_rows"] == 1
    assert official["known_cancellation_schedule_rows"] == 1
    assert official["known_cancellation_policy_rows"] == 3
    assert official["strict_metadata_ready_rows"] == 1
    assert official["strict_metadata_ready_ratio"] == pytest.approx(1 / 3, abs=1e-6)
    assert official["strict_metadata_missing_fields"] == {
        "tax_inclusion": 2,
        "cancellation_class": 1,
        "cancellation_deadline": 2,
    }
    assert payload["structured_cancellation_schedules"][0]["schedule"] == [
        {
            "days_before_from": 13,
            "days_before_to": 4,
            "penalty_basis": "deposit",
            "penalty_percent": 30,
        },
        {
            "days_before_from": 3,
            "days_before_to": 1,
            "penalty_basis": "deposit",
            "penalty_percent": 70,
        },
        {
            "days_before_from": 0,
            "days_before_to": 0,
            "penalty_basis": "deposit",
            "penalty_percent": 100,
        },
    ]
    assert json.loads(target.read_text(encoding="utf-8")) == payload

    public = public_quality_payload(payload)
    assert public["rows"] == 4
    assert public["schema_version"] == "1.3"
    assert public["quality"]["known_tax_ratio"] == 0.25
    assert public["quality"]["strict_metadata_ready_ratio"] == 0.25
    assert public["top_tax_gaps"] == [
        {
            "hotel_id": "hotel-a",
            "rows": 3,
            "known_tax_rows": 1,
            "unknown_tax_rows": 2,
        },
        {
            "hotel_id": "hotel-b",
            "rows": 1,
            "known_tax_rows": 0,
            "unknown_tax_rows": 1,
        },
    ]
    assert public["unresolved_cancellation_rows"] == 2
    assert public["unresolved_cancellation_groups"] == 2
    assert public["cancellation_blockers"] == payload["cancellation_blockers"]
    assert public["top_strict_metadata_gaps"] == payload[
        "strict_metadata_gap_hotels"
    ]


def test_build_warehouse_analysis_rejects_manifest_row_mismatch(tmp_path):
    warehouse = tmp_path / "warehouse"
    rates = warehouse / "rates"
    rates.mkdir(parents=True)
    _write_test_parquet(rates / "2026-10.parquet")
    manifest = warehouse / "manifest.json"
    _write_manifest(manifest, 5)

    with pytest.raises(ValueError, match="row mismatch"):
        build_warehouse_analysis(rates / "*.parquet", manifest, warehouse / "analysis.json")
