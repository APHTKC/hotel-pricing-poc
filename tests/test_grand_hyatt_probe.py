from datetime import date

from scripts.probe_grand_hyatt_taipei import booking_url


def test_grand_hyatt_booking_url_contains_property_dates_and_guests():
    url = booking_url(date(2026, 10, 10), date(2026, 10, 11), 2)
    assert "/shop/rooms/taigh?" in url
    assert "checkinDate=2026-10-10" in url
    assert "checkoutDate=2026-10-11" in url
    assert "adults=2" in url
    assert "rate=Standard" in url
