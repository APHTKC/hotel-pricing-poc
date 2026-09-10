from datetime import date

from scrapers.adapters.shangrila import (
    ShangriLaScraper,
    display_currency,
    is_public_cash_rate,
)


def test_shangrila_booking_url_contains_hotel_and_dates():
    url = ShangriLaScraper().booking_url(date(2026, 10, 7), date(2026, 10, 8), 2)
    assert "hotelCode=TPE" in url
    assert "checkInDate=2026-10-07" in url
    assert "checkOutDate=2026-10-08" in url
    assert "%22adultNum%22%3A2" in url


def test_shangrila_keeps_only_public_rates():
    assert is_public_cash_rate("") is True
    assert is_public_cash_rate(None) is True
    assert is_public_cash_rate("Member Rate") is False


def test_shangrila_detects_visitor_currency():
    assert display_currency("English\nNTD\nSelect a Hotel") == "TWD"
    assert display_currency("English\nUSD\nSelect a Hotel") == "USD"
    assert display_currency("USD 303\nCancellation fee NTD 10,000") == "USD"
