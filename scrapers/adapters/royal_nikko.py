import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, parse_money


BOOKING_URL = "https://tlathena.ec-hotel.net/webhotel-v4/0839/index"


def parse_room_size(text: str) -> Decimal | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*平方公尺", text)
    return Decimal(match.group(1)) if match else None


def parse_breakfast(plan_name: str) -> bool | None:
    if "無早餐" in plan_name or "不含早餐" in plan_name:
        return False
    if any(term in plan_name for term in ("早餐", "一泊一食", "含2早")):
        return True
    return None


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
    raise RuntimeError(f"Could not select {value.isoformat()} in Royal-Nikko calendar")


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
        pass


class RoyalNikkoScraper(CapellaScraper):
    supported_hotel_id = "royal_nikko_taipei"
    diagnostic_name = "Royal-Nikko Taipei"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id != self.supported_hotel_id:
            raise ValueError(
                f"RoyalNikkoScraper currently supports only {self.supported_hotel_id}"
            )
        queried_at = datetime.now(UTC)
        page = await self._page()
        try:
            await page.goto(
                BOOKING_URL, wait_until="domcontentloaded", timeout=self.timeout_ms
            )
            await dismiss_startup_overlays(page)
            await page.locator(".athDateRange .el-date-editor").click(force=True)
            await select_calendar_date(page, check_in)
            await select_calendar_date(page, check_out)
            await page.locator("#athSearch").click()
            await page.locator(
                "#athTabpage__cntainRoom > .row.mb-40 .athTable__row"
            ).first.wait_for(timeout=self.timeout_ms)
            expected = [check_in.isoformat(), check_out.isoformat()]
            await page.wait_for_function(
                "expected => Array.from(document.querySelectorAll('.athDateRange input')).map(el => el.value).join('|') === expected.join('|')",
                arg=expected,
            )
            return await self._collect(
                page, hotel, check_in, check_out, adults, queried_at, page.url
            )
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
            room_size = parse_room_size(await room.inner_text())
            rates = room.locator(".col-xs-12.d-mdx-none .athTable__row")
            for rate_index in range(await rates.count()):
                rate = rates.nth(rate_index)
                plan_name = (
                    await rate.locator(".athTable__product").first.inner_text()
                ).strip()
                total = parse_money(
                    await rate.locator(".athSale-price").first.inner_text()
                )
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
                        total_price=total,
                        currency="TWD",
                        source_url=source_url,
                        status=ScrapeStatus.LIVE,
                        fx_rate_to_twd=Decimal("1"),
                    )
                )
        return observations
