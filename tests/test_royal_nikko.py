from decimal import Decimal

from scrapers.adapters.royal_nikko import parse_breakfast, parse_room_size


def test_parse_room_size():
    assert parse_room_size("面積大約26平方公尺") == Decimal("26")
    assert parse_room_size("面積約50 平方公尺") == Decimal("50")
    assert parse_room_size("unknown") is None


def test_parse_breakfast():
    assert parse_breakfast("專案無早餐") is False
    assert parse_breakfast("生日祝房專案|一泊一食國人專案") is True
    assert parse_breakfast("一般住房專案") is None
