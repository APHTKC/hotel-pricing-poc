import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.base import HotelScraper


ROOMS = (
    ("DELUXE", "Deluxe Room", Decimal("45"), "Flexible Rate", True),
    ("PREMIER", "Premier Room", Decimal("55"), "Best Available Rate", False),
    ("SUITE", "Executive Suite", Decimal("82"), "Flexible Rate with Breakfast", True),
)


class DemoScraper(HotelScraper):
    """Deterministic sample data for pipeline/UI testing; never a live quote."""

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        queried_at = datetime.now(UTC)
        lead_days = (check_in - queried_at.date()).days
        seed = int(hashlib.sha256(f"{hotel.id}:{check_in}".encode()).hexdigest()[:8], 16)
        hotel_base = Decimal(7800 + seed % 6500)
        results = []
        for index, (code, name, size, plan, breakfast) in enumerate(ROOMS):
            before_tax = (hotel_base * Decimal(str(1 + index * 0.42))).quantize(Decimal("1"))
            service = (before_tax * Decimal("0.10")).quantize(Decimal("1"))
            tax = ((before_tax + service) * Decimal("0.05")).quantize(Decimal("1"))
            results.append(
                RateObservation(
                    observation_id=hashlib.sha256(
                        f"{hotel.id}:{check_in}:{code}:{plan}:{queried_at.isoformat()}".encode()
                    ).hexdigest()[:24],
                    queried_at=queried_at,
                    check_in=check_in,
                    check_out=check_out,
                    lead_days=lead_days,
                    adults=adults,
                    hotel_id=hotel.id,
                    hotel_name=hotel.name,
                    room_type_code=code,
                    room_type_name=name,
                    room_size_sqm=size,
                    rate_plan_name=plan,
                    breakfast_included=breakfast,
                    cancellation_policy="Demo: free cancellation until 18:00 one day before arrival",
                    price_before_tax=before_tax,
                    service_charge=service,
                    tax=tax,
                    total_price=before_tax + service + tax,
                    currency=hotel.currency,
                    source_url=hotel.booking_url,
                    status=ScrapeStatus.DEMO,
                    fx_rate_to_twd=Decimal("1"),
                    cpi_index=Decimal("108.4"),
                    cpi_base_index=Decimal("100"),
                )
            )
        return results
