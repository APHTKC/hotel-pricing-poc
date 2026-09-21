import asyncio
import json
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx

from app.models import Hotel
from app.models import RateObservation, ScrapeStatus
from scrapers.ota.base import OtaRateProvider
from scrapers.ota.booking_com import BookingComProvider, parse_availability
from scrapers.ota.config import load_ota_property_mappings
from scrapers.ota.registry import OTA_PROVIDER_SPECS, configured_ota_providers


class ExampleProvider(OtaRateProvider):
    platform = "booking_com"

    async def fetch_rates(self, hotel, source_property_id, check_in, check_out, adults=2):
        return []


def test_ota_registry_requires_complete_partner_credentials():
    assert configured_ota_providers({}) == []
    assert configured_ota_providers({"AGODA_API_KEY": "key"}) == []
    configured = configured_ota_providers(
        {"AGODA_API_KEY": "key", "AGODA_SITE_ID": "site"}
    )
    assert [spec.platform for spec in configured] == ["agoda"]
    assert {spec.platform for spec in OTA_PROVIDER_SPECS} == {
        "booking_com",
        "agoda",
        "expedia_group",
        "rakuten_travel",
    }


def test_ota_provider_tags_rate_source_metadata():
    observation = RateObservation(
        observation_id="sample",
        queried_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        check_in=date(2026, 10, 1),
        check_out=date(2026, 10, 2),
        lead_days=10,
        hotel_id="sample_hotel",
        hotel_name="Sample Hotel",
        room_type_name="Deluxe",
        rate_plan_name="Flexible",
        total_price=Decimal("10000"),
        currency="TWD",
        source_url="https://example.com/rate",
        status=ScrapeStatus.LIVE,
    )

    tagged = ExampleProvider().tag_observation(observation, "property-123")

    assert tagged.source_platform == "booking_com"
    assert tagged.source_method == "partner_api"
    assert tagged.source_property_id == "property-123"


def _hotel() -> Hotel:
    return Hotel(
        id="capella_taipei",
        name="Capella Taipei",
        short_name="Capella",
        city="Taipei",
        district="Songshan",
        country="TW",
        booking_url="https://example.com/capella",
        adapter="capella",
    )


def test_booking_com_availability_parser_preserves_price_and_policies():
    queried_at = datetime(2026, 9, 21, tzinfo=timezone.utc)
    rows = parse_availability(
        {
            "data": {
                "currency": "TWD",
                "url": "https://www.booking.com/hotel/tw/example.html",
                "rooms": [{"id": 55, "name": "Deluxe King"}],
                "products": [
                    {
                        "id": "product-1",
                        "room": 55,
                        "policies": {
                            "meal_plan": {"plan": "breakfast_included"},
                            "cancellation": {
                                "type": "free_cancellation",
                                "free_cancellation_until": "2026-10-01T16:00:00+00:00",
                            },
                        },
                        "price": {
                            "base": {"booker_currency": 10000},
                            "total": {"booker_currency": 11550},
                        },
                    }
                ],
            }
        },
        _hotel(),
        "123456",
        date(2026, 10, 2),
        date(2026, 10, 3),
        2,
        queried_at,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.room_type_name == "Deluxe King"
    assert row.breakfast_included is True
    assert row.price_before_tax == Decimal("10000")
    assert row.total_price == Decimal("11550")
    assert row.total_twd == Decimal("11550")
    assert row.source_platform == "booking_com"
    assert row.source_property_id == "123456"


def test_booking_com_provider_uses_partner_headers_and_expected_request():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/accommodations/details"):
            return httpx.Response(
                200,
                json={"data": [{"rooms": [{"id": "55", "name": {"en-gb": "Deluxe"}}]}]},
            )
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": {"currency": "TWD", "products": []}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = BookingComProvider("secret", "affiliate-1", client=client)
    try:
        rows = asyncio.run(
            provider.fetch_rates(
                _hotel(), "123456", date(2026, 10, 2), date(2026, 10, 3)
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert rows == []
    assert captured["headers"]["authorization"] == "Bearer secret"
    assert captured["headers"]["x-affiliate-id"] == "affiliate-1"
    assert captured["body"]["accommodation"] == 123456
    assert captured["body"]["currency"] == "TWD"
    assert captured["body"]["extras"] == ["products", "extra_charges"]


def test_booking_com_property_discovery_is_hotel_only_and_normalized():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "123456",
                        "type": "hotel",
                        "name": {"en-gb": "Capella Taipei"},
                        "location": {
                            "city_name": {"en-gb": "Taipei"},
                            "country": "tw",
                        },
                    },
                    {"id": "-2637882", "type": "city", "name": "Taipei"},
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = BookingComProvider("secret", "affiliate-1", client=client)
    try:
        candidates = asyncio.run(provider.discover_properties("Capella Taipei"))
    finally:
        asyncio.run(client.aclose())

    assert candidates == [
        {
            "id": "123456",
            "name": "Capella Taipei",
            "city": "Taipei",
            "country": "tw",
        }
    ]
    assert captured["headers"]["authorization"] == "Bearer secret"
    assert captured["body"] == {
        "query": "Capella Taipei",
        "country": "tw",
        "language": "en-gb",
        "filters": {"types": ["hotel"]},
    }


def test_booking_com_property_discovery_rejects_short_queries():
    provider = BookingComProvider(
        "secret",
        "affiliate-1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: None)),
    )
    try:
        try:
            asyncio.run(provider.discover_properties("ab"))
        except ValueError as error:
            assert "3+" in str(error)
        else:
            raise AssertionError("Expected short query to be rejected")
    finally:
        asyncio.run(provider.client.aclose())


def test_ota_mapping_loader_ignores_blank_property_ids(tmp_path):
    config = tmp_path / "ota.yaml"
    config.write_text(
        "providers:\n  booking_com:\n    enabled: true\n    properties:\n"
        "      capella_taipei: '123456'\n      mo_taipei: ''\n",
        encoding="utf-8",
    )
    enabled, mappings = load_ota_property_mappings(config, "booking_com")
    assert enabled is True
    assert mappings == {"capella_taipei": "123456"}
