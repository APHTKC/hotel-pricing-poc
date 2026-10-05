import json

import scripts.build_static_data as build_static_data
from scripts.build_static_data import (
    DASHBOARD_FIELDS,
    _dashboard_row,
    _daily_market_digest,
    _data_quality_warnings,
    _history_summary,
    _heatmap_row,
    _latest_batch,
    _month_key,
    _partition_id,
    _plausible_luxury_rate,
    _public_adapter_health,
    _weekly_digest,
)


def test_latest_batch_uses_recent_workflow_window():
    rows = [
        {"queried_at": "2026-09-07T03:31:00+00:00", "hotel_name": "old"},
        {"queried_at": "2026-09-07T22:09:00+00:00", "hotel_name": "Capella"},
        {"queried_at": "2026-09-07T22:11:00+00:00", "hotel_name": "Okura"},
    ]

    latest = _latest_batch(rows)

    assert [row["hotel_name"] for row in latest] == ["Capella", "Okura"]


def test_implausibly_low_twd_rate_is_not_published():
    assert _plausible_luxury_rate({"total_twd": "350"}) is False
    assert _plausible_luxury_rate({"total_twd": "12300"}) is True


def test_dashboard_row_drops_large_internal_fields():
    source = {
        "hotel_id": "okura-taipei",
        "hotel_name": "The Okura Prestige Taipei",
        "city": "Taipei",
        "district": "Zhongshan",
        "queried_at": "2026-09-07T22:11:00+00:00",
        "raw_payload": "not for the browser",
        "cancellation_policy": "kept in the JSONL source",
    }

    published = _dashboard_row(source)

    assert set(published) == set(DASHBOARD_FIELDS)
    assert published["city"] == "Taipei"
    assert published["district"] == "Zhongshan"
    assert "raw_payload" not in published
    assert published["cancellation_policy"] == "kept in the JSONL source"
    assert published["comparison_status"] == "insufficient_product_metadata"


def test_dashboard_row_preserves_and_backfills_rate_source_metadata():
    ota = _dashboard_row(
        {
            "source_platform": "booking_com",
            "source_method": "partner_api",
            "source_property_id": "property-123",
        }
    )
    legacy_official = _dashboard_row({})

    assert ota["source_platform"] == "booking_com"
    assert ota["source_method"] == "partner_api"
    assert ota["source_property_id"] == "property-123"
    assert legacy_official["source_platform"] == "official"
    assert legacy_official["source_method"] == "public_booking_page"
    assert legacy_official["source_property_id"] is None


