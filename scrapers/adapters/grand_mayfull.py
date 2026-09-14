import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, parse_money


BASE_URL = "https://book-directonline.com/properties/GrandMayfullHotelTaipeiDirect"


def parse_room_size(text: str) -> Decimal | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*m²", text)
    return Decimal(match.group(1)) if match else None


def booking_url(check_in: date, check_out: date, adults: int = 2) -> str:
    query = urlencode(
        {
            "locale": "zh-TW",
            "items[0][adults]": adults,
            "items[0][children]": 0,
            "items[0][infants]": 0,
            "currency": "TWD",
            "checkInDate": check_in.isoformat(),
            "checkOutDate": check_out.isoformat(),
            "trackPage": "no",
        }
    )
    return f"{BASE_URL}?{query}"


class GrandMayfullScraper(CapellaScraper):
    supported_hotel_id = "grand_mayfull_taipei"
    diagnostic_name = "Grand Mayfull Taipei"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id != self.supported_hotel_id:
            raise ValueError(
                f"GrandMayfullScraper currently supports only {self.supported_hotel_id}"
            )
        queried_at = datetime.now(UTC)
        source_url = booking_url(check_in, check_out, adults)
        page = await self._page()
        try:
            await page.goto(
                source_url, wait_until="domcontentloaded", timeout=self.timeout_ms
            )
            await page.locator("[id^='room-rate-']").first.wait_for()
            await page.wait_for_timeout(500)
            return await self._collect(
                page, hotel, check_in, check_out, adults, queried_at, source_url
            )
        finally:
            await page.close()

    async def _collect(
        self, page, hotel, check_in, check_out, adults, queried_at, source_url
    ) -> list[RateObservation]:
        observations: list[RateObservation] = []
        room_cards = page.locator("[id^='roomType-']")
        for room_index in range(await room_cards.count()):
            room = room_cards.nth(room_index)
            room_code = (await room.get_attribute("id") or "").replace("roomType-", "")
            room_name = (await room.locator("h2").first.inner_text()).strip()
            room_text = await room.inner_text()
            room_size = parse_room_size(room_text)
            rates = room.locator("[id^='room-rate-']")
            for rate_index in range(await rates.count()):
                rate = rates.nth(rate_index)
                rate_id = (await rate.get_attribute("id") or "").replace("room-rate-", "")
                plan_name = (await rate.locator("h3").first.inner_text()).strip()
                messages = [
                    " ".join(text.split())
                    for text in await rate.locator(".rate-inclusions .message").all_inner_texts()
                    if text.strip()
                ]
                price_text = await rate.locator(".price--now").first.inner_text()
                total = parse_money(price_text)
                cancellation = next(
                    (text for text in messages if "取消" in text), None
                )
                breakfast = any("含早餐" in text for text in messages)
                key = ":".join(
                    (
                        hotel.id,
                        check_in.isoformat(),
                        room_code,
                        rate_id or plan_name,
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
                        room_type_code=room_code or None,
                        room_type_name=room_name,
                        room_size_sqm=room_size,
                        rate_plan_code=rate_id or None,
                        rate_plan_name=plan_name,
                        breakfast_included=breakfast,
                        cancellation_policy=cancellation,
                        price_before_tax=None,
                        service_charge=None,
                        tax=None,
                        total_price=total,
                        currency="TWD",
                        source_url=source_url,
                        status=ScrapeStatus.LIVE,
                        fx_rate_to_twd=Decimal("1"),
                    )
                )
        return observations
