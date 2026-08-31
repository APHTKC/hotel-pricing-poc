from datetime import date

from app.models import Hotel, RateObservation
from scrapers.base import HotelScraper, ScraperNotImplementedError


class StubScraper(HotelScraper):
    def __init__(self, adapter_name: str):
        self.adapter_name = adapter_name

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        raise ScraperNotImplementedError(
            f"Adapter '{self.adapter_name}' for {hotel.name} is a stub. "
            "Implement and validate the official booking flow before enabling live collection."
        )