def test_static_build_deduplicates_and_embeds_shared_market_summary(
    monkeypatch, tmp_path
):
    source = tmp_path / "rates.jsonl"
    rates_dir = tmp_path / "rates"
    summary = tmp_path / "history_summary.json"
    rates_index = rates_dir / "index.json"
    latest_summary = tmp_path / "latest_summary.json"
    latest_heatmap = tmp_path / "latest_heatmap.json"
    latest_details = tmp_path / "latest_details.json"
    legacy_latest = tmp_path / "latest.json"
    legacy_latest.write_text("legacy", encoding="utf-8")
    health_source = tmp_path / "adapter_health.json"
    health_target = tmp_path / "public_health.json"
    digest_target = tmp_path / "digest.json"
    legacy = tmp_path / "rates.json"
    legacy.write_text("legacy", encoding="utf-8")
    common = {
        "check_in": "2026-10-01",
        "room_type_code": "ROOM",
        "room_type_name": "Room",
        "rate_plan_code": "BAR",
        "rate_plan_name": "Best Available Rate",
        "price_per_sqm": "200",
        "currency": "TWD",
        "source_url": "https://example.com",
    }
    rows = [
        {
            **common,
            "observation_id": "old",
            "hotel_id": "hotel-a",
            "hotel_name": "Hotel A",
            "queried_at": "2026-09-24T01:00:00+00:00",
            "total_price": "9000",
            "total_twd": "9000",
        },
        {
            **common,
            "observation_id": "new",
            "hotel_id": "hotel-a",
            "hotel_name": "Hotel A",
            "queried_at": "2026-09-24T20:00:00+00:00",
            "total_price": "10000",
            "total_twd": "10000",
        },
        {
            **common,
            "observation_id": "other",
            "hotel_id": "hotel-b",
            "hotel_name": "Hotel B",
            "queried_at": "2026-09-24T20:01:00+00:00",
            "total_price": "20000",
            "total_twd": "20000",
        },
    ]
    source.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(build_static_data, "SOURCE", source)
    monkeypatch.setattr(build_static_data, "RATES_DIR", rates_dir)
    monkeypatch.setattr(build_static_data, "HISTORY_SUMMARY_TARGET", summary)
    monkeypatch.setattr(build_static_data, "RATES_INDEX_TARGET", rates_index)
    monkeypatch.setattr(build_static_data, "LATEST_SUMMARY_TARGET", latest_summary)
    monkeypatch.setattr(build_static_data, "LATEST_HEATMAP_TARGET", latest_heatmap)
    monkeypatch.setattr(build_static_data, "LATEST_DETAILS_TARGET", latest_details)
    monkeypatch.setattr(build_static_data, "LEGACY_LATEST_TARGET", legacy_latest)
    monkeypatch.setattr(build_static_data, "HEALTH_SOURCE", health_source)
    monkeypatch.setattr(build_static_data, "HEALTH_TARGET", health_target)
    monkeypatch.setattr(build_static_data, "DIGEST_TARGET", digest_target)
    monkeypatch.setattr(build_static_data, "LEGACY_TARGET", legacy)

    build_static_data.main()

    hotel_a = json.loads((rates_dir / "2026-09" / "hotel-a.json").read_text(encoding="utf-8"))
    hotel_b = json.loads((rates_dir / "2026-09" / "hotel-b.json").read_text(encoding="utf-8"))
    assert len(hotel_a["rates"]) == 1
    assert len(hotel_b["rates"]) == 1
    assert {hotel_a["rates"][0]["total_twd"], hotel_b["rates"][0]["total_twd"]} == {"10000", "20000"}
    assert hotel_a["market_summary"]["median_adr_twd"] == 10000
    index_payload = json.loads(rates_index.read_text(encoding="utf-8"))
    assert index_payload["months"][0]["month"] == "2026-09"
    assert {item["path"] for item in index_payload["months"][0]["hotels"]} == {
        "rates/2026-09/hotel-a.json", "rates/2026-09/hotel-b.json"
    }
    details_payload = json.loads(latest_details.read_text(encoding="utf-8"))
    summary_latest_payload = json.loads(latest_summary.read_text(encoding="utf-8"))
    heatmap_payload = json.loads(latest_heatmap.read_text(encoding="utf-8"))
    assert details_payload["market_summary"]["median_adr_twd"] == 15000
    assert summary_latest_payload["market_summary"] == details_payload["market_summary"]
    assert summary_latest_payload["record_count"] == 2
    assert len(heatmap_payload["rates"]) == 2
    assert "cancellation_policy" not in heatmap_payload["rates"][0]
    summary_payload = json.loads(summary.read_text(encoding="utf-8"))
    assert summary_payload["available_months"] == ["2026-09"]
    assert not legacy.exists()
    assert not legacy_latest.exists()
    assert len(summary_payload["daily"]) == 2
    assert {row["hotel_id"] for row in summary_payload["hotels"]} == {
        "hotel-a", "hotel-b"
    }
    assert digest_target.exists()


def test_static_partition_ids_fail_closed_and_heatmap_rows_are_lightweight():
    assert _partition_id("hotel-safe_123") == "hotel-safe_123"
    try:
        _partition_id("../unsafe")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe hotel ids must not become output paths")

    row = _heatmap_row({"hotel_id": "hotel-a", "total_twd": 10000, "source_url": "secret"})
    assert row["hotel_id"] == "hotel-a"
    assert row["total_twd"] == 10000
    assert "source_url" not in row


def test_month_key_uses_observation_month_and_rejects_missing_timestamp():
    assert _month_key({"queried_at": "2026-09-30T23:59:00+00:00"}) == "2026-09"
    assert _month_key({}) is None


def test_history_summary_preaggregates_daily_and_lead_metrics():
    rows = [
        {
            "hotel_id": "hotel-a", "hotel_name": "Hotel A", "city": "Taipei",
            "district": "Xinyi", "queried_at": "2026-09-24T01:00:00+00:00",
            "lead_days": 7, "room_size_sqm": 50, "total_twd": 10000,
            "price_per_sqm": 200,
        },
        {
            "hotel_id": "hotel-a", "hotel_name": "Hotel A", "city": "Taipei",
            "district": "Xinyi", "queried_at": "2026-09-24T20:00:00+00:00",
            "lead_days": 7, "room_size_sqm": 70, "total_twd": 14000,
            "price_per_sqm": 200,
        },
    ]

    payload = _history_summary(rows)

    assert payload["daily"][0]["average_twd"] == 12000
    assert payload["daily"][0]["median_twd"] == 12000
    assert payload["daily"][0]["core_median_twd"] == 10000
    assert payload["lead_curve"][0]["median_twd"] == 12000


