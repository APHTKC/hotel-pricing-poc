import json
from pathlib import Path

from services.room_type_dimension import (
    area_spec,
    bed_type,
    build_room_type_dimension,
    build_room_type_lookup,
    match_room_type,
    normalize_room_label,
    room_class,
)


def test_room_normalization_helpers():
    assert area_spec({"size_sqm": 48}) == (48.0, 48.0, "48")
    assert area_spec({"size_sqm_min": 45, "size_sqm_max": 59}) == (45.0, 59.0, "45-59")
    assert room_class({"name_zh": "豪華套房"}) == "suite"
    assert room_class({"name_en": "Pool Villa"}) == "villa"
    assert bed_type({"name_zh": "豪華雙床客房"}) == "twin"


def test_room_type_dimension_has_stable_ids_evidence_and_dual_counts():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    payload = build_room_type_dimension(profiles)
    rows = payload["room_types"]
    assert rows
    assert len({row["stable_room_type_id"] for row in rows}) == len(rows)
    assert all(row["evidence"]["source_url"].startswith("https://") for row in rows)
    assert all(row["strict_parity_eligible"] is False for row in rows)

    capella = next(row for row in payload["hotel_summaries"] if row["hotel_id"] == "capella_taipei")
    assert capella["room_name_count"] == 13
    assert capella["area_spec_count"] == 7
    assert capella["normalized_family_count"] == 7


def test_published_room_type_dimension_matches_builder_output():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    published = json.loads(Path("public/data/room_type_dimension.json").read_text(encoding="utf-8"))
    assert published == build_room_type_dimension(profiles)


def test_evidenced_room_match_is_exact_and_checks_area():
    dimension = {
        "room_types": [{
            "hotel_id": "hotel-a",
            "stable_room_type_id": "rt_deluxe_king",
            "normalized_room_family": "room:55",
            "room_class": "room",
            "name_zh": "豪華客房（一大床）",
            "name_en": "Deluxe Room – King",
            "name_ja": None,
            "aliases_zh": ["豪華大床房"],
            "size_sqm_min": 55,
            "size_sqm_max": 55,
        }]
    }
    lookup = build_room_type_lookup(dimension)

    matched = match_room_type({
        "hotel_id": "hotel-a",
        "room_type_name": "Deluxe Room - King",
        "room_size_sqm": 55,
    }, lookup)
    mismatch = match_room_type({
        "hotel_id": "hotel-a",
        "room_type_name": "Deluxe Room - King",
        "room_size_sqm": 80,
    }, lookup)
    described = match_room_type({
        "hotel_id": "hotel-a",
        "room_type_name": "Deluxe Room - King, City View",
        "room_size_sqm": 56,
    }, lookup)

    assert normalize_room_label(" Deluxe Room – King ") == normalize_room_label("deluxe room-king")
    assert matched["stable_room_type_id"] == "rt_deluxe_king"
    assert described["stable_room_type_id"] == "rt_deluxe_king"
    assert described["room_match_status"] == "matched_evidenced_label_with_descriptors"
    assert mismatch["stable_room_type_id"] is None
    assert mismatch["room_match_status"] == "area_mismatch"
