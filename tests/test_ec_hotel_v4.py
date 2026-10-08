import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from scrapers.adapters.ec_hotel_v4 import (
    PROPERTIES,
    include_rate_plan,
    parse_breakfast,
    parse_room_size,
    room_size_for,
    ECHotelV4Scraper,
)


def test_property_registry_contains_existing_and_hsinchu_hotels():
    assert PROPERTIES["royal_nikko_taipei"]["property_id"] == "0839"
    assert PROPERTIES["hotel_royal_hsinchu"]["property_id"] == "0232"
    assert PROPERTIES["radium_kagaya_taipei"]["property_id"] == "0918"
    assert PROPERTIES["the_lin_taichung"]["property_id"] == "0321"


def test_parse_room_size_supports_ec_hotel_units():
    assert parse_room_size("面積大約26平方公尺") == Decimal("26")
    assert parse_room_size("Room size 39 m²") == Decimal("39")
    assert parse_room_size("unknown") is None


def test_hsinchu_official_room_profile_fills_missing_booking_size():
    assert room_size_for("hotel_royal_hsinchu", "雅緻客房", "未顯示面積") == Decimal("36")
    assert room_size_for("hotel_royal_hsinchu", "豪華家庭客房", "未顯示面積") == Decimal("43")


def test_kagaya_official_room_profile_fills_exact_known_sizes_only():
    assert room_size_for(
        "radium_kagaya_taipei", "園景半露天風呂套房", "未顯示面積"
    ) == Decimal("53")
    assert room_size_for(
        "radium_kagaya_taipei", "特別室套房", "未顯示面積"
    ) == Decimal("105")


def test_the_lin_official_room_profile_fills_missing_booking_size():
    assert room_size_for("the_lin_taichung", "豪華客房", "未顯示面積") == Decimal("50")
    assert room_size_for(
        "the_lin_taichung", "國王行宮總統套房 2501", "未顯示面積"
    ) == Decimal("218")


def test_breakfast_and_public_offer_filtering():
    assert parse_breakfast("國人住房專案｜不含早") is False
    assert parse_breakfast("國人住房專案｜含早") is True
    assert include_rate_plan("hotel_royal_hsinchu", "國人住房專案｜含早") is True
    assert include_rate_plan("hotel_royal_hsinchu", "2026夏季旅展｜住宿券") is False
    assert include_rate_plan("royal_nikko_taipei", "一般住房專案") is True


def test_fetch_accepts_attached_hidden_rate_rows(monkeypatch):
    """The engine may keep valid rate rows hidden behind its project tab."""

    page = MagicMock()
    page.url = PROPERTIES["hotel_royal_hsinchu"]["booking_url"]
    page.goto = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.close = AsyncMock()
    loading = MagicMock()
    loading.count = AsyncMock(return_value=0)
    room_rows = MagicMock()
    first_row = MagicMock()
    first_row.wait_for = AsyncMock()
    room_rows.first = first_row

    def locator(selector):
        if selector == ".el-loading-mask":
            return loading
        if selector == "#athTabpage__cntainRoom > .row.mb-40 .athTable__row":
            return room_rows
        element = MagicMock()
        element.click = AsyncMock()
        return element

    page.locator.side_effect = locator
    scraper = ECHotelV4Scraper()
    scraper._page = AsyncMock(return_value=page)
    scraper._collect = AsyncMock(return_value=[MagicMock()])
    monkeypatch.setattr(
        "scrapers.adapters.ec_hotel_v4.dismiss_startup_overlays", AsyncMock()
    )
    monkeypatch.setattr(
        "scrapers.adapters.ec_hotel_v4.select_calendar_date", AsyncMock()
    )
    hotel = MagicMock()
    hotel.id = "hotel_royal_hsinchu"

    asyncio.run(scraper.fetch_rates(hotel, date(2026, 11, 7), date(2026, 11, 8)))

    first_row.wait_for.assert_awaited_once_with(
        state="attached", timeout=scraper.timeout_ms
    )
