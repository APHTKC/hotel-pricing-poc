"""Strict same-product matching for official and OTA public rates."""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

UNKNOWN = "unknown"

def _value(row: Mapping[str, Any] | Any, name: str, default=None):
    return row.get(name, default) if isinstance(row, Mapping) else getattr(row, name, default)

def normalize_cancellation_class(policy: str | None) -> str:
    if not policy:
        return UNKNOWN
    text = " ".join(policy.lower().split())
    if any(term in text for term in (
        "non-refundable",
        "non refundable",
        "不可退款",
        "不得退款",
        "不得取消",
        "取消不可",
        "取消須付費（訂單總額）",
        "取消須付費 (訂單總額)",
        "返金不可",
        "キャンセル不可",
    )):
        return "non_refundable"
    # A rate that is free only until a stated date/number of days is a
    # conditional product, even when the page also says "free cancellation".
    # Classifying it as unrestricted free cancellation prevents a legitimate
    # official/OTA match when both sources express the same deadline in
    # different word order.
    has_deadline = bool(
        re.search(r"(?:before|prior to|抵達前|入住前|日前|日まで).{0,30}\d+", text)
        or re.search(r"\d{4}\s*[年/-]\s*\d{1,2}\s*[月/-]\s*\d{1,2}\s*日前", text)
    )
    if has_deadline:
        return "conditional"
    if any(term in text for term in ("free cancellation", "free cancel", "免費取消", "可免費取消", "無料キャンセル", "キャンセル無料")):
        return "free_cancellation"
    return UNKNOWN

def normalize_tax_inclusion(row: Mapping[str, Any] | Any) -> str:
    explicit = _value(row, "tax_inclusion")
    if explicit in {"included", "excluded"}:
        return explicit
    if _value(row, "total_price") is not None and any(_value(row, name) is not None for name in ("price_before_tax", "tax", "service_charge")):
        return "included"
    return UNKNOWN

def normalize_size_band(row: Mapping[str, Any] | Any) -> str:
    band = _value(row, "size_band")
    if band and band != UNKNOWN:
        return str(band)
    try:
        number = float(_value(row, "room_size_sqm"))
    except (TypeError, ValueError):
        return UNKNOWN
    if number <= 0:
        return UNKNOWN
    return "<45㎡" if number < 45 else "45–59㎡" if number < 60 else "60–79㎡" if number < 80 else "80㎡+"

def occupancy_key(row: Mapping[str, Any] | Any) -> str:
    raw_values = tuple(_value(row, name) for name in ("rooms", "adults", "children"))
    if any(value is None for value in raw_values):
        return UNKNOWN
    try:
        rooms, adults, children = (int(value) for value in raw_values)
    except (TypeError, ValueError):
        return UNKNOWN
    if rooms <= 0 or adults <= 0 or children < 0:
        return UNKNOWN
    return f"{rooms}r-{adults}a-{children}c"

@dataclass(frozen=True)
class CanonicalComparisonKey:
    hotel_id: str
    check_in: str
    check_out: str
    occupancy: str
    size_band: str
    breakfast_included: bool
    cancellation_class: str
    tax_inclusion: str

    def serialize(self) -> str:
        values = (self.hotel_id, self.check_in, self.check_out, self.occupancy, self.size_band, "breakfast" if self.breakfast_included else "room_only", self.cancellation_class, self.tax_inclusion)
        return "|".join(str(value) for value in values)

def canonical_comparison_key(row: Mapping[str, Any] | Any) -> CanonicalComparisonKey | None:
    hotel_id, check_in, check_out = _value(row, "hotel_id"), _value(row, "check_in"), _value(row, "check_out")
    breakfast = _value(row, "breakfast_included")
    occupancy = occupancy_key(row)
    size_band = normalize_size_band(row)
    cancellation = normalize_cancellation_class(_value(row, "cancellation_policy"))
    tax_inclusion = normalize_tax_inclusion(row)
    if not hotel_id or not check_in or not check_out or breakfast is None or UNKNOWN in {occupancy, size_band, cancellation, tax_inclusion}:
        return None
    return CanonicalComparisonKey(str(hotel_id), str(check_in), str(check_out), occupancy, size_band, bool(breakfast), cancellation, tax_inclusion)

