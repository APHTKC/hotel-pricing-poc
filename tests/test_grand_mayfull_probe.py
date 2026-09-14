from datetime import date
from urllib.parse import parse_qs, urlparse

from scripts.probe_grand_mayfull_taipei import booking_url


def test_grand_mayfull_booking_url_contains_dates_guests_and_currency():
    url = booking_url(date(2026, 10, 10), date(2026, 10, 11), 2)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.path.endswith("/properties/GrandMayfullHotelTaipeiDirect")
    assert query["checkInDate"] == ["2026-10-10"]
    assert query["checkOutDate"] == ["2026-10-11"]
    assert query["items[0][adults]"] == ["2"]
    assert query["currency"] == ["TWD"]
    assert query["locale"] == ["zh-TW"]
