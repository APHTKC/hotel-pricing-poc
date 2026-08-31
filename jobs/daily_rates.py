import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.models import JobResult
from app.settings import Settings, get_settings
from config.loader import load_hotels
from scrapers.registry import get_scraper
from storage.factory import get_store

LEAD_DAYS = (1, 7, 14, 30, 60, 90)
logger = logging.getLogger(__name__)


async def run_daily_rates(settings: Settings | None = None) -> JobResult:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)
    started = datetime.now(UTC)
    observations = []
    failures: list[dict[str, str]] = []
    today = started.date()

    for hotel in load_hotels():
        if not hotel.enabled:
            continue
        scraper = get_scraper(hotel.adapter, settings)
        try:
            for lead_days in LEAD_DAYS:
                check_in = today + timedelta(days=lead_days)
                try:
                    observations.extend(
                        await scraper.fetch_rates(hotel, check_in, check_in + timedelta(days=1))
                    )
                except Exception as exc:  # One date/hotel must not stop the daily run.
                    logger.exception("Rate fetch failed for %s +%s", hotel.id, lead_days)
                    failures.append({"hotel_id": hotel.id, "lead_days": str(lead_days), "error": str(exc)})
        finally:
            await scraper.close()

    written = get_store(settings).append(observations)
    return JobResult(
        started_at=started,
        finished_at=datetime.now(UTC),
        observations=written,
        failures=failures,
        storage_backend=settings.storage_backend,
    )


if __name__ == "__main__":
    print(asyncio.run(run_daily_rates()).model_dump_json(indent=2))
