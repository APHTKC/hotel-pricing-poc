from config.loader import load_hotels
from scrapers.registry import ADAPTERS


def test_daily_tracking_catalog_is_the_default_and_has_known_adapters():
    hotels = load_hotels()
    assert len(hotels) == 23
    assert any(hotel.id == "the_gaia_taipei" for hotel in hotels)
    assert any(hotel.id == "hotel_royal_hsinchu" for hotel in hotels)
    assert {hotel.city for hotel in hotels} == {
        "Kaohsiung",
        "Hsinchu",
        "Nantou",
        "Taichung",
        "Tainan",
        "Taipei",
        "Yilan",
    }
    assert all(hotel.enabled for hotel in hotels)
    assert {hotel.adapter for hotel in hotels} <= set(ADAPTERS)
    assert all(hotel.booking_url.startswith("https://") for hotel in hotels)
