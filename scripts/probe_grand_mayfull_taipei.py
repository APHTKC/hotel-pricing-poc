import asyncio
import json
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from playwright.async_api import async_playwright


BASE_URL = "https://book-directonline.com/properties/GrandMayfullHotelTaipeiDirect"


def booking_url(check_in: date, check_out: date, adults: int = 2) -> str:
    query = urlencode(
        {
            "locale": "zh-TW",
            "items[0][adults]": adults,
            "items[0][children]": 0,
            "items[0][infants]": 0,
            "currency": "TWD",
            "checkInDate": check_in.isoformat(),
            "checkOutDate": check_out.isoformat(),
            "trackPage": "no",
        }
    )
    return f"{BASE_URL}?{query}"


async def main() -> None:
    check_in = date.today() + timedelta(days=30)
    check_out = check_in + timedelta(days=1)
    target = booking_url(check_in, check_out)
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
        response = await page.goto(target, wait_until="domcontentloaded", timeout=90_000)
        load_error = None
        try:
            await page.locator("[id^='room-rate-']").first.wait_for(timeout=60_000)
        except Exception as exc:
            load_error = repr(exc)

        rooms = []
        room_cards = page.locator("[id^='roomType-']")
        for room_index in range(await room_cards.count()):
            card = room_cards.nth(room_index)
            text = "\n".join(
                line.strip()
                for line in (await card.inner_text()).splitlines()
                if line.strip()
            )
            heading = card.locator("h2").first
            rooms.append(
                {
                    "id": await card.get_attribute("id"),
                    "name": (await heading.inner_text()).strip(),
                    "size_sqm": (
                        float(match.group(1))
                        if (match := re.search(r"(\d+(?:\.\d+)?)\s*m²", text))
                        else None
                    ),
                    "rate_count": await card.locator("[id^='room-rate-']").count(),
                    "preview": text[:4_000],
                }
            )

        rates = []
        rate_cards = page.locator("[id^='room-rate-']")
        for rate_index in range(await rate_cards.count()):
            card = rate_cards.nth(rate_index)
            text = "\n".join(
                line.strip()
                for line in (await card.inner_text()).splitlines()
                if line.strip()
            )
            rates.append(
                {
                    "id": await card.get_attribute("id"),
                    "text": text[:2_000],
                    "aria_label": await card.get_attribute("aria-label"),
                }
            )

        body = " ".join((await page.locator("body").inner_text()).split())
        report = {
            "requested_url": target,
            "http_status": response.status if response else None,
            "final_url": page.url,
            "title": await page.title(),
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "load_error": load_error,
            "room_count": len(rooms),
            "rate_count": len(rates),
            "rooms": rooms,
            "rates": rates,
            "has_twd": "TWD" in body,
            "body_preview": body[:16_000],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        (artifact_dir / "grand-mayfull-taipei-probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await page.screenshot(
            path=artifact_dir / "grand-mayfull-taipei-probe.png", full_page=True
        )
        await browser.close()

        if load_error or not rooms or not rates or not report["has_twd"]:
            raise RuntimeError("Grand Mayfull Taipei did not expose TWD room rates")


if __name__ == "__main__":
    asyncio.run(main())
