import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP

from app.models import Hotel, RateObservation, ScrapeStatus
from scrapers.adapters.capella import CapellaScraper, parse_money


PROPERTIES = {
    "palais_de_chine": {
        "slug": "LDC-PALAIS-TP",
        "plan_code": "82518fbc-b968-44a1-b58d-4fc9734e3a0f",
        "plan_name": "最優惠房價｜不含早餐",
        "cancellation": "入住日前至少 3 天取消或更改可免收取消費",
    },
    "solaria_nishitetsu_taipei": {
        "slug": "SOLARIA-TPXM",
        "plan_code": "a25b928f-1de1-4e85-af69-2b62e246fd25",
        "plan_name": "【年度住房優惠】不含早餐",
        "cancellation": "入住 3 天前取消可全額退款",
    },
}


def parse_room_size(text: str) -> Decimal | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:平方公尺|平方米)", text)
    return Decimal(match.group(1)) if match else None


def split_tax_inclusive_total(total: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Split Gobooking's displayed total into base, 10% service and 5% tax.

    The booking page states that its TWD amount includes 10% service charge and
    5% tax. Tax is calculated on base plus service, so total = base * 1.155.
    """

    whole = Decimal("1")
    base = (total / Decimal("1.155")).quantize(whole, rounding=ROUND_HALF_UP)
    service = (base * Decimal("0.10")).quantize(whole, rounding=ROUND_HALF_UP)
    tax = (Decimal(total) - base - service).quantize(whole, rounding=ROUND_HALF_UP)
    return base, service, tax


class GobookingScraper(CapellaScraper):
    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id not in PROPERTIES:
            raise ValueError(f"GobookingScraper does not support hotel {hotel.id}")

        prop = PROPERTIES[hotel.id]
        package_url = (
            f"https://hotel.gobooking.com.tw/zh-TW/{prop['slug']}/"
            f"Packages/Details/{prop['plan_code']}"
        )
        queried_at = datetime.now(UTC)
        page = await self._page()
        try:
            await page.goto(
                package_url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            await page.locator(".js-package-room").first.wait_for(
                timeout=self.timeout_ms
            )
            await self._dismiss_overlays(page)
            return await self._collect(
                page, hotel, check_in, check_out, adults, queried_at, prop
            )
        finally:
            await page.close()

    async def _dismiss_overlays(self, page) -> None:
        message = page.locator("#modal-tempdata-message.active .js-modal-close")
        if await message.count():
            await message.first.click(force=True)
        cookie = page.get_by_role("button", name="同意並進入網站")
        if await cookie.count() and await cookie.first.is_visible():
            await cookie.first.click(force=True)

    async def _collect(
        self, page, hotel, check_in, check_out, adults, queried_at, prop
    ) -> list[RateObservation]:
        observations: list[RateObservation] = []
        rooms = page.locator(".js-package-room")
        room_details: list[tuple[str | None, str, Decimal | None]] = []
        for index in range(await rooms.count()):
            room = rooms.nth(index)
            button = room.locator(".js-calendar-btn")
            if not await button.count():
                continue
            room_name = (await room.locator(".card-title").first.inner_text()).strip()
            room_size = parse_room_size(await room.inner_text())
            room_code = await button.first.get_attribute("data-packageroomid")
            room_details.append((room_code, room_name, room_size))

        arrival = check_in.isoformat()
        for room_code, room_name, room_size in room_details:
            if not room_code:
                continue
            reserve_url = (
                f"https://hotel.gobooking.com.tw/zh-TW/{prop['slug']}/"
                "Reservations/Reserve?"
                f"packageId={prop['plan_code']}&packageRoomId={room_code}"
                f"&arrival={arrival}"
            )
            await page.goto(
                reserve_url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            try:
                price = page.locator(".amount").first
                await price.wait_for(state="visible", timeout=8_000)
                if await price.count():
                    total = parse_money(await price.inner_text())
                    base, service, tax = split_tax_inclusive_total(total)
                    key = ":".join(
                        (
                            hotel.id,
                            check_in.isoformat(),
                            room_code or room_name,
                            prop["plan_code"],
                            queried_at.isoformat(),
                        )
                    )
                    observations.append(
                        RateObservation(
                            observation_id=hashlib.sha256(
                                key.encode()
                            ).hexdigest()[:24],
                            queried_at=queried_at,
                            check_in=check_in,
                            check_out=check_out,
                            lead_days=(check_in - queried_at.date()).days,
                            nights=(check_out - check_in).days,
                            adults=adults,
                            hotel_id=hotel.id,
                            hotel_name=hotel.name,
                            city=hotel.city,
                            room_type_code=room_code,
                            room_type_name=room_name,
                            room_size_sqm=room_size,
                            rate_plan_code=prop["plan_code"],
                            rate_plan_name=prop["plan_name"],
                            breakfast_included=False,
                            cancellation_policy=prop["cancellation"],
                            price_before_tax=base,
                            service_charge=service,
                            tax=tax,
                            total_price=total,
                            currency="TWD",
                            source_url=reserve_url,
                            status=ScrapeStatus.LIVE,
                            fx_rate_to_twd=Decimal("1"),
                        )
                    )
            except Exception:
                # A room may be sold out for this date while other rooms remain.
                continue

        return observations
