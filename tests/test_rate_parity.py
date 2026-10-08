from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from services.rate_parity import (
    canonical_comparison_key,
    calculate_rate_parity,
    normalize_cancellation_class,
)


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
        ("rooms", 2),
        ("adults", 1),
        ("children", 1),
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
    ["hotel_id", "check_in", "check_out", "rooms", "adults", "children", "room_size_sqm", "breakfast_included", "cancellation_policy", "tax_inclusion"],
)
def test_incomplete_metadata_is_not_comparable(missing_field):
    row = product()
    row[missing_field] = None if missing_field != "tax_inclusion" else "unknown"
    assert canonical_comparison_key(row) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("rooms", 0), ("adults", 0), ("children", -1), ("adults", "invalid")],
)
def test_invalid_occupancy_is_not_comparable(field, value):
    row = product()
    row[field] = value
    assert canonical_comparison_key(row) is None


@pytest.mark.parametrize(
    "policy",
    [
        "入住日前至少 3 天取消或更改可免收取消費",
        "2026年10月12日前（不含當日）可免費取消",
        "Free cancellation before 2026-10-12",
    ],
)
def test_deadline_based_free_cancellation_is_conditional(policy):
    assert normalize_cancellation_class(policy) == "conditional"


def test_unrestricted_free_cancellation_remains_free_cancellation():
    assert normalize_cancellation_class("Free cancellation") == "free_cancellation"
