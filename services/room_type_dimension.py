"""Build a deterministic room-type dimension from evidenced hotel snapshots.

The dimension deliberately keeps a named room type separate from its area
specification.  Hotels frequently publish king/twin or view variants under
different names even though the physical room size is identical.  Consumers
can therefore report both counts without treating every marketing label as a
different physical product.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from decimal import Decimal


def _number(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _format_number(value: float) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def area_spec(room: dict) -> tuple[float | None, float | None, str | None]:
    exact = _number(room.get("size_sqm"))
    minimum = _number(room.get("size_sqm_min")) or exact
    maximum = _number(room.get("size_sqm_max")) or exact or minimum
    if minimum is None:
        return None, None, None
    maximum = maximum or minimum
    key = _format_number(minimum)
    if maximum != minimum:
        key = f"{key}-{_format_number(maximum)}"
    return minimum, maximum, key


def room_class(room: dict) -> str:
    text = " ".join(str(room.get(key) or "") for key in ("name_zh", "name_en", "name_ja")).lower()
    if any(token in text for token in ("villa", "別墅", "ヴィラ")):
        return "villa"
    if any(token in text for token in ("residence", "公寓", "レジデンス")):
        return "residence"
    if any(token in text for token in ("suite", "套房", "スイート")):
        return "suite"
    return "room"


def bed_type(room: dict) -> str:
    text = " ".join(
        [str(room.get(key) or "") for key in ("name_zh", "name_en", "name_ja")]
        + [str(value) for value in room.get("aliases_zh", [])]
    ).lower()
    matches = []
    for label, tokens in (
        ("king", ("king", "特大床", "一大床", "キング")),
        ("queen", ("queen", "大床", "クイーン")),
        ("twin", ("twin", "雙床", "兩床", "ツイン")),
        ("double", ("double", "雙人床", "ダブル")),
    ):
        if any(token in text for token in tokens):
            matches.append(label)
    if len(matches) > 1:
        return "multiple"
    return matches[0] if matches else "unspecified"


def _stable_id(hotel_id: str, room: dict, area_key: str | None) -> str:
    identity = "|".join(
        str(value or "").strip().casefold()
        for value in (
            hotel_id,
            room.get("name_en"),
            room.get("name_zh"),
            room.get("name_ja"),
            area_key,
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"rt_{digest}"


def build_room_type_dimension(profiles_payload: dict) -> dict:
    rows = []
    counts = defaultdict(lambda: {"room_name_count": 0, "area_spec_keys": set(), "room_family_keys": set()})
    for profile in profiles_payload.get("profiles", []):
        hotel_id = profile.get("hotel_id")
        snapshot = profile.get("room_snapshot") or {}
        if not hotel_id or not snapshot.get("rooms"):
            continue
        for room in snapshot["rooms"]:
            minimum, maximum, area_key = area_spec(room)
            classification = room_class(room)
            # Conservative physical family: class + published area.  It is a
            # reporting aid, not yet sufficient for strict rate parity.
            family_key = f"{classification}:{area_key or 'unknown'}"
            row = {
                "hotel_id": hotel_id,
                "stable_room_type_id": _stable_id(hotel_id, room, area_key),
                "normalized_room_family": family_key,
                "room_class": classification,
                "name_zh": room.get("name_zh"),
                "name_en": room.get("name_en"),
                "name_ja": room.get("name_ja"),
                "aliases_zh": room.get("aliases_zh", []),
                "size_sqm": _number(room.get("size_sqm")),
                "size_sqm_min": minimum,
                "size_sqm_max": maximum,
                "area_spec_key": area_key,
                "bed_type": bed_type(room),
                "room_count": room.get("room_count"),
                "evidence": {
                    "source_type": snapshot.get("source_type"),
                    "source_url": snapshot.get("source_url"),
                    "observed_at": snapshot.get("observed_at"),
                },
                "normalization_method": "room_class_and_published_area",
                "strict_parity_eligible": False,
            }
            rows.append(row)
            summary = counts[hotel_id]
            summary["room_name_count"] += 1
            if area_key:
                summary["area_spec_keys"].add(area_key)
            summary["room_family_keys"].add(family_key)

    summaries = []
    for hotel_id in sorted(counts):
        item = counts[hotel_id]
        summaries.append(
            {
                "hotel_id": hotel_id,
                "room_name_count": item["room_name_count"],
                "area_spec_count": len(item["area_spec_keys"]),
                "normalized_family_count": len(item["room_family_keys"]),
            }
        )
    return {
        "schema_version": "1.0",
        "updated_at": profiles_payload.get("updated_at"),
        "definition": {
            "room_name_count": "Distinct evidenced room labels published by the source.",
            "area_spec_count": "Distinct exact or ranged room areas; bed and view labels sharing an area count once.",
            "normalized_family_count": "Conservative room class plus area grouping; not sufficient alone for strict rate parity.",
        },
        "strict_parity_note": "A matching area or family alone is never sufficient for strict rate parity.",
        "hotel_summaries": summaries,
        "room_types": sorted(rows, key=lambda row: (row["hotel_id"], row["size_sqm_min"] or 1e9, row["stable_room_type_id"])),
    }
