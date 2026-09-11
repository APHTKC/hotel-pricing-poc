from datetime import date

from scripts.probe_hilton_taipei import booking_url


def test_hilton_booking_url_contains_property_dates_and_guests():
    url = booking_url(date(2026, 10, 11), date(2026, 10, 12), 2)
    assert "ctyhocn=TSAUPUP" in url
    assert "arrivalDate=2026-10-11" in url
    assert "departureDate=2026-10-12" in url
    assert "room1NumAdults=2" in url
