from datetime import date
from decimal import Decimal

from scrapers.adapters.siteminder import booking_url, parse_cancellation, parse_room_size


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


def test_siteminder_room_size_and_cancellation_parsing():
    assert parse_room_size("面積：69平方米(21坪)") == Decimal("69")
    assert parse_cancellation("含早餐\n10月14日 之前可免費取消\n即刻預訂") == "10月14日 之前可免費取消"
