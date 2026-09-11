import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from playwright.async_api import async_playwright


HOTEL_CODE = "TSAUPUP"
BASE_URL = "https://www.hilton.com/en/book/reservation/rooms/"


def booking_url(check_in: date, check_out: date, adults: int = 2) -> str:
    query = urlencode(
        {
            "ctyhocn": HOTEL_CODE,
            "arrivalDate": check_in.isoformat(),
            "departureDate": check_out.isoformat(),
            "room1NumAdults": adults,
            "room1NumChildren": 0,
        }
    )
    return f"{BASE_URL}?{query}"


async def main() -> None:
    check_in = date.today() + timedelta(days=30)
    target = booking_url(check_in, check_in + timedelta(days=1))
    artifact_dir = Path("artifacts")
    artifact_dir.mkdir(exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="en-US", timezone_id="Asia/Taipei", viewport={"width": 1440, "height": 1100}
        )
        page = await context.new_page()
        response = await page.goto(target, wait_until="domcontentloaded", timeout=90_000)
        await page.get_by_text("rooms found", exact=False).first.wait_for(timeout=60_000)
        body = " ".join((await page.locator("body").inner_text()).split())
        room_buttons = page.locator("button").filter(has_text="Book From NT$")
        room_count = await room_buttons.count()
        room_previews = [
            " ".join((await room_buttons.nth(i).inner_text()).split())
            for i in range(room_count)
        ]
        report = {
            "requested_url": target,
            "http_status": response.status if response else None,
            "final_url": page.url,
            "title": await page.title(),
            "room_count": room_count,
            "room_previews": room_previews,
            "body_preview": body[:16_000],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        (artifact_dir / "hilton-taipei-probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await page.screenshot(path=artifact_dir / "hilton-taipei-probe.png", full_page=True)
        await browser.close()

        if not room_count or "New Taiwan Dollar" not in body:
            raise RuntimeError("Hilton booking page did not expose TWD room rates")


if __name__ == "__main__":
    asyncio.run(main())
