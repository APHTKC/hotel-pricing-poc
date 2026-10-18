import json

import duckdb
import pytest

from scripts.build_warehouse_analysis import build_warehouse_analysis


def _write_test_parquet(path):
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE rows AS SELECT * FROM (VALUES
          ('a', 'hotel-a', 'official', '2026-10-18T01:00:00Z', '2026-11-02', 45.0, 'included', 'Non-refundable', 10000.0),
          ('b', 'hotel-a', 'booking_com', '2026-10-18T01:01:00Z', '2026-11-02', NULL, 'unknown', NULL, NULL)
        ) AS t(observation_id, hotel_id, source_platform, queried_at,
               check_in, room_size_sqm, tax_inclusion, cancellation_policy, nightly_adr_twd)
        """
    )
    connection.execute("COPY rows TO ? (FORMAT PARQUET)", [str(path)])
    connection.close()


def _write_manifest(path, rows):
    path.write_text(
        json.dumps(
            {
                "rows": rows,
                "natural_keys": 2,
                "partitions": [{"month": "2026-10", "sha256": "abc"}],
            }
        ),
        encoding="utf-8",
    )


def test_build_warehouse_analysis_profiles_parquet_deterministically(tmp_path):
    warehouse = tmp_path / "warehouse"
    rates = warehouse / "rates"
    rates.mkdir(parents=True)
    _write_test_parquet(rates / "2026-10.parquet")
    manifest = warehouse / "manifest.json"
    _write_manifest(manifest, 2)
    target = warehouse / "analysis.json"

    payload = build_warehouse_analysis(rates / "*.parquet", manifest, target)

    assert payload["schema_version"] == "1.1"
    assert payload["rows"] == 2
    assert payload["hotels"] == 1
    assert payload["quality"]["known_room_size_ratio"] == 0.5
    assert payload["quality"]["known_tax_ratio"] == 0.5
    assert payload["quality"]["known_cancellation_policy_ratio"] == 0.5
    assert payload["quality"]["known_cancellation_class_ratio"] == 0.5
    assert payload["quality"]["known_cancellation_deadline_ratio"] == 0.5
    assert payload["quality"]["nightly_adr_ratio"] == 0.5
    assert [item["source_platform"] for item in payload["sources"]] == [
        "booking_com",
        "official",
    ]
    assert payload["hotels_by_unknown_room_size"][0]["unknown_room_size_rows"] == 1
    official = next(
        item for item in payload["sources"] if item["source_platform"] == "official"
    )
    assert official["known_cancellation_class_rows"] == 1
    assert official["known_cancellation_deadline_rows"] == 1
    assert official["known_cancellation_policy_rows"] == 1
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_build_warehouse_analysis_rejects_manifest_row_mismatch(tmp_path):
    warehouse = tmp_path / "warehouse"
    rates = warehouse / "rates"
    rates.mkdir(parents=True)
    _write_test_parquet(rates / "2026-10.parquet")
    manifest = warehouse / "manifest.json"
    _write_manifest(manifest, 3)

    with pytest.raises(ValueError, match="row mismatch"):
        build_warehouse_analysis(rates / "*.parquet", manifest, warehouse / "analysis.json")
