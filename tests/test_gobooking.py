from decimal import Decimal

from scrapers.adapters.gobooking import parse_room_size, split_tax_inclusive_total


def test_parse_room_size():
    assert parse_room_size("9坪/30平方公尺") == Decimal("30")
    assert parse_room_size("房間佔地約11坪(37 平方公尺)") == Decimal("37")
    assert parse_room_size("unknown") is None


def test_split_tax_inclusive_total():
    assert split_tax_inclusive_total(Decimal("5544")) == (
        Decimal("4800"),
        Decimal("480"),
        Decimal("264"),
    )
