import asyncio

from jobs.daily_rates import run_daily_rates


async def main() -> None:
    result = await run_daily_rates()
    print(result.model_dump_json(indent=2))
    if result.observations == 0 or result.failures:
        raise SystemExit("Mandarin Oriental probe did not complete cleanly")


if __name__ == "__main__":
    asyncio.run(main())
