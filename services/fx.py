from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal


class FXProvider(ABC):
    @abstractmethod
    async def rate(self, currency: str, target: str, on_date: date) -> Decimal | None:
        raise NotImplementedError


class IdentityFXProvider(FXProvider):
    async def rate(self, currency: str, target: str, on_date: date) -> Decimal | None:
        return Decimal("1") if currency == target else None


# Production extension point: implement an official central-bank or licensed
# market-data provider here, with caching and source-date metadata.
