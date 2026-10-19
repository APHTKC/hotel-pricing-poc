import json

import duckdb

from scripts.build_rate_warehouse import build_rate_warehouse


def test_build_rate_warehouse_preserves_rows_and_natural_keys(tmp_path):
    source = tmp_path / "rates"
    month = source / "2026-10"
    month.mkdir(parents=True)
    rows = [
        {
            "observation_id": "a",
            "hotel_id": "hotel-a",
            "source_platform": "official",
            "check_in": "2026-11-01",
            "check_out": "2026-11-02",
            "rooms": 1,
            "adults": 2,
            "children": 0,
            "room_type_code": "ROOM",
            "room_type_name": "Room",
            "rate_plan_code": "BAR",
            "rate_plan_name": "Best Available Rate",
            "currency": "TWD",
            "total_price": 10000,
            "queried_at": "2026-10-17T01:00:00+00:00",
        },
        {
            "observation_id": "b",
            "hotel_id": "hotel-b",
            "source_platform": "booking_com",
            "check_in": "2026-11-01",
            "check_out": "2026-11-02",
            "rooms": 1,
            "adults": 2,
            "children": 0,
            "room_type_code": "ROOM",
            "room_type_name": "Room",
            "rate_plan_code": "BAR",
            "rate_plan_name": "Best Available Rate",
            "currency": "TWD",
            "total_price": 11000,
            "queried_at": "2026-10-17T01:01:00+00:00",
        },
    ]
    (month / "2026-10-17.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    target = tmp_path / "warehouse" / "rates"
    manifest_target = tmp_path / "warehouse" / "manifest.json"

    manifest = build_rate_warehouse(source, target, manifest_target)

    assert manifest["rows"] == 2
    assert manifest["natural_keys"] == 2
    assert manifest["sources"] == [str(source).replace("\\", "/")]
    assert manifest["partitions"][0]["month"] == "2026-10"
    assert manifest["partitions"][0]["source_shards"] == 1
    assert manifest_target.exists()
    assert duckdb.connect().execute(
        "SELECT observation_id, total_price, nights, nightly_adr_twd "
        "FROM read_parquet(?) ORDER BY observation_id",
        [str(target / "2026-10.parquet")],
    ).fetchall() == [("a", 10000, 1, 10000.0), ("b", 11000, 1, 11000.0)]


def test_build_rate_warehouse_normalizes_multi_night_adr_without_mutating_source(tmp_path):
    source = tmp_path / "rates"
    month = source / "2026-10"
    month.mkdir(parents=True)
    row = {
        "observation_id": "multi",
        "hotel_id": "hotel-a",
        "source_platform": "official",
        "check_in": "2026-11-01",
        "check_out": "2026-11-03",
        "rooms": 1,
        "adults": 2,
        "children": 0,
        "room_type_code": "ROOM",
        "rate_plan_code": "BAR",
        "currency": "TWD",
        "total_price": 18000,
        "queried_at": "2026-10-17T01:00:00+00:00",
    }
    shard = month / "2026-10-17.jsonl"
    original = json.dumps(row) + "\n"
    shard.write_text(original, encoding="utf-8")

    target = tmp_path / "warehouse" / "rates"
    build_rate_warehouse(source, target, tmp_path / "warehouse" / "manifest.json")

    assert duckdb.connect().execute(
        "SELECT nights, nightly_adr_twd FROM read_parquet(?)",
        [str(target / "2026-10.parquet")],
    ).fetchone() == (2, 9000.0)
    assert shard.read_text(encoding="utf-8") == original


def test_build_rate_warehouse_verifies_tax_inclusion_only_when_components_reconcile(tmp_path):
    source = tmp_path / "rates"
    month = source / "2026-10"
    month.mkdir(parents=True)
    base = {
        "hotel_id": "hotel-a",
        "source_platform": "official",
        "check_in": "2026-11-01",
        "check_out": "2026-11-02",
        "rooms": 1,
        "adults": 2,
        "children": 0,
        "room_type_code": "ROOM",
        "rate_plan_code": "BAR",
        "currency": "TWD",
        "queried_at": "2026-10-17T01:00:00+00:00",
        "price_before_tax": 10000,
        "service_charge": 1000,
        "tax": 500,
    }
    rows = [
        {**base, "observation_id": "matches", "total_price": 11500},
        {**base, "observation_id": "mismatch", "total_price": 12000},
        {
            **base,
            "observation_id": "foreign-currency-match",
            "rate_plan_code": "BAR-USD",
            "currency": "USD",
            "price_before_tax": 100,
            "service_charge": 10,
            "tax": 5,
            "total_price": 115,
            "total_twd": 3680,
        },
        {
            **base,
            "observation_id": "capella-visible-total",
            "hotel_id": "capella_taipei",
            "source_method": "public_booking_page",
            "room_type_code": "RS1",
            "rate_plan_code": "BAR-CAPELLA",
            "price_before_tax": None,
            "service_charge": None,
            "tax": None,
            "tax_inclusion": "unknown",
            "total_price": 25200,
        },
        {
            **base,
            "observation_id": "capella-legacy-visible-total",
            "hotel_id": "capella_taipei",
            "source_url": "https://be.synxis.com/?Hotel=47696&Chain=21430",
            "room_type_code": "RS2",
            "rate_plan_code": "BAR-CAPELLA-LEGACY",
            "price_before_tax": None,
            "service_charge": None,
            "tax": None,
            "tax_inclusion": "unknown",
            "total_price": 25200,
        },
        {
            **base,
            "observation_id": "grand-hotel-visible-total",
            "hotel_id": "grand_hotel_taipei",
            "source_url": "https://tlathena.ec-hotel.net/webhotel-v5/1071",
            "room_type_code": "DELUXE",
            "rate_plan_code": "GRAND-HOLIDAY",
            "price_before_tax": None,
            "service_charge": None,
            "tax": None,
            "tax_inclusion": "unknown",
            "total_price": 5360,
        },
    ]
    shard = month / "2026-10-17.jsonl"
    original = "".join(json.dumps(row) + "\n" for row in rows)
    shard.write_text(original, encoding="utf-8")

    target = tmp_path / "warehouse" / "rates"
    build_rate_warehouse(source, target, tmp_path / "warehouse" / "manifest.json")

    assert duckdb.connect().execute(
        "SELECT observation_id, tax_inclusion FROM read_parquet(?) ORDER BY observation_id",
        [str(target / "2026-10.parquet")],
    ).fetchall() == [
        ("capella-legacy-visible-total", "included"),
        ("capella-visible-total", "included"),
        ("foreign-currency-match", "included"),
        ("grand-hotel-visible-total", "included"),
        ("matches", "included"),
        ("mismatch", "unknown"),
    ]
    assert shard.read_text(encoding="utf-8") == original
