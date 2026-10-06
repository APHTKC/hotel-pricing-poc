from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models import Hotel, TaxInclusion
from scrapers.adapters.fastbooking import (
    FastBookingScraper,
    parse_widget_config,
    quotation_url,
)


def _config():
    return {
        "property": "twtai17118",
        "_authCode": "public-page-token",
        "baseHost": "https://websdk.fastbooking-services.com",
        "currency": "TWD",
        "locale": "zh_HK",
    }


def _hotel():
    return Hotel(
        id="taipei_garden_hotel",
        name="Taipei Garden Hotel",
        short_name="Taipei Garden",
        city="Taipei",
        district="Zhongzheng",
        country="TW",
        booking_url="https://www.taipeigarden.com.tw/en/",
        adapter="fastbooking",
    )


def test_parse_widget_config_requires_dynamic_public_credentials():
    assert parse_widget_config('{"property":"twtai17118","_authCode":"x",'
                               '"baseHost":"https://example.test"}')["property"] == "twtai17118"
    with pytest.raises(ValueError):
        parse_widget_config('{"property":"twtai17118"}')


def test_parse_widget_config_supports_current_nested_params_shape():
    parsed = parse_widget_config(
        '{"params":{"property":"twtai17118","currency":"TWD"},'
        '"_authCode":"x","baseHost":"https://example.test"}'
    )
    assert parsed["property"] == "twtai17118"
    assert parsed["currency"] == "TWD"


def test_parse_widget_config_supports_query_string_params():
    parsed = parse_widget_config(
        '{"params":"property=twtai17118&currency=TWD&locale=zh_HK",'
        '"propertyIndex":0,"_authCode":"x",'
        '"baseHost":"https://example.test"}'
    )
    assert parsed["property"] == "twtai17118"
    assert parsed["locale"] == "zh_HK"


def test_quotation_url_uses_requested_stay_and_occupancy():
    url = quotation_url(_config(), date(2026, 10, 13), date(2026, 10, 15), 2)
    assert "arrivalDate=2026-10-13" in url
    assert "nights=2" in url
    assert "adults=2" in url
    assert "property=twtai17118" in url
    assert "public-page-token" in url


def test_observations_preserve_unknown_terms_instead_of_guessing():
    rows = [{
        "adults": 2,
        "room": "Premier-Double",
        "rate": "Love-Our-Environment",
        "totalPrice": 3045,
        "currency": "TWD",
        "plainBookLink": "https://redirect.fastbooking.com/example",
    }]
    observations = FastBookingScraper._observations(
        rows,
        _hotel(),
        date(2026, 10, 13),
        date(2026, 10, 14),
        2,
        datetime(2026, 10, 6, 1, 0, tzinfo=UTC),
        _config(),
        "https://example.test/quotation",
    )
    assert len(observations) == 1
    rate = observations[0]
    assert rate.room_type_name == "Premier Double Room"
    assert rate.room_size_sqm == Decimal("22")
    assert rate.total_price == Decimal("3045")
    assert rate.tax_inclusion == TaxInclusion.UNKNOWN
    assert rate.breakfast_included is None
    assert rate.cancellation_policy is None
    assert rate.source_property_id == "twtai17118"
