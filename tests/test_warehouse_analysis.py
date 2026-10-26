import json

import duckdb
import pytest

from scripts.build_warehouse_analysis import (
    STRICT_METADATA_REVIEWS_SOURCE,
    _latest_stream_rows,
    _load_strict_metadata_reviews,
    build_warehouse_analysis,
    classify_cancellation_blocker,
    public_quality_payload,
)


def test_latest_stream_rows_prefers_the_newest_explicit_run_id():
    rows = [
        {
            "hotel_id": "hotel-a",
            "source_platform": "official",
            "queried_at": "2026-10-24T01:00:00Z",
            "run_id": "older",
        },
        {
            "hotel_id": "hotel-a",
            "source_platform": "official",
            "queried_at": "2026-10-24T01:04:00Z",
            "run_id": "newer",
        },
        {
            "hotel_id": "hotel-a",
            "source_platform": "official",
            "queried_at": "2026-10-24T01:05:00Z",
            "run_id": "newer",
        },
    ]

    assert [row["run_id"] for row in _latest_stream_rows(rows)] == [
        "newer",
        "newer",
    ]


def test_repository_metadata_reviews_preserve_known_source_blockers():
    reviews = _load_strict_metadata_reviews(STRICT_METADATA_REVIEWS_SOURCE)
    statuses = {review["hotel_id"]: review["status"] for review in reviews}
    source_keys = {
        (review["hotel_id"], review["source_platform"]) for review in reviews
    }

    assert statuses["grand_hilai_kaohsiung"] == "blocked_source_shell"
    assert statuses["windsor_taichung"] == "blocked_source_unavailable"
    assert statuses["grand_hotel_taipei"] == "blocked_source_unavailable"
    assert statuses["the_gaia_taipei"] == "blocked_source_unavailable"
    assert statuses["grand_mayfull_taipei"] == "blocked_source_unavailable"
    assert statuses["mo_taipei"] == "blocked_source_unavailable"
    assert statuses["renaissance_taipei_shihlin"] == "blocked_source_unavailable"
    assert statuses["radium_kagaya_taipei"] == "blocked_source_unavailable"
    assert statuses["taipei_garden_hotel"] == "blocked_source_unavailable"
    assert statuses["solaria_nishitetsu_taipei"] == "blocked_source_unavailable"
    assert statuses["doubletree_taipei_zhongshan"] == "blocked_source_unavailable"
    assert statuses["howard_plaza_taipei"] == "blocked_source_unavailable"
    assert statuses["humble_house_taipei"] == "blocked_source_unavailable"
    assert statuses["hoshinoya_guguan"] == "blocked_source_unavailable"
    assert statuses["grand_hilai_taipei"] == "blocked_source_unavailable"
    assert statuses["hotel_nikko_kaohsiung"] == "blocked_source_unavailable"
    assert statuses["silks_place_yilan"] == "blocked_source_unavailable"
    assert statuses["taipei_marriott"] == "blocked_source_unavailable"
    assert statuses["grand_hyatt_taipei"] == "blocked_source_unavailable"
    assert statuses["hotel_gracery_taipei"] == "blocked_source_unavailable"
    assert statuses["shangrila_taipei"] == "blocked_source_unavailable"
    assert ("grand_hilai_taipei", "official") in source_keys
    assert ("grand_hilai_taipei", "booking_com") in source_keys
    assert ("okura_prestige_taipei", "official") in source_keys
    assert ("okura_prestige_taipei", "booking_com") in source_keys
    assert statuses["palais_de_chine"] == "blocked_source_unavailable"
    assert statuses["episode_daan_taipei"] == "blocked_source_unavailable"
    assert statuses["hotel_metropolitan_premier_taipei"] == "blocked_source_unavailable"
    assert statuses["hotel_proverbs_taipei"] == "blocked_source_unavailable"
    assert statuses["okura_prestige_taipei"] == "blocked_source_unavailable"
    assert statuses["the_landis_taipei"] == "blocked_source_unavailable"
    assert statuses["mo_taipei"] == "blocked_source_unavailable"
    assert statuses["miramar_garden_taipei"] == "blocked_source_unavailable"
    assert statuses["le_meridien_taipei"] == "blocked_source_unavailable"
    assert statuses["royal_nikko_taipei"] == "blocked_source_unavailable"
    assert statuses["eslite_hotel"] == "blocked_source_unavailable"
    assert statuses["hotel_metropolitan_premier_taipei"] == "blocked_source_unavailable"
    assert statuses["mitsui_garden_taipei_zhongxiao"] == "blocked_source_unavailable"
    assert statuses["shangrila_tainan"] == "blocked_source_unavailable"
    assert statuses["hotel_royal_hsinchu"] == "blocked_source_unavailable"
    assert statuses["sheraton_grand_taipei"] == "blocked_source_unavailable"
    assert statuses["w_taipei"] == "blocked_source_unavailable"
    assert statuses["courtyard_taipei_downtown"] == "blocked_source_unavailable"
    assert statuses["grand_mayfull_taipei"] == "blocked_source_unavailable"
    assert statuses["intercontinental_taipei"] == "blocked_source_unavailable"
    assert statuses["regent_taipei"] == "blocked_source_unavailable"
    assert statuses["kimpton_da_an"] == "blocked_source_unavailable"
    assert statuses["shangrila_taipei"] == "blocked_source_unavailable"