def comparison_metadata(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    key = canonical_comparison_key(row)
    return {"comparison_key": key.serialize() if key else None, "comparison_status": "comparable" if key else "insufficient_product_metadata", "occupancy": occupancy_key(row), "cancellation_class": normalize_cancellation_class(_value(row, "cancellation_policy")), "tax_inclusion": normalize_tax_inclusion(row), "size_band": normalize_size_band(row)}

def _queried_at(row: Mapping[str, Any] | Any) -> datetime | None:
    value = _value(row, "queried_at")
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def calculate_rate_parity(
    rows: Iterable[Mapping[str, Any] | Any],
    *,
    max_query_gap_hours: float = 24,
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, list[tuple[Decimal, datetime | None]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    examples: dict[str, CanonicalComparisonKey] = {}
    for row in rows:
        key = canonical_comparison_key(row)
        if key is None:
            continue
        total = _value(row, "total_twd") or _value(row, "total_price")
        try:
            value = Decimal(str(total))
        except (TypeError, ValueError, InvalidOperation):
            continue
        platform = str(_value(row, "source_platform", "official") or "official")
        serialized = key.serialize()
        groups[serialized][platform].append((value, _queried_at(row)))
        examples[serialized] = key
    comparisons = []
    for serialized, sources in groups.items():
        official_entries = sources.get("official", [])
        if not official_entries:
            continue
        for platform, ota_entries in sources.items():
            if platform == "official" or not ota_entries:
                continue
            ota_timestamps = [timestamp for _, timestamp in ota_entries if timestamp is not None]
            official_timestamps = [
                timestamp for _, timestamp in official_entries if timestamp is not None
            ]
            ota_timestamp = max(ota_timestamps) if ota_timestamps else None
            official_timestamp = None
            selected_ota = ota_entries
            selected_official = official_entries
            gap_hours = None
            if ota_timestamp is not None:
                selected_ota = [entry for entry in ota_entries if entry[1] == ota_timestamp]
                if official_timestamps:
                    official_timestamp = min(
                        official_timestamps,
                        key=lambda timestamp: abs((timestamp - ota_timestamp).total_seconds()),
                    )
                    gap_hours = abs(
                        (official_timestamp - ota_timestamp).total_seconds()
                    ) / 3600
                    if gap_hours > max_query_gap_hours:
                        continue
                    selected_official = [
                        entry for entry in official_entries if entry[1] == official_timestamp
                    ]
            official = Decimal(
                str(statistics.median(value for value, _ in selected_official))
            )
            ota = Decimal(str(statistics.median(value for value, _ in selected_ota)))
            key = examples[serialized]
            comparisons.append({
                "comparison_key": serialized,
                "hotel_id": key.hotel_id,
                "check_in": key.check_in,
                "check_out": key.check_out,
                "occupancy": key.occupancy,
                "size_band": key.size_band,
                "breakfast_included": key.breakfast_included,
                "cancellation_class": key.cancellation_class,
                "tax_inclusion": key.tax_inclusion,
                "ota_source": platform,
                "official_median_twd": float(official),
                "ota_median_twd": float(ota),
                "gap_percent": float((ota - official) / official) if official else None,
                "official_queried_at": official_timestamp.isoformat() if official_timestamp else None,
                "ota_queried_at": ota_timestamp.isoformat() if ota_timestamp else None,
                "query_time_gap_hours": round(gap_hours, 2) if gap_hours is not None else None,
            })
    return sorted(comparisons, key=lambda item: (item["check_in"], item["hotel_id"], item["ota_source"]))
