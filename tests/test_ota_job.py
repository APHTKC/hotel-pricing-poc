import asyncio
from datetime import UTC, datetime

import httpx

from app.models import Hotel
from app.settings import Settings
from jobs import ota_rates


class MemoryStore:
    def __init__(self):
        self.rows = []

    def append(self, rows):
        self.rows.extend(rows)
        return len(rows)


def _hotel(hotel_id: str) -> Hotel:
    return Hotel(
        id=hotel_id,
        name=f"Hotel {hotel_id}",
        short_name=hotel_id,
        city="Taipei",
        country="TW",
        booking_url="https://example.com",
        adapter="stub",
    )


def _settings(tmp_path) -> Settings:
    return Settings(
        booking_com_api_key="secret",
        booking_com_affiliate_id="affiliate",
        ota_config_path=tmp_path / "ota.yaml",
        local_data_path=tmp_path / "rates.jsonl",
        adapter_health_path=tmp_path / "health.json",
        diagnostic_snapshot_dir=tmp_path / "diagnostics",
        lead_days="1,7,14,30,60,90",
    )


def test_ota_job_skips_remaining_dates_after_two_empty_responses(
    monkeypatch, tmp_path
):
    class EmptyProvider:
        instance = None

        def __init__(self, *args):
            self.calls = 0
            self.closed = False
            EmptyProvider.instance = self

        async def fetch_rates(self, *args):
            self.calls += 1
            return []

        async def close(self):
            self.closed = True

    monkeypatch.setattr(
        ota_rates, "load_ota_property_mappings", lambda *args: (True, {"a": "1"})
    )
    monkeypatch.setattr(ota_rates, "load_hotels", lambda: [_hotel("a")])
    monkeypatch.setattr(ota_rates, "BookingComProvider", EmptyProvider)
    monkeypatch.setattr(ota_rates, "get_store", lambda settings: MemoryStore())

    result = asyncio.run(ota_rates.run_ota_rates(_settings(tmp_path)))

    assert EmptyProvider.instance.calls == 2
    assert EmptyProvider.instance.closed is True
    assert result.observations == 0
    assert [failure["error"] for failure in result.failures] == [
        "No OTA rates returned",
        "No OTA rates returned",
    ]


def test_ota_job_stops_provider_after_auth_failure(monkeypatch, tmp_path):
    class UnauthorizedProvider:
        instance = None

        def __init__(self, *args):
            self.calls = 0
            self.closed = False
            UnauthorizedProvider.instance = self

        async def fetch_rates(self, *args):
            self.calls += 1
            request = httpx.Request("POST", "https://demandapi.booking.com/test")
            response = httpx.Response(401, request=request)
            raise httpx.HTTPStatusError("Unauthorized", request=request, response=response)

        async def close(self):
            self.closed = True

    monkeypatch.setattr(
        ota_rates,
        "load_ota_property_mappings",
        lambda *args: (True, {"a": "1", "b": "2"}),
    )
    monkeypatch.setattr(ota_rates, "load_hotels", lambda: [_hotel("a"), _hotel("b")])
    monkeypatch.setattr(ota_rates, "BookingComProvider", UnauthorizedProvider)
    monkeypatch.setattr(ota_rates, "get_store", lambda settings: MemoryStore())

    result = asyncio.run(ota_rates.run_ota_rates(_settings(tmp_path)))

    assert UnauthorizedProvider.instance.calls == 1
    assert UnauthorizedProvider.instance.closed is True
    assert result.observations == 0
    assert len(result.failures) == 1
    assert result.failures[0]["hotel_id"] == "a"


def test_ota_job_uses_hotel_local_date_and_normalizes_lead_days(monkeypatch, tmp_path):
    class SuccessfulProvider:
        instance = None

        def __init__(self, *args):
            self.requests = []
            SuccessfulProvider.instance = self

        async def fetch_rates(self, hotel, property_id, check_in, check_out):
            from decimal import Decimal

            from app.models import RateObservation, ScrapeStatus

            self.requests.append(check_in)
            return [
                RateObservation(
                    observation_id=f"{hotel.id}-{check_in}",
                    queried_at=datetime(2026, 10, 6, 22, 0, tzinfo=UTC),
                    check_in=check_in,
                    check_out=check_out,
                    lead_days=0,
                    hotel_id=hotel.id,
                    hotel_name=hotel.name,
                    room_type_code="ROOM",
                    room_type_name="Room",
                    rate_plan_code="BAR",
                    rate_plan_name="BAR",
                    total_price=Decimal("10000"),
                    currency="TWD",
                    source_platform="booking_com",
                    source_url="https://example.com",
                    status=ScrapeStatus.LIVE,
                )
            ]

        async def close(self):
            return None

    store = MemoryStore()
    monkeypatch.setattr(
        ota_rates, "load_ota_property_mappings", lambda *args: (True, {"a": "1"})
    )
    monkeypatch.setattr(ota_rates, "load_hotels", lambda: [_hotel("a")])
    monkeypatch.setattr(ota_rates, "BookingComProvider", SuccessfulProvider)
    monkeypatch.setattr(ota_rates, "get_store", lambda settings: store)

    asyncio.run(
        ota_rates.run_ota_rates(
            _settings(tmp_path).model_copy(update={"lead_days": "1,7"}),
            started_at=datetime(2026, 10, 6, 22, 0, tzinfo=UTC),
        )
    )

    assert [item.isoformat() for item in SuccessfulProvider.instance.requests] == [
        "2026-10-08",
        "2026-10-14",
    ]
    assert [row.lead_days for row in store.rows] == [1, 7]