def _write_test_parquet(path):
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE rows AS SELECT * FROM (VALUES
          ('a', 'hotel-a', 'official', '2026-10-18T01:00:00Z', '2026-11-02', '2026-11-03', 1, 2, 0, false, '45.0', 'included', 'Non-refundable', 10000.0, NULL, NULL, NULL, NULL, NULL),
          ('b', 'hotel-a', 'booking_com', '2026-10-18T01:01:00Z', '2026-11-02', '2026-11-03', 1, 2, 0, false, NULL, 'unknown', 'Cancellation policy is available on the official booking page', NULL, NULL, NULL, NULL, NULL, NULL),
          ('c', 'hotel-a', 'official', '2026-10-18T01:02:00Z', '2026-11-02', '2026-11-03', 1, 2, 0, true, '"45"', 'unknown', '13~4天之前 訂金的30％ 3~1天之前 訂金的70％ 當天 訂金的100％', NULL, NULL, NULL, NULL, NULL, NULL),
          ('d', 'hotel-b', 'official', '2026-10-18T01:03:00Z', '2026-11-02', '2026-11-03', 1, 2, 0, false, '45.0', 'unknown', '�N���������O��', NULL, NULL, NULL, NULL, NULL, NULL)
        ) AS t(observation_id, hotel_id, source_platform, queried_at,
               check_in, check_out, rooms, adults, children, breakfast_included,
               room_size_sqm, tax_inclusion, cancellation_policy, nightly_adr_twd,
               total_price, price_before_tax, service_charge, tax, run_id)
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
    reviews = tmp_path / "empty-reviews.json"
    reviews.write_text(
        json.dumps({"schema_version": "1.0", "reviews": []}), encoding="utf-8"
    )

    payload = build_warehouse_analysis(
        rates / "*.parquet", manifest, target, reviews
    )

    assert payload["schema_version"] == "1.10"
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
    assert payload["quality"]["latest_rows"] == 4
    assert payload["quality"]["latest_strict_metadata_ready_rows"] == 1
    assert payload["quality"]["latest_strict_metadata_ready_ratio"] == 0.25
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
    assert payload["actionable_strict_metadata_gap_hotels"] == payload[
        "strict_metadata_gap_hotels"
    ]
    assert payload["latest_strict_metadata_gap_hotels"] == [
        {**item, "latest_queried_at": {
            ("hotel-a", "booking_com"): "2026-10-18T01:01:00Z",
            ("hotel-a", "official"): "2026-10-18T01:02:00Z",
            ("hotel-b", "official"): "2026-10-18T01:03:00Z",
        }[(item["hotel_id"], item["source_platform"])]}
        for item in payload["strict_metadata_gap_hotels"]
    ]
    assert payload["actionable_latest_strict_metadata_gap_hotels"] == payload[
        "latest_strict_metadata_gap_hotels"
    ]
    assert payload["strict_metadata_matched_review_entries"] == 0
    assert payload["strict_metadata_stale_review_entries"] == []
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
    assert public["schema_version"] == "1.6"
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
    assert public["actionable_strict_metadata_gaps"] == payload[
        "actionable_strict_metadata_gap_hotels"
    ]
    assert public["actionable_latest_strict_metadata_gaps"] == payload[
        "actionable_latest_strict_metadata_gap_hotels"
    ]


