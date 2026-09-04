import hashlib
import logging
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from playwright.async_api import Locator, Page, async_playwright

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.base import HotelScraper


CAPELLA_TAIPEI_HOTEL_ID = "47696"
CAPELLA_CHAIN_ID = "21430"
SYNXIS_URL = "https://be.synxis.com/"
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
logger = logging.getLogger(__name__)


def parse_money(text: str) -> Decimal:
    normalized = re.sub(r"[^0-9.-]", "", text)
    if not normalized:
        raise ValueError(f"Could not parse money value: {text!r}")
    return Decimal(normalized)


def parse_room_size(text: str) -> Decimal | None:
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return Decimal(match.group(1)) if match else None


def breakfast_included(features: list[str]) -> bool | None:
    joined = " ".join(features).lower()
    if any(term in joined for term in ("不含早餐", "breakfast not included", "room only")):
        return False
    if any(term in joined for term in ("含早餐", "breakfast included", "with breakfast")):
        return True
    return None


def cancellation_text(features: list[str]) -> str | None:
    terms = ("取消", "cancell", "不可退款", "non-refundable", "non refundable")
    return next((item.strip() for item in features if any(term in item.lower() for term in terms)), None)


class CapellaScraper(HotelScraper):
    """Live adapter for Capella Taipei's official SynXis booking page.

    Verified against Hotel=47696 / Chain=21430 on 2026-08-28. The search
    result exposes tax-inclusive totals but not a reliable tax/service split,
    so component fields deliberately remain null.
    """

    def __init__(self, timeout_ms: int = 45_000):
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None

    def booking_url(self, check_in: date, check_out: date, adults: int) -> str:
        query = urlencode({
            "Hotel": CAPELLA_TAIPEI_HOTEL_ID, "Chain": CAPELLA_CHAIN_ID,
            "arrive": check_in.isoformat(), "depart": check_out.isoformat(),
            "adult": adults, "child": 0, "rooms": 1, "currency": "TWD",
            "locale": "zh-TW", "level": "hotel", "productcurrency": "TWD",
        })
        return f"{SYNXIS_URL}?{query}"

    async def _page(self) -> Page:
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        page = await self._browser.new_page(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=CHROME_USER_AGENT,
            viewport={"width": 1440, "height": 1000},
            extra_http_headers={"Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"},
        )
        page.set_default_timeout(self.timeout_ms)
        return page

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id != "capella_taipei":
            raise ValueError("CapellaScraper currently supports only Capella Taipei")
        source_url = self.booking_url(check_in, check_out, adults)
        queried_at = datetime.now(UTC)
        page = await self._page()
        response = None
        try:
            response = await page.goto(
                source_url, wait_until="domcontentloaded", timeout=self.timeout_ms
            )
            await page.locator("h1").filter(has_text=re.compile("選取房間|Select a Room", re.I)).wait_for()
            await page.locator("div[id^='auto-category-card-']").first.wait_for()
            return await self._collect_categories(
                page, hotel, check_in, check_out, adults, queried_at, source_url
            )
        except Exception:
            title = await page.title()
            raw_body = await page.locator("body").text_content(timeout=3_000) or ""
            body_text = " ".join(raw_body.split())[:1200]
            logger.error(
                "Capella diagnostic: status=%s final_url=%s title=%r body=%r",
                response.status if response else None,
                page.url,
                title,
                body_text,
            )
            raise
        finally:
            await page.close()

    async def _collect_categories(
        self, page: Page, hotel: Hotel, check_in: date, check_out: date,
        adults: int, queried_at: datetime, source_url: str,
    ) -> list[RateObservation]:
        category_ids = await page.locator("div[id^='auto-category-card-']").evaluate_all(
            "els => els.map(el => el.id)"
        )
        observations: list[RateObservation] = []
        for category_id in category_ids:
            category = page.locator(f"#{category_id}")
            variant_count = await category.locator("button[data-testid='button-pill']").count()
            for variant_index in range(max(1, variant_count)):
                category = page.locator(f"#{category_id}")
                if variant_count:
                    button = category.locator("button[data-testid='button-pill']").nth(variant_index)
                    if (await button.get_attribute("aria-pressed")) != "true":
                        await button.click()
                        await page.wait_for_timeout(400)
                    room_name = (await button.inner_text()).strip()
                    room_code = self._room_code(await button.get_attribute("datatest"), category_id)
                else:
                    room_name = (await category.locator("h2").first.inner_text()).strip()
                    room_code = category_id.replace("auto-category-card-", "CATEGORY-")
                observations.extend(await self._collect_rates(
                    page.locator(f"#{category_id}"), hotel, room_code, room_name,
                    check_in, check_out, adults, queried_at, source_url
                ))
        return observations

    async def _collect_rates(
        self, category: Locator, hotel: Hotel, room_code: str, room_name: str,
        check_in: date, check_out: date, adults: int, queried_at: datetime,
        source_url: str,
    ) -> list[RateObservation]:
        size_locator = category.locator("[class*='guests-and-roomsize_size']").first
        room_size = parse_room_size(await size_locator.inner_text()) if await size_locator.count() else None
        rate_cards = category.locator("div[data-rate-code]")
        results: list[RateObservation] = []
        for index in range(await rate_cards.count()):
            rate = rate_cards.nth(index)
            if not await rate.is_visible():
                continue
            rate_code = await rate.get_attribute("data-rate-code")
            plan_name = (await rate.locator("h3").first.inner_text()).strip()
            features = [t.strip() for t in await rate.locator("li").all_inner_texts() if t.strip()]
            total_price = parse_money(await rate.locator("[data-testid='regular-price']").first.inner_text())
            key = ":".join((hotel.id, check_in.isoformat(), room_code, rate_code or plan_name, queried_at.isoformat()))
            results.append(RateObservation(
                observation_id=hashlib.sha256(key.encode()).hexdigest()[:24],
                queried_at=queried_at, check_in=check_in, check_out=check_out,
                lead_days=(check_in - queried_at.date()).days,
                nights=(check_out - check_in).days, adults=adults,
                hotel_id=hotel.id, hotel_name=hotel.name, city=hotel.city,
                room_type_code=room_code, room_type_name=room_name,
                room_size_sqm=room_size, rate_plan_code=rate_code,
                rate_plan_name=plan_name,
                breakfast_included=breakfast_included(features),
                cancellation_policy=cancellation_text(features),
                price_before_tax=None, service_charge=None, tax=None,
                total_price=total_price, currency="TWD", source_url=source_url,
                status=ScrapeStatus.LIVE, fx_rate_to_twd=Decimal("1"),
            ))
        return results

    @staticmethod
    def _room_code(datatest: str | None, fallback: str) -> str:
        return datatest.rsplit("_", 1)[-1] if datatest and "_" in datatest else fallback

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
