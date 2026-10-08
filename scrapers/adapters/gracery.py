import hashlib
import logging
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlencode, urlparse

from app.models import Hotel, RateObservation, ScrapeStatus, TaxInclusion
from scrapers.adapters.capella import CapellaScraper, parse_money


logger = logging.getLogger(__name__)
BASE_URL = "https://go-fujita-kanko.reservation.jp/ja/hotels/fkg046/plans"


def booking_url(check_in: date, check_out: date, adults: int = 2) -> str:
    query = urlencode(
        {
            "checkin_date": check_in.strftime("%Y%m%d"),
            "checkout_date": check_out.strftime("%Y%m%d"),
            "adults": adults,
            "child1": 0,
            "child2": 0,
            "child3": 0,
            "child4": 0,
            "child5": 0,
            "children": 0,
            "rooms": 1,
            "dayuseFlg": 0,
            "sort": 1,
            "dateUndecidedFlg": 0,
        }
    )
    return f"{BASE_URL}?{query}"


def code_from_url(url: str, query_name: str | None = None) -> str | None:
    parsed = urlparse(url)
    if query_name:
        values = parse_qs(parsed.query).get(query_name)
        return values[0] if values else None
    match = re.search(r"/plans/([^/?]+)", parsed.path)
    return match.group(1) if match else None


def parse_size(text: str) -> Decimal | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*m\s*(?:2|²)", text, re.I)
    return Decimal(match.group(1)) if match else None


def breakfast_status(plan_name: str, plan_text: str) -> bool | None:
    joined = f"{plan_name} {plan_text}".lower()
    if any(term in joined for term in ("朝食付き", "朝食付", "with breakfast")):
        return True
    if any(term in joined for term in ("素泊まり", "朝食は含まれていません", "room only")):
        return False
    return None


class GraceryScraper(CapellaScraper):
    """Official Reservation.jp adapter for Hotel Gracery Taipei.

    The first document is a Livewire loading skeleton.  The public page then
    replaces it with plan and room cards.  Waiting for the stable room-card
    selector lets Playwright follow that normal browser flow without calling
    undocumented endpoints or bypassing a protection mechanism.
    """

    supported_hotel_id = "hotel_gracery_taipei"
    diagnostic_name = "Hotel Gracery Taipei"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id != self.supported_hotel_id:
            raise ValueError(
                f"{type(self).__name__} currently supports only {self.supported_hotel_id}"
            )

        source_url = booking_url(check_in, check_out, adults)
        queried_at = datetime.now(UTC)
        page = await self._page()
        response = None
        try:
            response = await page.goto(
                source_url, wait_until="domcontentloaded", timeout=self.timeout_ms
            )
            await page.locator(".c-listRoom-item .c-listPlan-item").first.wait_for(
                state="attached", timeout=self.timeout_ms
            )
            return await self._collect(
                page, hotel, check_in, check_out, adults, queried_at, source_url
            )
        except Exception:
            title = await page.title()
            raw_body = await page.locator("body").text_content(timeout=3_000) or ""
            logger.error(
                "%s diagnostic: status=%s final_url=%s title=%r body=%r",
                self.diagnostic_name,
                response.status if response else None,
                page.url,
                title,
                " ".join(raw_body.split())[:1200],
            )
            raise
        finally:
            await page.close()

    async def _collect(
        self, page, hotel: Hotel, check_in: date, check_out: date, adults: int,
        queried_at: datetime, source_url: str,
    ) -> list[RateObservation]:
        observations: list[RateObservation] = []
        plans = page.locator(".c-listRoom-item")
        for plan_index in range(await plans.count()):
            plan = plans.nth(plan_index)
            room_cards = plan.locator(".c-listPlan-item")
            if not await room_cards.count():
                continue
            plan_name = (await plan.locator("h2.c-headingMain").first.inner_text()).strip()
            plan_text = await plan.locator(".c-roomDetailBox-inner").first.inner_text()
            plan_link = plan.locator("a[href*='/plans/']:not([href*='room_id='])").first
            plan_href = await plan_link.get_attribute("href") if await plan_link.count() else ""
            plan_code = code_from_url(plan_href or "") or f"plan-{plan_index}"
            breakfast = breakfast_status(plan_name, plan_text)

            for room_index in range(await room_cards.count()):
                room = room_cards.nth(room_index)
                price = room.locator(".c-textPrice-total strong").first
                detail_link = room.locator("a[href*='room_id=']").first
                if not await price.count() or not await detail_link.count():
                    continue
                detail_href = await detail_link.get_attribute("href") or source_url
                room_code = code_from_url(detail_href, "room_id")
                room_name = (
                    await room.locator(".c-listPlan-item-detail-name").first.inner_text()
                ).strip()
                room_text = await room.inner_text()
                total = parse_money(await price.inner_text())
                key = ":".join(
                    (
                        hotel.id,
                        check_in.isoformat(),
                        room_code or room_name,
                        plan_code,
                        queried_at.isoformat(),
                    )
                )
                observations.append(
                    RateObservation(
                        observation_id=hashlib.sha256(key.encode()).hexdigest()[:24],
                        queried_at=queried_at,
                        check_in=check_in,
                        check_out=check_out,
                        lead_days=(check_in - queried_at.date()).days,
                        nights=(check_out - check_in).days,
                        adults=adults,
                        hotel_id=hotel.id,
                        hotel_name=hotel.name,
                        city=hotel.city,
                        district=hotel.district,
                        room_type_code=room_code,
                        room_type_name=room_name,
                        room_size_sqm=parse_size(room_text),
                        rate_plan_code=plan_code,
                        rate_plan_name=plan_name,
                        breakfast_included=breakfast,
                        cancellation_policy=None,
                        price_before_tax=None,
                        service_charge=None,
                        tax=None,
                        tax_inclusion=TaxInclusion.INCLUDED,
                        total_price=total,
                        currency="TWD",
                        source_property_id="fkg046",
                        source_url=detail_href,
                        status=ScrapeStatus.LIVE,
                        fx_rate_to_twd=Decimal("1"),
                    )
                )
        return observations
