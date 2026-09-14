import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, parse_money


PROPERTY_CODE = "twtai28740"
BOOKING_BASE = "https://www.book-secure.com/index.php"

# The booking engine does not repeat room area in its results cards. These
# values come from Grand View Resort Beitou's official room pages.
ROOM_SIZES = {
    "Superior-Twin-Room": Decimal("50"),
    "Deluxe-Double-Room": Decimal("50"),
    "Deluxe-Twin-Room": Decimal("50"),
    "Deluxe-Family-Room": Decimal("50"),
    "You-Ya-Family-Room": Decimal("63"),
    "Yu-Ya-Junior-Room": Decimal("63"),
    "You-Ya-Suite": Decimal("63"),
    "Grand-View-Suite": Decimal("116"),
    "GRAND-VIEW-SUITE-603": Decimal("96"),
}


def booking_url(check_in: date, check_out: date, adults: int = 2) -> str:
    query = urlencode(
        {
            "s": "results",
            "property": PROPERTY_CODE,
            "arrival": check_in.isoformat(),
            "departure": check_out.isoformat(),
            "adults1": adults,
            "children1": 0,
            "locale": "zh_Hant_HK",
            "currency": "TWD",
            "showPromotions": 1,
        }
    )
    return f"{BOOKING_BASE}?{query}"


def parse_included_tax(text: str) -> Decimal | None:
    match = re.search(r"已包含稅費\s*:?\s*NT\$?\s*([\d,]+)", text)
    return Decimal(match.group(1).replace(",", "")) if match else None


class GrandViewScraper(CapellaScraper):
    supported_hotel_id = "grand_view_resort_beitou"
    diagnostic_name = "Grand View Resort Beitou"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id != self.supported_hotel_id:
            raise ValueError(
                f"GrandViewScraper currently supports only {self.supported_hotel_id}"
            )
        queried_at = datetime.now(UTC)
        source_url = booking_url(check_in, check_out, adults)
        page = await self._page()
        try:
            response = await page.goto(
                source_url, wait_until="domcontentloaded", timeout=self.timeout_ms
            )
            if response is not None and response.status >= 400:
                raise RuntimeError(f"Grand View booking page returned HTTP {response.status}")
            rooms = page.locator(
                "#results-items div.fb-results-accommodation[id^='accommodation-']"
            )
            await rooms.first.wait_for(state="visible", timeout=self.timeout_ms)
            return await self._collect(
                page, hotel, check_in, check_out, adults, queried_at, source_url
            )
        finally:
            await page.close()

    async def _collect(
        self, page, hotel, check_in, check_out, adults, queried_at, source_url
    ) -> list[RateObservation]:
        observations: list[RateObservation] = []
        room_cards = page.locator(
            "#results-items div.fb-results-accommodation[id^='accommodation-']"
        )
        for room_index in range(await room_cards.count()):
            room = room_cards.nth(room_index)
            room_code = (await room.get_attribute("id") or "").removeprefix(
                "accommodation-"
            )
            room_name = (
                await room.locator(".fb-results-acc-title").first.inner_text()
            ).strip()
            rates = room.locator(".fb-results-rate")
            for rate_index in range(await rates.count()):
                rate = rates.nth(rate_index)
                rate_id = await rate.get_attribute("id") or ""
                plan_name = (await rate.locator("a").first.inner_text()).strip()
                rate_text = " ".join((await rate.inner_text()).split())
                total = parse_money(await rate.locator(".fb-price").first.inner_text())
                included_tax = parse_included_tax(rate_text)
                features = [
                    " ".join(value.split())
                    for value in await rate.locator(".fb-results-ratekey").all_inner_texts()
                    if value.strip()
                ]
                cancellation = next(
                    (value for value in features if "取消" in value), None
                )
                breakfast = any(
                    "含早餐" in value or "一泊二食" in value for value in features
                )
                key = ":".join(
                    (
                        hotel.id,
                        check_in.isoformat(),
                        room_code,
                        rate_id or plan_name,
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
                        room_type_code=room_code or None,
                        room_type_name=room_name,
                        room_size_sqm=ROOM_SIZES.get(room_code),
                        rate_plan_code=rate_id or None,
                        rate_plan_name=plan_name,
                        breakfast_included=breakfast,
                        cancellation_policy=cancellation,
                        price_before_tax=(
                            total - included_tax if included_tax is not None else None
                        ),
                        service_charge=None,
                        tax=included_tax,
                        total_price=total,
                        currency="TWD",
                        source_url=source_url,
                        status=ScrapeStatus.LIVE,
                        fx_rate_to_twd=Decimal("1"),
                    )
                )
        return observations
