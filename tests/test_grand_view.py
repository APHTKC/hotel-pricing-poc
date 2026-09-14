from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from scrapers.adapters.grand_view import ROOM_SIZES, booking_url, parse_included_tax


def test_booking_url_uses_dated_twd_results():
    query = parse_qs(
        urlparse(booking_url(date(2026, 10, 14), date(2026, 10, 15))).query
    )
    assert query["property"] == ["twtai28740"]
    assert query["arrival"] == ["2026-10-14"]
    assert query["departure"] == ["2026-10-15"]
    assert query["currency"] == ["TWD"]


def test_parse_included_tax():
    assert parse_included_tax("已包含稅費: NT$ 1,145") == Decimal("1145")
    assert parse_included_tax("沒有稅額明細") is None


def test_official_room_sizes_are_mapped():
    assert ROOM_SIZES["Superior-Twin-Room"] == Decimal("50")
    assert ROOM_SIZES["You-Ya-Family-Room"] == Decimal("63")
    assert ROOM_SIZES["Grand-View-Suite"] == Decimal("116")
    assert ROOM_SIZES["GRAND-VIEW-SUITE-603"] == Decimal("96")
