from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal


class CPIProvider(ABC):
    @abstractmethod
    async def index(self, country: str, on_date: date) -> Decimal | None:
        raise NotImplementedError


class NullCPIProvider(CPIProvider):
    async def index(self, country: str, on_date: date) -> Decimal | None:
        return None


# Production extension point: monthly Taiwan DGBAS / Japan Statistics Bureau CPI.
