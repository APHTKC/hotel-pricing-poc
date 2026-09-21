import logging
from datetime import UTC, datetime, timedelta

import httpx

from app.models import JobResult
from app.settings import Settings, get_settings
from config.loader import load_hotels
from jobs.daily_rates import parse_lead_days
from scrapers.ota.booking_com import BookingComProvider
from scrapers.ota.config import load_ota_property_mappings
from storage.factory import get_store

logger = logging.getLogger(__name__)


async def run_ota_rates(settings: Settings | None = None) -> JobResult:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)
    started = datetime.now(UTC)
    observations = []
    failures: list[dict[str, str]] = []
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
                consecutive_empty = 0
                consecutive_failures = 0
                for lead_days in parse_lead_days(settings.lead_days):
                    check_in = started.date() + timedelta(days=lead_days)
                    try:
                        rows = await provider.fetch_rates(
                            hotel, property_id, check_in, check_in + timedelta(days=1)
                        )
                        consecutive_failures = 0
                        if not rows:
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
                        observations.extend(rows)
                    except Exception as exc:
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
