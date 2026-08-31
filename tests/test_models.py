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
    assert row.size_band == "50–69㎡"
    assert row.price_per_sqm == Decimal("231")
    assert row.total_twd == Decimal("11550")
    assert row.cpi_adjusted_twd == Decimal("10500")
