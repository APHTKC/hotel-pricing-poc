from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import RateObservation, ScrapeStatus


def test_derived_fields():
    row = RateObservation(
        observation_id="test", queried_at=datetime.now(UTC), check_in=date(2026, 9, 1),
        check_out=date(2026, 9, 2), lead_days=5, hotel_id="h", hotel_name="Hotel",
        room_type_name="Room", room_size_sqm=Decimal("50"), rate_plan_name="Flexible",
        price_before_tax=Decimal("10000"), service_charge=Decimal("1000"),
        tax=Decimal("550"), total_price=Decimal("11550"), currency="TWD",
        source_url="https://example.com", status=ScrapeStatus.DEMO,
        fx_rate_to_twd=Decimal("1"), cpi_index=Decimal("110"), cpi_base_index=Decimal("100"),
    )
    assert row.size_band == "45–59㎡"
    assert row.price_per_sqm == Decimal("231")
    assert row.total_twd == Decimal("11550")
    assert row.cpi_adjusted_twd == Decimal("10500")
    assert row.schema_version == "1.3"
    assert row.run_id is None
    assert row.scheduled_for is None
    assert row.source_platform == "official"
    assert row.source_method == "public_booking_page"
    assert row.source_property_id is None


def test_foreign_currency_price_per_sqm_uses_twd_value():
    row = RateObservation(
        observation_id="usd", queried_at=datetime.now(UTC), check_in=date(2026, 9, 1),
        check_out=date(2026, 9, 2), lead_days=5, hotel_id="h", hotel_name="Hotel",
        room_type_name="Room", room_size_sqm=Decimal("50"), rate_plan_name="Flexible",
        total_price=Decimal("400"), currency="USD", fx_rate_to_twd=Decimal("30"),
        source_url="https://example.com", status=ScrapeStatus.LIVE,
    )
    assert row.total_twd == Decimal("12000")
    assert row.price_per_sqm == Decimal("240")


def test_missing_room_size_has_unknown_band():
    row = RateObservation(
        observation_id="unknown-size",
        queried_at=datetime.now(UTC),
        check_in=date(2026, 9, 1),
        check_out=date(2026, 9, 2),
        lead_days=5,
        hotel_id="h",
        hotel_name="Hotel",
        room_type_name="Room",
        room_size_sqm=None,
        rate_plan_name="Flexible",
        total_price=Decimal("10000"),
        currency="TWD",
        source_url="https://example.com",
        status=ScrapeStatus.LIVE,
    )

    assert row.size_band == "unknown"
    assert row.price_per_sqm is None
