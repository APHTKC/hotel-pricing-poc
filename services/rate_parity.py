"""Strict same-product matching for official and OTA public rates."""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from services.pricing import nightly_adr_twd

UNKNOWN = "unknown"

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fourteen": 14,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
}


def normalize_cancellation_schedule(policy: str | None) -> list[dict[str, Any]]:
    """Return explicit multi-stage cancellation penalties without inference.

    Some official booking engines publish tiered penalties instead of one
    free-cancellation deadline. Preserving those tiers makes the policy useful
    for analysis, while an empty result deliberately leaves vague text and
    single-deadline products outside this representation.
    """
    if not policy:
        return []
    text = " ".join(str(policy).split())
    tiers: list[dict[str, Any]] = []
    for start, end, percent in re.findall(
        r"(\d+)\s*[~～-]\s*(\d+)\s*(?:天|日)(?:之前|前)"
        r".{0,30}?訂金(?:的)?\s*(\d+)\s*[％%]",
        text,
    ):
        start_days, end_days, penalty = int(start), int(end), int(percent)
        if start_days < end_days or not 0 <= penalty <= 100:
            return []
        tiers.append(
            {
                "days_before_from": start_days,
                "days_before_to": end_days,
                "penalty_percent": penalty,
                "penalty_basis": "deposit",
            }
        )
    same_day = re.search(
        r"當天.{0,30}?訂金(?:的)?\s*(\d+)\s*[％%]",
        text,
    )
    if same_day:
        penalty = int(same_day.group(1))
        if not 0 <= penalty <= 100:
            return []
        tiers.append(
            {
                "days_before_from": 0,
                "days_before_to": 0,
                "penalty_percent": penalty,
                "penalty_basis": "deposit",
            }
        )
    return tiers if len(tiers) >= 2 else []


def _value(row: Mapping[str, Any] | Any, name: str, default=None):
    return row.get(name, default) if isinstance(row, Mapping) else getattr(row, name, default)

def normalize_cancellation_class(policy: str | None) -> str:
    if not policy:
        return UNKNOWN
    text = " ".join(policy.lower().split())
    if normalize_cancellation_schedule(policy):
        return "conditional"
    if any(term in text for term in (
        "non-refundable",
        "non refundable",
        "不可退款",
        "不得退款",
        "不得取消",
        "取消不可",
        "取消須付費（訂單總額）",
        "取消須付費 (訂單總額)",
        "100% of stay room charge",
        "無法退款",
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
        or re.search(r"\d+.{0,30}(?:before|prior to|日前|日まで)", text)
        or re.search(r"(?:入住|抵達)\s*\d+\s*(?:天|日)前", text)
        or re.search(r"\d{4}\s*[年/-]\s*\d{1,2}\s*[月/-]\s*\d{1,2}\s*日前", text)
        or re.search(
            r"cancelled\s+after.{0,80}\d{1,2}\s+[a-z]{3,9}\s+20\d{2}",
            text,
        )
        or re.search(
            rf"(?:{'|'.join(NUMBER_WORDS)})\s+days?\s+prior to\s+"
            r"(?:arrival|check[- ]?in)",
            text,
        )
        or "day prior to arrival" in text
    )
    if has_deadline:
        return "conditional"
    if any(term in text for term in ("free cancellation", "free cancel", "免費取消", "可免費取消", "無料キャンセル", "キャンセル無料")):
        return "free_cancellation"
    return UNKNOWN


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def normalize_cancellation_deadline(row: Mapping[str, Any] | Any) -> str:
    """Return a comparable refund deadline, not merely a broad policy class.

    Conditional rates are strict-comparison eligible only when their refund
    deadline can be normalized to an exact calendar date.  This prevents, for
    example, an OTA rate refundable until five days before arrival from being
    compared with an official rate refundable until the day before arrival.
    """
    policy = _value(row, "cancellation_policy")
    policy_class = normalize_cancellation_class(policy)
    if policy_class == "non_refundable":
        return "non_refundable"
    if policy_class == "free_cancellation":
        return "unrestricted"
    if policy_class != "conditional" or not policy:
        return UNKNOWN

    text = " ".join(str(policy).lower().split())
    check_in = _as_date(_value(row, "check_in"))

    # Fully dated public policies, including the forms used by Hotels.com and
    # Booking.com snapshots.
    match = re.search(r"(20\d{2})\s*[年/-]\s*(\d{1,2})\s*[月/-]\s*(\d{1,2})", text)
    if match:
        try:
            return date(*(int(part) for part in match.groups())).isoformat()
        except ValueError:
            return UNKNOWN

    # Localized month/day labels omit the year.  Select the latest occurrence
    # that does not fall after check-in (important for January stays).
    match = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if match and check_in:
        month, day = (int(part) for part in match.groups())
        try:
            candidate = date(check_in.year, month, day)
            if candidate > check_in:
                candidate = date(check_in.year - 1, month, day)
            return candidate.isoformat()
        except ValueError:
            return UNKNOWN

    month_names = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    match = re.search(
        r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d{2})",
        text,
    )
    if match:
        day, month_name, year = match.groups()
        try:
            return date(int(year), month_names[month_name], int(day)).isoformat()
        except ValueError:
            return UNKNOWN

    # Relative deadlines are anchored to the requested check-in date.
    days = None
    relative_patterns = (
        r"入住日前至少\s*(\d+)\s*(?:天|日)",
        r"入住\s*(\d+)\s*(?:天|日)前",
        r"抵達前\s*(\d+)\s*(?:天|日)",
        # SynXis exposes the cutoff time before the relative-day value in
        # localized feature text, for example
        # ``抵達前免費取消最多 15:00 1 天``.  Anchor on the time so ``15`` is
        # never mistaken for the day offset.
        r"抵達前.{0,40}?\d{1,2}:\d{2}\s*(\d+)\s*(?:天|日)",
        r"(\d+)\s*(?:\(\d+\))?\s*days?\s+prior to\s+(?:arrival|check[- ]?in)",
    )
    for pattern in relative_patterns:
        match = re.search(pattern, text)
        if match:
            days = int(match.group(1))
            break
    if days is None:
        match = re.search(
            rf"({'|'.join(NUMBER_WORDS)})\s+days?\s+prior to\s+"
            r"(?:arrival|check[- ]?in)",
            text,
        )
        if match:
            days = NUMBER_WORDS[match.group(1)]
    if days is None and re.search(r"(?:the|one) day prior to arrival", text):
        days = 1
    if days is not None and check_in and days > 0:
        return (check_in - timedelta(days=days)).isoformat()
    return UNKNOWN

