import asyncio
import json
import re
from datetime import date, timedelta
from pathlib import Path

from playwright.async_api import async_playwright


BOOKING_URL = "https://tlathena.ec-hotel.net/webhotel-v5/1003"


async def select_date(page, value: date) -> None:
    for _ in range(5):
        panels = page.locator(".el-date-range-picker__content")
        for index in range(await panels.count()):
            panel = panels.nth(index)
            heading = await panel.locator(".el-date-range-picker__header").inner_text()
            if f"{value.year} 年 {value.month} 月" not in " ".join(heading.split()):
                continue
            day = panel.locator("td.available").filter(has_text=re.compile(rf"^\s*{value.day}\s*$"))
            await day.evaluate("el => el.click()")
            return
        await page.locator(".el-picker-panel__icon-btn.el-icon-arrow-right").last.evaluate(
            "el => el.click()"
        )
        await page.wait_for_timeout(100)
    raise RuntimeError(f"Could not select date {value.isoformat()} from Grand Hi-Lai calendar")


async def main() -> None:
    check_in = date.today() + timedelta(days=30)
    check_out = check_in + timedelta(days=1)
    artifact_dir = Path("artifacts")
    artifact_dir.mkdir(exist_ok=True)
    network = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            locale="zh-TW", timezone_id="Asia/Taipei", viewport={"width": 1440, "height": 1100}
        )
        page = await context.new_page()
        page.on(
            "response",
            lambda response: network.append(
                {"status": response.status, "url": response.url}
            ) if "ec-hotel.net" in response.url else None,
        )
        response = await page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=90_000)
        await page.get_by_placeholder("入住日").click()
        await select_date(page, check_in)
        await select_date(page, check_out)
        await page.get_by_role("button", name="搜尋", exact=True).evaluate("el => el.click()")
        await page.wait_for_timeout(3_000)

        body = "\n".join(line.strip() for line in (await page.locator("body").inner_text()).splitlines() if line.strip())
        public_plans = re.findall(r"一般訂房[^\n]*", body)
        prices = re.findall(r"NT\$\s*([\d,]+)", body)
        report = {
            "requested_url": BOOKING_URL,
            "http_status": response.status if response else None,
            "final_url": page.url,
            "title": await page.title(),
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "date_values": await page.locator('input[placeholder="入住日"], input[placeholder="退房日"]').evaluate_all(
                "els => els.map(el => el.value)"
            ),
            "public_plans": public_plans,
            "price_count": len(prices),
            "prices": prices[:40],
            "network": network[-80:],
            "body_preview": body[:20_000],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        (artifact_dir / "grand-hilai-taipei-probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await page.screenshot(path=artifact_dir / "grand-hilai-taipei-probe.png", full_page=True)
        await browser.close()

        expected_dates = [check_in.strftime("%Y/%m/%d"), check_out.strftime("%Y/%m/%d")]
        if not public_plans or not prices or report["date_values"] != expected_dates:
            raise RuntimeError("Grand Hi-Lai Taipei did not expose dated public rates")


if __name__ == "__main__":
    asyncio.run(main())
