from datetime import date

from app.models import Hotel
from scrapers.adapters.ihg import IHGScraper, ihg_month


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
    assert "/intercontinental/" in taichung_url and "qSlH=RMQTT" in taichung_url
    assert "qSHBrC=IC" in taichung_url and "qCiMy=092026" in taichung_url
    assert "qSlH=KHHKT" in kaohsiung_url and "Kaohsiung" in kaohsiung_url
