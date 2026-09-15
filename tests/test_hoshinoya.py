from datetime import date
from decimal import Decimal

from scrapers.adapters.hoshinoya import booking_url, meal_included, plan_code, room_size


def test_hoshinoya_booking_url():
    url = booking_url(date(2026, 10, 15), date(2026, 10, 16), 2)
    assert "/CH/hotels/0000000503/search?" in url
    assert "checkIn=2026%2F10%2F15" in url
    assert "stay=1" in url and "a=2" in url


def test_hoshinoya_room_and_plan_helpers():
    assert room_size("1〜2位 75㎡ 雙人床") == Decimal("75")
    assert plan_code("/rooms/6/plans/0000000016?stay=1") == "0000000016"
    assert meal_included("基本住宿專案(不含餐)") is False
    assert meal_included("基本住宿專案(含早晚餐)") is True