def test_weekly_digest_uses_equal_weight_hotel_medians_and_previous_week():
    rows = []
    for day, hotel_id, values in [
        ("2026-09-10", "hotel-a", [8000, 12000]),
        ("2026-09-10", "hotel-b", [20000]),
        ("2026-09-17", "hotel-a", [10000, 14000]),
        ("2026-09-17", "hotel-b", [24000]),
    ]:
        for index, value in enumerate(values):
            rows.append({
                "hotel_id": hotel_id,
                "hotel_name": hotel_id.title(),
                "queried_at": f"{day}T0{index}:00:00+00:00",
                "lead_days": 7 if index == 0 else 30,
                "total_twd": value,
            })

    digest = _weekly_digest(rows)

    assert digest["available"] is True
    assert digest["current_period"]["market_median_twd"] == 18000
    assert digest["previous_period"]["market_median_twd"] == 15000
    assert digest["change_pct"] == 0.2
    assert digest["comparable_hotels"] == 2
    assert {item["lead_days"] for item in digest["lead_time_curve"]} == {7, 30}


def test_weekly_digest_fails_closed_without_history():
    assert _weekly_digest([]) == {
        "available": False,
        "reason": "no_history",
        "currency": "TWD",
    }


def test_public_adapter_health_excludes_diagnostics_and_daily_details():
    payload = _public_adapter_health({"adapters": {"stub:hotel-a": {
        "adapter": "stub", "hotel_id": "hotel-a", "attempts": 3,
        "successes": 2, "failures": 1, "blocked_count": 0,
        "success_rate": 0.6667, "average_response_ms": 1200,
        "last_status": "failed", "last_attempt_at": "2026-09-24T01:00:00+00:00",
        "last_success_at": "2026-09-23T01:00:00+00:00", "cooldown_until": None,
        "daily": {"2026-09-24": {"attempts": 3}}, "reason": "private detail",
    }}})

    assert payload["generated_at"] == "2026-09-24T01:00:00+00:00"
    assert payload["adapters"][0]["success_rate"] == 0.6667
    assert "daily" not in payload["adapters"][0]
    assert "reason" not in payload["adapters"][0]


def test_daily_market_digest_uses_core_rooms_movers_and_strict_parity():
    rows = []
    for day, hotel_id, value in [
        ("2026-09-23", "hotel-a", 10000),
        ("2026-09-23", "hotel-b", 20000),
        ("2026-09-30", "hotel-a", 12000),
        ("2026-09-30", "hotel-b", 18000),
    ]:
        rows.append({
            "hotel_id": hotel_id, "hotel_name": hotel_id.title(),
            "queried_at": f"{day}T01:00:00+00:00", "check_in": "2026-10-07",
            "check_out": "2026-10-08", "room_size_sqm": 50,
            "total_twd": value, "rooms": 1, "adults": 2, "children": 0,
            "breakfast_included": True, "cancellation_policy": "Free cancellation",
            "tax_inclusion": "included", "source_platform": "official",
        })
    rows.append({
        **rows[-2], "source_platform": "booking_com", "total_twd": 12300,
    })

    digest = _daily_market_digest(rows)

    assert digest["available"] is True
    assert digest["metrics"]["core_adr_change_pct"] == 0.005
    assert digest["metrics"]["largest_increase"]["hotel_id"] == "hotel-a"
    assert digest["metrics"]["largest_decrease"]["hotel_id"] == "hotel-b"
    assert digest["metrics"]["rate_parity_normal_rate"] == 1
    assert 3 <= len(digest["insights"]) <= 4


def test_data_quality_flags_low_volume_and_large_price_change():
    rows = []
    for index in range(1, 8):
        day = f"2026-09-{30-index:02d}"
        rows.extend({
            "hotel_id": "hotel-a", "hotel_name": "Hotel A",
            "queried_at": f"{day}T01:00:00+00:00", "total_twd": 10000,
        } for _ in range(10))
    rows.extend({
        "hotel_id": "hotel-a", "hotel_name": "Hotel A",
        "queried_at": "2026-09-30T01:00:00+00:00", "total_twd": 20000,
    } for _ in range(4))

    quality = _data_quality_warnings(rows)

    assert quality["as_of"] == "2026-09-30"
    codes = {item["code"] for item in quality["hotels"][0]["warnings"]}
    assert codes == {"low_volume", "price_spike"}
