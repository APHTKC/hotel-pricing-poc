import asyncio

from app.models import Hotel
from app.settings import Settings
from jobs import daily_rates


class EmptyScraper:
    def __init__(self):
        self.calls = 0
        self.closed = False

    async def fetch_rates(self, hotel, check_in, check_out, adults=2):
        self.calls += 1
        return []

    async def close(self):
        self.closed = True


class MemoryStore:
    def __init__(self):
        self.rows = []

    def append(self, observations):
        self.rows.extend(observations)
        return len(observations)


def test_daily_job_skips_remaining_dates_after_two_empty_responses(monkeypatch):
    hotel = Hotel(
        id="empty_hotel",
        name="Empty Hotel",
        short_name="Empty",
        city="Taipei",
        country="TW",
        booking_url="https://example.com",
        adapter="empty",
    )
    scraper = EmptyScraper()
    store = MemoryStore()
    monkeypatch.setattr(daily_rates, "load_hotels", lambda: [hotel])
    monkeypatch.setattr(daily_rates, "get_scraper", lambda adapter, settings: scraper)
    monkeypatch.setattr(daily_rates, "get_store", lambda settings: store)

    result = asyncio.run(
        daily_rates.run_daily_rates(
            Settings(demo_mode=False, lead_days="1,7,14,30,60,90")
        )
    )

    assert scraper.calls == 2
    assert scraper.closed is True
    assert result.observations == 0
    assert len(result.failures) == 2
    assert {failure["lead_days"] for failure in result.failures} == {"1", "7"}
    assert all(failure["error"] == "No public rates returned" for failure in result.failures)


def test_daily_job_assigns_one_run_id_and_schedule_to_all_rows(monkeypatch):
    class SuccessfulScraper:
        async def fetch_rates(self, hotel, check_in, check_out, adults=2):
            from datetime import UTC, datetime
            from decimal import Decimal

            from app.models import RateObservation, ScrapeStatus

            return [
                RateObservation(
                    observation_id=f"{hotel.id}-{check_in}",
                    queried_at=datetime.now(UTC),
                    check_in=check_in,
                    check_out=check_out,
                    lead_days=(check_in - datetime.now(UTC).date()).days,
                    hotel_id=hotel.id,
                    hotel_name=hotel.name,
                    room_type_code="ROOM",
                    room_type_name="Room",
                    rate_plan_code="BAR",
                    rate_plan_name="BAR",
                    total_price=Decimal("10000"),
                    currency="TWD",
                    source_url="https://example.com",
                    status=ScrapeStatus.LIVE,
                )
            ]

        async def close(self):
            return None

    hotel = Hotel(
        id="hotel",
        name="Hotel",
        short_name="Hotel",
        city="Taipei",
        country="TW",
        booking_url="https://example.com",
        adapter="test",
    )
    store = MemoryStore()
    monkeypatch.setattr(daily_rates, "load_hotels", lambda: [hotel])
    monkeypatch.setattr(daily_rates, "get_scraper", lambda *args: SuccessfulScraper())
    monkeypatch.setattr(daily_rates, "get_store", lambda settings: store)

    asyncio.run(daily_rates.run_daily_rates(Settings(demo_mode=False, lead_days="1,7")))

    assert len(store.rows) == 2
    assert len({row.run_id for row in store.rows}) == 1
    assert store.rows[0].run_id
    assert all(row.scheduled_for is not None for row in store.rows)
