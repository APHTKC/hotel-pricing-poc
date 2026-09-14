from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from scrapers.adapters.grand_mayfull import booking_url, parse_room_size


def test_parse_room_size():
    assert parse_room_size("面積 : 15坪(50m²)") == Decimal("50")
    assert parse_room_size("105 m² 皇家套房") == Decimal("105")
    assert parse_room_size("unknown") is None


def test_booking_url():
    query = parse_qs(
        urlparse(booking_url(date(2026, 10, 10), date(2026, 10, 11))).query
    )
    assert query["checkInDate"] == ["2026-10-10"]
    assert query["checkOutDate"] == ["2026-10-11"]
    assert query["currency"] == ["TWD"]
