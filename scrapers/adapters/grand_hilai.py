import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, parse_money


BOOKING_URL = "https://tlathena.ec-hotel.net/webhotel-v5/1003"
PING_TO_SQM = Decimal("3.305785")


def ping_to_sqm(text: str) -> Decimal | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*坪", text)
    if not match:
        return None
    return (Decimal(match.group(1)) * PING_TO_SQM).quantize(Decimal("0.1"))


async def select_calendar_date(page, value: date) -> None:
    for _ in range(5):
        panels = page.locator(".el-date-range-picker__content")
        for index in range(await panels.count()):
            panel = panels.nth(index)
            heading = " ".join(
                (await panel.locator(".el-date-range-picker__header").inner_text()).split()
            )
            if heading != f"{value.year} 年 {value.month} 月":
                continue
            day = panel.locator("td.available").filter(
                has_text=re.compile(rf"^\s*{value.day}\s*$")
            )
            await day.evaluate("el => el.click()")
            return
        await page.locator(
            ".el-picker-panel__icon-btn.el-icon-arrow-right"
        ).last.evaluate("el => el.click()")
        await page.wait_for_timeout(100)
    raise RuntimeError(f"Could not select {value.isoformat()} in Grand Hi-Lai calendar")


class GrandHiLaiScraper(CapellaScraper):
    supported_hotel_id = "grand_hilai_taipei"
    diagnostic_name = "Grand Hi-Lai Taipei"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id != self.supported_hotel_id:
            raise ValueError(
                f"GrandHiLaiScraper currently supports only {self.supported_hotel_id}"
            )
        queried_at = datetime.now(UTC)
        page = await self._page()
        try:
            await page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await page.get_by_placeholder("入住日").click()
            await select_calendar_date(page, check_in)
            await select_calendar_date(page, check_out)
            await page.get_by_role("button", name="搜尋", exact=True).evaluate(
                "el => el.click()"
            )
            expected = [check_in.strftime("%Y/%m/%d"), check_out.strftime("%Y/%m/%d")]
            await page.wait_for_function(
                "expected => Array.from(document.querySelectorAll('input[placeholder=入住日], input[placeholder=退房日]')).map(el => el.value).join('|') === expected.join('|')",
                arg=expected,
            )
            await page.locator(".product .room-size").first.wait_for()
            await page.wait_for_timeout(700)
            return await self._collect(
                page, hotel, check_in, check_out, adults, queried_at, page.url
            )
        finally:
            await page.close()

    async def _collect(
        self, page, hotel, check_in, check_out, adults, queried_at, source_url
    ) -> list[RateObservation]:
        rooms = page.locator(".product").filter(has=page.locator(".room-size"))
        observations: list[RateObservation] = []
        for index in range(await rooms.count()):
            payload = await rooms.nth(index).evaluate("""el => {
              const wrapper = el.parentElement;
              const detail = wrapper && wrapper.querySelector(':scope > .detail');
              const title = el.querySelector('.descript > .flex .fw-5.fz-30');
              const size = el.querySelector('.room-size span');
              const plans = detail ? Array.from(detail.querySelectorAll(':scope > div > .contain')).map(plan => {
                const name = plan.querySelector('.descript .fw-5.fz-30.pb-30');
                const price = plan.querySelector('.price span');
                return {name: name ? name.textContent.trim() : '', price: price ? price.textContent.trim() : ''};
              }) : [];
              return {name: title ? title.textContent.trim() : '', size: size ? size.textContent.trim() : '', code: detail ? detail.id : '', plans};
            }""")
            if not payload["name"]:
                continue
            for plan in payload["plans"]:
                plan_name = " ".join(plan["name"].split())
                if not plan_name.startswith("一般訂房") or not plan["price"]:
                    continue
                total = parse_money(plan["price"])
                key = ":".join(
                    (hotel.id, check_in.isoformat(), payload["code"], plan_name, queried_at.isoformat())
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
                        room_type_code=payload["code"] or None,
                        room_type_name=payload["name"],
                        room_size_sqm=ping_to_sqm(payload["size"]),
                        rate_plan_code=None,
                        rate_plan_name=plan_name,
                        breakfast_included="含島語早餐" in plan_name and "不含" not in plan_name,
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
