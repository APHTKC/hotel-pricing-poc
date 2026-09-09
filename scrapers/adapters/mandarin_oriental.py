import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from playwright.async_api import Page

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import (
    CapellaScraper,
    breakfast_included,
    parse_money,
    parse_room_size,
)


MO_TAIPEI_HOTEL_ID = "59555"
MO_CHAIN_ID = "507"
MO_SYNXIS_URL = "https://be.synxis.com/"
MO_SERVICE_RATE = Decimal("0.10")
MO_VAT_ON_BASE_AND_SERVICE = Decimal("0.055")


def is_comparable_public_plan(plan_name: str) -> bool:
    normalized = plan_name.casefold()
    excluded = ("fans of m.o.", "member", "travel advisor", "rack rate")
    return not any(term in normalized for term in excluded)


class MandarinOrientalScraper(CapellaScraper):
    """Live adapter for Mandarin Oriental, Taipei's official SynXis page."""

    supported_hotel_id = "mo_taipei"
    diagnostic_name = "Mandarin Oriental Taipei"

    def booking_url(self, check_in: date, check_out: date, adults: int) -> str:
        query = urlencode(
            {
                "Hotel": MO_TAIPEI_HOTEL_ID,
                "Chain": MO_CHAIN_ID,
                "arrive": check_in.isoformat(),
                "depart": check_out.isoformat(),
                "adult": adults,
                "child": 0,
                "rooms": 1,
                "currency": "TWD",
                "productcurrency": "TWD",
                "locale": "en-US",
                "level": "hotel",
            }
        )
        return f"{MO_SYNXIS_URL}?{query}"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id != self.supported_hotel_id:
            raise ValueError(
                f"MandarinOrientalScraper currently supports only {self.supported_hotel_id}"
            )

        source_url = self.booking_url(check_in, check_out, adults)
        queried_at = datetime.now(UTC)
        page = await self._page()
        try:
            await page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await page.locator("h1").filter(has_text="Select a Room").wait_for()
            await page.locator("div[id^='auto-parent-card-']").first.wait_for()
            return await self._collect_rooms(
                page, hotel, check_in, check_out, adults, queried_at, source_url
            )
        finally:
            await page.close()

    async def _collect_rooms(
        self,
        page: Page,
        hotel: Hotel,
        check_in: date,
        check_out: date,
        adults: int,
        queried_at: datetime,
        source_url: str,
    ) -> list[RateObservation]:
        parent_ids = await page.locator("div[id^='auto-parent-card-']").evaluate_all(
            "els => els.map(el => el.id)"
        )
        observations: list[RateObservation] = []
        for parent_id in parent_ids:
            parent = page.locator(f"#{parent_id}")
            room_name = (await parent.locator("h2").first.inner_text()).strip()
            room_code_locator = parent.locator("[data-room-code]").first
            room_code = (
                await room_code_locator.get_attribute("data-room-code")
                if await room_code_locator.count()
                else None
            )
            if not room_code:
                room_code = parent_id.replace("auto-parent-card-", "MO-")
            size_locator = parent.locator("[class*='guests-and-roomsize_size']").first
            room_size = (
                parse_room_size(await size_locator.inner_text())
                if await size_locator.count()
                else None
            )

            expand = parent.get_by_role("button", name=re.compile("View More Rates", re.I))
            if await expand.count() and await expand.first.is_visible():
                await expand.first.click(force=True)
                await page.wait_for_timeout(250)

            rate_ids = await page.locator(
                f"#{parent_id} div[id^='auto-child-card-']"
            ).evaluate_all("els => els.map(el => el.id)")
            for rate_id in rate_ids:
                rate = page.locator(f"#{rate_id}")
                if not await rate.is_visible():
                    continue
                rate_code = await rate.get_attribute("data-rate-code")
                plan_name = (await rate.locator("h3").first.inner_text()).strip()
                if not is_comparable_public_plan(plan_name):
                    continue
                description_locator = rate.locator(".thumb-cards_rateShortDesc").first
                description = (
                    (await description_locator.inner_text()).strip()
                    if await description_locator.count()
                    else ""
                )
                displayed_price = parse_money(
                    await rate.locator("[data-testid='regular-price']").first.inner_text()
                )
                cancellation = await self._read_cancellation_policy(page, rate)
                breakfast = breakfast_included([plan_name, description])
                if breakfast is None and any(
                    term in plan_name.casefold()
                    for term in ("best available rate", "plan ahead")
                ):
                    breakfast = False

                service_charge = displayed_price * MO_SERVICE_RATE
                tax = displayed_price * MO_VAT_ON_BASE_AND_SERVICE
                total_price = displayed_price + service_charge + tax
                key = ":".join(
                    (
                        hotel.id,
                        check_in.isoformat(),
                        room_code,
                        rate_code or rate_id,
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
                        room_type_code=room_code,
                        room_type_name=room_name,
                        room_size_sqm=room_size,
                        rate_plan_code=rate_code or rate_id,
                        rate_plan_name=plan_name,
                        breakfast_included=breakfast,
                        cancellation_policy=cancellation,
                        price_before_tax=displayed_price,
                        service_charge=service_charge,
                        tax=tax,
                        total_price=total_price,
                        currency="TWD",
                        source_url=source_url,
                        status=ScrapeStatus.LIVE,
                        fx_rate_to_twd=Decimal("1"),
                    )
                )
        return observations

    async def _read_cancellation_policy(self, page: Page, rate) -> str | None:
        details = rate.locator("h3 a").first
        if not await details.count():
            return None
        await details.click(force=True)
        modal = page.locator("#outsideModalBody-overlay")
        await modal.wait_for()
        text = await modal.inner_text()
        match = re.search(r"Cancel Policy\s*(.+?)(?:NT\$|$)", text, re.I | re.S)
        cancellation = " ".join(match.group(1).split()) if match else None
        await modal.get_by_role("button", name="Close").click(force=True)
        await modal.wait_for(state="hidden")
        return cancellation
