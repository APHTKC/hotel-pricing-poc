import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.models import Hotel, RateObservation, ScrapeStatus, TaxInclusion
from scrapers.ota.base import OtaRateProvider


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("booker_currency", value.get("accommodation_currency"))
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _localized_text(value: Any, language: str) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict) or not value:
        return None
    return value.get(language) or value.get("en-gb") or next(iter(value.values()), None)


def _policy_text(product: dict[str, Any]) -> str | None:
    cancellation = (product.get("policies") or {}).get("cancellation") or {}
    policy_type = cancellation.get("type")
    deadline = cancellation.get("free_cancellation_until")
    if policy_type == "free_cancellation" and deadline:
        return f"Free cancellation until {deadline}"
    return str(policy_type).replace("_", " ") if policy_type else None


def _breakfast_included(product: dict[str, Any]) -> bool | None:
    meal_plan = (product.get("policies") or {}).get("meal_plan") or {}
    plan = meal_plan.get("plan") or meal_plan.get("type")
    if plan is None:
        return None
    text = str(plan).lower()
    if "breakfast" in text:
        return not any(word in text for word in ("without", "excluded", "no_"))
    if text in {"no_meal", "room_only"}:
        return False
    return None


def parse_availability(
    payload: dict[str, Any],
    hotel: Hotel,
    source_property_id: str,
    check_in: date,
    check_out: date,
    adults: int,
    queried_at: datetime,
    room_details: list[dict[str, Any]] | None = None,
) -> list[RateObservation]:
    """Convert Booking.com Demand API 3.1/3.2 availability to our schema."""
    data = payload.get("data") or {}
    products = data.get("products") or []
    currency = data.get("currency") or hotel.currency
    source_url = data.get("url") or data.get("deep_link_url") or "https://www.booking.com/"
    rooms = room_details if room_details is not None else (data.get("rooms") or [])
    room_names = {
        str(room.get("id")): (
            next(iter(room.get("name", {}).values()), None)
            if isinstance(room.get("name"), dict)
            else room.get("name")
        )
        for room in rooms
        if isinstance(room, dict) and room.get("id") is not None
    }
    room_sizes = {
        str(room.get("id")): _decimal(
            (room.get("size") or {}).get("value")
            if isinstance(room.get("size"), dict)
            else room.get("size")
        )
        for room in rooms
        if isinstance(room, dict) and room.get("id") is not None
    }
    observations: list[RateObservation] = []
    for product in products:
        price = product.get("price") or {}
        total = _decimal(price.get("total"))
        if total is None:
            continue
        room = product.get("room")
        if isinstance(room, dict):
            room_code = str(room.get("id") or "") or None
            room_name = room.get("name") or room_names.get(str(room.get("id")))
        else:
            room_code = str(room) if room is not None else None
            room_name = room_names.get(str(room)) if room is not None else None
        room_name = room_name or (f"Room {room_code}" if room_code else "Available room")
        breakfast = _breakfast_included(product)
        cancellation = _policy_text(product)
        plan_bits = ["Booking.com"]
        if breakfast is True:
            plan_bits.append("breakfast included")
        elif breakfast is False:
            plan_bits.append("room only")
        if cancellation:
            plan_bits.append(cancellation)
        product_id = str(product.get("id") or "") or None
        key = ":".join(
            (
                "booking_com",
                hotel.id,
                source_property_id,
                check_in.isoformat(),
                product_id or room_name,
                queried_at.isoformat(),
            )
        )
        observations.append(
            RateObservation(
                observation_id=hashlib.sha256(key.encode()).hexdigest()[:24],
                queried_at=queried_at,
                check_in=check_in,
                check_out=check_out,
                lead_days=(check_in - queried_at.date()).days,
                nights=(check_out - check_in).days,
                adults=adults,
                hotel_id=hotel.id,
                hotel_name=hotel.name,
                city=hotel.city,
                district=hotel.district,
                room_type_code=room_code,
                room_type_name=str(room_name),
                room_size_sqm=room_sizes.get(str(room_code)),
                rate_plan_code=product_id,
                rate_plan_name=" · ".join(plan_bits),
                breakfast_included=breakfast,
                cancellation_policy=cancellation,
                price_before_tax=_decimal(price.get("base")),
                service_charge=None,
                tax=None,
                total_price=total,
                tax_inclusion=TaxInclusion.INCLUDED,
                currency=str(currency),
                source_platform="booking_com",
                source_method="partner_api",
                source_property_id=source_property_id,
                source_url=str(source_url),
                status=ScrapeStatus.LIVE,
                fx_rate_to_twd=Decimal("1") if currency == "TWD" else None,
            )
        )
    return observations


