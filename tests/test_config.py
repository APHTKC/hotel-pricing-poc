from config.loader import load_hotels


def test_nine_taipei_hotels_have_known_adapters():
    hotels = load_hotels()
    assert len(hotels) == 9
    assert {hotel.city for hotel in hotels} == {"Taipei"}
    assert all(hotel.booking_url.startswith("https://") for hotel in hotels)
