import asyncio
import os

from app.settings import get_settings
from jobs.daily_rates import run_daily_rates


async def main() -> None:
    os.environ["HOTELS_CONFIG_PATH"] = "config/hotels.windsor-taichung-only.yaml"
    os.environ.setdefault("LEAD_DAYS", "7")
    print((await run_daily_rates(get_settings())).model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
