from datetime import date, datetime, timezone
from decimal import Decimal

from app.models import RateObservation, ScrapeStatus
from scrapers.ota.base import OtaRateProvider
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
