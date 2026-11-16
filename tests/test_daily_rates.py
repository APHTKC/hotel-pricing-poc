import asyncio
from datetime import UTC, datetime
from pathlib import Path

import yaml

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


def test_daily_config_keeps_international_and_japanese_chains_in_core_scope():
    payload = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    hotels = {row["id"]: row for row in payload["hotels"]}

    for hotel_id in {
        "mitsui_garden_taipei_zhongxiao",
        "solaria_nishitetsu_taipei",
        "hotel_metropolitan_premier_taipei",
        "okura_prestige_taipei",
        "royal_nikko_taipei",
        "hotel_nikko_kaohsiung",
        "hoshinoya_guguan",
    }:
        assert hotels[hotel_id].get("market_scope", "core") == "core"
        assert hotels[hotel_id].get("collection_frequency", "daily") == "daily"

    supplemental = {
        hotel_id
        for hotel_id, row in hotels.items()
        if row.get("market_scope") == "supplemental"
    }
    assert supplemental == {
        "united_hotel_taipei",
        "k_hotel_taipei_changan",
        "tango_hotel_taichung",
        "tango_hotel_taipei_jiantan",
        "tango_hotel_taipei_xinyi",
        "tango_hotel_taipei_shilin",
        "tango_hotel_taipei_linsen",
        "tango_hotel_taipei_changan",
        "tango_hotel_taipei_fuhsing",
        "tango_hotel_taipei_nanshi",
    }


def test_daily_job_checks_all_dates_without_cooling_down_on_empty_availability(monkeypatch, tmp_path):
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
            Settings(
                demo_mode=False,
                lead_days="1,7,14,30,60,90",
                adapter_health_path=tmp_path / "health.json",
                diagnostic_snapshot_dir=tmp_path / "diagnostics",
            )
        )
    )

    assert scraper.calls == 6
    assert scraper.closed is True
    assert result.observations == 0
    assert len(result.failures) == 6
    assert {failure["lead_days"] for failure in result.failures} == {"1", "7", "14", "30", "60", "90"}
    assert all(failure["error"] == "No public rates returned" for failure in result.failures)
    health = __import__("json").loads((tmp_path / "health.json").read_text(encoding="utf-8"))
    record = health["adapters"]["empty:empty_hotel"]
    assert record["empty_responses"] == 6
    assert record["failures"] == 0
    assert record["cooldown_until"] is None


def test_daily_job_assigns_one_run_id_and_schedule_to_all_rows(monkeypatch, tmp_path):
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

    asyncio.run(daily_rates.run_daily_rates(
        Settings(
            demo_mode=False,
            lead_days="1,7",
            rate_run_id="workflow-123",
            adapter_health_path=tmp_path / "health.json",
            diagnostic_snapshot_dir=tmp_path / "diagnostics",
        ),
        started_at=datetime(2026, 10, 6, 22, 0, tzinfo=UTC),
    ))

    assert len(store.rows) == 2
    assert {row.run_id for row in store.rows} == {"workflow-123"}
    assert all(row.scheduled_for is not None for row in store.rows)
    assert [row.check_in.isoformat() for row in store.rows] == ["2026-10-08", "2026-10-14"]
    assert [row.lead_days for row in store.rows] == [1, 7]


def test_daily_job_skips_supplemental_weekly_hotels_outside_sunday(monkeypatch, tmp_path):
    hotel = Hotel(
        id="supplemental_hotel",
        name="Supplemental Hotel",
        short_name="Supplemental",
        city="Taipei",
        country="TW",
        booking_url="https://example.com",
        adapter="test",
        market_scope="supplemental",
        collection_frequency="weekly",
    )
    store = MemoryStore()
    monkeypatch.setattr(daily_rates, "load_hotels", lambda: [hotel])
    monkeypatch.setattr(
        daily_rates,
        "get_scraper",
        lambda *args: (_ for _ in ()).throw(AssertionError("weekly hotel should be skipped")),
    )
    monkeypatch.setattr(daily_rates, "get_store", lambda settings: store)

    result = asyncio.run(
        daily_rates.run_daily_rates(
            Settings(
                demo_mode=False,
                lead_days="1",
                adapter_health_path=tmp_path / "health.json",
                diagnostic_snapshot_dir=tmp_path / "diagnostics",
            ),
            # 2026-11-16 06:17 in Asia/Taipei is a Monday.
            started_at=datetime(2026, 11, 15, 22, 17, tzinfo=UTC),
        )
    )

    assert result.observations == 0
    assert result.failures == []
    assert store.rows == []
