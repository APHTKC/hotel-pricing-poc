import logging
from datetime import UTC, datetime, timedelta

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
            for hotel_id, property_id in mappings.items():
                hotel = hotels.get(hotel_id)
                if hotel is None:
                    failures.append(
                        {"hotel_id": hotel_id, "lead_days": "", "error": "Unknown hotel mapping"}
                    )
                    continue
                for lead_days in parse_lead_days(settings.lead_days):
                    check_in = started.date() + timedelta(days=lead_days)
                    try:
                        observations.extend(
                            await provider.fetch_rates(
                                hotel, property_id, check_in, check_in + timedelta(days=1)
                            )
                        )
                    except Exception as exc:
                        logger.exception("Booking.com fetch failed for %s +%s", hotel_id, lead_days)
                        failures.append(
                            {"hotel_id": hotel_id, "lead_days": str(lead_days), "error": str(exc)}
                        )
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
