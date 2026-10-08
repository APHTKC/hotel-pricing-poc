import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import Hotel, RateObservation, ScrapeStatus, TaxInclusion
from scrapers.adapters.capella import CapellaScraper, parse_money


PROPERTIES = {
    "royal_nikko_taipei": {
        "booking_url": "https://tlathena.ec-hotel.net/webhotel-v4/0839/index",
        "property_id": "0839",
    },
    "hotel_royal_hsinchu": {
        "booking_url": "https://tlathena.ec-hotel.net/webhotel-v4/0232/index",
        "property_id": "0232",
    },
    "hotel_royal_chihpen": {
        "booking_url": "https://tlathena.ec-hotel.net/webhotel-v4/0162/index",
        "property_id": "0162",
    },
}

ROOM_SIZE_FALLBACKS = {
    "hotel_royal_hsinchu": {
        "雅緻客房": Decimal("36"),
        "豪華客房": Decimal("39"),
        "豪華家庭房": Decimal("43"),
        "豪華家庭客房": Decimal("43"),
        "行政客房": Decimal("43"),
        "景緻客房": Decimal("40"),
        "老爺套房": Decimal("56"),
    },
}


def parse_room_size(text: str) -> Decimal | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:平方公尺|平方米|m[²2])", text, re.I)
    return Decimal(match.group(1)) if match else None


def room_size_for(hotel_id: str, room_name: str, text: str) -> Decimal | None:
    return parse_room_size(text) or ROOM_SIZE_FALLBACKS.get(hotel_id, {}).get(room_name)


def parse_breakfast(plan_name: str) -> bool | None:
    normalized = plan_name.replace(" ", "")
    if any(term in normalized for term in ("無早餐", "不含早餐", "不含早")):
        return False
    if any(term in normalized for term in ("早餐", "含早", "一泊一食")):
        return True
    return None


def include_rate_plan(hotel_id: str, plan_name: str) -> bool:
    """Keep repeatable public offers and exclude voucher-only products.

    Hsinchu publishes a long list of travel-fair vouchers beside its ordinary
    public room offers.  Those vouchers require a previously purchased serial
    number, so they are not comparable public room rates.
    """

    if hotel_id == "hotel_royal_hsinchu":
        normalized = plan_name.replace(" ", "")
        return normalized.startswith("國人住房專案")
    return True


async def select_calendar_date(page, value: date) -> None:
    for _ in range(8):
        panels = page.locator(".el-date-range-picker__content")
        for index in range(await panels.count()):
            panel = panels.nth(index)
            heading = " ".join((await panel.inner_text()).split())
            if not heading.startswith(f"{value.year} 年 {value.month} 月"):
                continue
            day = panel.locator("td.available").filter(
                has_text=re.compile(rf"^\s*{value.day}\s*$")
            )
            await day.click()
            return
        await page.locator(
            ".el-picker-panel__icon-btn.el-icon-arrow-right"
        ).last.click()
        await page.wait_for_timeout(100)
    raise RuntimeError(f"Could not select {value.isoformat()} in EC-hotel v4 calendar")


async def dismiss_startup_overlays(page) -> None:
    loading = page.locator(".el-loading-mask")
    if await loading.count():
        await loading.first.wait_for(state="hidden", timeout=45_000)
    popup = page.locator(".el-dialog__wrapper.athPopup:visible")
    try:
        await popup.first.wait_for(state="visible", timeout=12_000)
        await popup.locator(".el-dialog__headerbtn").first.click(force=True)
        await popup.first.wait_for(state="hidden", timeout=10_000)
    except Exception:
        # Campaign announcements are optional and may disappear between runs.
        pass


class ECHotelV4Scraper(CapellaScraper):
    """Shared adapter for the public EC-hotel v4 booking engine."""

    diagnostic_name = "EC-hotel v4"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id not in PROPERTIES:
            raise ValueError(f"ECHotelV4Scraper does not support hotel {hotel.id}")
        queried_at = datetime.now(UTC)
        page = await self._page()
        try:
            await page.goto(
                PROPERTIES[hotel.id]["booking_url"],
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            await dismiss_startup_overlays(page)
            await page.locator(".athDateRange .el-date-editor").click(force=True)
            await select_calendar_date(page, check_in)
            await select_calendar_date(page, check_out)
            await page.locator("#athSearch").click()
            # Some properties retain the project-oriented tab after a dated
            # search. Its mobile room rows exist in the DOM but stay hidden,
            # which previously looked like an empty result in headless runs.
            # Select the room-oriented tab explicitly before waiting.
            await page.locator('a[href="#athTabpage__room"]').click(force=True)
            await page.locator(
                "#athTabpage__cntainRoom > .row.mb-40 .athTable__row"
            ).first.wait_for(timeout=self.timeout_ms)
            expected = [check_in.isoformat(), check_out.isoformat()]
            await page.wait_for_function(
                "expected => Array.from(document.querySelectorAll('.athDateRange input')).map(el => el.value).join('|') === expected.join('|')",
                arg=expected,
            )
            observations = await self._collect(
                page, hotel, check_in, check_out, adults, queried_at, page.url
            )
            if not observations:
                raise RuntimeError(f"EC-hotel v4 returned no comparable public rates for {hotel.id}")
            return observations
        finally:
            await page.close()

    async def _collect(
        self, page, hotel, check_in, check_out, adults, queried_at, source_url
    ) -> list[RateObservation]:
        observations: list[RateObservation] = []
        rooms = page.locator("#athTabpage__cntainRoom > .row.mb-40")
        for room_index in range(await rooms.count()):
            room = rooms.nth(room_index)
            room_code = await room.locator(".roomMainPicture").first.get_attribute("id")
            room_name = (await room.locator(".athRoom__title").first.inner_text()).strip()
            room_text = await room.inner_text()
            room_size = room_size_for(hotel.id, room_name, room_text)
            rates = room.locator(".col-xs-12.d-mdx-none .athTable__row")
            for rate_index in range(await rates.count()):
                rate = rates.nth(rate_index)
                plan_name = (await rate.locator(".athTable__product").first.inner_text()).strip()
                if not include_rate_plan(hotel.id, plan_name):
                    continue
                total = parse_money(await rate.locator(".athSale-price").first.inner_text())
                key = ":".join(
                    (
                        hotel.id,
                        check_in.isoformat(),
                        room_code or room_name,
                        plan_name,
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
                        rate_plan_code=None,
                        rate_plan_name=plan_name,
                        breakfast_included=parse_breakfast(plan_name),
                        cancellation_policy=None,
                        price_before_tax=None,
                        service_charge=None,
                        tax=None,
                        tax_inclusion=TaxInclusion.INCLUDED,
                        total_price=total,
                        currency="TWD",
                        source_property_id=PROPERTIES[hotel.id]["property_id"],
                        source_url=source_url,
                        status=ScrapeStatus.LIVE,
                        fx_rate_to_twd=Decimal("1"),
                    )
                )
        return observations
