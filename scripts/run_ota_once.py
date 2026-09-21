import asyncio

from jobs.ota_rates import run_ota_rates


if __name__ == "__main__":
    print(asyncio.run(run_ota_rates()).model_dump_json(indent=2))
