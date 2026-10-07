import asyncio
import json
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
    # ASCII-safe output keeps Windows CP950 diagnostics readable while GitHub
    # Actions continues to receive the complete structured result.
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=True, indent=2))
    if result.observations == 0 or result.failures:
        raise SystemExit("IHG hotel probe did not collect clean live data")


if __name__ == "__main__":
    asyncio.run(main())
