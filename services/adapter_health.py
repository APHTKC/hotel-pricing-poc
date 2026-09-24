"""Persistent scraper health, exponential backoff, and safe diagnostics."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class BackoffPolicy:
    failure_threshold: int = 2
    base_minutes: int = 360
    blocked_base_minutes: int = 1440
    max_minutes: int = 10080


def status_code_from_exception(error: Exception) -> int | None:
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        return status
    match = re.search(r"(?:HTTP|status(?: code)?)\s*[:=]?\s*(\d{3})", str(error), re.I)
    return int(match.group(1)) if match else None


def safe_reason(error: Exception | str) -> str:
    text = " ".join(str(error).split())
    text = re.sub(r"([?&](?:token|key|api_key|authorization|signature)=)[^&\s]+", r"\1[redacted]", text, flags=re.I)
    text = re.sub(r"(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+", "[redacted authorization]", text, flags=re.I)
    return text[:500]


class AdapterHealthStore:
    def __init__(self, path: Path, diagnostics_dir: Path, policy: BackoffPolicy | None = None):
        self.path = path
        self.diagnostics_dir = diagnostics_dir
        self.policy = policy or BackoffPolicy()
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": "1.0", "adapters": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"schema_version": "1.0", "adapters": {}}
        payload.setdefault("schema_version", "1.0")
        payload.setdefault("adapters", {})
        return payload

    @staticmethod
    def key(adapter: str, hotel_id: str) -> str:
        return f"{adapter}:{hotel_id}"

    def _record(self, adapter: str, hotel_id: str) -> dict:
        return self.data["adapters"].setdefault(self.key(adapter, hotel_id), {
            "adapter": adapter, "hotel_id": hotel_id, "attempts": 0,
            "successes": 0, "failures": 0, "blocked_count": 0,
            "consecutive_failures": 0, "total_response_ms": 0.0,
            "average_response_ms": None, "success_rate": None,
            "last_status": None, "last_attempt_at": None,
            "last_success_at": None, "cooldown_until": None, "daily": {},
        })

    def cooldown_until(self, adapter: str, hotel_id: str, now: datetime | None = None) -> datetime | None:
        now = now or datetime.now(UTC)
        value = self._record(adapter, hotel_id).get("cooldown_until")
        if not value:
            return None
        try:
            cooldown = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return cooldown if cooldown > now else None

    def _update_common(self, record: dict, now: datetime, duration_ms: float, success: bool, blocked: bool) -> dict:
        record["attempts"] += 1
        record["successes" if success else "failures"] += 1
        if blocked:
            record["blocked_count"] += 1
        record["total_response_ms"] += max(0.0, duration_ms)
        record["average_response_ms"] = round(record["total_response_ms"] / record["attempts"], 2)
        record["success_rate"] = round(record["successes"] / record["attempts"], 4)
        record["last_attempt_at"] = now.isoformat()
        day = record["daily"].setdefault(now.date().isoformat(), {"attempts": 0, "successes": 0, "failures": 0, "blocked": 0, "response_ms": 0.0})
        day["attempts"] += 1
        day["successes" if success else "failures"] += 1
        day["blocked"] += int(blocked)
        day["response_ms"] = round(day["response_ms"] + max(0.0, duration_ms), 2)
        day["success_rate"] = round(day["successes"] / day["attempts"], 4)
        day["average_response_ms"] = round(day["response_ms"] / day["attempts"], 2)
        return record

    def record_success(self, adapter: str, hotel_id: str, duration_ms: float, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        record = self._update_common(self._record(adapter, hotel_id), now, duration_ms, True, False)
        record.update({"consecutive_failures": 0, "last_status": "success", "last_success_at": now.isoformat(), "cooldown_until": None})
        self.save()

    def record_failure(self, adapter: str, hotel_id: str, error: Exception | str, duration_ms: float, status_code: int | None = None, now: datetime | None = None) -> datetime | None:
        now = now or datetime.now(UTC)
        status_code = status_code if status_code is not None else (status_code_from_exception(error) if isinstance(error, Exception) else None)
        blocked = status_code in {403, 429}
        record = self._update_common(self._record(adapter, hotel_id), now, duration_ms, False, blocked)
        record["consecutive_failures"] += 1
        record["last_status"] = "blocked" if blocked else "failed"
        cooldown = None
        if blocked:
            exponent = max(0, record["blocked_count"] - 1)
            minutes = self.policy.blocked_base_minutes * (2 ** exponent)
            cooldown = now + timedelta(minutes=min(minutes, self.policy.max_minutes))
        elif record["consecutive_failures"] >= self.policy.failure_threshold:
            exponent = record["consecutive_failures"] - self.policy.failure_threshold
            minutes = self.policy.base_minutes * (2 ** exponent)
            cooldown = now + timedelta(minutes=min(minutes, self.policy.max_minutes))
        record["cooldown_until"] = cooldown.isoformat() if cooldown else None
        self._snapshot(adapter, hotel_id, error, status_code, now, duration_ms, cooldown)
        self.save()
        return cooldown

    def _snapshot(self, adapter: str, hotel_id: str, error: Exception | str, status_code: int | None, now: datetime, duration_ms: float, cooldown: datetime | None) -> None:
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {"timestamp": now.isoformat(), "adapter": adapter, "hotel_id": hotel_id, "status_code": status_code, "error_type": type(error).__name__ if isinstance(error, Exception) else "CollectionFailure", "reason": safe_reason(error), "response_ms": round(max(0.0, duration_ms), 2), "cooldown_until": cooldown.isoformat() if cooldown else None}
        with (self.diagnostics_dir / f"{now.date().isoformat()}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
