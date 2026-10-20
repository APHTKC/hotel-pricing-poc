import json
from pathlib import Path

from services.room_type_dimension import (
    area_spec,
    bed_type,
    build_room_type_dimension,
    build_room_type_lookup,
    evidenced_aliases,
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
    assert evidenced_aliases({"aliases": [
        {"label": "小型套房", "source_url": "https://example.com", "observed_at": "2026-10-18"},
        {"label": "沒有日期", "source_url": "https://example.com"},
    ]}) == [{
        "label": "小型套房",
        "language": None,
        "source_type": None,
        "source_platform": None,
        "source_url": "https://example.com",
        "observed_at": "2026-10-18",
    }]


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


def test_four_character_cjk_label_requires_matching_published_area():
    dimension = {
        "room_types": [
            {
                "hotel_id": "hotel-a",
                "stable_room_type_id": "rt_superior",
                "normalized_room_family": "room:48",
                "room_class": "room",
                "name_zh": "卓越客房",
                "name_en": "Superior Room",
                "name_ja": None,
                "aliases_zh": [],
                "size_sqm_min": 48,
                "size_sqm_max": 48,
            },
            {
                "hotel_id": "hotel-b",
                "stable_room_type_id": "rt_generic",
                "normalized_room_family": "room:48",
                "room_class": "room",
                "name_zh": None,
                "name_en": "Room",
                "name_ja": None,
                "aliases_zh": [],
                "size_sqm_min": 48,
                "size_sqm_max": 48,
            },
        ]
    }
    lookup = build_room_type_lookup(dimension)

    matched = match_room_type({
        "hotel_id": "hotel-a",
        "room_type_name": "卓越客房一大床",
        "room_size_sqm": 48,
    }, lookup)
    missing_area = match_room_type({
        "hotel_id": "hotel-a",
        "room_type_name": "卓越客房一大床",
    }, lookup)
    generic_english = match_room_type({
        "hotel_id": "hotel-b",
        "room_type_name": "Room with city view",
        "room_size_sqm": 48,
    }, lookup)

    assert matched["stable_room_type_id"] == "rt_superior"
    assert matched["room_match_status"] == "matched_evidenced_label_with_descriptors"
    assert missing_area["stable_room_type_id"] is None
    assert generic_english["stable_room_type_id"] is None


def test_dated_evidenced_alias_is_published_and_matchable():
    profiles = {
        "profiles": [{
            "hotel_id": "hotel-a",
            "room_snapshot": {
                "source_type": "official",
                "source_url": "https://official.example/rooms",
                "observed_at": "2026-10-18",
                "rooms": [{
                    "name_zh": "精緻套房",
                    "name_en": "Junior Suite",
                    "name_ja": None,
                    "size_sqm": 65,
                    "aliases": [{
                        "label": "小型套房",
                        "language": "zh-TW",
                        "source_type": "ota",
                        "source_platform": "booking_com",
                        "source_url": "https://ota.example/dated-snapshot",
                        "observed_at": "2026-10-14",
                    }],
                }],
            },
        }]
    }

    dimension = build_room_type_dimension(profiles)
    room = dimension["room_types"][0]
    matched = match_room_type({
        "hotel_id": "hotel-a",
        "room_type_name": "小型套房",
        "room_size_sqm": 65,
    }, build_room_type_lookup(dimension))

    assert room["aliases"][0]["source_platform"] == "booking_com"
    assert matched["stable_room_type_id"] == room["stable_room_type_id"]


def test_intercontinental_taipei_booking_aliases_match_official_room_types():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)

    expected = {
        ("經典雙床房", 38): "Classic Room",
        ("小型特大雙人床套房", 43): "Junior Suite",
        ("單臥室套房", 76): "Residential Suite",
    }
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "intercontinental_taipei"
    }

    for (label, area), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "intercontinental_taipei",
            "room_type_name": label,
            "room_size_sqm": area,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["label"] == label)

        assert room["name_en"] == official_name
        assert alias["source_platform"] == "booking_com"
        assert alias["observed_at"] == "2026-10-13"


def test_taipei_marriott_dated_ota_aliases_match_official_room_types():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)

    expected = {
        "經典特大雙人床房": "Classic Room",
        "經典雙床房": "Classic Room",
        "豪華特大雙人床房": "Deluxe Room",
        "豪華雙床房": "Deluxe Room",
        "尊爵特大雙人床房": "Premier Room",
        "尊爵雙床房": "Premier Room",
        "尊榮特大雙人床房－享行政貴賓廳使用權": "Privilege Room",
        "尊榮雙床房－享行政貴賓廳使用權": "Privilege Room",
    }
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "taipei_marriott"
    }

    for label, official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "taipei_marriott",
            "room_type_name": label,
            "room_size_sqm": 40,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["label"] == label)

        assert room["name_en"] == official_name
        assert alias["source_platform"] == "booking_com"
        assert alias["observed_at"] == "2026-10-14"


def test_grand_mayfull_dated_hotels_com_aliases_match_official_room_types():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)

    expected = {
        "行政客房, 1 張特大雙人床": "Executive King",
        "行政客房, 2 張單人床": "Executive Twin",
    }
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "grand_mayfull_taipei"
    }

    for label, official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "grand_mayfull_taipei",
            "room_type_name": label,
            "room_size_sqm": 50,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["label"] == label)

        assert room["name_en"] == official_name
        assert alias["source_platform"] == "expedia_group"
        assert alias["observed_at"] == "2026-10-17"
