import json

import scripts.build_static_data as build_static_data
from scripts.build_static_data import (
    DASHBOARD_FIELDS,
    _dashboard_row,
    _history_summary,
    _latest_batch,
    _month_key,
    _plausible_luxury_rate,
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
    assert "cancellation_policy" not in published


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
    latest = tmp_path / "latest.json"
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
    monkeypatch.setattr(build_static_data, "LATEST_TARGET", latest)
    monkeypatch.setattr(build_static_data, "LEGACY_TARGET", legacy)

    build_static_data.main()

    payload = json.loads((rates_dir / "2026-09.json").read_text(encoding="utf-8"))
    assert len(payload["rates"]) == 2
    assert {row["total_twd"] for row in payload["rates"]} == {"10000", "20000"}
    assert payload["market_summary"]["median_adr_twd"] == 15000
    latest_payload = json.loads(latest.read_text(encoding="utf-8"))
    assert latest_payload["market_summary"] == payload["market_summary"]
    summary_payload = json.loads(summary.read_text(encoding="utf-8"))
    assert summary_payload["available_months"] == ["2026-09"]
    assert not legacy.exists()
    assert len(summary_payload["daily"]) == 2
    assert {row["hotel_id"] for row in summary_payload["hotels"]} == {
        "hotel-a", "hotel-b"
    }


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
