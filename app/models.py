from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class ScrapeStatus(StrEnum):
    LIVE = "live"
    DEMO = "demo"
    UNAVAILABLE = "unavailable"


class Hotel(BaseModel):
    id: str
    name: str
    short_name: str
    city: str
    country: str
    currency: str = "TWD"
    timezone: str = "Asia/Taipei"
    booking_url: str
    adapter: str
    enabled: bool = True


class RateObservation(BaseModel):
    schema_version: str = "1.0"
    observation_id: str
    queried_at: datetime
    check_in: date
    check_out: date
    lead_days: int
    nights: int = 1
    adults: int = 2
    hotel_id: str
    hotel_name: str
    city: str = "Taipei"
    room_type_code: str | None = None
    room_type_name: str
    room_size_sqm: Decimal | None = None
    rate_plan_code: str | None = None
    rate_plan_name: str
    breakfast_included: bool | None = None
    cancellation_policy: str | None = None
    price_before_tax: Decimal | None = None
    service_charge: Decimal | None = None
    tax: Decimal | None = None
    total_price: Decimal
    currency: str
    source_url: str
    status: ScrapeStatus
    fx_rate_to_twd: Decimal | None = None
    cpi_index: Decimal | None = None
    cpi_base_index: Decimal | None = None

    @computed_field
    @property
    def price_per_sqm(self) -> Decimal | None:
        return self.total_price / self.room_size_sqm if self.room_size_sqm else None

    @computed_field
    @property
    def total_twd(self) -> Decimal | None:
        if self.currency == "TWD":
            return self.total_price
        return self.total_price * self.fx_rate_to_twd if self.fx_rate_to_twd else None

    @computed_field
    @property
    def cpi_adjusted_twd(self) -> Decimal | None:
        if not self.total_twd or not self.cpi_index or not self.cpi_base_index:
            return None
        return self.total_twd * self.cpi_base_index / self.cpi_index

    @computed_field
    @property
    def size_band(self) -> str:
        if self.room_size_sqm is None:
            return "unknown"
        size = float(self.room_size_sqm)
        if size < 40:
            return "<40㎡"
        if size < 50:
            return "40–49㎡"
        if size < 70:
            return "50–69㎡"
        return "70㎡+"


class JobResult(BaseModel):
    started_at: datetime
    finished_at: datetime
    observations: int
    failures: list[dict[str, str]] = Field(default_factory=list)
    storage_backend: str
