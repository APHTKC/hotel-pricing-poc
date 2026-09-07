import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import (
    CapellaScraper,
    breakfast_included,
    parse_money,
    parse_room_size,
)


OKURA_TAIPEI_HOTEL_ID = "56124"
OKURA_CHAIN_ID = "9542"
OKURA_SYNXIS_URL = "https://rsv.okura.com/"
OKURA_SERVICE_RATE = Decimal("0.10")
OKURA_TAX_RATE = Decimal("0.05")


def is_comparable_public_plan(plan_name: str) -> bool:
    """Keep public consumer offers while excluding member, rack and mileage rates."""
    normalized = plan_name.casefold()
    excluded = ("member price", "rack rate", "airlines ffp")
    return not any(term in normalized for term in excluded)


class OkuraScraper(CapellaScraper):
    """Live candidate adapter for the official Okura SynXis booking page.

    The Okura site identifies The Okura Prestige Taipei as hotel 56124 in
    chain 9542. Its official room pages state that displayed room prices are
    subject to a combined 15% tax and service charge; the booking engine also
    labels its prices as excluding taxes and fees.
    """

    supported_hotel_id = "okura_prestige_taipei"
    diagnostic_name = "Okura"

    def booking_url(self, check_in: date, check_out: date, adults: int) -> str:
        query = urlencode({
            "Hotel": OKURA_TAIPEI_HOTEL_ID,
            "Chain": OKURA_CHAIN_ID,
            "arrive": check_in.isoformat(),
            "depart": check_out.isoformat(),
            "adult": adults,
            "child": 0,
            "rooms": 1,
            "currency": "TWD",
            "productcurrency": "TWD",
            "locale": "en-US",
            "level": "hotel",
            "config": "EXCLTAX",
            "theme": "OHSBE",
            "themecode": "OHSBE",
            "src": "ohm",
        })
        return f"{OKURA_SYNXIS_URL}?{query}"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id != self.supported_hotel_id:
            raise ValueError(
                f"OkuraScraper currently supports only {self.supported_hotel_id}"
            )

        source_url = self.booking_url(check_in, check_out, adults)
        queried_at = datetime.now(UTC)
        page = await self._page()
        try:
            await page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await page.locator("h1").filter(has_text="Select a Room").wait_for()
            await page.locator("div[id^='auto-parent-card-']").first.wait_for()
            await self._dismiss_cookie_banner(page)
            return await self._collect_rate_plans(
                page, hotel, check_in, check_out, adults, queried_at, source_url
            )
        finally:
            await page.close()

    async def _dismiss_cookie_banner(self, page: Page) -> None:
        button = page.locator("#onetrust-reject-all-handler")
        try:
            await button.wait_for(state="visible", timeout=5_000)
            await button.click(force=True)
            await page.locator("#onetrust-consent-sdk").wait_for(
                state="hidden", timeout=5_000
            )
        except PlaywrightTimeoutError:
            # Returning visitors may not receive the OneTrust banner.
            return

    async def _collect_rate_plans(
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
            rate_code = await parent.locator("[data-rate-code]").first.get_attribute(
                "data-rate-code"
            )
            plan_name = (await parent.locator("h2").first.inner_text()).strip()
            if not is_comparable_public_plan(plan_name):
                continue
            description_locator = parent.locator(".thumb-cards_rateShortDesc").first
            description = (
                (await description_locator.inner_text()).strip()
                if await description_locator.count()
                else ""
            )
            cancellation = await self._read_cancellation_policy(page, parent)

            parent = page.locator(f"#{parent_id}")
            expand = parent.get_by_role("button", name=re.compile("View More Rooms", re.I))
            if await expand.count() and await expand.first.is_visible():
                await expand.first.click(force=True)
                await page.wait_for_timeout(250)

            rooms = page.locator(f"#{parent_id} .thumb-cards_room[data-room-code]")
            for index in range(await rooms.count()):
                room = rooms.nth(index)
                if not await room.is_visible():
                    continue
                room_code = await room.get_attribute("data-room-code")
                room_name = (await room.locator("h3 a").first.inner_text()).strip()
                size_text = await room.locator(".guests-and-roomsize_size").first.inner_text()
                room_size = parse_room_size(size_text)
                features = [
                    text.strip()
                    for text in await room.locator(
                        ".product-icons_iconList li, .thumb-cards_roomShortDesc li"
                    ).all_inner_texts()
                    if text.strip()
                ]
                displayed_price = parse_money(
                    await room.locator("[data-testid='regular-price']").first.inner_text()
                )
                service_charge = displayed_price * OKURA_SERVICE_RATE
                tax = displayed_price * OKURA_TAX_RATE
                total_price = displayed_price + service_charge + tax
                key = ":".join(
                    (
                        hotel.id,
                        check_in.isoformat(),
                        room_code or room_name,
                        rate_code or plan_name,
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
                        rate_plan_code=rate_code,
                        rate_plan_name=plan_name,
                        breakfast_included=breakfast_included([description, *features]),
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

    async def _read_cancellation_policy(self, page: Page, parent) -> str | None:
        details = parent.locator(".thumb-cards_detailsLink a").first
        if not await details.count():
            return None
        await details.click(force=True)
        modal = page.locator("#outsideModalBody-overlay")
        await modal.wait_for()
        text = await modal.inner_text()
        match = re.search(r"Cancel Policy\s*(.+)$", text, re.I | re.S)
        cancellation = " ".join(match.group(1).split()) if match else None
        await modal.get_by_role("button", name="Close").click(force=True)
        await modal.wait_for(state="hidden")
        return cancellation
