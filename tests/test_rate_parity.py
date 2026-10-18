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
        "stable_room_type_id": "rt_evidenced_deluxe_king",
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


def test_multinight_parity_compares_nightly_adr():
    official = product(
        check_out=date(2026, 10, 3), nights=2, total_price=Decimal("24000")
    )
    ota = product(
        check_out=date(2026, 10, 3), nights=2,
        source_platform="booking_com", total_price=Decimal("26000"),
    )

    comparison = calculate_rate_parity([official, ota])[0]

    assert comparison["official_median_twd"] == 12000
    assert comparison["ota_median_twd"] == 13000
    assert comparison["gap_percent"] == pytest.approx(1 / 12)


def test_comparison_uses_nearest_observation_batch_within_one_day():
    official_old = product(
        queried_at="2026-10-01T01:00:00Z", total_price=Decimal("7000")
    )
    official_near = product(
        queried_at="2026-10-08T01:00:00Z", total_price=Decimal("10000")
    )
    ota = product(
        source_platform="booking_com",
        queried_at="2026-10-08T12:00:00Z",
        total_price=Decimal("11000"),
    )

    comparisons = calculate_rate_parity([official_old, official_near, ota])

    assert len(comparisons) == 1
    assert comparisons[0]["official_median_twd"] == 10000
    assert comparisons[0]["query_time_gap_hours"] == 11
    assert comparisons[0]["official_queried_at"] == "2026-10-08T01:00:00+00:00"
    assert comparisons[0]["ota_queried_at"] == "2026-10-08T12:00:00+00:00"


def test_comparison_rejects_stale_official_observation():
    official = product(queried_at="2026-10-01T01:00:00Z")
    ota = product(
        source_platform="booking_com",
        queried_at="2026-10-08T12:00:00Z",
        total_price=Decimal("11000"),
    )

    assert calculate_rate_parity([official, ota]) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("check_out", date(2026, 10, 3)),
        ("rooms", 2),
        ("adults", 1),
        ("children", 1),
        ("stable_room_type_id", "rt_evidenced_suite"),
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


def test_strict_key_requires_evidenced_stable_room_type():
    row = product(stable_room_type_id=None)

    assert canonical_comparison_key(row) is not None
    assert canonical_comparison_key(row, require_stable_room_type=True) is None
    assert calculate_rate_parity([
        row,
        product(source_platform="booking_com", stable_room_type_id=None),
    ]) == []


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


def test_full_booking_value_cancellation_fee_is_non_refundable():
    assert (
        normalize_cancellation_class("取消須付費（訂單總額）；無需訂金，入住時付款")
        == "non_refundable"
    )
    assert normalize_cancellation_class("不得退款") == "non_refundable"
    assert normalize_cancellation_class("取消須付費") == "unknown"
