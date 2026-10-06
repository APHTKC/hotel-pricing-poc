import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlencode

from app.models import Hotel, RateObservation, ScrapeStatus, TaxInclusion
from scrapers.adapters.capella import CapellaScraper


PROPERTIES = {
    "taipei_garden_hotel": {
        "expected_property": "twtai17118",
        "rooms": {
            "Premier-Double": ("Premier Double Room", Decimal("22")),
            "Premier-Family": ("Premier Family Room", Decimal("25")),
            "Premier-Triple": ("Premier Triple Room", Decimal("25")),
            "Premier-Quad": ("Premier Quad Room", Decimal("25")),
            "Luxury-Room": ("Luxury Room", Decimal("25")),
            "Deluxe-Suite": ("Deluxe Suite", Decimal("43")),
            "Garden-Suite": ("Garden Suite", Decimal("63")),
        },
    }
}


def parse_widget_config(raw: str) -> dict:
    """Parse the public JSON configuration embedded by the official website."""

    payload = json.loads(raw)
    original_keys = sorted(payload)
    # Current D-EDGE widgets nest search parameters under ``params`` while
    # keeping the host and public token at the top level. Older integrations
    # put all values at the top level, so support both forms.
    params = payload.get("params")
    if isinstance(params, dict):
        nested = params
    elif isinstance(params, list) and params:
        index = payload.get("propertyIndex", 0)
        selected = params[index] if isinstance(index, int) and index < len(params) else params[0]
        nested = selected if isinstance(selected, dict) else {}
    elif isinstance(params, str):
        nested = {key: values[-1] for key, values in parse_qs(params).items()}
    else:
        nested = {}
    payload = {**payload, **nested, "_request_params": nested}
    required = ("property", "_authCode", "baseHost")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        object_keys = {
            key: sorted(value)
            for key, value in payload.items()
            if isinstance(value, dict)
        }
        raise ValueError(
            f"FastBooking widget config is missing: {', '.join(missing)}; "
            f"top-level keys={original_keys}; object keys={object_keys}"
        )
    if not str(payload["baseHost"]).startswith("https://"):
        raise ValueError("FastBooking widget baseHost must use HTTPS")
    return payload


def quotation_url(config: dict, check_in: date, check_out: date, adults: int) -> str:
    nights = (check_out - check_in).days
    if nights < 1:
        raise ValueError("check_out must be later than check_in")
    # Preserve every public parameter emitted by the official widget (notably
    # its complete device descriptor) and only replace the requested stay.
    params = dict(config.get("_request_params") or {})
    params.update({
        "arrivalDate": check_in.isoformat(),
        "property": config["property"],
        "nights": nights,
        "adults": adults,
        "currency": config.get("currency") or "TWD",
        "_authCode": config["_authCode"],
        "output": "json",
        "s": 1,
        "version": "0.0.1",
        "locale": config.get("locale") or "zh_HK",
    })
    return f"{str(config['baseHost']).rstrip('/')}/quotation?{urlencode(params)}"


class FastBookingScraper(CapellaScraper):
    """Adapter for the public FastBooking/D-EDGE widget on official hotel sites.

    The official page supplies the current property id and public widget token.
    Neither is bypassed or persisted. The quotation response does not state the
    tax, breakfast, or cancellation treatment, so those fields remain unknown.
    """

    diagnostic_name = "FastBooking"

    async def fetch_rates(
        self, hotel: Hotel, check_in: date, check_out: date, adults: int = 2
    ) -> list[RateObservation]:
        if hotel.id not in PROPERTIES:
            raise ValueError(f"FastBookingScraper does not support hotel {hotel.id}")

        page = await self._page()
        queried_at = datetime.now(UTC)
        try:
            response = await page.goto(
                hotel.booking_url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            if response is None or not response.ok:
                status = response.status if response else "no response"
                raise RuntimeError(f"Official hotel page returned {status}")

            config_node = page.locator("#fb-widget-config")
            await config_node.wait_for(state="attached", timeout=self.timeout_ms)
            raw_config = await config_node.text_content()
            config = parse_widget_config(raw_config or "")
            expected = PROPERTIES[hotel.id]["expected_property"]
            if config["property"] != expected:
                raise ValueError(
                    f"Unexpected FastBooking property for {hotel.id}: {config['property']}"
                )

            url = quotation_url(config, check_in, check_out, adults)
            quote_response = await page.request.get(
                url,
                headers={"Referer": hotel.booking_url, "Accept": "application/json"},
                timeout=self.timeout_ms,
            )
            if not quote_response.ok:
                raise RuntimeError(
                    f"FastBooking quotation returned HTTP {quote_response.status}"
                )
            payload = await quote_response.json()
            if payload.get("error"):
                raise RuntimeError(f"FastBooking quotation error: {payload.get('error')}")
            return self._observations(
                payload.get("data") or [],
                hotel,
                check_in,
                check_out,
                adults,
                queried_at,
                config,
                url,
            )
        finally:
            await page.close()

    @staticmethod
    def _observations(
        rows: list[dict],
        hotel: Hotel,
        check_in: date,
        check_out: date,
        adults: int,
        queried_at: datetime,
        config: dict,
        quotation_source_url: str,
    ) -> list[RateObservation]:
        room_map = PROPERTIES[hotel.id]["rooms"]
        observations: list[RateObservation] = []
        for row in rows:
            room_code = str(row.get("room") or "").strip()
            rate_code = str(row.get("rate") or "").strip()
            amount = row.get("totalPrice")
            if not room_code or not rate_code or amount is None:
                continue
            room_name, room_size = room_map.get(
                room_code, (room_code.replace("-", " "), None)
            )
            source_url = row.get("plainBookLink") or quotation_source_url
            key = ":".join(
                (
                    hotel.id,
                    check_in.isoformat(),
                    room_code,
                    rate_code,
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
                    adults=int(row.get("adults") or adults),
                    hotel_id=hotel.id,
                    hotel_name=hotel.name,
                    city=hotel.city,
                    district=hotel.district,
                    room_type_code=room_code,
                    room_type_name=room_name,
                    room_size_sqm=room_size,
                    rate_plan_code=rate_code,
                    rate_plan_name=rate_code.replace("-", " "),
                    breakfast_included=None,
                    cancellation_policy=None,
                    price_before_tax=None,
                    service_charge=None,
                    tax=None,
                    tax_inclusion=TaxInclusion.UNKNOWN,
                    total_price=Decimal(str(amount)),
                    currency=str(row.get("currency") or config.get("currency") or "TWD"),
                    source_platform="official",
                    source_method="public_booking_api",
                    source_property_id=config["property"],
                    source_url=source_url,
                    status=ScrapeStatus.LIVE,
                    fx_rate_to_twd=Decimal("1"),
                )
            )
        return observations
