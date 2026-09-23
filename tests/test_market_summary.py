from datetime import UTC, date, datetime
from decimal import Decimal

from app.main import market_summary
from app.models import RateObservation, ScrapeStatus
from app.settings import Settings


def observation(hotel_id: str, price: str, size: str = "50") -> RateObservation:
    return RateObservation(
        observation_id=f"{hotel_id}-{price}",
        queried_at=datetime(2026, 9, 23, tzinfo=UTC),
        check_in=date(2026, 9, 30),
        check_out=date(2026, 10, 1),
        lead_days=7,
        hotel_id=hotel_id,
        hotel_name=hotel_id,
        room_type_name="Room",
        room_size_sqm=Decimal(size),
        rate_plan_name="Public rate",
        total_price=Decimal(price),
        currency="TWD",
        source_url="https://example.com",
        status=ScrapeStatus.LIVE,
        fx_rate_to_twd=Decimal("1"),
    )


def test_market_summary_equal_weights_hotels(monkeypatch):
    rows = [
        observation("many_rows", "100"),
        observation("many_rows", "200"),
        observation("many_rows", "300"),
        observation("one_row", "1000"),
    ]
    monkeypatch.setattr("app.main.filtered_rates", lambda *args, **kwargs: rows)

    result = market_summary(settings=Settings(demo_mode=False))

    assert result["observations"] == 4
    assert result["hotels"] == 2
    assert result["average_adr_twd"] == 600
    assert result["median_adr_twd"] == 600
    assert result["median_per_sqm_twd"] == 12
    assert result["demo_mode"] is False
