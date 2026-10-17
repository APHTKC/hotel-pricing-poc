from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


def field(row: object, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def stay_nights(row: object) -> int | None:
    """Return the actual positive stay length, preferring the date interval."""
    check_in = field(row, "check_in")
    check_out = field(row, "check_out")
    try:
        arrival = check_in if isinstance(check_in, date) else date.fromisoformat(str(check_in))
        departure = check_out if isinstance(check_out, date) else date.fromisoformat(str(check_out))
        interval = (departure - arrival).days
        if interval > 0:
            return interval
    except (TypeError, ValueError):
        pass
    raw_nights = field(row, "nights", 1)
    if raw_nights is None:
        raw_nights = 1
    try:
        nights = int(raw_nights)
    except (TypeError, ValueError):
        return None
    return nights if nights > 0 else None


def nightly_adr_twd(row: object) -> Decimal | None:
    """Normalize a stay total to one room-night in TWD."""
    total = field(row, "total_twd")
    if total is None:
        total = field(row, "total_price")
        currency = str(field(row, "currency", "TWD") or "TWD").upper()
        if currency not in {"TWD", "NTD"}:
            try:
                total = Decimal(str(total)) * Decimal(str(field(row, "fx_rate_to_twd")))
            except (TypeError, ValueError, InvalidOperation):
                return None
    nights = stay_nights(row)
    try:
        value = Decimal(str(total))
    except (TypeError, ValueError, InvalidOperation):
        return None
    if value <= 0 or not nights:
        return None
    return value / Decimal(nights)


def nightly_price_per_sqm_twd(row: object) -> Decimal | None:
    nightly = nightly_adr_twd(row)
    try:
        size = Decimal(str(field(row, "room_size_sqm")))
    except (TypeError, ValueError, InvalidOperation):
        try:
            legacy_unit = Decimal(str(field(row, "price_per_sqm")))
        except (TypeError, ValueError, InvalidOperation):
            return None
        nights = stay_nights(row)
        return legacy_unit / Decimal(nights) if legacy_unit > 0 and nights else None
    if nightly is None or size <= 0:
        return None
    return nightly / size