def normalize_tax_inclusion(row: Mapping[str, Any] | Any) -> str:
    explicit = _value(row, "tax_inclusion")
    if explicit in {"included", "excluded"}:
        return str(explicit)

    try:
        total = Decimal(str(_value(row, "total_price")))
        before_tax = Decimal(str(_value(row, "price_before_tax")))
    except (TypeError, ValueError, ArithmeticError):
        return UNKNOWN
    component_values = tuple(_value(row, name) for name in ("service_charge", "tax"))
    if not any(value is not None for value in component_values):
        return UNKNOWN
    try:
        service_charge, tax = (
            Decimal("0") if value is None else Decimal(str(value))
            for value in component_values
        )
    except (TypeError, ValueError, ArithmeticError):
        return UNKNOWN
    if min(total, before_tax, service_charge, tax) < 0:
        return UNKNOWN
    tolerance = max(Decimal("1"), abs(total) * Decimal("0.0001"))
    if abs(total - (before_tax + service_charge + tax)) <= tolerance:
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
    stable_room_type_id: str | None
    breakfast_included: bool
    cancellation_class: str
    cancellation_deadline: str
    tax_inclusion: str

    def serialize(self) -> str:
        room_key = self.stable_room_type_id or self.size_band
        values = (self.hotel_id, self.check_in, self.check_out, self.occupancy, room_key, "breakfast" if self.breakfast_included else "room_only", self.cancellation_class, self.cancellation_deadline, self.tax_inclusion)
        return "|".join(str(value) for value in values)

