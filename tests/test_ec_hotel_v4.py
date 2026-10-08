from decimal import Decimal

from scrapers.adapters.ec_hotel_v4 import (
    PROPERTIES,
    include_rate_plan,
    parse_breakfast,
    parse_room_size,
    room_size_for,
)


def test_property_registry_contains_existing_and_hsinchu_hotels():
    assert PROPERTIES["royal_nikko_taipei"]["property_id"] == "0839"
    assert PROPERTIES["hotel_royal_hsinchu"]["property_id"] == "0232"


def test_parse_room_size_supports_ec_hotel_units():
    assert parse_room_size("面積大約26平方公尺") == Decimal("26")
    assert parse_room_size("Room size 39 m²") == Decimal("39")
    assert parse_room_size("unknown") is None


def test_hsinchu_official_room_profile_fills_missing_booking_size():
    assert room_size_for("hotel_royal_hsinchu", "雅緻客房", "未顯示面積") == Decimal("36")
    assert room_size_for("hotel_royal_hsinchu", "豪華家庭客房", "未顯示面積") == Decimal("43")


def test_breakfast_and_public_offer_filtering():
    assert parse_breakfast("國人住房專案｜不含早") is False
    assert parse_breakfast("國人住房專案｜含早") is True
    assert include_rate_plan("hotel_royal_hsinchu", "國人住房專案｜含早") is True
    assert include_rate_plan("hotel_royal_hsinchu", "2026夏季旅展｜住宿券") is False
    assert include_rate_plan("royal_nikko_taipei", "一般住房專案") is True
