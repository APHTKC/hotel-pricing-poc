from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from services.rate_parity import (
    canonical_comparison_key,
    calculate_rate_parity,
    comparison_key_missing_fields,
    normalize_cancellation_class,
    normalize_cancellation_deadline,
    normalize_cancellation_schedule,
    normalize_tax_inclusion,
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
        "queried_at": "2026-09-01T01:00:00Z",
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


def test_comparison_uses_latest_ota_batch_that_has_a_valid_official_pair():
    official = product(
        queried_at="2026-10-08T01:00:00Z", total_price=Decimal("10000")
    )
    ota_valid = product(
        source_platform="booking_com",
        queried_at="2026-10-08T12:00:00Z",
        total_price=Decimal("11000"),
    )
    ota_newer_but_stale = product(
        source_platform="booking_com",
        queried_at="2026-10-12T12:00:00Z",
        total_price=Decimal("13000"),
    )

    comparison = calculate_rate_parity([official, ota_valid, ota_newer_but_stale])[0]

    assert comparison["ota_median_twd"] == 11000
    assert comparison["ota_queried_at"] == "2026-10-08T12:00:00+00:00"
    assert comparison["query_time_gap_hours"] == 11


def test_comparison_rejects_rows_without_query_timestamps():
    official = product(queried_at=None)
    ota = product(source_platform="booking_com", queried_at=None)

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


def test_different_conditional_refund_deadlines_are_not_compared():
    official = product(
        check_in=date(2026, 12, 20),
        cancellation_policy="No charge for bookings cancelled the day prior to arrival",
    )
    ota = product(
        check_in=date(2026, 12, 20),
        source_platform="booking_com",
        cancellation_policy="2026年12月15日前可全額退款",
    )

    assert calculate_rate_parity([official, ota]) == []


def test_relative_and_absolute_matching_refund_deadlines_are_compared():
    official = product(
        check_in=date(2026, 12, 20),
        cancellation_policy="入住 3 天前取消可全額退款",
    )
    ota = product(
        check_in=date(2026, 12, 20),
        source_platform="booking_com",
        cancellation_policy="2026年12月17日前可全額退款",
    )

    assert len(calculate_rate_parity([official, ota])) == 1


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


def test_missing_fields_explain_strict_key_rejection():
    row = product(
        stable_room_type_id=None,
        breakfast_included=None,
        cancellation_policy="Cancellation policy is available on booking page",
        tax_inclusion="unknown",
    )

    assert comparison_key_missing_fields(
        row, require_stable_room_type=True
    ) == [
        "stable_room_type_id",
        "breakfast_included",
        "cancellation_class",
        "cancellation_deadline",
        "tax_inclusion",
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [("rooms", 0), ("adults", 0), ("children", -1), ("adults", "invalid")],
)
def test_invalid_occupancy_is_not_comparable(field, value):
    row = product()
    row[field] = value
    assert canonical_comparison_key(row) is None


def test_tax_inclusion_requires_reconciled_price_components():
    matching = product(
        tax_inclusion="unknown",
        price_before_tax=Decimal("10000"),
        service_charge=Decimal("1000"),
        tax=Decimal("500"),
        total_price=Decimal("11500"),
    )
    mismatch = {**matching, "total_price": Decimal("12000")}

    assert normalize_tax_inclusion(matching) == "included"
    assert canonical_comparison_key(matching) is not None
    assert normalize_tax_inclusion(mismatch) == "unknown"
    assert canonical_comparison_key(mismatch) is None


def test_explicit_tax_inclusion_remains_authoritative():
    assert normalize_tax_inclusion(
        product(tax_inclusion="excluded", total_price=Decimal("10000"))
    ) == "excluded"


@pytest.mark.parametrize(
    "policy",
    [
        "入住日前至少 3 天取消或更改可免收取消費",
        "入住 3 天前取消可全額退款",
        "2026年10月12日前（不含當日）可免費取消",
        "Free cancellation before 2026-10-12",
    ],
)
def test_deadline_based_free_cancellation_is_conditional(policy):
    assert normalize_cancellation_class(policy) == "conditional"


@pytest.mark.parametrize(
    ("policy", "check_in", "expected"),
    [
        ("入住日前至少 3 天取消可免收取消費", date(2027, 1, 9), "2027-01-06"),
        ("入住 3 天前取消可全額退款", date(2026, 12, 20), "2026-12-17"),
        ("抵達前免費取消最多 15:00 1 天", date(2026, 12, 20), "2026-12-19"),
        ("2026年12月17日前可全額退款", date(2026, 12, 20), "2026-12-17"),
        ("12 月 15 日前可全額退款", date(2026, 12, 20), "2026-12-15"),
        ("15 Dec 2026 before arrival", date(2026, 12, 20), "2026-12-15"),
        ("No charge when cancelled the day prior to arrival", date(2026, 12, 20), "2026-12-19"),
        (
            "Reservations must be cancelled three day prior to arrival",
            date(2026, 12, 22),
            "2026-12-19",
        ),
        (
            "Reservations must be cancelled ten days prior to arrival",
            date(2027, 1, 16),
            "2027-01-06",
        ),
    ],
)
def test_cancellation_deadline_normalizes_to_calendar_date(policy, check_in, expected):
    assert normalize_cancellation_deadline(
        product(cancellation_policy=policy, check_in=check_in)
    ) == expected


def test_unrestricted_free_cancellation_remains_free_cancellation():
    assert normalize_cancellation_class("Free cancellation") == "free_cancellation"


def test_full_booking_value_cancellation_fee_is_non_refundable():
    assert (
        normalize_cancellation_class("取消須付費（訂單總額）；無需訂金，入住時付款")
        == "non_refundable"
    )
    assert normalize_cancellation_class("不得退款") == "non_refundable"
    assert normalize_cancellation_class("取消須付費") == "unknown"


def test_full_stay_charge_and_explicit_no_refund_are_non_refundable():
    policy = (
        "Room cancelled will be subject to 100% of stay room charge, plus "
        "applicable service charges, taxes, and fees."
    )
    assert normalize_cancellation_class(policy) == "non_refundable"
    assert normalize_cancellation_deadline(
        product(cancellation_policy=policy)
    ) == "non_refundable"
    assert normalize_cancellation_class("事先付款・無法退款") == "non_refundable"


def test_tiered_deposit_penalties_are_structured_without_fake_deadline():
    policy = (
        "取消費用 取消日期 取消日期計費比例 "
        "13~4天之前 訂金的30％ 3~1天之前 訂金的70％ 當天 訂金的100％"
    )

    assert normalize_cancellation_class(policy) == "conditional"
    assert normalize_cancellation_deadline(
        product(cancellation_policy=policy, check_in="2026-12-20")
    ) == "unknown"
    assert normalize_cancellation_schedule(policy) == [
        {
            "days_before_from": 13,
            "days_before_to": 4,
            "penalty_percent": 30,
            "penalty_basis": "deposit",
        },
        {
            "days_before_from": 3,
            "days_before_to": 1,
            "penalty_percent": 70,
            "penalty_basis": "deposit",
        },
        {
            "days_before_from": 0,
            "days_before_to": 0,
            "penalty_percent": 100,
            "penalty_basis": "deposit",
        },
    ]
    assert canonical_comparison_key(
        product(cancellation_policy=policy, check_in="2026-12-20")
    ) is None


def test_english_dated_room_charge_policy_is_conditional():
    policy = (
        "Room cancelled after 18:00 local hotel time on 11 Oct 2026 will be "
        "subject to 1 night(s) room charge, plus applicable service charges, "
        "taxes, and fees."
    )
    row = product(cancellation_policy=policy, check_in="2026-10-12")
    assert normalize_cancellation_class(policy) == "conditional"
    assert normalize_cancellation_deadline(row) == "2026-10-11"
