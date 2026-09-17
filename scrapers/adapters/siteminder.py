import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from playwright.async_api import Locator, Page

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, breakfast_included, parse_money


PROPERTIES = {
    "eslite_hotel": "EsliteHotel",
}


def booking_url(hotel_id: str, check_in: date, check_out: date, adults: int = 2) -> str:
    if hotel_id not in PROPERTIES:
        raise ValueError(f"SiteMinderScraper does not support hotel {hotel_id}")
    query = urlencode(
        {
            "locale": "zh-TW",
            "items[0][adults]": adults,
            "items[0][children]": 0,
            "items[0][infants]": 0,
            "currency": "TWD",
            "checkInDate": check_in.isoformat(),
            "checkOutDate": check_out.isoformat(),
        }
    )
    return f"https://book-directonline.com/properties/{PROPERTIES[hotel_id]}?{query}"


def parse_room_size(text: str) -> Decimal | None:
    match = re.search(
        r"(?:面積|Room size)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:平方米|平方公尺|m²|sqm)",
        text,
        re.IGNORECASE,
    )
    return Decimal(match.group(1)) if match else None


def parse_cancellation(text: str) -> str | None:
    for line in (part.strip() for part in text.splitlines()):
        if line and any(term in line.lower() for term in ("取消", "cancel")):
            return line
    return None


class SiteMinderScraper(CapellaScraper):
    """Adapter for public SiteMinder Direct Booking availability pages."""

    diagnostic_name = "SiteMinder Direct Booking"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        source_url = booking_url(hotel.id, check_in, check_out, adults)
        queried_at = datetime.now(UTC)
        page = await self._page()
        response = None
        try:
            response = await page.goto(
                source_url, wait_until="domcontentloaded", timeout=self.timeout_ms
            )
            await self._dismiss_cookie(page)
            await page.locator("[id^='roomType-']").first.wait_for(
                state="visible", timeout=self.timeout_ms
            )
            return await self._collect(
                page, hotel, check_in, check_out, adults, queried_at, source_url
            )
        except Exception:
            title = await page.title()
            raw_body = await page.locator("body").text_content(timeout=3_000) or ""
            body_text = " ".join(raw_body.split())[:1200]
            raise RuntimeError(
                f"SiteMinder fetch failed: status={response.status if response else None} "
                f"final_url={page.url} title={title!r} body={body_text!r}"
            )
        finally:
            await page.close()

    async def _dismiss_cookie(self, page: Page) -> None:
        reject = page.get_by_role(
            "button", name=re.compile(r"全部拒絕|Reject all", re.IGNORECASE)
        )
        if await reject.count() and await reject.first.is_visible():
            await reject.first.click()

    async def _collect(
        self,
        page: Page,
        hotel: Hotel,
        check_in: date,
        check_out: date,
        adults: int,
        queried_at: datetime,
        source_url: str,
    ) -> list[RateObservation]:
        observations: list[RateObservation] = []
        rooms = page.locator("[id^='roomType-']")
        for room_index in range(await rooms.count()):
            room = rooms.nth(room_index)
            room_code = (await room.get_attribute("id") or "").removeprefix("roomType-")
            room_name = (await room.locator("h2").first.inner_text()).strip()
            room_text = await room.inner_text()
            room_size = parse_room_size(room_text)
            rates = room.locator("[id^='room-rate-']")
            for rate_index in range(await rates.count()):
                observation = await self._rate_observation(
                    rates.nth(rate_index), hotel, room_code, room_name, room_size,
                    check_in, check_out, adults, queried_at, source_url,
                )
                if observation is not None:
                    observations.append(observation)
        return observations

    async def _rate_observation(
        self,
        rate: Locator,
        hotel: Hotel,
        room_code: str,
        room_name: str,
        room_size: Decimal | None,
        check_in: date,
        check_out: date,
        adults: int,
        queried_at: datetime,
        source_url: str,
    ) -> RateObservation | None:
        text = await rate.inner_text()
        price_match = re.search(r"TWD\s*([\d,]+(?:\.\d+)?)", text.replace("\u00a0", " "))
        if not price_match:
            return None
        plan_name = (await rate.locator("h3").first.inner_text()).strip()
        rate_id = await rate.get_attribute("id")
        rate_code = rate_id.removeprefix("room-rate-") if rate_id else None
        total = parse_money(price_match.group(1))
        key = ":".join(
            (
                hotel.id,
                check_in.isoformat(),
                room_code or room_name,
                rate_code or plan_name,
                queried_at.isoformat(),
            )
        )
        return RateObservation(
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
            rate_plan_code=rate_code,
            rate_plan_name=plan_name,
            breakfast_included=breakfast_included([plan_name, text]),
            cancellation_policy=parse_cancellation(text),
            price_before_tax=None,
            service_charge=None,
            tax=None,
            total_price=total,
            currency="TWD",
            source_url=source_url,
            status=ScrapeStatus.LIVE,
            fx_rate_to_twd=Decimal("1"),
        )
