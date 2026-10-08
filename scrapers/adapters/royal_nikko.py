from scrapers.adapters.ec_hotel_v4 import (
    ECHotelV4Scraper,
    dismiss_startup_overlays,
    parse_breakfast,
    parse_room_size,
    select_calendar_date,
)


BOOKING_URL = "https://tlathena.ec-hotel.net/webhotel-v4/0839/index"


class RoyalNikkoScraper(ECHotelV4Scraper):
    """Backward-compatible adapter name for the existing Taipei property."""

    diagnostic_name = "Royal-Nikko Taipei"
