from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
import json
from pathlib import Path


class FXProvider(ABC):
    @abstractmethod
    async def rate(self, currency: str, target: str, on_date: date) -> Decimal | None:
        raise NotImplementedError


class IdentityFXProvider(FXProvider):
    async def rate(self, currency: str, target: str, on_date: date) -> Decimal | None:
        return Decimal("1") if currency == target else None


def published_rate_to_twd(
    currency: str, path: Path = Path("public/data/fx.json")
) -> Decimal:
    """Read the last successfully published Google Finance conversion rate.

    The dashboard file stores foreign currency units per TWD, so converting a
    foreign room price back to TWD requires the reciprocal.
    """
    normalized = "TWD" if currency.upper() == "NTD" else currency.upper()
    if normalized == "TWD":
        return Decimal("1")
    payload = json.loads(path.read_text(encoding="utf-8"))
    foreign_per_twd = Decimal(str(payload["rates"][normalized]))
    if foreign_per_twd <= 0:
        raise ValueError(f"Invalid Google Finance rate for {normalized}")
    return Decimal("1") / foreign_per_twd


# Production extension point: implement an official central-bank or licensed
# market-data provider here, with caching and source-date metadata.
