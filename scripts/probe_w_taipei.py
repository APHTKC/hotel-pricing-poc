import asyncio
import json
import re
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
        # The button is visible before Marriott's client-side click handler is
        # hydrated. Clicking immediately is accepted but does not navigate.
        await page.wait_for_timeout(8_000)
        await page.get_by_role("button", name=re.compile("Find Hotels", re.I)).click()
        await page.wait_for_url(
            "**/reservation/rateListMenu.mi",
            wait_until="domcontentloaded",
            timeout=90_000,
        )
        await page.get_by_role(
            "heading", name=re.compile("SELECT A ROOM AND RATE", re.I)
        ).wait_for()

        before_tax_text = " ".join(
            (await page.locator("body").inner_text()).split()
        )[:12_000]
        taxes_checkbox = page.get_by_role(
            "checkbox", name=re.compile("Show with taxes and fees", re.I)
        )
        if not await taxes_checkbox.is_checked():
            await taxes_checkbox.check()
        await page.wait_for_timeout(800)

        first_view_rates = page.get_by_role(
            "button", name=re.compile("View Rates", re.I)
        ).first
        await first_view_rates.click()
        await page.get_by_role("heading", name=re.compile("Flexible Rate", re.I)).wait_for()
        after_tax_text = " ".join(
            (await page.locator("body").inner_text()).split()
        )[:16_000]

        cancellation_policy = None
        rate_details = page.get_by_role("button", name=re.compile("Rate Details", re.I)).first
        if await rate_details.count():
            await rate_details.click()
            dialog = page.get_by_role("dialog")
            await dialog.wait_for()
            cancellation_policy = " ".join((await dialog.inner_text()).split())[:4000]

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
            "room_page_before_tax": before_tax_text,
            "room_page_with_tax_and_rates": after_tax_text,
            "first_rate_details": cancellation_policy,
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
