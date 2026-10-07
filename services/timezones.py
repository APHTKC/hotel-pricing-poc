from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def local_date_at(moment: datetime, timezone_name: str) -> date:
    """Return the calendar date at ``moment`` in an IANA timezone."""
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {timezone_name}") from exc
    return moment.astimezone(timezone).date()


def utc_now() -> datetime:
    return datetime.now(UTC)
