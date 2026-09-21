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
