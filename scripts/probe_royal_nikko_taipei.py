import asyncio
import json
import re
from datetime import date, timedelta
from pathlib import Path

from playwright.async_api import async_playwright


BOOKING_URL = "https://tlathena.ec-hotel.net/webhotel-v4/0839/index"


async def select_date(page, value: date) -> None:
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
        # The announcement is campaign-controlled and is not always present.
        pass


async def main() -> None:
    check_in = date.today() + timedelta(days=30)
    check_out = check_in + timedelta(days=1)
    artifact_dir = Path("artifacts")
    artifact_dir.mkdir(exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            viewport={"width": 1440, "height": 1100},
        )
        page = await context.new_page()
        response = await page.goto(
            BOOKING_URL, wait_until="domcontentloaded", timeout=90_000
        )

        await dismiss_startup_overlays(page)

        await page.locator(".athDateRange .el-date-editor").click(force=True)
        await select_date(page, check_in)
        await select_date(page, check_out)
        await page.locator("#athSearch").click()
        await page.locator(
            "#athTabpage__cntainRoom > .row.mb-40 .athTable__row"
        ).first.wait_for(timeout=60_000)

        date_values = await page.locator(".athDateRange input").evaluate_all(
            "els => els.map(el => el.value)"
        )
        room_cards = page.locator("#athTabpage__cntainRoom > .row.mb-40")
        rooms = []
        rate_count = 0
        for index in range(await room_cards.count()):
            card = room_cards.nth(index)
            text = " ".join((await card.inner_text()).split())
            rates = card.locator(
                ".col-xs-12.d-mdx-none .athTable__row"
            )
            current_rate_count = await rates.count()
            rate_count += current_rate_count
            size_match = re.search(r"(\d+(?:\.\d+)?)\s*平方公尺", text)
            rooms.append(
                {
                    "code": await card.locator(".roomMainPicture").first.get_attribute("id"),
                    "name": (await card.locator(".athRoom__title").first.inner_text()).strip(),
                    "size_sqm": float(size_match.group(1)) if size_match else None,
                    "rate_count": current_rate_count,
                    "preview": text[:3_000],
                }
            )

        report = {
            "requested_url": BOOKING_URL,
            "http_status": response.status if response else None,
            "final_url": page.url,
            "title": await page.title(),
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "date_values": date_values,
            "room_count": len(rooms),
            "rate_count": rate_count,
            "rooms": rooms,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        (artifact_dir / "royal-nikko-taipei-probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await page.screenshot(
            path=artifact_dir / "royal-nikko-taipei-probe.png", full_page=True
        )
        await browser.close()

        expected = [check_in.isoformat(), check_out.isoformat()]
        if date_values != expected or not rooms or not rate_count:
            raise RuntimeError("Royal-Nikko Taipei did not expose dated public rates")


if __name__ == "__main__":
    asyncio.run(main())
