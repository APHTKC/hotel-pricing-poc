from abc import ABC, abstractmethod
from datetime import date

from app.models import Hotel, RateObservation


class OtaRateProvider(ABC):
    """Contract for an authorized OTA API or partner feed."""

    platform: str
    source_method = "partner_api"

    @abstractmethod
    async def fetch_rates(
        self,
        hotel: Hotel,
        source_property_id: str,
        check_in: date,
        check_out: date,
        adults: int = 2,
    ) -> list[RateObservation]:
        """Return verified rates for one mapped OTA property."""
        raise NotImplementedError

    def tag_observation(
        self, observation: RateObservation, source_property_id: str
    ) -> RateObservation:
        """Apply consistent source metadata before storage and comparison."""
        return observation.model_copy(
            update={
                "source_platform": self.platform,
                "source_method": self.source_method,
                "source_property_id": source_property_id,
            }
        )

    async def close(self) -> None:
        return None
