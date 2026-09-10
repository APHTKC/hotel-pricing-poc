import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, breakfast_included, parse_room_size
from services.fx import published_rate_to_twd


SHANGRILA_URL = (
    "https://www.shangri-la.com/en/taipei/fareasternplazashangrila/"
    "reservations/select-room-rate/"
)


def is_public_cash_rate(member_rate: str | None) -> bool:
    """Exclude signed-in Circle discounts while retaining public cash offers."""
    return not bool((member_rate or "").strip())


def display_currency(header_text: str) -> str:
    """Return the currency selected by Shangri-La for this visitor."""
    words = {word.strip("()[]{}.,:;").upper() for word in header_text.split()}
    for code in ("NTD", "TWD", "USD", "JPY"):
        if code in words:
            return "TWD" if code == "NTD" else code
    raise ValueError("Shangri-La display currency could not be identified")


class ShangriLaScraper(CapellaScraper):
    """Live candidate adapter for Shangri-La Far Eastern, Taipei.

    The official result page exposes room, plan, pre-tax price and tax-inclusive
    price as structured DOM attributes. Only rates available without membership
    are collected.
    """

    supported_hotel_id = "shangrila_taipei"
    diagnostic_name = "Shangri-La"

    def booking_url(self, check_in: date, check_out: date, adults: int) -> str:
        query = urlencode({
            "hotel": "Shangri-La Far Eastern, Taipei",
            "hotelCode": "TPE",
            "timeZone": "+8",
            "city": "Taipei",
            "cityEn": "Taipei",
            "checkInDate": check_in.isoformat(),
            "checkOutDate": check_out.isoformat(),
            "rooms": json.dumps([{"adultNum": adults, "childNum": 0}], separators=(",", ":")),
            "confirmationNo": "",
            "specialCode": "",
            "specialCodeType": "",
            "country": "",
            "specialCodeToken": "",
            "flexible": "false",
            "roomClassCodeList": "",
        })
        return f"{SHANGRILA_URL}?{query}"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id != self.supported_hotel_id:
            raise ValueError(
                f"ShangriLaScraper currently supports only {self.supported_hotel_id}"
            )
        source_url = self.booking_url(check_in, check_out, adults)
        queried_at = datetime.now(UTC)
        page = await self._page()
        try:
            await page.goto(source_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await page.locator(".js-room-item").first.wait_for()
            await page.locator(".room-price-item").first.wait_for()
            return await self._collect_rates(
                page, hotel, check_in, check_out, adults, queried_at, source_url,
            )
        finally:
            await page.close()

    async def _collect_rates(
        self, page, hotel: Hotel, check_in: date, check_out: date, adults: int,
        queried_at: datetime, source_url: str,
    ) -> list[RateObservation]:
        observations: list[RateObservation] = []
        rooms = page.locator(".js-room-item")
        for room_index in range(await rooms.count()):
            room = rooms.nth(room_index)
            room_name = (await room.get_attribute("data-room-name-en") or "").strip()
            room_code = await room.get_attribute("data-room-code")
            size_locator = room.locator(".room-basic .facilities li").first
            room_size = parse_room_size(await size_locator.inner_text()) if await size_locator.count() else None
            rates = room.locator(".room-price-item")
            for rate_index in range(await rates.count()):
                rate = rates.nth(rate_index)
                if not is_public_cash_rate(await rate.get_attribute("data-member-rate")):
                    continue
                price_node = rate.locator(".price-book-num-curr .number").first
                if not await price_node.count():
                    continue
                before_raw = await price_node.get_attribute("data-price-without-tax")
                total_raw = await price_node.get_attribute("data-price-with-tax")
                if not before_raw or not total_raw:
                    continue
                rate_text = await rate.inner_text()
                currency = display_currency(rate_text)
                fx_rate_to_twd = published_rate_to_twd(currency)
                before_tax = Decimal(before_raw.replace(",", ""))
                total_price = Decimal(total_raw.replace(",", ""))
                service_charge = before_tax * Decimal("00.10")
                tax = total_price - before_tax - service_charge
                plan_name = (await rate.locator(".js-room-price-title-text").first.inner_text()).strip()
                cancellation_node = rate.locator(".js-info-tips-content").first
                cancellation = (
                    " ".join((await cancellation_node.inner_text()).split())
                    if await cancellation_node.count() else None
                )
                breakfast_text = " ".join(filter(None, (
                    await rate.get_attribute("data-breakfast-tag-filter"),
                    rate_text,
                )))
                rate_code = await rate.get_attribute("data-rate-code")
                bed_name = await rate.get_attribute("data-bed-name")
                rate_room_code = await rate.get_attribute("data-room-type-code")
                displayed_room_name = f"{room_name} {bed_name}".strip()
                key = ":".join((hotel.id, check_in.isoformat(), rate_room_code or room_code or room_name,
                                rate_code or plan_name, queried_at.isoformat()))
                observations.append(RateObservation(
                    observation_id=hashlib.sha256(key.encode()).hexdigest()[:24],
                    queried_at=queried_at, check_in=check_in, check_out=check_out,
                    lead_days=(check_in - queried_at.date()).days,
                    nights=(check_out - check_in).days, adults=adults,
                    hotel_id=hotel.id, hotel_name=hotel.name, city=hotel.city,
                    room_type_code=rate_room_code or room_code,
                    room_type_name=displayed_room_name, room_size_sqm=room_size,
                    rate_plan_code=rate_code, rate_plan_name=plan_name,
                    breakfast_included=breakfast_included([breakfast_text]),
                    cancellation_policy=cancellation, price_before_tax=before_tax,
                    service_charge=service_charge, tax=tax, total_price=total_price,
                    currency=currency, source_url=source_url, status=ScrapeStatus.LIVE,
                    fx_rate_to_twd=fx_rate_to_twd,
                ))
        return observations
