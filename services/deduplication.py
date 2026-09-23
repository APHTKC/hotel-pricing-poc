from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any, TypeVar


T = TypeVar("T")
NaturalKey = tuple[str, str, str, str, str]


def _field(row: object, name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name, None)


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "")
    return text[:10]


def _timestamp_text(row: object) -> str:
    value = _field(row, "queried_at")
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def observation_natural_key(row: object) -> NaturalKey:
    """Return the stable daily natural key used by storage and publishing.

    Some booking engines omit their internal room/rate codes. Names are used
    only as a fallback in those cases so distinct public plans are not lost.
    """

    room_code = _field(row, "room_type_code")
    rate_code = _field(row, "rate_plan_code")
    room_key = str(room_code) if room_code not in (None, "") else f"name:{_field(row, 'room_type_name') or ''}"
    rate_key = str(rate_code) if rate_code not in (None, "") else f"name:{_field(row, 'rate_plan_name') or ''}"
    return (
        str(_field(row, "hotel_id") or ""),
        _date_text(_field(row, "check_in")),
        room_key,
        rate_key,
        _date_text(_field(row, "queried_at")),
    )


def deduplicate_observations(rows: Iterable[T], *, keep: str = "latest") -> list[T]:
    """Deduplicate observations while preserving deterministic ordering."""

    if keep not in {"first", "latest"}:
        raise ValueError("keep must be 'first' or 'latest'")
    unique: dict[NaturalKey, T] = {}
    for row in rows:
        key = observation_natural_key(row)
        if keep == "first" and key in unique:
            continue
        if (
            keep == "latest"
            and key in unique
            and _timestamp_text(row) < _timestamp_text(unique[key])
        ):
            continue
        unique[key] = row
    return list(unique.values())
