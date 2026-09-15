from datetime import date

from app.models import Hotel
from decimal import Decimal

from scrapers.adapters.ihg import IHGScraper, ihg_month, parse_rate_card


def test_ihg_month_is_zero_based():
    assert ihg_month(date(2026, 9, 10)) == "082026"


def test_regent_booking_url():
    hotel = Hotel(id="regent_taipei", name="Regent Taipei", short_name="Regent", city="Taipei", country="TW", booking_url="https://example.com", adapter="ihg")
    url = IHGScraper().booking_url(hotel, date(2026, 10, 9), date(2026, 10, 10), 2)
    assert "qSlH=TPERG" in url and "qAdlt=2" in url and "qDest=" in url
    assert "qCiD=09" in url and "qCiMy=092026" in url


def test_intercontinental_booking_urls():
    taichung = Hotel(id="intercontinental_taichung", name="InterContinental Taichung", short_name="IC Taichung", city="Taichung", country="TW", booking_url="https://example.com", adapter="ihg")
    kaohsiung = Hotel(id="intercontinental_kaohsiung", name="InterContinental Kaohsiung", short_name="IC Kaohsiung", city="Kaohsiung", country="TW", booking_url="https://example.com", adapter="ihg")
    scraper = IHGScraper()
    taichung_url = scraper.booking_url(taichung, date(2026, 10, 11), date(2026, 10, 12), 2)
    kaohsiung_url = scraper.booking_url(kaohsiung, date(2026, 10, 11), date(2026, 10, 12), 2)
    assert "/hotels/tw/zh/find-hotels/select-roomrate?" in taichung_url
    assert "qSlH=RMQTT" in taichung_url and "qAkamaiCC=TW" in taichung_url
    assert "qSHBrC=IC" in taichung_url and "qCiMy=092026" in taichung_url
    assert "qAAR=6CBARC" in taichung_url and "qpMn=0" in taichung_url
    assert "%E8%87%BA%E4%B8%AD%E5%8B%A4%E7%BE%8E%E6%B4%B2%E9%9A%9B%E9%85%92%E5%BA%97" in taichung_url
    assert "/hotels/tw/zh/find-hotels/hotel/rooms?" in kaohsiung_url
    assert "qSlH=KHHKT" in kaohsiung_url and "Kaohsiung" in kaohsiung_url
    assert "qIta=99618783" in kaohsiung_url and "qSmP=1" in kaohsiung_url
    assert "qAkamaiCC=TW" in kaohsiung_url


def test_parse_current_ihg_rate_card():
    result = parse_rate_card(
        "Best Flexible With Breakfast\nFully refundable before Oct 13, 2026\n"
        "No prepayment needed - pay at the property\nDaily Breakfast Included\n"
        "10,589\nTWD\nper night\nSelect"
    )
    assert result == (
        "Best Flexible With Breakfast",
        Decimal("10589"),
        True,
        "Fully refundable before Oct 13, 2026 No prepayment needed - pay at the property Daily Breakfast Included",
    )