class BookingComProvider(OtaRateProvider):
    platform = "booking_com"
    endpoint = "https://demandapi.booking.com/3.2/accommodations/availability"
    autocomplete_endpoint = "https://demandapi.booking.com/3.2/common/autocomplete"

    def __init__(
        self,
        api_key: str,
        affiliate_id: str,
        booker_country: str = "tw",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.affiliate_id = affiliate_id
        self.booker_country = booker_country.lower()
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=30)
        self._rooms: dict[str, list[dict[str, Any]]] = {}

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-Affiliate-Id": self.affiliate_id,
            "Content-Type": "application/json",
        }

    async def discover_properties(
        self,
        query: str,
        country: str = "tw",
        language: str = "en-gb",
    ) -> list[dict[str, Any]]:
        """Return ranked Booking.com hotel suggestions for one hotel name.

        Discovery is deliberately an explicit, one-hotel-at-a-time operation so
        it cannot consume partner quota by scanning the whole catalog.
        """
        query = query.strip()
        if len(query) < 3:
            raise ValueError("Booking.com autocomplete queries require 3+ characters")
        response = await self.client.post(
            self.autocomplete_endpoint,
            headers=self.headers,
            json={
                "query": query,
                "country": country.lower(),
                "language": language.lower(),
                "filters": {"types": ["hotel"]},
            },
        )
        response.raise_for_status()
        results = []
        for item in response.json().get("data") or []:
            if item.get("type") != "hotel" or item.get("id") is None:
                continue
            location = item.get("location") or {}
            results.append(
                {
                    "id": str(item["id"]),
                    "name": _localized_text(item.get("name"), language),
                    "city": _localized_text(location.get("city_name"), language),
                    "country": location.get("country"),
                }
            )
        return results

    async def _room_details(self, source_property_id: str) -> list[dict[str, Any]]:
        if source_property_id in self._rooms:
            return self._rooms[source_property_id]
        try:
            response = await self.client.post(
                "https://demandapi.booking.com/3.2/accommodations/details",
                headers=self.headers,
                json={
                    "accommodations": [int(source_property_id)],
                    "extras": ["rooms"],
                    "languages": ["zh-tw", "en-gb"],
                },
            )
            response.raise_for_status()
            properties = response.json().get("data") or []
            rooms = properties[0].get("rooms") or [] if properties else []
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            rooms = []
        self._rooms[source_property_id] = rooms
        return rooms

    async def fetch_rates(
        self,
        hotel: Hotel,
        source_property_id: str,
        check_in: date,
        check_out: date,
        adults: int = 2,
    ) -> list[RateObservation]:
        queried_at = datetime.now(UTC)
        room_details = await self._room_details(source_property_id)
        response = await self.client.post(
            self.endpoint,
            headers=self.headers,
            json={
                "accommodation": int(source_property_id),
                "booker": {"country": self.booker_country, "platform": "desktop"},
                "checkin": check_in.isoformat(),
                "checkout": check_out.isoformat(),
                "currency": "TWD",
                "extras": ["products", "extra_charges"],
                "guests": {"number_of_adults": adults, "number_of_rooms": 1},
            },
        )
        response.raise_for_status()
        return parse_availability(
            response.json(),
            hotel,
            source_property_id,
            check_in,
            check_out,
            adults,
            queried_at,
            room_details,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()
