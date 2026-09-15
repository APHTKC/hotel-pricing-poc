import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, parse_money


PROPERTIES = {"hotel_nikko_kaohsiung": {"chain": "9542", "hotel": "47062"}}


def booking_url(hotel_id: str, check_in: date, check_out: date, adults: int = 2) -> str:
    prop = PROPERTIES[hotel_id]
    return "https://be.synxis.com/?" + urlencode({
        "adult": adults, "arrive": check_in.isoformat(), "chain": prop["chain"],
        "child": 0, "currency": "TWD", "depart": check_out.isoformat(),
        "hotel": prop["hotel"], "level": "hotel", "locale": "zh-TW",
        "productcurrency": "TWD", "rooms": 1,
    })


def tax_components(base: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    service = (base * Decimal("0.10")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    tax = ((base + service) * Decimal("0.05")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return service, tax, base + service + tax


class SynxisScraper(CapellaScraper):
    diagnostic_name = "SynXis"

    async def fetch_rates(self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2) -> list[RateObservation]:
        if hotel.id not in PROPERTIES:
            raise ValueError(f"SynxisScraper does not support {hotel.id}")
        queried_at = datetime.now(UTC)
        source_url = booking_url(hotel.id, check_in, check_out, adults)
        page = await self._page()
        try:
            response = await page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            if response is not None and response.status >= 400:
                raise RuntimeError(f"SynXis returned HTTP {response.status}")
            rooms = page.locator("[id^='auto-parent-card-']")
            await rooms.first.wait_for(state="visible", timeout=self.timeout_ms)
            return await self._collect(page, hotel, check_in, check_out, adults, queried_at, source_url)
        finally:
            await page.close()

    async def _collect(self, page, hotel, check_in, check_out, adults, queried_at, source_url):
        observations = []
        rooms = page.locator("[id^='auto-parent-card-']")
        for index in range(await rooms.count()):
            room = rooms.nth(index)
            room_code = await room.locator("[data-room-code]").first.get_attribute("data-room-code")
            room_name = (await room.locator("h2").first.inner_text()).strip()
            size_text = (await room.locator("[class*='roomsize_size']").first.inner_text()).strip()
            size = Decimal("".join(c for c in size_text if c.isdigit()) or "0") or None
            rate = room.locator("[data-rate-code]").first
            if not await rate.count():
                continue
            rate_code = await rate.get_attribute("data-rate-code")
            plan_name = " ".join((await rate.locator("h3").first.inner_text()).split())
            base = parse_money(await rate.locator("[data-testid='regular-price']").first.inner_text())
            service, tax, total = tax_components(base)
            text = " ".join((await room.inner_text()).split())
            key = ":".join((hotel.id, check_in.isoformat(), room_code or room_name, rate_code or plan_name, queried_at.isoformat()))
            observations.append(RateObservation(
                observation_id=hashlib.sha256(key.encode()).hexdigest()[:24], queried_at=queried_at,
                check_in=check_in, check_out=check_out, lead_days=(check_in-queried_at.date()).days,
                nights=(check_out-check_in).days, adults=adults, hotel_id=hotel.id,
                hotel_name=hotel.name, city=hotel.city, room_type_code=room_code,
                room_type_name=room_name, room_size_sqm=size, rate_plan_code=rate_code,
                rate_plan_name=plan_name, breakfast_included="含早餐" in text or "含早" in plan_name,
                cancellation_policy=None, price_before_tax=base, service_charge=service, tax=tax,
                total_price=total, currency="TWD", source_url=source_url, status=ScrapeStatus.LIVE,
                fx_rate_to_twd=Decimal("1"),
            ))
        return observations
