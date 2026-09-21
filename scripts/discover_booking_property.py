"""Find Booking.com property IDs one hotel at a time using the official API."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import get_settings
from config.loader import load_hotels
from scrapers.ota.booking_com import BookingComProvider


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find ranked Booking.com property candidates for one catalog hotel."
    )
    parser.add_argument("hotel_id", help="Internal hotel id from config/hotels.yaml")
    parser.add_argument(
        "--language", default="en-gb", help="Booking.com response language"
    )
    parser.add_argument(
        "--query", help="Optional search text; defaults to the catalog hotel name"
    )
    return parser.parse_args()


async def discover(hotel_id: str, query: str | None, language: str) -> dict:
    settings = get_settings()
    if not settings.booking_com_api_key or not settings.booking_com_affiliate_id:
        raise SystemExit(
            "Booking.com partner credentials are missing. Set "
            "BOOKING_COM_API_KEY and BOOKING_COM_AFFILIATE_ID first."
        )
    hotels = {hotel.id: hotel for hotel in load_hotels()}
    if hotel_id not in hotels:
        raise SystemExit(f"Unknown hotel_id: {hotel_id}")
    hotel = hotels[hotel_id]
    provider = BookingComProvider(
        settings.booking_com_api_key,
        settings.booking_com_affiliate_id,
        settings.ota_booker_country,
    )
    try:
        candidates = await provider.discover_properties(
            query or hotel.name,
            country=hotel.country,
            language=language,
        )
    finally:
        await provider.close()
    return {
        "hotel_id": hotel.id,
        "catalog_name": hotel.name,
        "query": query or hotel.name,
        "candidates": candidates,
        "mapping_hint": (
            f'{hotel.id}: "{candidates[0]["id"]}"' if candidates else None
        ),
    }


if __name__ == "__main__":
    args = _arguments()
    print(
        json.dumps(
            asyncio.run(discover(args.hotel_id, args.query, args.language)),
            ensure_ascii=False,
            indent=2,
        )
    )
