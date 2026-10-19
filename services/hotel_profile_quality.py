"""Evidence coverage reporting for the curated hotel profile dataset."""

from __future__ import annotations

from collections import Counter
from datetime import date


FACILITY_FIELDS = ("pool", "fitness", "spa", "sauna", "steam_room")


def _date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _ratio(count: int, total: int) -> dict:
    return {
        "count": count,
        "total": total,
        "percent": round((count / total * 100) if total else 0, 2),
    }


def build_hotel_profile_quality(payload: dict, *, review_days: int = 31) -> dict:
    """Build a deterministic, evidence-only profile completeness report.

    The newest verification date in the source is the report reference date.
    This keeps static builds reproducible while still exposing profiles that
    have exceeded the project's monthly review interval.
    """
    profiles = payload.get("profiles") or []
    verified_dates = [
        parsed for profile in profiles
        if (parsed := _date(profile.get("verified_at"))) is not None
    ]
    source_updated_at = _date(payload.get("updated_at"))
    candidates = verified_dates + ([source_updated_at] if source_updated_at else [])
    as_of = max(candidates) if candidates else None

    counters = Counter()
    facility_counts = Counter()
    source_type_counts = Counter()
    michelin_distinctions = Counter()
    michelin_entries = []
    hotel_rows = []
    room_total = 0
    trilingual_room_total = 0
    area_room_total = 0

    for profile in sorted(profiles, key=lambda item: str(item.get("hotel_id") or "")):
        hotel_id = profile.get("hotel_id")
        verified_at = _date(profile.get("verified_at"))
        review_age_days = (as_of - verified_at).days if as_of and verified_at else None
        review_current = review_age_days is not None and review_age_days <= review_days
        stay_times = profile.get("stay_times") or {}
        snapshot = profile.get("room_snapshot") or {}
        rooms = snapshot.get("rooms") or []
        facilities = profile.get("facilities") or {}
        lounge = profile.get("lounge") or {}

        stay_times_sourced = bool(
            stay_times.get("check_in")
            and stay_times.get("check_out")
            and stay_times.get("source_type")
            and stay_times.get("source_url")
        )
        room_inventory_known = isinstance(profile.get("room_inventory"), int) and profile["room_inventory"] > 0
        restaurants_documented = bool(profile.get("restaurants"))
        lounge_status_explicit = isinstance(lounge.get("available"), bool)
        room_snapshot_sourced = bool(
            rooms
            and snapshot.get("observed_at")
            and snapshot.get("source_type")
            and snapshot.get("source_url")
        )
        source_urls_present = bool(profile.get("source_urls"))
        trilingual_rooms = sum(
            bool(room.get("name_zh") and room.get("name_en") and room.get("name_ja"))
            for room in rooms
        )
        area_rooms = sum(
            any(room.get(field) is not None for field in ("size_sqm", "size_sqm_min", "size_sqm_max"))
            for room in rooms
        )
        room_total += len(rooms)
        trilingual_room_total += trilingual_rooms
        area_room_total += area_rooms
        source_type_counts[str(snapshot.get("source_type") or "unknown")] += 1
        for restaurant in profile.get("michelin_restaurants") or []:
            distinction = restaurant.get("distinction")
            evidenced = bool(
                restaurant.get("name")
                and restaurant.get("guide_year")
                and distinction
                and restaurant.get("source_url")
                and restaurant.get("verified_at")
            )
            if not evidenced:
                continue
            michelin_distinctions[str(distinction)] += 1
            michelin_entries.append(
                {
                    "hotel_id": hotel_id,
                    "name": restaurant["name"],
                    "guide_year": restaurant["guide_year"],
                    "distinction": distinction,
                    "verified_at": restaurant["verified_at"],
                    "source_url": restaurant["source_url"],
                    "restaurant_url": restaurant.get("restaurant_url"),
                    "relationship": restaurant.get("relationship", "hotel_restaurant"),
                }
            )

        checks = {
            "monthly_review_current": review_current,
            "stay_times_sourced": stay_times_sourced,
            "room_inventory_known": room_inventory_known,
            "restaurants_documented": restaurants_documented,
            "lounge_status_explicit": lounge_status_explicit,
            "room_snapshot_sourced": room_snapshot_sourced,
            "source_urls_present": source_urls_present,
            "all_rooms_trilingual": bool(rooms) and trilingual_rooms == len(rooms),
            "all_rooms_have_area": bool(rooms) and area_rooms == len(rooms),
        }
        counters.update({key: 1 for key, passed in checks.items() if passed})
        for field in FACILITY_FIELDS:
            if isinstance(facilities.get(field), bool):
                facility_counts[field] += 1

        hotel_rows.append(
            {
                "hotel_id": hotel_id,
                "verified_at": profile.get("verified_at"),
                "review_age_days": review_age_days,
                "room_count": len(rooms),
                "trilingual_room_count": trilingual_rooms,
                "area_documented_room_count": area_rooms,
                "missing_evidence": [key for key, passed in checks.items() if not passed],
                "unknown_facilities": [
                    field for field in FACILITY_FIELDS
                    if not isinstance(facilities.get(field), bool)
                ],
            }
        )

    profile_total = len(profiles)
    return {
        "schema_version": "1.0",
        "source_updated_at": payload.get("updated_at"),
        "as_of": as_of.isoformat() if as_of else None,
        "monthly_review_interval_days": review_days,
        "profile_count": profile_total,
        "room_count": room_total,
        "profile_coverage": {
            field: _ratio(counters[field], profile_total)
            for field in (
                "monthly_review_current",
                "stay_times_sourced",
                "room_inventory_known",
                "restaurants_documented",
                "lounge_status_explicit",
                "room_snapshot_sourced",
                "source_urls_present",
                "all_rooms_trilingual",
                "all_rooms_have_area",
            )
        },
        "room_coverage": {
            "trilingual_names": _ratio(trilingual_room_total, room_total),
            "area_documented": _ratio(area_room_total, room_total),
        },
        "facility_evidence": {
            field: _ratio(facility_counts[field], profile_total)
            for field in FACILITY_FIELDS
        },
        "room_snapshot_source_types": dict(sorted(source_type_counts.items())),
        "michelin": {
            "scope": "evidence_confirmed_only",
            "restaurant_count": len(michelin_entries),
            "hotel_count": len({item["hotel_id"] for item in michelin_entries}),
            "latest_guide_year": max(
                (item["guide_year"] for item in michelin_entries), default=None
            ),
            "distinction_counts": dict(sorted(michelin_distinctions.items())),
            "restaurants": sorted(
                michelin_entries,
                key=lambda item: (str(item["hotel_id"]), str(item["name"])),
            ),
        },
        "hotels": sorted(
            hotel_rows,
            key=lambda item: (
                -len(item["missing_evidence"]),
                -len(item["unknown_facilities"]),
                str(item["hotel_id"]),
            ),
        ),
    }
