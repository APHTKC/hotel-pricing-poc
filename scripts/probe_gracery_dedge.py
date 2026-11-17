import asyncio
import json
from datetime import date, timedelta
from urllib.parse import urlencode

from playwright.async_api import async_playwright


PROPERTY_CODE = "twtai31625"
BOOKING_BASE = "https://www.book-secure.com/index.php"
OFFICIAL_URL = "https://tw.gracery.com/taipei/"


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
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            executable_path=(
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            ),
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
        cards = page.locator(
            "#results-items div.fb-results-accommodation[id^='accommodation-']"
        )
        try:
            await cards.first.wait_for(state="visible", timeout=60_000)
        except Exception:
            pass

        rooms = []
        for index in range(await cards.count()):
            card = cards.nth(index)
            rates = card.locator(".fb-results-rate")
            rooms.append(
                {
                    "code": (await card.get_attribute("id") or "").removeprefix(
                        "accommodation-"
                    ),
                    "name": (
                        await card.locator(".fb-results-acc-title").first.inner_text()
                    ).strip(),
                    "rates": [
                        {
                            "id": await rates.nth(rate_index).get_attribute("id"),
                            "price": await rates.nth(rate_index)
                            .locator(".fb-price")
                            .first.inner_text(),
                            "features": await rates.nth(rate_index)
                            .locator(".fb-results-ratekey")
                            .all_inner_texts(),
                            "preview": " ".join(
                                (await rates.nth(rate_index).inner_text()).split()
                            )[:1200],
                        }
                        for rate_index in range(await rates.count())
                    ],
                }
            )

        report = {
            "hotel_id": "hotel_gracery_taipei",
            "source": "official_dedge_book_secure",
            "requested_url": url,
            "http_status": response.status if response else None,
            "final_url": page.url,
            "title": await page.title(),
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "room_count": len(rooms),
            "rate_count": sum(len(room["rates"]) for room in rooms),
            "rooms": rooms,
            "body_preview": " ".join(
                ((await page.locator("body").text_content()) or "").split()
            )[:3000],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
