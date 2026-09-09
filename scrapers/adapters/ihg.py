import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, breakfast_included, parse_money


IHG_HOTEL_CODES = {"regent_taipei": ("TPERG", "RE")}
TOTAL_MULTIPLIER = Decimal("1.155")


def ihg_month(value: date) -> str:
    return f"{value.month - 1:02d}{value.year}"


class IHGScraper(CapellaScraper):
    """Public, non-member cash rates from IHG's official room-rate page."""

    def booking_url(self, hotel: Hotel, check_in: date, check_out: date, adults: int) -> str:
        hotel_code, brand_code = IHG_HOTEL_CODES[hotel.id]
        query = urlencode({
            "fromRedirect": "true", "qSrt": "sBR", "qErm": "false",
            "qSlH": hotel_code, "qRms": 1, "qAdlt": adults, "qChld": 0,
            "qCiD": f"{check_in.day:02d}", "qCiMy": ihg_month(check_in),
            "qCoD": f"{check_out.day:02d}", "qCoMy": ihg_month(check_out),
            "qAAR": "6CBARC", "qRtP": "6CBARC", "setPMCookies": "true",
            "qSHBrC": brand_code, "qPt": "CASH", "srb_u": 1,
            "qDest": "No.3, Ln.39, Sec.2 Zhongshan N. Rd., Taipei, TW",
        })
        return f"https://www.ihg.com/regent/hotels/us/en/find-hotels/select-roomrate?{query}"

    async def fetch_rates(self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2) -> list[RateObservation]:
        if hotel.id not in IHG_HOTEL_CODES:
            raise ValueError(f"IHGScraper does not yet support {hotel.id}")
        queried_at = datetime.now(UTC)
        source_url = self.booking_url(hotel, check_in, check_out, adults)
        page = await self._page()
        try:
            await page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await page.get_by_role("heading", name="Select your room").wait_for(timeout=self.timeout_ms)
            taxes = page.locator("#taxes_fees_checkbox")
            if not await taxes.is_checked():
                await taxes.check(force=True)
            member = page.get_by_role("checkbox", name=re.compile("IHG One Rewards Discount", re.I))
            if await member.is_checked():
                await member.uncheck(force=True)
            await page.wait_for_timeout(800)
            return await self._collect(page, hotel, check_in, check_out, adults, queried_at, source_url)
        finally:
            await page.close()

    async def _collect(self, page, hotel, check_in, check_out, adults, queried_at, source_url):
        buttons = page.get_by_role("button", name=re.compile("View prices", re.I))
        observations = []
        for index in range(await buttons.count()):
            button = buttons.nth(index)
            await button.click(force=True)
            await page.wait_for_timeout(180)
            data = await button.evaluate("""el => {
              let root = el.parentElement;
              while (root && !(root.querySelector('h2') && /Best Flexible/i.test(root.innerText))) root = root.parentElement;
              const heading = root && root.querySelector('h2');
              return {name: heading ? heading.innerText.trim() : '', text: root ? root.innerText : ''};
            }""")
            room_name, text = data["name"], data["text"]
            if not room_name:
                continue
            size_match = re.search(r"(\d+(?:\.\d+)?)\s*sqm", text, re.I)
            size = Decimal(size_match.group(1)) if size_match else None
            pattern = re.compile(r"(Best Flexible(?: with Breakfast| Rate)?)(.*?Price details)\s*([\d,]+)\s*TWD", re.I | re.S)
            for match in pattern.finditer(text):
                plan_name = " ".join(match.group(1).split())
                total = parse_money(match.group(3))
                before_tax = (total / TOTAL_MULTIPLIER).quantize(Decimal("1"))
                service = (before_tax * Decimal("0.10")).quantize(Decimal("1"))
                tax = total - before_tax - service
                terms = " ".join(match.group(2).replace("", " ").split())
                key = f"{hotel.id}:{check_in}:{room_name}:{plan_name}:{queried_at.isoformat()}"
                observations.append(RateObservation(
                    observation_id=hashlib.sha256(key.encode()).hexdigest()[:24], queried_at=queried_at,
                    check_in=check_in, check_out=check_out, lead_days=(check_in - queried_at.date()).days,
                    nights=1, adults=adults, hotel_id=hotel.id, hotel_name=hotel.name, city=hotel.city,
                    room_type_code=re.sub(r"[^A-Z0-9]+", "-", room_name.upper()).strip("-"),
                    room_type_name=room_name, room_size_sqm=size, rate_plan_code=None,
                    rate_plan_name=plan_name, breakfast_included=breakfast_included([plan_name]),
                    cancellation_policy=terms or None, price_before_tax=before_tax,
                    service_charge=service, tax=tax, total_price=total, currency="TWD",
                    source_url=source_url, status=ScrapeStatus.LIVE, fx_rate_to_twd=Decimal("1"),
                ))
        return observations
