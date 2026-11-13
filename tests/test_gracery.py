import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from scrapers.adapters.gracery import (
    booking_url,
    breakfast_status,
    code_from_url,
    parse_size,
)


def test_booking_url_has_explicit_stay_and_occupancy():
    url = booking_url(date(2026, 11, 7), date(2026, 11, 8), adults=2)
    assert "checkin_date=20261107" in url
    assert "checkout_date=20261108" in url
    assert "adults=2" in url
    assert "dateUndecidedFlg=0" in url


def test_reservation_codes_are_read_from_public_detail_url():
    url = (
        "https://go-fujita-kanko.reservation.jp/ja/hotels/fkg046/"
        "plans/10083590?room_id=10026956&checkin_date=20261107"
    )
    assert code_from_url(url) == "10083590"
    assert code_from_url(url, "room_id") == "10026956"


def test_parse_room_size_handles_reservation_jp_markup_text():
    assert parse_size("禁煙\n25.00m\n2\n1~2名") == Decimal("25.00")
    assert parse_size("25.00m²") == Decimal("25.00")
    assert parse_size("size not shown") is None


def test_breakfast_classification_is_conservative():
    assert breakfast_status("朝食付きプラン", "") is True
    assert breakfast_status("一般料金 Room Rate", "朝食は含まれていません") is False
    assert breakfast_status("Flexible rate", "現地払い") is None


def test_official_html_probe_requires_canonical_product_validation():
    diagnostic = json.loads(
        Path(
            "artifacts/hotel-gracery-taipei-official-html-probe-diagnostic.json"
        ).read_text(encoding="utf-8")
    )

    assert diagnostic["hotel_id"] == "hotel_gracery_taipei"
    assert diagnostic["probe_limit"] == {
        "candidate_attempts_this_batch": 1,
        "retried": False,
    }
    assert diagnostic["outcome"]["http_status"] == 200
    assert diagnostic["outcome"]["room_group_marker_count"] == 4
    assert diagnostic["outcome"]["plan_card_marker_count"] == 29
    assert diagnostic["outcome"]["cloudflare_marker_count"] == 0
    assert diagnostic["outcome"]["captcha_marker_count"] == 0
    assert diagnostic["unvalidated_canonical_fields"] == [
        "stable_room_type_id_per_product",
        "breakfast_included_per_product",
        "cancellation_class_per_product",
        "cancellation_deadline_per_product",
        "tax_inclusion_per_product",
        "total_price_per_product",
        "queried_at_price_per_product",
    ]
    assert "Keep the official adapter disabled" in diagnostic["decision"]
