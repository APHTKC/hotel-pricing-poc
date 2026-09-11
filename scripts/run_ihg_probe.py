import asyncio
import os

from app.settings import get_settings
from jobs.daily_rates import run_daily_rates


async def main() -> None:
    os.environ["HOTELS_CONFIG_PATH"] = os.environ.get(
        "IHG_PROBE_CONFIG", "config/hotels.intercontinental-taichung-only.yaml"
    )
    os.environ["LEAD_DAYS"] = os.environ.get("LEAD_DAYS", "30")
    get_settings.cache_clear()
    result = await run_daily_rates()
    print(result.model_dump_json(indent=2))
    if result.observations == 0 or result.failures:
        raise SystemExit("IHG hotel probe did not collect clean live data")


if __name__ == "__main__":
    asyncio.run(main())
