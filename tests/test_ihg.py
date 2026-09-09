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
