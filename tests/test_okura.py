from datetime import date

from scrapers.adapters.okura import OkuraScraper


def test_okura_booking_url_contains_official_ids_and_dates():
    url = OkuraScraper().booking_url(date(2026, 10, 7), date(2026, 10, 8), 2)
    assert "Hotel=56124" in url
    assert "Chain=9542" in url
    assert "arrive=2026-10-07" in url
    assert "depart=2026-10-08" in url
    assert "config=EXCLTAX" in url
    assert "currency=TWD" in url
