import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from playwright.async_api import async_playwright


PROPERTY_CODE = "twtai28740"
BOOKING_BASE = "https://www.book-secure.com/index.php"
OFFICIAL_URL = "https://www.gvrb.com.tw/"


def booking_url(check_in: date, check_out: date) -> str:
    return f"{BOOKING_BASE}?{urlencode({
        's': 'results',
        'property': PROPERTY_CODE,
        'arrival': check_in.isoformat(),
        'departure': check_out.isoformat(),
        'adults1': 2,
        'children1': 0,
        'locale': 'zh_Hant_HK',
        'currency': 'TWD',
        'showPromotions': 1,
    })}"


async def main() -> None:
    check_in = date.today() + timedelta(days=30)
    check_out = check_in + timedelta(days=1)
    url = booking_url(check_in, check_out)
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
        await page.goto(OFFICIAL_URL, wait_until="domcontentloaded", timeout=90_000)
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=90_000,
            referer=OFFICIAL_URL,
        )
        room_cards = page.locator(
            "#results-items div.fb-results-accommodation[id^='accommodation-']"
        )
        try:
            await room_cards.first.wait_for(state="visible", timeout=60_000)
        except Exception:
            report = {
                "requested_url": url,
                "http_status": response.status if response else None,
                "final_url": page.url,
                "title": await page.title(),
                "body": " ".join(
                    ((await page.locator("body").text_content()) or "").split()
                )[:5_000],
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))
            (artifact_dir / "grand-view-beitou-probe.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            await page.screenshot(
                path=artifact_dir / "grand-view-beitou-probe.png", full_page=True
            )
            raise

        rooms = []
        rate_count = 0
        for index in range(await room_cards.count()):
            card = room_cards.nth(index)
            rates = card.locator(".fb-results-rate")
            current_rate_count = await rates.count()
            rate_count += current_rate_count
            rooms.append(
                {
                    "code": (await card.get_attribute("id") or "").removeprefix(
                        "accommodation-"
                    ),
                    "name": (
                        await card.locator(".fb-results-acc-title").first.inner_text()
                    ).strip(),
                    "rate_count": current_rate_count,
                    "prices": await rates.locator(".fb-price").all_inner_texts(),
                    "preview": " ".join((await card.inner_text()).split())[:3_000],
                }
            )

        report = {
            "requested_url": url,
            "http_status": response.status if response else None,
            "final_url": page.url,
            "title": await page.title(),
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "room_count": len(rooms),
            "rate_count": rate_count,
            "rooms": rooms,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        (artifact_dir / "grand-view-beitou-probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await page.screenshot(
            path=artifact_dir / "grand-view-beitou-probe.png", full_page=True
        )
        await browser.close()

        if response is None or response.status >= 400 or not rooms or not rate_count:
            raise RuntimeError("Grand View Resort Beitou did not expose public rates")


if __name__ == "__main__":
    asyncio.run(main())
