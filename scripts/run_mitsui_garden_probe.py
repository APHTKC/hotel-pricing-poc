import asyncio
import json
from datetime import date, timedelta

from app.models import Hotel
from scrapers.adapters.synxis import SynxisScraper


async def main() -> None:
    hotel = Hotel(
        id="mitsui_garden_taipei_zhongxiao",
        name="MGH Mitsui Garden Hotel Taipei Zhongxiao",
        short_name="Mitsui Garden",
        city="Taipei",
        district="Da'an",
        country="TW",
        booking_url="https://be.synxis.com/?chain=26262&hotel=31000&locale=zh-TW",
        adapter="synxis",
    )
    scraper = SynxisScraper()
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
                "tax_inclusion": row.tax_inclusion.value,
            }
            for row in rows
        ], ensure_ascii=False, indent=2))
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
