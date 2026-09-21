from datetime import date
from decimal import Decimal

import pytest

from scrapers.adapters.shangrila import (
    ShangriLaScraper,
    display_currency,
    is_public_cash_rate,
    resolve_display_currency,
)


def test_shangrila_booking_url_contains_hotel_and_dates():
    url = ShangriLaScraper().booking_url(date(2026, 10, 7), date(2026, 10, 8), 2)
    assert "hotelCode=TPE" in url
    assert "checkInDate=2026-10-07" in url
    assert "checkOutDate=2026-10-08" in url
    assert "%22adultNum%22%3A2" in url


def test_tainan_shangrila_booking_url_uses_official_property_code():
    url = ShangriLaScraper().booking_url(
        date(2026, 10, 21), date(2026, 10, 22), 2, "shangrila_tainan"
    )
    assert "/en/tainan/fareasternplazashangrila/" in url
    assert "hotelCode=SLTN" in url
    assert "city=Tainan" in url


def test_shangrila_keeps_only_public_rates():
    assert is_public_cash_rate("") is True
    assert is_public_cash_rate(None) is True
    assert is_public_cash_rate("Member Rate") is False


def test_shangrila_detects_visitor_currency():
    assert display_currency("English\nNTD\nSelect a Hotel") == "TWD"
    assert display_currency("English\nUSD\nSelect a Hotel") == "USD"
    assert display_currency("USD 303\nCancellation fee NTD 10,000") == "USD"
    assert display_currency("NT$ 12,960") == "TWD"
    assert display_currency("US$ 303") == "USD"
    assert display_currency("\u00a5 45,000") == "JPY"


def test_shangrila_infers_unlabelled_cloud_prices_by_taiwan_rate_scale():
    assert resolve_display_currency("303", Decimal("303")) == "USD"
    assert resolve_display_currency("12,960", Decimal("12960")) == "TWD"
    with pytest.raises(ValueError):
        resolve_display_currency("0", Decimal("0"))
