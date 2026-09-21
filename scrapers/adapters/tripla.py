import hashlib
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from playwright.async_api import Locator, Page

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, breakfast_included, parse_money
from scrapers.adapters.gobooking import split_tax_inclusive_total


PROPERTIES = {
    "windsor_taichung": "35107e0b-6d82-4b23-850c-a46c7b9e0e84",
}


def booking_url(hotel_id: str, check_in: date, check_out: date, adults: int = 2) -> str:
    if hotel_id not in PROPERTIES:
        raise ValueError(f"TriplaScraper does not support hotel {hotel_id}")
    query = urlencode(
        {
            "code": PROPERTIES[hotel_id],
            "checkin": check_in.strftime("%Y/%m/%d"),
            "checkout": check_out.strftime("%Y/%m/%d"),
            "type": "rooms",
            "is_day_use": "false",
            "order": "price_low_to_high",
            "is_including_occupied": "false",
            "rooms": json.dumps([{"adults": adults}], separators=(",", ":")),
        }
    )
    return f"https://bw.tripla.ai/booking/result?{query}"


def parse_room_size(text: str) -> Decimal | None:
    match = re.search(r"(?:客房大小|Room size)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*m", text, re.I)
    return Decimal(match.group(1)) if match else None


class TriplaScraper(CapellaScraper):
    """Adapter for public Tripla booking result pages."""

    diagnostic_name = "Tripla"

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
            rooms = page.locator("[data-cy='search-result-room-item']")
            await rooms.first.wait_for(state="visible", timeout=self.timeout_ms)
            await self._load_all_rooms(page, rooms)
            return await self._collect(
                rooms, hotel, check_in, check_out, adults, queried_at, source_url
            )
        except Exception:
            title = await page.title()
            raw_body = await page.locator("body").text_content(timeout=3_000) or ""
            body_text = " ".join(raw_body.split())[:1200]
            raise RuntimeError(
                f"Tripla fetch failed: status={response.status if response else None} "
                f"final_url={page.url} title={title!r} body={body_text!r}"
            )
        finally:
            await page.close()

    async def _load_all_rooms(self, page: Page, rooms: Locator) -> None:
        previous_count = -1
        stable_rounds = 0
        for _ in range(12):
            count = await rooms.count()
            stable_rounds = stable_rounds + 1 if count == previous_count else 0
            if count:
                await rooms.last.scroll_into_view_if_needed()
            await page.wait_for_timeout(300)
            previous_count = count
            if stable_rounds >= 2:
                break
        view_more = page.locator("[data-cy^='room-type-'][data-cy$='-view-more']")
        for index in range(await view_more.count()):
            try:
                await view_more.nth(index).click(timeout=2_000)
            except Exception:
                continue

    async def _collect(
        self,
        rooms: Locator,
        hotel: Hotel,
        check_in: date,
        check_out: date,
        adults: int,
        queried_at: datetime,
        source_url: str,
    ) -> list[RateObservation]:
        observations: list[RateObservation] = []
        for room_index in range(await rooms.count()):
            room = rooms.nth(room_index)
            room_name = (await room.locator(".room-name").first.inner_text()).strip()
            size_text = await room.locator("[data-cy$='-room-size']").first.inner_text()
            room_size = parse_room_size(size_text)
            plans = room.locator("article[data-cy^='room-']")
            for plan_index in range(await plans.count()):
                observation = await self._plan_observation(
                    plans.nth(plan_index), hotel, room_name, room_size,
                    check_in, check_out, adults, queried_at, source_url,
                )
                if observation is not None:
                    observations.append(observation)
        return observations

    async def _plan_observation(
        self,
        plan: Locator,
        hotel: Hotel,
        room_name: str,
        room_size: Decimal | None,
        check_in: date,
        check_out: date,
        adults: int,
        queried_at: datetime,
        source_url: str,
    ) -> RateObservation | None:
        price = plan.locator("strong.price").first
        if not await price.count():
            return None
        total = parse_money(await price.inner_text())
        plan_heading = plan.locator(".room-plan-name").first
        plan_name = (await plan_heading.inner_text()).strip()
        plan_attr = await plan_heading.get_attribute("data-cy")
        rate_code = (
            plan_attr.removeprefix("room-").removesuffix("-plan-name")
            if plan_attr else None
        )
        room_attr = await plan.get_attribute("data-cy")
        room_code = room_attr.removeprefix("room-") if room_attr else None
        text = await plan.inner_text()
        base, service, tax = split_tax_inclusive_total(total)
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
            room_type_code=room_code,
            room_type_name=room_name,
            room_size_sqm=room_size,
            rate_plan_code=rate_code,
            rate_plan_name=plan_name,
            breakfast_included=breakfast_included([plan_name, text]),
            cancellation_policy="Cancellation policy is available on the official booking page",
            price_before_tax=base,
            service_charge=service,
            tax=tax,
            total_price=total,
            currency="TWD",
            source_url=source_url,
            status=ScrapeStatus.LIVE,
            fx_rate_to_twd=Decimal("1"),
        )
