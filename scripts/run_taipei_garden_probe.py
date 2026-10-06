import asyncio
import json
from datetime import date, timedelta

from app.models import Hotel
from scrapers.adapters.fastbooking import FastBookingScraper


async def main() -> None:
    hotel = Hotel(
        id="taipei_garden_hotel",
        name="Taipei Garden Hotel",
        short_name="Taipei Garden",
        city="Taipei",
        district="Zhongzheng",
        country="TW",
        booking_url="https://www.taipeigarden.com.tw/en/",
        adapter="fastbooking",
    )
    scraper = FastBookingScraper()
    try:
        check_in = date.today() + timedelta(days=7)
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
                "tax_inclusion": row.tax_inclusion.value,
                "source_property_id": row.source_property_id,
            }
            for row in rows
        ], ensure_ascii=False, indent=2))
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
