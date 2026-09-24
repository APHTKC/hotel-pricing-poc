import json
from datetime import UTC, datetime, timedelta

from services.adapter_health import AdapterHealthStore, BackoffPolicy, safe_reason


def store(tmp_path, **policy):
    return AdapterHealthStore(
        tmp_path / "health.json",
        tmp_path / "diagnostics",
        BackoffPolicy(**policy),
    )


def test_success_metrics_are_persisted(tmp_path):
    health = store(tmp_path)
    now = datetime(2026, 9, 24, tzinfo=UTC)
    health.record_success("synxis", "hotel-a", 125.5, now)

    reloaded = store(tmp_path)
    record = reloaded.data["adapters"]["synxis:hotel-a"]
    assert record["attempts"] == 1
    assert record["success_rate"] == 1
    assert record["average_response_ms"] == 125.5
    assert record["daily"]["2026-09-24"]["successes"] == 1


def test_generic_failures_trigger_exponential_backoff(tmp_path):
    health = store(tmp_path, failure_threshold=2, base_minutes=10)
    now = datetime(2026, 9, 24, tzinfo=UTC)
    assert health.record_failure("stub", "hotel-a", "empty", 10, now=now) is None
    cooldown = health.record_failure("stub", "hotel-a", "empty", 20, now=now)
    assert cooldown == now + timedelta(minutes=10)
    assert health.cooldown_until("stub", "hotel-a", now) == cooldown
    assert health.cooldown_until("stub", "hotel-a", cooldown) is None


def test_403_creates_cooldown_and_redacted_diagnostic(tmp_path):
    health = store(tmp_path, blocked_base_minutes=30)
    now = datetime(2026, 9, 24, tzinfo=UTC)
    cooldown = health.record_failure(
        "booking_com", "hotel-a", "HTTP 403 https://x.test/?token=secret", 50,
        status_code=403, now=now,
    )
    assert cooldown == now + timedelta(minutes=30)
    line = (tmp_path / "diagnostics" / "2026-09-24.jsonl").read_text(encoding="utf-8")
    snapshot = json.loads(line)
    assert snapshot["status_code"] == 403
    assert "secret" not in snapshot["reason"]
    assert "[redacted]" in snapshot["reason"]


def test_safe_reason_redacts_authorization():
    assert "abc123" not in safe_reason("Authorization: Bearer abc123")