def test_metadata_review_registry_excludes_exact_blocker_and_detects_stale(tmp_path):
    warehouse = tmp_path / "warehouse"
    rates = warehouse / "rates"
    rates.mkdir(parents=True)
    _write_test_parquet(rates / "2026-10.parquet")
    manifest = warehouse / "manifest.json"
    _write_manifest(manifest, 4)
    reviews = tmp_path / "reviews.json"
    review = {
        "hotel_id": "hotel-a",
        "source_platform": "booking_com",
        "missing_fields": [
            "cancellation_class",
            "cancellation_deadline",
            "room_size",
            "tax_inclusion",
        ],
        "status": "blocked_no_explicit_label",
        "reviewed_at": "2026-10-24",
        "evidence_urls": ["https://example.com/rate"],
        "note": "The source exposes no explicit product-level metadata.",
    }
    reviews.write_text(
        json.dumps({"schema_version": "1.0", "reviews": [review]}),
        encoding="utf-8",
    )

    payload = build_warehouse_analysis(
        rates / "*.parquet", manifest, warehouse / "analysis.json", reviews
    )
    assert payload["strict_metadata_review_registry_entries"] == 1
    assert payload["strict_metadata_matched_review_entries"] == 1
    assert payload["strict_metadata_stale_review_entries"] == []
    assert payload["reviewed_strict_metadata_gaps"][0]["hotel_id"] == "hotel-a"
    assert all(
        item["source_platform"] != "booking_com"
        for item in payload["actionable_strict_metadata_gap_hotels"]
    )
    assert all(
        item["source_platform"] != "booking_com"
        for item in payload["actionable_latest_strict_metadata_gap_hotels"]
    )

    review["missing_fields"] = ["tax_inclusion"]
    reviews.write_text(
        json.dumps({"schema_version": "1.0", "reviews": [review]}),
        encoding="utf-8",
    )
    stale = build_warehouse_analysis(
        rates / "*.parquet", manifest, warehouse / "stale.json", reviews
    )
    assert stale["strict_metadata_matched_review_entries"] == 0
    assert stale["strict_metadata_stale_review_entries"] == [review]


def test_metadata_review_registry_matches_a_latest_only_signature(tmp_path):
    warehouse = tmp_path / "warehouse"
    rates = warehouse / "rates"
    rates.mkdir(parents=True)
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE rows AS SELECT * FROM (VALUES
          ('old', 'hotel-a', 'official', '2026-10-18T01:00:00Z', '2026-11-02', '2026-11-03', 1, 2, 0, NULL, '45.0', 'unknown', 'Free cancellation', 10000.0, NULL, NULL, NULL, NULL, 'older'),
          ('new', 'hotel-a', 'official', '2026-10-18T02:00:00Z', '2026-11-02', '2026-11-03', 1, 2, 0, true, '45.0', 'unknown', 'Free cancellation', 10000.0, NULL, NULL, NULL, NULL, 'newer')
        ) AS t(observation_id, hotel_id, source_platform, queried_at,
               check_in, check_out, rooms, adults, children, breakfast_included,
               room_size_sqm, tax_inclusion, cancellation_policy, nightly_adr_twd,
               total_price, price_before_tax, service_charge, tax, run_id)
        """
    )
    connection.execute(
        "COPY rows TO ? (FORMAT PARQUET)",
        [str(rates / "2026-10.parquet")],
    )
    connection.close()
    manifest = warehouse / "manifest.json"
    _write_manifest(manifest, 2)
    reviews = tmp_path / "reviews.json"
    review = {
        "hotel_id": "hotel-a",
        "source_platform": "official",
        "missing_fields": ["tax_inclusion"],
        "status": "blocked_no_explicit_label",
        "reviewed_at": "2026-10-24",
        "evidence_urls": ["https://example.com/rate"],
        "note": "The latest source exposes no explicit tax label.",
    }
    reviews.write_text(
        json.dumps({"schema_version": "1.0", "reviews": [review]}),
        encoding="utf-8",
    )

    payload = build_warehouse_analysis(
        rates / "*.parquet", manifest, warehouse / "analysis.json", reviews
    )

    assert payload["strict_metadata_matched_review_entries"] == 1
    assert payload["strict_metadata_stale_review_entries"] == []
    assert payload["actionable_latest_strict_metadata_gap_hotels"] == []
    assert payload["actionable_strict_metadata_gap_hotels"][0]["missing_fields"] == {
        "breakfast_included": 1,
        "tax_inclusion": 2,
    }
    assert payload["reviewed_strict_metadata_gaps"][0]["missing_fields"] == {
        "tax_inclusion": 1,
    }


def test_build_warehouse_analysis_rejects_manifest_row_mismatch(tmp_path):
    warehouse = tmp_path / "warehouse"
    rates = warehouse / "rates"
    rates.mkdir(parents=True)
    _write_test_parquet(rates / "2026-10.parquet")
    manifest = warehouse / "manifest.json"
    _write_manifest(manifest, 5)

    with pytest.raises(ValueError, match="row mismatch"):
        build_warehouse_analysis(rates / "*.parquet", manifest, warehouse / "analysis.json")
