from datetime import UTC, datetime

import pytest

from services.timezones import local_date_at


def test_local_date_uses_taipei_calendar_at_scheduled_run_time():
    run_time = datetime(2026, 10, 6, 22, 0, tzinfo=UTC)

    assert local_date_at(run_time, "Asia/Taipei").isoformat() == "2026-10-07"
    assert local_date_at(run_time, "UTC").isoformat() == "2026-10-06"


def test_local_date_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        local_date_at(datetime(2026, 10, 7, 6, 0), "Asia/Taipei")


def test_local_date_rejects_unknown_timezone():
    with pytest.raises(ValueError, match="Unknown IANA timezone"):
        local_date_at(datetime(2026, 10, 6, 22, 0, tzinfo=UTC), "Mars/Olympus")
