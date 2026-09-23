import json
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import RateObservation, ScrapeStatus
from services.deduplication import deduplicate_observations, observation_natural_key
from storage.local_jsonl import LocalJsonlStore


def observation(*, observation_id: str, queried_at: datetime, price: str = "10000"):
    return RateObservation(
        observation_id=observation_id,
        run_id=f"run-{observation_id}",
        scheduled_for=queried_at,
        queried_at=queried_at,
        check_in=date(2026, 10, 1),
        check_out=date(2026, 10, 2),
        lead_days=7,
        hotel_id="hotel",
        hotel_name="Hotel",
        room_type_code="ROOM",
        room_type_name="Room",
        rate_plan_code="BAR",
        rate_plan_name="Best Available Rate",
        total_price=Decimal(price),
        currency="TWD",
        source_url="https://example.com",
        status=ScrapeStatus.LIVE,
    )


def test_natural_key_uses_queried_calendar_date_not_exact_time():
    morning = observation(
        observation_id="morning", queried_at=datetime(2026, 9, 24, 1, tzinfo=UTC)
    )
    evening = observation(
        observation_id="evening", queried_at=datetime(2026, 9, 24, 20, tzinfo=UTC)
    )

    assert observation_natural_key(morning) == observation_natural_key(evening)
    assert deduplicate_observations([morning, evening]) == [evening]


def test_local_jsonl_store_deduplicates_existing_and_current_batch(tmp_path):
    path = tmp_path / "rates.jsonl"
    store = LocalJsonlStore(path)
    first = observation(
        observation_id="first", queried_at=datetime(2026, 9, 24, 1, tzinfo=UTC)
    )
    duplicate = observation(
        observation_id="duplicate", queried_at=datetime(2026, 9, 24, 20, tzinfo=UTC)
    )

    assert store.append([first, duplicate]) == 1
    assert store.append([duplicate]) == 0
    saved = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["observation_id"] for row in saved] == ["first"]
    assert saved[0]["run_id"] == "run-first"
    assert saved[0]["scheduled_for"].startswith("2026-09-24T01:00:00")
