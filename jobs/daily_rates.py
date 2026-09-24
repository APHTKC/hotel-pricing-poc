import asyncio
import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

from app.models import JobResult
from app.settings import Settings, get_settings
from config.loader import load_hotels
from scrapers.registry import get_scraper
from services.adapter_health import AdapterHealthStore, BackoffPolicy, status_code_from_exception
from storage.factory import get_store

logger = logging.getLogger(__name__)
MAX_CONSECUTIVE_FAILURES = 2


def parse_lead_days(value: str) -> tuple[int, ...]:
    days = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not days or any(day < 1 for day in days):
        raise ValueError("LEAD_DAYS must contain positive comma-separated integers")
    return days


async def run_daily_rates(settings: Settings | None = None, health_store: AdapterHealthStore | None = None) -> JobResult:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)
    started = datetime.now(UTC)
    run_id = str(uuid4())
    scheduled_for = started
    observations = []
    failures: list[dict[str, str]] = []
    today = started.date()
    health_store = health_store or AdapterHealthStore(
        settings.adapter_health_path,
        settings.diagnostic_snapshot_dir,
        BackoffPolicy(
            failure_threshold=settings.backoff_failure_threshold,
            base_minutes=settings.backoff_base_minutes,
            blocked_base_minutes=settings.backoff_blocked_base_minutes,
            max_minutes=settings.backoff_max_minutes,
        ),
    )

    for hotel in load_hotels():
        if not hotel.enabled:
            continue
        cooldown = health_store.cooldown_until(hotel.adapter, hotel.id, started)
        if cooldown:
            failures.append({"hotel_id": hotel.id, "lead_days": "", "error": f"Cooldown active until {cooldown.isoformat()}"})
            logger.info("Skipping %s during adapter cooldown until %s", hotel.id, cooldown.isoformat())
            continue
        try:
            scraper = get_scraper(hotel.adapter, settings)
        except Exception as exc:
            health_store.record_failure(hotel.adapter, hotel.id, exc, 0)
            failures.append({"hotel_id": hotel.id, "lead_days": "", "error": str(exc)})
            logger.exception("Adapter initialization failed for %s", hotel.id)
            continue
        try:
            consecutive_failures = 0
            for lead_days in parse_lead_days(settings.lead_days):
                check_in = today + timedelta(days=lead_days)
                request_started = perf_counter()
                try:
                    rates = await scraper.fetch_rates(hotel, check_in, check_in + timedelta(days=1))
                    duration_ms = (perf_counter() - request_started) * 1000
                    if not rates:
                        health_store.record_failure(hotel.adapter, hotel.id, "No public rates returned", duration_ms)
                        failures.append(
                            {
                                "hotel_id": hotel.id,
                                "lead_days": str(lead_days),
                                "error": "No public rates returned",
                            }
                        )
                        consecutive_failures += 1
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            logger.warning(
                                "Skipping remaining dates for %s after %s consecutive empty responses",
                                hotel.id,
                                consecutive_failures,
                            )
                            break
                        continue
                    observations.extend(
                        rate.model_copy(
                            update={
                                "district": rate.district or hotel.district,
                                "run_id": run_id,
                                "scheduled_for": scheduled_for,
                            }
                        )
                        for rate in rates
                    )
                    health_store.record_success(hotel.adapter, hotel.id, duration_ms)
                    consecutive_failures = 0
                except Exception as exc:  # One date/hotel must not stop the daily run.
                    duration_ms = (perf_counter() - request_started) * 1000
                    status_code = status_code_from_exception(exc)
                    health_store.record_failure(hotel.adapter, hotel.id, exc, duration_ms, status_code)
                    logger.exception("Rate fetch failed for %s +%s", hotel.id, lead_days)
                    failures.append({"hotel_id": hotel.id, "lead_days": str(lead_days), "error": str(exc)})
                    consecutive_failures += 1
                    if status_code in {403, 429}:
                        logger.warning("Skipping remaining dates for %s after HTTP %s", hotel.id, status_code)
                        break
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        logger.warning(
                            "Skipping remaining dates for %s after %s consecutive failures",
                            hotel.id,
                            consecutive_failures,
                        )
                        break
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
