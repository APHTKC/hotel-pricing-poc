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
import unicodedata
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


def normalize_room_label(value: str | None) -> str:
    """Normalize an evidenced room label without fuzzy guessing.

    The matcher deliberately removes only presentation differences such as
    case, Unicode width, punctuation and whitespace.  It does not remove bed,
    view, club or suite wording because those attributes can describe a
    materially different product.
    """
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def evidenced_aliases(room: dict) -> list[dict]:
    """Return only aliases carrying a dated, directly inspectable source."""
    aliases = []
    for alias in room.get("aliases") or []:
        if not isinstance(alias, dict):
            continue
        label = str(alias.get("label") or "").strip()
        source_url = str(alias.get("source_url") or "").strip()
        observed_at = str(alias.get("observed_at") or "").strip()
        if not label or not source_url.startswith("https://") or not observed_at:
            continue
        if alias.get("label_match") is False and not (
            str(alias.get("source_platform") or "").strip()
            and str(alias.get("room_type_code") or "").strip()
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", observed_at)
        ):
            # A code-only alias has no safe text fallback. Without both
            # source dimensions it cannot be matched deterministically.
            continue
        item = {
            "label": label,
            "language": alias.get("language"),
            "source_type": alias.get("source_type"),
            "source_platform": alias.get("source_platform"),
            "room_type_code": alias.get("room_type_code"),
            "source_url": source_url,
            "observed_at": observed_at,
        }
        # A generic label may be safe only when paired with the source's
        # stable room code.  Preserve that evidence without allowing the
        # label to match other, materially different products by containment.
        if alias.get("label_match") is False:
            item["label_match"] = False
        aliases.append(item)
    return aliases


def _cjk_character_count(value: str) -> int:
    return sum(
        "\u3400" <= character <= "\u4dbf" or "\u4e00" <= character <= "\u9fff"
        for character in value
    )


def build_room_type_lookup(dimension_payload: dict) -> dict[tuple[str, str], tuple[dict, ...]]:
    """Index exact evidenced labels, retaining ambiguity for fail-closed matching."""
    candidates: dict[tuple[str, str], list[dict]] = defaultdict(list)
    hotel_candidates: dict[str, list[dict]] = defaultdict(list)
    for room in dimension_payload.get("room_types", []):
        hotel_id = str(room.get("hotel_id") or "")
        if not hotel_id:
            continue
        labels = [room.get(key) for key in ("name_zh", "name_en", "name_ja")]
        labels.extend(room.get("aliases_zh") or [])
        aliases = evidenced_aliases(room)
        labels.extend(
            alias["label"] for alias in aliases
            if alias.get("label_match") is not False
        )
        for alias in aliases:
            source_platform = str(alias.get("source_platform") or "").strip()
            room_type_code = str(alias.get("room_type_code") or "").strip()
            if source_platform and room_type_code:
                code_key = (hotel_id, f"__code__{source_platform}:{room_type_code}")
                if room not in candidates[code_key]:
                    candidates[code_key].append(room)
        for label in labels:
            normalized = normalize_room_label(label)
            if normalized and room not in candidates[(hotel_id, normalized)]:
                candidates[(hotel_id, normalized)].append(room)
                labeled_room = {**room, "_match_label": normalized}
                if not any(
                    item["_match_label"] == normalized
                    and item["stable_room_type_id"] == room["stable_room_type_id"]
                    for item in hotel_candidates[hotel_id]
                ):
                    hotel_candidates[hotel_id].append(labeled_room)
    for hotel_id, labeled_rooms in hotel_candidates.items():
        candidates[(hotel_id, "")] = labeled_rooms
    return {key: tuple(value) for key, value in candidates.items()}


def match_room_type(row: dict, lookup: dict[tuple[str, str], tuple[dict, ...]]) -> dict:
    """Resolve a rate observation to one evidenced stable room type.

    Matching is exact after presentation-only normalization.  When a source
    publishes an area it must also agree with the dimension.  Ambiguous,
    missing, or conflicting observations stay visible but are not eligible
    for strict rate parity.
    """
    hotel_id = str(row.get("hotel_id") or "")
    normalized = normalize_room_label(row.get("room_type_name"))
    empty = {
        "stable_room_type_id": None,
        "normalized_room_family": None,
        "room_class": None,
        "room_match_status": "unmatched_label" if normalized else "missing_room_type_name",
    }
    observed_area = _number(row.get("room_size_sqm"))
    source_platform = str(row.get("source_platform") or "").strip()
    room_type_code = str(row.get("room_type_code") or "").strip()
    candidates = []
    if source_platform and room_type_code:
        candidates = list(lookup.get((hotel_id, f"__code__{source_platform}:{room_type_code}"), ()))
    match_status = "matched_evidenced_source_code" if candidates else "matched_exact_evidenced_label"
    if not candidates:
        candidates = list(lookup.get((hotel_id, normalized), ()))
    if not candidates:
        # OTA labels commonly append bed, view and occupancy wording to the
        # hotel's evidenced room name.  Accept only literal containment of an
        # evidenced label, then keep the longest match so "Club Deluxe Room"
        # does not collapse into the shorter "Deluxe Room".  This is not a
        # fuzzy or area-only match.
        contained = []
        for candidate in lookup.get((hotel_id, ""), ()):
            label = candidate.get("_match_label", "")
            # Four-character Chinese room names such as 卓越客房 and 壯美客房
            # are complete branded labels, but shorter than the previous
            # generic safety threshold.  Accept them only when the source also
            # publishes an area that can be checked below.  English "Room"
            # and other short generic fragments remain ineligible.
            sufficiently_specific = len(label) >= 5 or (
                observed_area is not None and _cjk_character_count(label) >= 4
            )
            if sufficiently_specific and label in normalized:
                contained.append(candidate)
        if not contained:
            return empty
        longest = max(len(candidate["_match_label"]) for candidate in contained)
        candidates = [
            candidate for candidate in contained
            if len(candidate["_match_label"]) == longest
        ]
        match_status = "matched_evidenced_label_with_descriptors"

    if observed_area is not None:
        area_matches = [
            candidate
            for candidate in candidates
            if candidate.get("size_sqm_min") is not None
            # A one-square-metre tolerance handles public sources that round
            # the same room differently (for example 110 vs 111 sqm).
            and float(candidate["size_sqm_min"]) - 1 <= observed_area <= float(candidate["size_sqm_max"]) + 1
        ]
        if not area_matches:
            return {**empty, "room_match_status": "area_mismatch"}
        candidates = area_matches
    if len(candidates) != 1:
        return {**empty, "room_match_status": "ambiguous_label"}

    matched = candidates[0]
    return {
        "stable_room_type_id": matched["stable_room_type_id"],
        "normalized_room_family": matched["normalized_room_family"],
        "room_class": matched["room_class"],
        "room_match_status": match_status,
    }


