from decimal import Decimal
from datetime import date

from scrapers.adapters.capella import (
    breakfast_included,
    cancellation_text,
    parse_money,
    parse_room_size,
    CapellaScraper,
)


def test_capella_parsers():
    assert parse_money("$31,300") == Decimal("31300")
    assert parse_room_size("48 平方米") == Decimal("48")
    features = ["抵達前免費取消最多 15:00 1 天", "以信用卡擔保", "含早餐"]
    assert breakfast_included(features) is True
    assert cancellation_text(features) == "抵達前免費取消最多 15:00 1 天"


def test_capella_booking_url_contains_official_ids_and_dates():
    url = CapellaScraper().booking_url(date(2026, 8, 29), date(2026, 8, 30), 2)
    assert "Hotel=47696" in url
    assert "Chain=21430" in url
    assert "arrive=2026-08-29" in url
    assert "adult=2" in url
