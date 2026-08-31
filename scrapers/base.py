from abc import ABC, abstractmethod
from datetime import date

from app.models import Hotel, RateObservation


class ScraperNotImplementedError(RuntimeError):
    pass


class HotelScraper(ABC):
    """Contract for one booking-engine adapter.

    Implementations may share one adapter across several hotels using the same
    engine. They must return only rates verified on the hotel's official site.
    """

    @abstractmethod
    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        raise NotImplementedError

    async def close(self) -> None:
        return None