def build_room_type_dimension(profiles_payload: dict) -> dict:
    rows = []
    incomplete_code_only_aliases = []
    counts = defaultdict(lambda: {"room_name_count": 0, "area_spec_keys": set(), "room_family_keys": set()})
    for profile in profiles_payload.get("profiles", []):
        hotel_id = profile.get("hotel_id")
        snapshot = profile.get("room_snapshot") or {}
        if not hotel_id or not snapshot.get("rooms"):
            continue
        for room in snapshot["rooms"]:
            for alias in room.get("aliases") or []:
                if not isinstance(alias, dict) or alias.get("label_match") is not False:
                    continue
                missing_fields = []
                if not str(alias.get("label") or "").strip():
                    missing_fields.append("label")
                if not str(alias.get("source_platform") or "").strip():
                    missing_fields.append("source_platform")
                if not str(alias.get("room_type_code") or "").strip():
                    missing_fields.append("room_type_code")
                if not str(alias.get("source_url") or "").strip().startswith("https://"):
                    missing_fields.append("source_url")
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(alias.get("observed_at") or "").strip()):
                    missing_fields.append("observed_at")
                if missing_fields:
                    incomplete_code_only_aliases.append({
                        "hotel_id": hotel_id,
                        "room_name": room.get("name_en") or room.get("name_zh") or room.get("name_ja"),
                        "alias_label": alias.get("label"),
                        "missing_fields": missing_fields,
                    })
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
                "aliases": evidenced_aliases(room),
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
    source_code_targets: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    evidenced_label_targets: dict[tuple[str, str], set[str]] = defaultdict(set)
    evidenced_label_examples: dict[tuple[str, str], str] = {}
    for row in rows:
        for alias in row["aliases"]:
            source_platform = str(alias.get("source_platform") or "").strip()
            room_type_code = str(alias.get("room_type_code") or "").strip()
            if source_platform and room_type_code:
                source_code_targets[(row["hotel_id"], source_platform, room_type_code)].add(
                    row["stable_room_type_id"]
                )
            normalized_label = normalize_room_label(alias.get("label"))
            if normalized_label and alias.get("label_match") is not False:
                label_key = (row["hotel_id"], normalized_label)
                evidenced_label_targets[label_key].add(row["stable_room_type_id"])
                evidenced_label_examples.setdefault(label_key, alias["label"])
    source_code_conflicts = [
        {
            "hotel_id": hotel_id,
            "source_platform": source_platform,
            "room_type_code": room_type_code,
            "stable_room_type_ids": sorted(stable_ids),
        }
        for (hotel_id, source_platform, room_type_code), stable_ids in sorted(source_code_targets.items())
        if len(stable_ids) > 1
    ]
    evidenced_label_conflicts = [
        {
            "hotel_id": hotel_id,
            "normalized_label": normalized_label,
            "example_label": evidenced_label_examples[(hotel_id, normalized_label)],
            "stable_room_type_ids": sorted(stable_ids),
        }
        for (hotel_id, normalized_label), stable_ids in sorted(evidenced_label_targets.items())
        if len(stable_ids) > 1
    ]
    return {
        "schema_version": "1.3",
        "updated_at": profiles_payload.get("updated_at"),
        "definition": {
            "room_name_count": "Distinct evidenced room labels published by the source.",
            "area_spec_count": "Distinct exact or ranged room areas; bed and view labels sharing an area count once.",
            "normalized_family_count": "Conservative room class plus area grouping; not sufficient alone for strict rate parity.",
        },
        "strict_parity_note": "A matching area or family alone is never sufficient for strict rate parity.",
        "evidence_quality": {
            "source_code_conflict_count": len(source_code_conflicts),
            "source_code_conflicts": source_code_conflicts,
            "evidenced_label_conflict_count": len(evidenced_label_conflicts),
            "evidenced_label_conflicts": evidenced_label_conflicts,
            "incomplete_code_only_alias_count": len(incomplete_code_only_aliases),
            "incomplete_code_only_aliases": incomplete_code_only_aliases,
        },
        "hotel_summaries": summaries,
        "room_types": sorted(rows, key=lambda row: (row["hotel_id"], row["size_sqm_min"] or 1e9, row["stable_room_type_id"])),
    }
