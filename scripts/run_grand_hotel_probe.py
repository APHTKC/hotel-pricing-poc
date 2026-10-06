import asyncio
import json
from datetime import date, timedelta

from app.models import Hotel
from scrapers.adapters.grand_hilai import GrandHiLaiScraper


async def main() -> None:
    hotel = Hotel(
        id="grand_hotel_taipei",
        name="The Grand Hotel Taipei",
        short_name="Grand Hotel",
        city="Taipei",
        district="Zhongshan",
        country="TW",
        booking_url="https://tlathena.ec-hotel.net/webhotel-v5/1071",
        adapter="grand_hilai",
    )
    scraper = GrandHiLaiScraper()
    try:
        check_in = date.today() + timedelta(days=30)
        rows = await scraper.fetch_rates(
            hotel, check_in, check_in + timedelta(days=1)
        )
        print(json.dumps([
            {
                "hotel_id": row.hotel_id,
                "check_in": row.check_in.isoformat(),
                "room": row.room_type_name,
                "size_sqm": str(row.room_size_sqm) if row.room_size_sqm else None,
                "rate": row.rate_plan_name,
                "total": str(row.total_price),
                "currency": row.currency,
            }
            for row in rows
        ], ensure_ascii=False, indent=2))
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
