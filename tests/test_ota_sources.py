import asyncio
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx

from app.models import Hotel
from app.models import RateObservation, ScrapeStatus
from scrapers.ota.base import OtaRateProvider
from scrapers.ota.booking_com import BookingComProvider, _room_size_sqm, parse_availability
from scrapers.ota.config import load_ota_property_mappings
from scrapers.ota.registry import OTA_PROVIDER_SPECS, configured_ota_providers
from services.rate_parity import canonical_comparison_key


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


def test_booking_com_room_size_requires_and_normalizes_explicit_units():
    assert _room_size_sqm({"value": 55, "unit": "SQM"}) == Decimal("55")
    assert _room_size_sqm({"value": 538, "unit": "sqft"}) == Decimal("49.98")
    assert _room_size_sqm({"value": 55}) is None
    assert _room_size_sqm(55) is None
    assert _room_size_sqm({"value": 55, "unit": "unknown"}) is None


def test_booking_com_parser_uses_normalized_room_size_for_comparison():
    rows = parse_availability(
        {
            "data": {
                "currency": "TWD",
                "rooms": [
                    {
                        "id": 55,
                        "name": "Deluxe King",
                        "size": {"value": 538, "unit": "SQFT"},
                    }
                ],
                "products": [
                    {
                        "id": "product-1",
                        "room": 55,
                        "policies": {
                            "meal_plan": {"plan": "room_only"},
                            "cancellation": {"type": "non_refundable"},
                        },
                        "price": {"total": {"booker_currency": 9000}},
                    }
                ],
            }
        },
        _hotel(),
        "123456",
        date(2026, 10, 2),
        date(2026, 10, 3),
        2,
        datetime(2026, 9, 21, tzinfo=timezone.utc),
    )

    assert rows[0].room_size_sqm == Decimal("49.98")
    assert rows[0].size_band == "45–59㎡"


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


def test_visible_browser_check_log_is_structured_and_non_retrying():
    path = Path("data/ota_browser_checks.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert rows
    keys = set()
    for row in rows:
        assert row["status"] in {"no_availability", "blocked", "verification_required"}
        assert row["reason"]
        assert row["occupancy"] == {"adults": 2, "children": 0, "rooms": 1}
        key = (
            row["hotel_id"],
            row["source_platform"],
            row["check_in"],
            row["check_out"],
        )
        assert key not in keys
        keys.add(key)


def test_repository_visible_browser_snapshots_are_canonical_products():
    path = Path("data/ota_browser_snapshots.jsonl")
    rows = [
        RateObservation.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert {row.hotel_id for row in rows} >= {
        "capella_taipei",
        "w_taipei",
        "hotel_metropolitan_premier_taipei",
    }
    assert all(row.source_method == "visible_browser_snapshot" for row in rows)
    assert all(canonical_comparison_key(row) is not None for row in rows)
    w_rows = [row for row in rows if row.hotel_id == "w_taipei"]
    assert {row.breakfast_included for row in w_rows} == {False, True}
    assert {row.total_price for row in w_rows} == {Decimal("15015"), Decimal("16632")}
    jr_rows = [
        row for row in rows
        if row.hotel_id == "hotel_metropolitan_premier_taipei"
    ]
    assert len(jr_rows) == 3
    assert {row.room_size_sqm for row in jr_rows} == {Decimal("36"), Decimal("43")}
    assert {row.total_price for row in jr_rows} == {Decimal("6696"), Decimal("7254")}


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
