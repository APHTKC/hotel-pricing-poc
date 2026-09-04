import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from playwright.async_api import async_playwright


PROPERTY_CODE = "TPEWH"
BASE_URL = "https://www.marriott.com/en-us/reservation/availability.mi"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def booking_url(check_in: date, check_out: date) -> str:
    query = urlencode(
        {
            "propertyCode": PROPERTY_CODE,
            "isSearch": "false",
            "fromDate": check_in.strftime("%m/%d/%Y"),
            "toDate": check_out.strftime("%m/%d/%Y"),
            "numberOfRooms": 1,
            "numberOfGuests": 2,
            "useRewardsPoints": "false",
        }
    )
    return f"{BASE_URL}?{query}"


async def main() -> None:
    check_in = date.today() + timedelta(days=1)
    check_out = check_in + timedelta(days=1)
    target = booking_url(check_in, check_out)
    artifact_dir = Path("artifacts")
    artifact_dir.mkdir(exist_ok=True)
    interesting_responses: list[dict[str, object]] = []
    failed_requests: list[dict[str, str]] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            locale="en-US",
            timezone_id="Asia/Taipei",
            user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 1100},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7"
            },
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        def on_response(response) -> None:
            lowered = response.url.lower()
            if any(term in lowered for term in ("graphql", "availability", "rate", "room")):
                interesting_responses.append(
                    {"status": response.status, "url": response.url.split("?", 1)[0][:1000]}
                )

        page.on("response", on_response)
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(
                {
                    "url": request.url.split("?", 1)[0][:1000],
                    "error": request.failure or "unknown",
                }
            ),
        )

        response = None
        navigation_error = None
        try:
            response = await page.goto(
                target, wait_until="domcontentloaded", timeout=90_000
            )
        except Exception as exc:
            navigation_error = repr(exc)
        await page.wait_for_timeout(10_000)
        body = await page.locator("body").inner_text(timeout=10_000) if await page.locator("body").count() else ""
        script_summary = await page.locator("script").evaluate_all(
            """scripts => scripts.map(s => ({
                id: s.id || null,
                type: s.type || null,
                src: s.src ? s.src.split('?')[0] : null,
                textLength: (s.textContent || '').length
            })).filter(x => x.id || x.src || x.type === 'application/ld+json')"""
        )

        report = {
            "requested_url": target,
            "http_status": response.status if response else None,
            "navigation_error": navigation_error,
            "final_url": page.url,
            "title": await page.title(),
            "body_preview": " ".join(body.split())[:8000],
            "script_summary": script_summary[:100],
            "interesting_responses": interesting_responses[-100:],
            "failed_requests": failed_requests[-50:],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        (artifact_dir / "w-probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        await page.screenshot(path=artifact_dir / "w-probe.png", full_page=True)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
