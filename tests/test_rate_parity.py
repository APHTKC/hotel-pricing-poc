from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from services.rate_parity import canonical_comparison_key, calculate_rate_parity


def product(**updates):
    row = {
        "hotel_id": "hotel-a",
        "check_in": date(2026, 10, 1),
        "check_out": date(2026, 10, 2),
        "rooms": 1,
        "adults": 2,
        "children": 0,
        "room_size_sqm": Decimal("55"),
        "breakfast_included": True,
        "cancellation_policy": "Free cancellation before arrival",
        "tax_inclusion": "included",
        "total_price": Decimal("10000"),
        "source_platform": "official",
    }
    row.update(updates)
    return row


def test_exact_same_product_is_compared():
    official = product(total_price=Decimal("10000"))
    ota = product(source_platform="booking_com", total_price=Decimal("11000"))

    comparisons = calculate_rate_parity([official, ota])

    assert len(comparisons) == 1
    assert comparisons[0]["official_median_twd"] == 10000
    assert comparisons[0]["ota_median_twd"] == 11000
    assert comparisons[0]["gap_percent"] == pytest.approx(0.1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("check_out", date(2026, 10, 3)),
        ("adults", 1),
        ("room_size_sqm", Decimal("80")),
        ("breakfast_included", False),
        ("cancellation_policy", "Non-refundable"),
        ("tax_inclusion", "excluded"),
    ],
)
def test_different_product_conditions_are_not_compared(field, value):
    official = product()
    ota = deepcopy(official)
    ota.update({"source_platform": "booking_com", field: value})

    assert calculate_rate_parity([official, ota]) == []


@pytest.mark.parametrize(
    "missing_field",
    ["check_out", "room_size_sqm", "breakfast_included", "cancellation_policy", "tax_inclusion"],
)
def test_incomplete_metadata_is_not_comparable(missing_field):
    row = product()
    row[missing_field] = None if missing_field != "tax_inclusion" else "unknown"
    assert canonical_comparison_key(row) is None
