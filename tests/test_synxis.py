from decimal import Decimal
from datetime import date
from decimal import Decimal

from scrapers.adapters.synxis import (
    booking_url,
    room_size,
    split_tax_inclusive_total,
    tax_components,
)

def test_tax_components_match_public_synxis_total():
    assert tax_components(Decimal("4450")) == (Decimal("445"), Decimal("245"), Decimal("5140"))


def test_jr_east_booking_url_uses_official_property_ids():
    url = booking_url(
        "hotel_metropolitan_premier_taipei",
        date(2026, 10, 17),
        date(2026, 10, 18),
    )
    assert "chain=10197" in url
    assert "hotel=99659" in url


def test_mitsui_garden_booking_url_uses_official_property_ids():
    url = booking_url(
        "mitsui_garden_taipei_zhongxiao",
        date(2026, 11, 5),
        date(2026, 11, 6),
    )
    assert "chain=26262" in url
    assert "hotel=31000" in url


def test_mitsui_room_size_falls_back_to_verified_official_profile():
    assert room_size("mitsui_garden_taipei_zhongxiao", "精緻雙床套房") == Decimal("60.4")
    assert room_size("mitsui_garden_taipei_zhongxiao", "標準大床房 - Queen（禁菸）") == Decimal("22.7")
    assert room_size("mitsui_garden_taipei_zhongxiao", "豪華景隅雙床房（禁菸）") == Decimal("35.3")
    assert room_size("mitsui_garden_taipei_zhongxiao", "小型套房（禁菸）") == Decimal("60.4")
    assert room_size("mitsui_garden_taipei_zhongxiao", "Unknown room") is None
    assert room_size("mitsui_garden_taipei_zhongxiao", "Unknown room", "30.5 m²") == Decimal("30.5")


def test_tax_inclusive_synxis_total_is_not_added_twice():
    base, service, tax = split_tax_inclusive_total(Decimal("10890"))
    assert base + service + tax == Decimal("10890")
