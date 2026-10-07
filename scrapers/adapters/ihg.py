import hashlib
import os
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlencode

from app.models import Hotel, RateObservation, ScrapeStatus, TaxInclusion
from scrapers.adapters.capella import CapellaScraper, breakfast_included, parse_money


IHG_HOTELS = {
    "regent_taipei": {
        "hotel_code": "TPERG",
        "brand_code": "RE",
        "brand_slug": "regent",
        "destination": "No.3, Ln.39, Sec.2 Zhongshan N. Rd., Taipei, TW",
        "legacy_query": True,
    },
    "intercontinental_taichung": {
        "hotel_code": "RMQTT",
        "brand_code": "IC",
        "brand_slug": "intercontinental",
        "destination": "InterContinental 臺中勤美洲際酒店",
        "booking_path": "tw/zh/find-hotels/select-roomrate",
        "qAAR": "6CBARC",
        "qpMn": 0,
        "official_form": True,
    },
    "intercontinental_kaohsiung": {
        "hotel_code": "KHHKT",
        "brand_code": "IC",
        "brand_slug": "intercontinental",
        "destination": "No. 33, Xinguang Rd., Qianzhen Dist., Kaohsiung, TW",
        "booking_path": "tw/zh/find-hotels/hotel/rooms",
        "qAAR": "6CBARC",
        "qIta": "99618783",
        "qBrs": "re.ic.in.vn.cp.vx.hi.ex.rs.cv.sb.cw.ma.ul.ki.va.ii.sp.nd.ct.sx.we.lx",
        "qSmP": 1,
        "qpMn": 0,
        "official_form": True,
    },
}
def ihg_month(value: date) -> str:
    return f"{value.month - 1:02d}{value.year}"


def parse_rate_card(text: str) -> tuple[str, Decimal, bool | None, str] | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    price_index = next(
        (index for index, line in enumerate(lines) if re.fullmatch(r"[\d,]+", line)),
        None,
    )
    if not lines or price_index is None or price_index + 1 >= len(lines):
        return None
    if lines[price_index + 1].upper() != "TWD":
        return None
    plan_name = lines[0]
    displayed_price = parse_money(lines[price_index])
    terms = " ".join(lines[1:price_index])
    return plan_name, displayed_price, breakfast_included([plan_name, terms]), terms


def included_total_fields(displayed_total: Decimal) -> dict:
    """Represent IHG's taxes-and-fees-inclusive display without inventing a split."""
    return {
        "price_before_tax": None,
        "service_charge": None,
        "tax": None,
        "tax_inclusion": TaxInclusion.INCLUDED,
        "total_price": displayed_total,
    }


def blocked_status_code(response_status: int | None, page_title: str) -> int | None:
    if response_status in {403, 429}:
        return response_status
    if re.search(r"access denied|request blocked|too many requests", page_title, re.I):
        return 403
    return None


