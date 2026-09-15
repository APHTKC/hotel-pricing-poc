import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode, urljoin

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, parse_money


HOTEL_CODE = "0000000503"
BOOKING_BASE = "https://hoshinoresorts.com"


def booking_url(check_in: date, check_out: date, adults: int = 2) -> str:
    nights = (check_out - check_in).days
    if nights < 1:
        raise ValueError("check_out must be after check_in")
    query = urlencode({
        "checkIn": check_in.strftime("%Y/%m/%d"),
        "stay": nights,
        "a": adults,
        "b": 0,
        "c": 0,
        "d": 0,
    })
    return f"{BOOKING_BASE}/CH/hotels/{HOTEL_CODE}/search?{query}"


def room_size(text: str) -> Decimal | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*㎡", text)
    return Decimal(match.group(1)) if match else None


def plan_code(href: str) -> str | None:
    match = re.search(r"/plans/([^/?]+)", href)
    return match.group(1) if match else None


def meal_included(text: str) -> bool | None:
    if "不含餐" in text:
        return False
    if "含早" in text or "早餐" in text or "早晚餐" in text:
        return True
    return None


class HoshinoyaScraper(CapellaScraper):
    """Public rates from HOSHINOYA Guguan's official reservation pages."""

    supported_hotel_id = "hoshinoya_guguan"
    diagnostic_name = "HOSHINOYA Guguan"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id != self.supported_hotel_id:
            raise ValueError(
                f"HoshinoyaScraper currently supports only {self.supported_hotel_id}"
            )
        queried_at = datetime.now(UTC)
        search_url = booking_url(check_in, check_out, adults)
        page = await self._page()
        try:
            response = await page.goto(
                search_url, wait_until="domcontentloaded", timeout=self.timeout_ms
            )
            if response is not None and response.status >= 400:
                raise RuntimeError(f"HOSHINOYA search returned HTTP {response.status}")
            rooms = page.locator("section.room-with-plan")
            await rooms.first.wait_for(state="visible", timeout=self.timeout_ms)
            room_data = []
            for index in range(await rooms.count()):
                room = rooms.nth(index)
                link = room.locator("a.hotel-name").first
                href = await link.get_attribute("href")
                if not href:
                    continue
                room_data.append({
                    "code": (await room.get_attribute("id") or "").removeprefix("roomWithPlan"),
                    "name": (await link.inner_text()).strip(),
                    "size": room_size(await room.inner_text()),
                    "url": urljoin(BOOKING_BASE, href),
                })

            observations: list[RateObservation] = []
            for room in room_data:
                await page.goto(
                    room["url"], wait_until="domcontentloaded", timeout=self.timeout_ms
                )
                plans = page.locator("section.hotel-plan-item")
                try:
                    await plans.first.wait_for(state="visible", timeout=self.timeout_ms)
                except Exception:
                    continue
                for index in range(await plans.count()):
                    card = plans.nth(index)
                    title = card.locator("a.plan-title").first
                    href = await title.get_attribute("href") or ""
                    name = (await title.inner_text()).strip()
                    total_text = await card.locator(".plan-price span").nth(1).inner_text()
                    total = parse_money(total_text)
                    card_text = " ".join((await card.inner_text()).split())
                    cancellation = card.locator(".content").first
                    cancellation_text = None
                    if await cancellation.count():
                        cancellation_text = " ".join(
                            ((await cancellation.text_content()) or "").split()
                        ) or None
                    code = plan_code(href)
                    key = ":".join((
                        hotel.id,
                        check_in.isoformat(),
                        room["code"],
                        code or name,
                        queried_at.isoformat(),
                    ))
                    observations.append(RateObservation(
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
                        room_type_code=room["code"] or None,
                        room_type_name=room["name"],
                        room_size_sqm=room["size"],
                        rate_plan_code=code,
                        rate_plan_name=name,
                        breakfast_included=meal_included(card_text),
                        cancellation_policy=cancellation_text,
                        price_before_tax=None,
                        service_charge=None,
                        tax=None,
                        total_price=total,
                        currency="TWD",
                        source_url=room["url"],
                        status=ScrapeStatus.LIVE,
                        fx_rate_to_twd=Decimal("1"),
                    ))
            return observations
        finally:
            await page.close()
