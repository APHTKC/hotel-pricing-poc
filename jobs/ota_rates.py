import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

import httpx

from app.models import JobResult
from app.settings import Settings, get_settings
from config.loader import load_hotels
from jobs.daily_rates import parse_lead_days
from scrapers.ota.booking_com import BookingComProvider
from scrapers.ota.config import load_ota_property_mappings
from services.adapter_health import AdapterHealthStore, BackoffPolicy, status_code_from_exception
from storage.factory import get_store

logger = logging.getLogger(__name__)


async def run_ota_rates(settings: Settings | None = None, health_store: AdapterHealthStore | None = None) -> JobResult:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)
    started = datetime.now(UTC)
    run_id = str(uuid4())
    scheduled_for = started
    observations = []
    failures: list[dict[str, str]] = []
    health_store = health_store or AdapterHealthStore(
        settings.adapter_health_path,
        settings.diagnostic_snapshot_dir,
        BackoffPolicy(settings.backoff_failure_threshold, settings.backoff_base_minutes, settings.backoff_blocked_base_minutes, settings.backoff_max_minutes),
    )
    enabled, mappings = load_ota_property_mappings(
        settings.ota_config_path, "booking_com"
    )

    if not enabled:
        logger.info("Booking.com OTA collection is disabled")
    elif not settings.booking_com_api_key or not settings.booking_com_affiliate_id:
        logger.info("Booking.com OTA collection skipped: partner credentials are not configured")
    elif not mappings:
        logger.info("Booking.com OTA collection skipped: no property IDs are mapped")
    else:
        hotels = {hotel.id: hotel for hotel in load_hotels()}
        provider = BookingComProvider(
            settings.booking_com_api_key,
            settings.booking_com_affiliate_id,
            settings.ota_booker_country,
        )
        try:
            stop_provider = False
            for hotel_id, property_id in mappings.items():
                hotel = hotels.get(hotel_id)
                if hotel is None:
                    failures.append(
                        {"hotel_id": hotel_id, "lead_days": "", "error": "Unknown hotel mapping"}
                    )
                    continue
                cooldown = health_store.cooldown_until("booking_com", hotel_id, started)
                if cooldown:
                    failures.append({"hotel_id": hotel_id, "lead_days": "", "error": f"Cooldown active until {cooldown.isoformat()}"})
                    continue
                consecutive_empty = 0
                consecutive_failures = 0
                for lead_days in parse_lead_days(settings.lead_days):
                    check_in = started.date() + timedelta(days=lead_days)
                    request_started = perf_counter()
                    try:
                        rows = await provider.fetch_rates(
                            hotel, property_id, check_in, check_in + timedelta(days=1)
                        )
                        duration_ms = (perf_counter() - request_started) * 1000
                        consecutive_failures = 0
                        if not rows:
                            health_store.record_failure("booking_com", hotel_id, "No OTA rates returned", duration_ms)
                            consecutive_empty += 1
                            failures.append(
                                {
                                    "hotel_id": hotel_id,
                                    "lead_days": str(lead_days),
                                    "error": "No OTA rates returned",
                                }
                            )
                            if consecutive_empty >= 2:
                                logger.info(
                                    "Booking.com skipped remaining dates for %s after two empty responses",
                                    hotel_id,
                                )
                                break
                            continue
                        consecutive_empty = 0
                        observations.extend(
                            row.model_copy(
                                update={
                                    "run_id": run_id,
                                    "scheduled_for": scheduled_for,
                                }
                            )
                            for row in rows
                        )
                        health_store.record_success("booking_com", hotel_id, duration_ms)
                    except Exception as exc:
                        duration_ms = (perf_counter() - request_started) * 1000
                        status_code = status_code_from_exception(exc)
                        health_store.record_failure("booking_com", hotel_id, exc, duration_ms, status_code)
                        logger.exception("Booking.com fetch failed for %s +%s", hotel_id, lead_days)
                        failures.append(
                            {"hotel_id": hotel_id, "lead_days": str(lead_days), "error": str(exc)}
                        )
                        consecutive_failures += 1
                        if isinstance(exc, httpx.HTTPStatusError):
                            status = exc.response.status_code
                            if status in {401, 403, 429}:
                                logger.error(
                                    "Booking.com provider stopped after HTTP %s to avoid repeated requests",
                                    status,
                                )
                                stop_provider = True
                                break
                            if status in {400, 404, 422}:
                                logger.info(
                                    "Booking.com skipped remaining dates for %s after HTTP %s",
                                    hotel_id,
                                    status,
                                )
                                break
                        if consecutive_failures >= 2:
                            logger.info(
                                "Booking.com skipped remaining dates for %s after two failures",
                                hotel_id,
                            )
                            break
                if stop_provider:
                    break
        finally:
            await provider.close()

    written = get_store(settings).append(observations)
    return JobResult(
        started_at=started,
        finished_at=datetime.now(UTC),
        observations=written,
        failures=failures,
        storage_backend=settings.storage_backend,
    )
