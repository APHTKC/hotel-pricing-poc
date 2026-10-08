from datetime import date
from decimal import Decimal

from scrapers.adapters.siteminder import (
    booking_url,
    parse_cancellation,
    parse_room_size,
    room_size,
)


def test_eslite_booking_url_contains_exact_stay_and_guests():
    url = booking_url("eslite_hotel", date(2026, 10, 17), date(2026, 10, 18), 2)

    assert "properties/EsliteHotel" in url
    assert "checkInDate=2026-10-17" in url
    assert "checkOutDate=2026-10-18" in url
    assert "items%5B0%5D%5Badults%5D=2" in url


def test_silks_place_yilan_uses_its_official_siteminder_property():
    url = booking_url(
        "silks_place_yilan", date(2026, 10, 21), date(2026, 10, 22), 2
    )

    assert "properties/silksplaceyilanhoteldirect" in url
    assert "checkInDate=2026-10-21" in url


def test_gaia_taipei_uses_its_official_siteminder_property():
    url = booking_url(
        "the_gaia_taipei", date(2026, 11, 7), date(2026, 11, 8), 2
    )

    assert "properties/thegaiahoteltaipeidirect" in url
    assert "checkInDate=2026-11-07" in url


def test_siteminder_room_size_and_cancellation_parsing():
    assert parse_room_size("面積：69平方米(21坪)") == Decimal("69")
    assert parse_cancellation("含早餐\n10月14日 之前可免費取消\n即刻預訂") == "10月14日 之前可免費取消"


def test_gaia_room_size_falls_back_to_verified_official_profile():
    assert room_size("the_gaia_taipei", "奇岩和室房 Qiyan Japanese Style Room", "") == Decimal("33")
    assert room_size("the_gaia_taipei", "丹鳳套房 Danfeng Suite", "") == Decimal("50")
    assert room_size("the_gaia_taipei", "大地套房 The Gaia Suite", "") == Decimal("66")
    assert room_size("the_gaia_taipei", "Unknown room", "") is None
