import asyncio

from jobs.daily_rates import run_daily_rates


async def main() -> None:
    result = await run_daily_rates()
    print(result.model_dump_json(indent=2))
    if result.observations == 0:
        raise SystemExit("No live observations were collected; existing published data was preserved.")


if __name__ == "__main__":
    asyncio.run(main())