def canonical_comparison_key(
    row: Mapping[str, Any] | Any,
    *,
    require_stable_room_type: bool = False,
) -> CanonicalComparisonKey | None:
    hotel_id, check_in, check_out = _value(row, "hotel_id"), _value(row, "check_in"), _value(row, "check_out")
    breakfast = _value(row, "breakfast_included")
    occupancy = occupancy_key(row)
    size_band = normalize_size_band(row)
    cancellation = normalize_cancellation_class(_value(row, "cancellation_policy"))
    cancellation_deadline = normalize_cancellation_deadline(row)
    tax_inclusion = normalize_tax_inclusion(row)
    stable_room_type_id = _value(row, "stable_room_type_id")
    if (
        not hotel_id
        or not check_in
        or not check_out
        or breakfast is None
        or UNKNOWN in {
            occupancy, size_band, cancellation, cancellation_deadline, tax_inclusion
        }
        or (require_stable_room_type and not stable_room_type_id)
    ):
        return None
    return CanonicalComparisonKey(
        str(hotel_id), str(check_in), str(check_out), occupancy, size_band,
        str(stable_room_type_id) if stable_room_type_id else None,
        bool(breakfast), cancellation, cancellation_deadline, tax_inclusion,
    )


def comparison_key_missing_fields(
    row: Mapping[str, Any] | Any,
    *,
    require_stable_room_type: bool = False,
) -> list[str]:
    """Return deterministic reasons a row cannot form a canonical key."""

    missing = []
    if not _value(row, "hotel_id"):
        missing.append("hotel_id")
    if not _value(row, "check_in"):
        missing.append("check_in")
    if not _value(row, "check_out"):
        missing.append("check_out")
    if occupancy_key(row) == UNKNOWN:
        missing.append("occupancy")
    if normalize_size_band(row) == UNKNOWN:
        missing.append("room_size")
    if require_stable_room_type and not _value(row, "stable_room_type_id"):
        missing.append("stable_room_type_id")
    if _value(row, "breakfast_included") is None:
        missing.append("breakfast_included")
    if normalize_cancellation_class(_value(row, "cancellation_policy")) == UNKNOWN:
        missing.append("cancellation_class")
    if normalize_cancellation_deadline(row) == UNKNOWN:
        missing.append("cancellation_deadline")
    if normalize_tax_inclusion(row) == UNKNOWN:
        missing.append("tax_inclusion")
    return missing


def comparison_metadata(
    row: Mapping[str, Any] | Any,
    *,
    require_stable_room_type: bool = False,
) -> dict[str, Any]:
    key = canonical_comparison_key(
        row, require_stable_room_type=require_stable_room_type
    )
    return {
        "comparison_key": key.serialize() if key else None,
        "comparison_status": "comparable" if key else "insufficient_product_metadata",
        "occupancy": occupancy_key(row),
        "cancellation_class": normalize_cancellation_class(_value(row, "cancellation_policy")),
        "cancellation_deadline": normalize_cancellation_deadline(row),
        "tax_inclusion": normalize_tax_inclusion(row),
        "size_band": normalize_size_band(row),
    }

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


def _latest_valid_timestamp_pair(
    ota_entries: list[tuple[Decimal, datetime | None]],
    official_entries: list[tuple[Decimal, datetime | None]],
    max_query_gap_hours: float,
) -> tuple[datetime, datetime, float] | None:
    ota_timestamps = sorted(
        {timestamp for _, timestamp in ota_entries if timestamp is not None},
        reverse=True,
    )
    official_timestamps = {
        timestamp for _, timestamp in official_entries if timestamp is not None
    }
    for ota_timestamp in ota_timestamps:
        nearest = min(
            official_timestamps,
            key=lambda timestamp: abs((timestamp - ota_timestamp).total_seconds()),
            default=None,
        )
        if nearest is None:
            continue
        gap_hours = abs((nearest - ota_timestamp).total_seconds()) / 3600
        if gap_hours <= max_query_gap_hours:
            return ota_timestamp, nearest, gap_hours
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
        key = canonical_comparison_key(row, require_stable_room_type=True)
        if key is None:
            continue
        value = nightly_adr_twd(row)
        if value is None:
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
            # Strict parity always requires two dated observations inside the
            # same query window.  Starting with the newest OTA timestamp that
            # actually has a valid official counterpart avoids an unrelated,
            # newer OTA snapshot suppressing an older valid comparison.
            matched_pair = _latest_valid_timestamp_pair(
                ota_entries, official_entries, max_query_gap_hours
            )
            if matched_pair is None:
                continue
            ota_timestamp, official_timestamp, gap_hours = matched_pair
            selected_ota = [entry for entry in ota_entries if entry[1] == ota_timestamp]
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
                "stable_room_type_id": key.stable_room_type_id,
                "breakfast_included": key.breakfast_included,
                "cancellation_class": key.cancellation_class,
                "cancellation_deadline": key.cancellation_deadline,
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
