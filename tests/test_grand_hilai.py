import asyncio
from datetime import date
from decimal import Decimal

import pytest

from app.models import Hotel
from scrapers.adapters.grand_hilai import BOOKING_URLS, GrandHiLaiScraper, ping_to_sqm


def test_ping_to_sqm():
    assert ping_to_sqm("9坪") == Decimal("29.8")
    assert ping_to_sqm("客房面積 18坪") == Decimal("59.5")
    assert ping_to_sqm("unknown") is None


def test_grand_hilai_property_urls():
    assert BOOKING_URLS["grand_hilai_taipei"].endswith("/1003")
    assert BOOKING_URLS["grand_hilai_kaohsiung"].endswith("/1084")


def test_grand_hilai_rejects_unknown_hotel():
    hotel = Hotel(
        id="unknown", name="Unknown", short_name="Unknown", city="Taipei",
        country="TW", booking_url="https://example.com", adapter="grand_hilai"
    )
    with pytest.raises(ValueError):
        asyncio.run(
            GrandHiLaiScraper().fetch_rates(
                hotel, date(2026, 10, 1), date(2026, 10, 2)
            )
        )
