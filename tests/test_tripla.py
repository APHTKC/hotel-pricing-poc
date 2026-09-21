from datetime import date
from decimal import Decimal

import pytest

from scrapers.adapters.tripla import booking_url, parse_room_size


def test_tripla_booking_url_has_dates_and_property_code():
    url = booking_url(
        "windsor_taichung", date(2026, 10, 1), date(2026, 10, 2), adults=2
    )
    assert "35107e0b-6d82-4b23-850c-a46c7b9e0e84" in url
    assert "checkin=2026%2F10%2F01" in url
    assert "checkout=2026%2F10%2F02" in url


def test_tripla_parse_room_size():
    assert parse_room_size("客房大小: 37 m 2") == Decimal("37")
    assert parse_room_size("Room size: 31 m²") == Decimal("31")
    assert parse_room_size("No size") is None


def test_tripla_rejects_unknown_hotel():
    with pytest.raises(ValueError):
        booking_url("unknown", date(2026, 10, 1), date(2026, 10, 2))
