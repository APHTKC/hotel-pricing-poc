from decimal import Decimal

from scrapers.adapters.gobooking import PROPERTIES, parse_room_size, split_tax_inclusive_total


def test_parse_room_size():
    assert parse_room_size("9坪/30平方公尺") == Decimal("30")
    assert parse_room_size("房間佔地約11坪(37 平方公尺)") == Decimal("37")
    assert parse_room_size("房間大小：6.5坪 / 21平方米") == Decimal("21")
    assert parse_room_size("unknown") is None


def test_split_tax_inclusive_total():
    assert split_tax_inclusive_total(Decimal("5544")) == (
        Decimal("4800"),
        Decimal("480"),
        Decimal("264"),
    )


def test_solaria_uses_verified_gobooking_property():
    assert PROPERTIES["solaria_nishitetsu_taipei"]["slug"] == "SOLARIA-TPXM"
    assert PROPERTIES["solaria_nishitetsu_taipei"]["plan_code"] == (
        "a25b928f-1de1-4e85-af69-2b62e246fd25"
    )