class IHGScraper(CapellaScraper):
    """Public, non-member cash rates from IHG's official room-rate page."""

    def __init__(self, timeout_ms: int = 120_000):
        super().__init__(timeout_ms=timeout_ms)

    def booking_url(self, hotel: Hotel, check_in: date, check_out: date, adults: int) -> str:
        details = IHG_HOTELS[hotel.id]
        params = {
            "fromRedirect": "true", "qSrt": "sBR", "qErm": "false",
            "qSlH": details["hotel_code"], "qRms": 1, "qAdlt": adults, "qChld": 0,
            "qCiD": f"{check_in.day:02d}", "qCiMy": ihg_month(check_in),
            "qCoD": f"{check_out.day:02d}", "qCoMy": ihg_month(check_out),
            "qAAR": details.get("qAAR", "6CBARC" if details.get("legacy_query") else ""),
            "qRtP": "6CBARC", "setPMCookies": "true",
            "qSHBrC": details["brand_code"], "srb_u": 1,
            "qDest": details["destination"],
            "qpMbw": 0, "qpMn": details.get("qpMn", 1), "qRmFltr": "",
        }
        for key in ("qIta", "qBrs", "qSmP"):
            if key in details:
                params[key] = details[key]
        if details.get("official_form"):
            params.update({"qAkamaiCC": "TW", "qWch": 0, "qRad": 30, "qRdU": "mi"})
        query = urlencode(params, quote_via=quote)
        if details.get("legacy_query"):
            query += "&qPt=CASH"
        path = details.get("booking_path", "us/en/find-hotels/select-roomrate")
        return f"https://www.ihg.com/{details['brand_slug']}/hotels/{path}?{query}"

    async def fetch_rates(self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2) -> list[RateObservation]:
        if hotel.id not in IHG_HOTELS:
            raise ValueError(f"IHGScraper does not yet support {hotel.id}")
        queried_at = datetime.now(UTC)
        source_url = self.booking_url(hotel, check_in, check_out, adults)
        page = await self._page()
        try:
            response = await page.goto(
                source_url, wait_until="domcontentloaded", timeout=self.timeout_ms
            )
            blocked_status = blocked_status_code(
                response.status if response else None, await page.title()
            )
            if blocked_status:
                raise RuntimeError(f"HTTP {blocked_status} blocked by IHG booking edge")
            ready = page.locator("app-room-rate-item").or_(page.get_by_role(
                "heading", name=re.compile(r"Select your room|選擇.*客房|选择.*客房", re.I)
            ))
            await ready.first.wait_for(timeout=self.timeout_ms)
            taxes = page.locator("#taxes_fees_checkbox")
            if not await taxes.count():
                await self._capture_debug(page, hotel.id)
                return []
            if not await taxes.is_checked():
                await taxes.check(force=True)
            if not await taxes.is_checked():
                await self._capture_debug(page, hotel.id)
                return []
            member = page.get_by_role(
                "checkbox", name=re.compile("IHG One Rewards Discount", re.I)
            ).or_(page.get_by_role(
                "switch", name=re.compile("IHG One Rewards Discount", re.I)
            ))
            if await member.count() and await member.is_checked():
                await member.uncheck(force=True)
            await page.wait_for_timeout(1_200)
            observations = await self._collect(
                page, hotel, check_in, check_out, adults, queried_at, source_url
            )
            if not observations:
                await self._capture_debug(page, hotel.id)
            return observations
        except Exception:
            await self._capture_debug(page, hotel.id)
            raise
        finally:
            await page.close()

    async def _capture_debug(self, page, hotel_id: str) -> None:
        debug_root = os.getenv("IHG_DEBUG_DIR")
        if not debug_root:
            return
        output_dir = Path(debug_root)
        output_dir.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(output_dir / f"{hotel_id}.png"), full_page=True)
        details = (
            f"URL: {page.url}\n"
            f"TITLE: {await page.title()}\n\n"
            f"BODY:\n{(await page.locator('body').inner_text())[:20000]}"
        )
        (output_dir / f"{hotel_id}.txt").write_text(details, encoding="utf-8")

    async def _collect(self, page, hotel, check_in, check_out, adults, queried_at, source_url):
        buttons = page.get_by_role(
            "button", name=re.compile(r"^(?:View prices for |查看(?:價格|房價)|檢視(?:價格|房價))", re.I)
        )
        observations = []
        for index in range(await buttons.count()):
            button = buttons.nth(index)
            await button.click(force=True)
            await page.wait_for_timeout(250)
            data = await button.evaluate("""el => {
              const root = el.closest('app-room-rate-item');
              const heading = root && root.querySelector('h2, h3');
              return {name: heading ? heading.innerText.trim() : '', text: root ? root.innerText : ''};
            }""")
            room_name, text = data["name"], data["text"]
            if not room_name:
                continue
            size_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:sqm|sqmt)", text, re.I)
            size = Decimal(size_match.group(1)) if size_match else None
            rate_buttons = page.get_by_role(
                "button", name=re.compile(rf"^Rate details for {re.escape(room_name)}$", re.I)
            )
            for rate_index in range(await rate_buttons.count()):
                plan_text = await rate_buttons.nth(rate_index).evaluate(
                    "el => el.parentElement && el.parentElement.parentElement "
                    "? el.parentElement.parentElement.innerText : ''"
                )
                parsed = parse_rate_card(plan_text)
                if parsed is None:
                    continue
                plan_name, displayed_total, includes_breakfast, terms = parsed
                key = f"{hotel.id}:{check_in}:{room_name}:{plan_name}:{queried_at.isoformat()}"
                observations.append(RateObservation(
                    observation_id=hashlib.sha256(key.encode()).hexdigest()[:24], queried_at=queried_at,
                    check_in=check_in, check_out=check_out, lead_days=(check_in - queried_at.date()).days,
                    nights=1, adults=adults, hotel_id=hotel.id, hotel_name=hotel.name, city=hotel.city,
                    room_type_code=re.sub(r"[^A-Z0-9]+", "-", room_name.upper()).strip("-"),
                    room_type_name=room_name, room_size_sqm=size, rate_plan_code=None,
                    rate_plan_name=plan_name, breakfast_included=includes_breakfast,
                    cancellation_policy=terms or None,
                    **included_total_fields(displayed_total), currency="TWD",
                    source_url=source_url, status=ScrapeStatus.LIVE, fx_rate_to_twd=Decimal("1"),
                ))
        return observations
