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
        "room_type_code": None,
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


def test_grand_hilai_taipei_evidenced_aliases_match_official_room_types():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)

    expected = {
        ("豪華特大雙人床房", 44): ("Deluxe Room", "booking_com"),
        ("豪華雙床房", 44): ("Deluxe Room", "booking_com"),
        ("豪華雙人房", 44): ("Deluxe Room", "expedia_group"),
        ("行政雙人房", 44): ("Executive Deluxe Room", "expedia_group"),
        ("豪華套房 Deluxe Suite(King)", 59.5): ("Executive Deluxe Suite", "official"),
        ("豪華套房 Deluxe Suite(Twin)", 59.5): ("Executive Deluxe Suite", "official"),
        ("豪華套房－可使用貴賓廳", 59): ("Executive Deluxe Suite", "booking_com"),
        ("豪華套房", 59): ("Executive Deluxe Suite", "expedia_group"),
    }
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "grand_hilai_taipei"
    }

    for (label, area), (official_name, source_platform) in expected.items():
        matched = match_room_type({
            "hotel_id": "grand_hilai_taipei",
            "room_type_name": label,
            "room_size_sqm": area,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["label"] == label)

        assert room["name_en"] == official_name
        assert alias["source_platform"] == source_platform
        assert alias["observed_at"].startswith("2026-10-")


def test_mandarin_oriental_taipei_dated_ota_aliases_match_official_room_types():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)

    expected = {
        ("豪華特大雙人床房", 55): ("Deluxe Room", "booking_com"),
        ("豪華雙床房", 55): ("Deluxe Room", "booking_com"),
        ("俱樂部豪華雙床房", 55): ("Club Deluxe Room", "booking_com"),
        ("行政豪華特大雙人床房", 55): ("Club Deluxe Room", "booking_com"),
        ("Club Deluxe 雙床房", 55): ("Club Deluxe Room", "expedia_group"),
        ("Mandarin 客房－1 張特大雙人床", 70): ("Mandarin Room", "expedia_group"),
        ("Mandarin 俱樂部客房－1 張特大雙人床", 70): ("Club Mandarin Room", "expedia_group"),
        ("Lifestyle 俱樂部套房－1 張特大雙人床", 110): ("Club Lifestyle Suite", "expedia_group"),
        ("俱樂部套房－1 張特大雙人床 (City)", 86): ("Club City Suite", "expedia_group"),
        ("俱樂部套房－1 張特大雙人床 (Boulevard)", 110): ("Club Boulevard Suite", "expedia_group"),
        ("俱樂部套房－1 張特大雙人床 (Premier)", 133): ("Club Premier Suite", "expedia_group"),
    }
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "mo_taipei"
    }

    for (label, area), (official_name, source_platform) in expected.items():
        matched = match_room_type({
            "hotel_id": "mo_taipei",
            "room_type_name": label,
            "room_size_sqm": area,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["label"] == label)

        assert room["name_en"] == official_name
        assert alias["source_platform"] == source_platform
        assert alias["observed_at"].startswith("2026-10-")


def test_shangrila_taipei_dated_ota_aliases_match_official_room_types():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)

    expected = {
        ("豪華特大雙人床房", 40): ("Deluxe Room", "booking_com"),
        ("豪華雙床房", 40): ("Deluxe Room", "booking_com"),
        ("台北 101 景觀豪華特大雙人床房", 40): ("Deluxe Taipei 101 View Room", "booking_com"),
        ("尊爵特大雙人床房", 60): ("Premier Room", "booking_com"),
        ("Horizon 高級客房 1 King", 36): ("Horizon Superior Room", "expedia_group"),
    }
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "shangrila_taipei"
    }

    for (label, area), (official_name, source_platform) in expected.items():
        matched = match_room_type({
            "hotel_id": "shangrila_taipei",
            "room_type_name": label,
            "room_size_sqm": area,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["label"] == label)

        assert room["name_en"] == official_name
        assert alias["source_platform"] == source_platform
        assert alias["observed_at"].startswith("2026-10-")


def test_the_gaia_official_booking_alias_matches_qiyan_room():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)

    matched = match_room_type({
        "hotel_id": "the_gaia_taipei",
        "room_type_name": "�_���M�ǩ� Qiyan Japanese Style Room",
        "room_type_code": "310941",
        "source_platform": "official",
        "room_size_sqm": 33,
    }, lookup)
    room = next(
        item for item in dimension["room_types"]
        if item["stable_room_type_id"] == matched["stable_room_type_id"]
    )
    alias = next(
        item for item in room["aliases"]
        if item["label"] == "奇岩和洋房 Qiyan Japanese Style Room"
    )

    assert room["name_en"] == "Qiyan Room"
    assert alias["source_type"] == "official"
    assert alias["source_platform"] == "official"
    assert alias["room_type_code"] == "310941"
    assert alias["observed_at"] == "2026-10-18"
    assert matched["room_match_status"] == "matched_evidenced_source_code"

    wrong_source = match_room_type({
        "hotel_id": "the_gaia_taipei",
        "room_type_name": "corrupted label",
        "room_type_code": "310941",
        "source_platform": "booking_com",
        "room_size_sqm": 33,
    }, lookup)
    assert wrong_source["stable_room_type_id"] is None


def test_shangrila_tainan_official_room_codes_match_grand_deluxe_room():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "shangrila_tainan"
    }

    for label, code in (("Grand Deluxe King", "DGK"), ("Grand Deluxe Twin", "DGT")):
        matched = match_room_type({
            "hotel_id": "shangrila_tainan",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "official",
            "room_size_sqm": 39,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == "Grand Deluxe Room"
        assert alias["label"] == label
        assert alias["observed_at"] == "2026-10-18"
        assert matched["room_match_status"] == "matched_evidenced_source_code"


def test_grand_hyatt_taipei_dated_booking_codes_match_official_rooms():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "grand_hyatt_taipei"
    }
    expected = {
        ("101 景觀特級行政套房", "booking:134101233", 83): "Grand Executive 101 View Suite",
        ("101 景觀雙床房", "booking:134101246", 33): "2 Twin Beds 101 View",
        ("特大號床間－可進入俱樂部", "booking:134101219", 33): "1 King Bed Club Access",
        ("101 景觀頂級特大雙人床單房公寓－可使用俱樂部", "booking:134101222", 50): "1 King Bed 101 View Club Access Premium Studio",
        ("101 景觀頂級雙床單房公寓－可使用俱樂部", "booking:134101247", 50): "2 Twin Beds 101 View Club Access Premium Studio",
        ("特級行政套房", "booking:134101234", 83): "Grand Executive Suite",
        ("豪華特大號床間－可使用俱樂部", "booking:134101220", 40): "1 King Bed Club Access Deluxe",
        ("豪華特大雙人床房", "booking:134101224", 40): "1 King Bed Deluxe",
        ("豪華雙床房", "booking:134101225", 40): "2 Twin Beds Deluxe",
        ("高級特大號床一室公寓", "booking:134101230", 50): "1 King Bed Premium Studio",
        ("高級雙床一室公寓", "booking:134101231", 50): "2 Twin Beds Premium Studio",
    }

    for (label, code, area), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "grand_hyatt_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "booking_com",
            "room_size_sqm": area,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == "2026-10-12"
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    area_mismatch = match_room_type({
        "hotel_id": "grand_hyatt_taipei",
        "room_type_name": "101 景觀特大雙人床房",
        "room_type_code": "booking:134101245",
        "source_platform": "booking_com",
        "room_size_sqm": 30,
    }, lookup)
    assert area_mismatch["stable_room_type_id"] is None


def test_sheraton_grand_taipei_dated_ota_codes_match_official_rooms():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "sheraton_grand_taipei"
    }
    expected = {
        ("高級加大雙人床房", "booking:33458317", "booking_com", 32): "Superior Room",
        ("豪華特大雙人床房", "booking:33458313", "booking_com", 35): "Deluxe Room",
        ("豪華雙床房", "booking:33458314", "booking_com", 35): "Deluxe Room",
        ("尊爵特大雙人床房", "booking:33458315", "booking_com", 40): "Premier Room",
        ("尊爵雙床房", "booking:33458316", "booking_com", 40): "Premier Room",
        ("行政豪華特大雙人床房－禮賓樓層", "booking:33458318", "booking_com", 35): "Executive Deluxe Room",
        ("行政豪華雙床房－禮賓樓層", "booking:33458319", "booking_com", 35): "Executive Deluxe Room",
        ("極品客房，1 張特大雙人床", "expedia:674443:premium-king", "expedia_group", 40): "Premier Room",
        ("極品雙床房，2 張單人床", "expedia:674443:premium-twin", "expedia_group", 40): "Premier Room",
        ("高級客房，1 張加大雙人床", "expedia:674443:superior-queen", "expedia_group", 32): "Superior Room",
    }

    for (label, code, source_platform, area), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "sheraton_grand_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": source_platform,
            "room_size_sqm": area,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["source_platform"] == source_platform
        assert alias["observed_at"].startswith("2026-10-")
        assert matched["room_match_status"] == "matched_evidenced_source_code"


def test_miramar_garden_dated_booking_codes_match_official_rooms():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "miramar_garden_taipei"
    }
    expected = {
        ("豪華雙人房", "booking:59177201"): "Deluxe Room",
        ("家庭三人房", "booking:59177229"): "Deluxe Triple Room",
        ("商務雙人房", "booking:59177203"): "Business Room",
        ("商務雙床房", "booking:59177225"): "Business Room",
        ("行政雙人房", "booking:59177205"): "Executive Room",
        ("行政雙床房", "booking:59177226"): "Executive Room",
        ("Elite Executive Double Room", "booking:59177236"): "Elite Executive Room",
        ("精英行政雙床間", "booking:59177237"): "Elite Executive Room",
        ("豪華雙床房", "booking:59177207"): "Deluxe Room",
        ("豪華雙床房, 2 張單人床", "expedia:1460579:deluxe-twin"): "Deluxe Room",
        ("精英行政大床房, 1 張特大雙人床", "expedia:1460579:elite-executive-king"): "Elite Executive Room",
        ("老闆套房", "booking:59177235"): "Boss Suite",
    }

    for (label, code), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "miramar_garden_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "expedia_group" if code.startswith("expedia:") else "booking_com",
            "room_size_sqm": 80 if code == "booking:59177235" else 42,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == ("2026-10-17" if code.startswith("expedia:") else "2026-10-14")
        assert matched["room_match_status"] == "matched_evidenced_source_code"


def test_episode_daan_dated_ota_codes_match_official_rooms_and_reject_area_mismatch():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "episode_daan_taipei"
    }
    expected = {
        ("雙床房", "booking:136265920", 30): "2 Twin Beds",
        ("城市景觀大床房", "expedia:10965601:city-view-king", 30): "1 King Bed, City View",
        ("城市景觀雙床房", "expedia:10965601:city-view-twin", 30): "2 Twin Beds, City View",
        ("市景雙人房－附 2 張雙人床", "booking:136265917", 30): "2 Double Beds",
        ("雙大床房", "expedia:10965601:double-queen", 30): "2 Double Beds",
        ("豪華角落特大雙人床房－附沙發床", "booking:136265921", 33): "1 King Bed, Sofa Bed",
        ("豪華特大雙人床房－附陽台", "booking:136265919", 36): "1 King Bed, Balcony, Deluxe",
        ("豪華客房, 1 張特大雙人床, 陽台", "expedia:10965601:deluxe-king-balcony", 36): "1 King Bed, Balcony, Deluxe",
    }

    for (label, code, size), official_name in expected.items():
        source_platform = "expedia_group" if code.startswith("expedia:") else "booking_com"
        matched = match_room_type({
            "hotel_id": "episode_daan_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": source_platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == ("2026-10-17" if code.startswith("expedia:") else "2026-10-13")
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    area_mismatch = match_room_type({
        "hotel_id": "episode_daan_taipei",
        "room_type_name": "一大床沙發床房",
        "room_type_code": "expedia:10965601:king-sofa-bed",
        "source_platform": "expedia_group",
        "room_size_sqm": 30,
    }, lookup)
    assert area_mismatch["stable_room_type_id"] is None


def test_doubletree_taipei_dated_ota_codes_match_evidenced_rooms():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "doubletree_taipei_zhongshan"
    }
    expected = {
        ("客房, 1 張特大雙人床", "expedia:30690749:king", 35): "King Guest Room",
        ("客房, 2 張單人床", "expedia:30690749:twin", 36): "Twin Guest Room with 2 Single Beds",
        ("轉角特大雙人床房－附陽台", "booking:448071702", 33): "King Corner Room with Balcony",
        ("客房, 1 張特大雙人床, 陽台, 邊間", "expedia:30690749:corner-balcony-king", 33): "King Corner Room with Balcony",
        ("一臥室特大號床角落套房", "booking:448071703", 46): "King One Bedroom Corner Suite",
        ("套房, 1 張特大雙人床和 1 張沙發床, 邊間", "expedia:30690749:corner-king-suite", 46): "King One Bedroom Corner Suite",
        ("套房, 多張床, 邊間", "expedia:30690749:corner-twin-suite", 46): "Corner Suite with 2 Single Beds",
        ("客房, 1 張特大雙人床, 無障礙", "expedia:30690749:accessible-king", 36): "King Accessible Room",
    }

    for (label, code, size), evidenced_name in expected.items():
        source_platform = "expedia_group" if code.startswith("expedia:") else "booking_com"
        matched = match_room_type({
            "hotel_id": "doubletree_taipei_zhongshan",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": source_platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == evidenced_name
        assert alias["observed_at"] == ("2026-10-17" if code.startswith("expedia:") else "2026-10-13")
        assert matched["room_match_status"] == "matched_evidenced_source_code"


def test_metropolitan_premier_taipei_dated_booking_codes_match_official_rooms():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "hotel_metropolitan_premier_taipei"
    }
    expected = {
        ("標準特大雙人床房", "booking:715720902", 36): "Deluxe King",
        ("標準雙床房", "booking:715720901", 36): "Deluxe Twin",
        ("高級特大雙人床房", "booking:715720903", 43): "Deluxe Premier King",
        ("高級雙床房", "booking:715720904", 43): "Deluxe Premier Twin",
        ("行政雙人房", "booking:715720905", 36): "Executive King",
        ("行政特大雙人床房", "booking:715720906", 43): "Executive Premier King",
        ("行政雙床房", "booking:715720907", 43): "Executive Premier Twin",
        ("行政角落雙床房", "booking:715720915", 62): "Executive Corner Twin",
        ("行政套房－特大雙人床", "booking:715720908", 62): "Executive Suite King",
        ("行政雙床套房－兩張單人床", "booking:715720909", 62): "Executive Suite Twin",
    }

    for (label, code, size), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "hotel_metropolitan_premier_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "booking_com",
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == "2026-10-14"
        assert matched["room_match_status"] == "matched_evidenced_source_code"


def test_kimpton_daan_dated_ota_codes_match_official_room_families_conservatively():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "kimpton_da_an"
    }
    expected = {
        ("Essential Room - Bed Type Not Guaranteed", "booking:415514709", 32): "Essential Room",
        ("市景基本特大雙人床房", "booking:415514715", 32): "Essential Room",
        ("市景基本特大雙人床房－附陽台", "booking:415514716", 32): "Essential Room",
        ("基本特大雙人床房", "booking:415514719", 32): "Essential Room",
        ("市景頂級特大雙人床房", "booking:415514712", 37): "Premium Room",
        ("頂級特大雙人床房", "booking:415514721", 37): "Premium Room",
        ("頂級特大雙人床房－獨立浴缸與步入式淋浴間", "booking:415514730", 37): "Premium Room",
        ("頂級雙床房", "booking:415514731", 37): "Premium Room",
        ("尊享房 大床", "expedia:23394208:premium-king", 37): "Premium Room",
        ("尊享房 大床 獨立浴缸及步入式淋浴間", "expedia:23394208:premium-king-bathtub", 38): "Premium Room",
        ("尊享房 大床 城市景觀", "expedia:23394208:premium-king-city-view", 38): "Premium Room",
        ("尊榮客房, 2 張單人床", "expedia:23394208:premium-twin", 37): "Premium Room",
        ("市景特大雙人床套房", "booking:415514707", 58): "Suite",
    }

    for (label, code, size), official_name in expected.items():
        source_platform = "expedia_group" if code.startswith("expedia:") else "booking_com"
        matched = match_room_type({
            "hotel_id": "kimpton_da_an",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": source_platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == ("2026-10-16" if code.startswith("expedia:") else ("2026-10-13" if code == "booking:415514709" else "2026-10-14"))
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    for label, code, size in (
        ("精華特大雙人床房－無障礙設施", "booking:415514702", 38),
        ("精選特大雙人床房－附陽台", "booking:415514720", 32),
    ):
        ambiguous = match_room_type({
            "hotel_id": "kimpton_da_an",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "booking_com",
            "room_size_sqm": size,
        }, lookup)
        assert ambiguous["stable_room_type_id"] is None


def test_okura_dated_source_codes_match_official_rooms_and_leave_generic_deluxe_unmapped():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "okura_prestige_taipei"
    }
    expected = {
        ("Okura Prestige King Bed", "OPKN", "official", 44): "Okura Prestige Room",
        ("Okura Prestige Twin Bed", "OPHS", "official", 44): "Okura Prestige Room",
        ("Executive King Bed WZ Balcony", "EXKB", "official", 56): "Executive Room with Balcony",
        ("Executive King Bed", "EXKN", "official", 56): "Executive Room",
        ("大倉特大雙人床房", "booking:44470803", "booking_com", 44): "Okura Prestige Room",
        ("大倉雙床房", "booking:44470804", "booking_com", 44): "Okura Prestige Room",
        ("大倉菁英一大床, 1 張特大雙人床", "expedia:5286939:okura-elite-king", "expedia_group", 44): "Okura Prestige Room",
        ("大倉菁英兩小床, 2 張單人床", "expedia:5286939:okura-elite-twin", "expedia_group", 44): "Okura Prestige Room",
    }

    for (label, code, source_platform, size), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "okura_prestige_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": source_platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == ({"official": "2026-10-18", "booking_com": "2026-10-14", "expedia_group": "2026-10-17"}[source_platform])
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    for label, code in (
        ("豪華特大雙人床房", "booking:44470801"),
        ("豪華雙床房", "booking:44470802"),
    ):
        generic = match_room_type({
            "hotel_id": "okura_prestige_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "booking_com",
            "room_size_sqm": 44,
        }, lookup)
        assert generic["stable_room_type_id"] is None


def test_le_meridien_dated_ota_codes_match_official_rooms_and_reject_area_mismatch():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "le_meridien_taipei"
    }
    expected = {
        ("豪華特大雙人床房", "booking:33385818", 38): "Deluxe Room",
        ("豪華雙床房", "booking:33385819", 38): "Deluxe Room",
        ("豪華客房，1 張特大雙人床", "expedia:3884803:deluxe-king", 38): "Deluxe Room",
        ("豪華雙床房，2 張單人床", "expedia:3884803:deluxe-twin", 38): "Deluxe Room",
        ("純淨豪華特大號床間", "booking:33385820", 38): "Pure Deluxe Room",
        ("純淨豪華雙床間", "booking:33385821", 38): "Pure Deluxe Room",
        ("豪華客房，1 張特大雙人床，非吸煙房，純淨", "expedia:3884803:pure-deluxe-king", 38): "Pure Deluxe Room",
        ("豪華客房，2 張單人床，非吸煙房，純淨", "expedia:3884803:pure-deluxe-twin", 38): "Pure Deluxe Room",
        ("行政特大雙人床房", "booking:33385822", 38): "Executive Deluxe Room",
        ("行政雙床房", "booking:33385823", 38): "Executive Deluxe Room",
        ("俱樂部雙床房，2 張單人床", "expedia:3884803:club-twin", 38): "Executive Deluxe Room",
        ("小型套房", "booking:33385824", 60): "Junior Suite",
        ("普通套房，1 間臥室", "expedia:3884803:junior-suite", 60): "Junior Suite",
        ("轉角套房", "booking:33385825", 60): "Corner Suite",
        ("套房，1 間臥室（Corner）", "expedia:3884803:corner-suite", 60): "Corner Suite",
        ("行政套房", "booking:33385826", 75): "Executive Suite",
        ("行政套房，1 間臥室", "expedia:3884803:executive-suite", 75): "Executive Suite",
    }

    for (label, code, size), official_name in expected.items():
        source_platform = "expedia_group" if code.startswith("expedia:") else "booking_com"
        matched = match_room_type({
            "hotel_id": "le_meridien_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": source_platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == ("2026-10-16" if code.startswith("expedia:") else "2026-10-13")
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    area_mismatch = match_room_type({
        "hotel_id": "le_meridien_taipei",
        "room_type_name": "俱樂部客房，1 張特大雙人床",
        "room_type_code": "expedia:3884803:club-king",
        "source_platform": "expedia_group",
        "room_size_sqm": 35,
    }, lookup)
    assert area_mismatch["stable_room_type_id"] is None


def test_metropolitan_premier_synxis_codes_disambiguate_generic_official_labels():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "hotel_metropolitan_premier_taipei"
    }
    expected = {
        ("大都會客房", "DPK", 43): "Deluxe Premier King",
        ("行政尊榮客房", "EPK", 43): "Executive Premier King",
        ("行政景隅客房", "ECT", 62): "Executive Corner Twin",
        ("行政套房", "SEK", 62): "Executive Suite King",
    }

    for (label, code, size), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "hotel_metropolitan_premier_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "official",
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == "2026-10-18"
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    ambiguous = match_room_type({
        "hotel_id": "hotel_metropolitan_premier_taipei",
        "room_type_name": "都會客房",
        "room_type_code": "DXTU",
        "source_platform": "official",
        "room_size_sqm": 36,
    }, lookup)
    assert ambiguous["stable_room_type_id"] is None


def test_humble_house_dated_ota_codes_match_official_rooms():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "humble_house_taipei"
    }
    expected = {
        ("豪華雙床房", "booking:80123520", 26): "Deluxe Room",
        ("地標景觀豪華特大雙人床房", "booking:80123516", 26): "Deluxe Room with Landmark View",
        ("頂級特大雙人床房", "booking:80123518", 36): "Premium Room",
        ("尊榮客房－特大雙人床", "expedia:7272454:premium-king", 36): "Premium Room",
        ("尊榮客房－兩張單人床", "expedia:7272454:premium-twin", 36): "Premium Room",
        ("地標景觀頂級特大雙人床房", "booking:80123519", 36): "Premium Room with Landmark View",
        ("豪華套房－兩張單人床", "expedia:7272454:deluxe-suite-twin", 53): "Twin Deluxe Suite",
        ("豪華套房－特大雙人床", "expedia:7272454:deluxe-suite-king", 53): "King Deluxe Suite with Landmark View",
    }

    for (label, code, size), official_name in expected.items():
        source_platform = "expedia_group" if code.startswith("expedia:") else "booking_com"
        matched = match_room_type({
            "hotel_id": "humble_house_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": source_platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == ("2026-10-16" if code.startswith("expedia:") else "2026-10-13")
        assert matched["room_match_status"] == "matched_evidenced_source_code"


def test_w_taipei_dated_booking_codes_match_evidenced_rooms_and_leave_generic_view_unmapped():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "w_taipei"
    }
    expected = {
        ("市景絕佳房－附特大雙人床", "booking:33385911", 46): "Fabulous Room",
        ("市景非凡客房－單臥室套房－附 1 張特大雙人床", "booking:33385914", 95): "Marvelous Suite",
    }

    for (label, code, size), evidenced_name in expected.items():
        matched = match_room_type({
            "hotel_id": "w_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "booking_com",
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == evidenced_name
        assert alias["observed_at"] == "2026-10-14"
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    generic_view = match_room_type({
        "hotel_id": "w_taipei",
        "room_type_name": "Room, 1 King Bed (View)",
        "room_type_code": "expedia:4071588:king-view",
        "source_platform": "expedia_group",
        "room_size_sqm": 43,
    }, lookup)
    assert generic_view["stable_room_type_id"] is None


def test_taipei_marriott_dated_expedia_codes_match_official_suites_and_leave_sky_rooms_unmapped():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "taipei_marriott"
    }
    expected = {
        ("客房，2 張標準雙人床", "expedia:10911958:residential-double", 51): "Homey Room",
        ("行政套房，1 張特大雙人床", "expedia:10911958:executive-suite-king", 66): "Comfort Suite",
        ("行政套房，1 間臥室", "expedia:10911958:executive-suite-bedroom", 66): "Comfort Suite",
        ("行政套房，1 張特大雙人床，獨立用餐區", "expedia:10911958:marriott-suite-king", 79): "Brilliant Suite",
    }

    for (label, code, size), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "taipei_marriott",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "expedia_group",
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == "2026-10-16"
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    for label, code in (
        ("天空特大雙人床房", "booking:146845510"),
        ("天空尊榮雙床房－享行政貴賓廳使用權", "booking:146845513"),
    ):
        unmatched = match_room_type({
            "hotel_id": "taipei_marriott",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "booking_com",
            "room_size_sqm": 43,
        }, lookup)
        assert unmatched["stable_room_type_id"] is None


def test_solaria_dated_official_codes_and_expedia_comfort_room_match_evidenced_rooms():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "solaria_nishitetsu_taipei"
    }
    expected = {
        ("景隅大床房", "f21af558-7fcf-490f-89cd-ded83ba055bb", "official", 18): ("Compact Queen", "2026-10-21"),
        ("舒適大床房", "d0259873-2e7f-4aca-80ce-0c3da1a932e3", "official", 24): ("Moderate King", "2026-10-21"),
        ("景隅三人房", "1493b6ab-7210-4cb5-8937-1a9fe0b928d3", "official", 28): ("Corner Triple", "2026-10-21"),
        ("經典三人房", "fca7392f-68d5-4dfa-b3a6-adf52d321649", "official", 39): ("Triple", "2026-10-21"),
        ("尊爵房", "5f455e97-1b54-4e83-a429-b88e5a1260aa", "official", 35): ("Premium Room", "2026-10-21"),
        ("舒適大床房", "expedia:93043356:comfort-double", "expedia_group", 23): ("Moderate King", "2026-10-18"),
    }

    for (label, code, platform, size), (official_name, observed_at) in expected.items():
        matched = match_room_type({
            "hotel_id": "solaria_nishitetsu_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == observed_at
        assert matched["room_match_status"] == "matched_evidenced_source_code"


def test_indigo_taipei_north_dated_ota_codes_match_evidenced_ihg_room_categories():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "indigo_taipei_north"
    }
    expected = {
        ("標準特大雙人床房", "booking:577965016", "booking_com", 36): ("Standard Room", "2026-10-13"),
        ("頂級特大雙人床房", "booking:577965002", "booking_com", 40): ("Premium Room", "2026-10-13"),
        ("豪華客房 （一大床）", "expedia:42515940:deluxe-king", "expedia_group", 40): ("Premium Room", "2026-10-17"),
        ("特大雙人床套房", "booking:577965011", "booking_com", 60): ("King Suite", "2026-10-13"),
        ("套房, 1 張特大雙人床", "expedia:42515940:suite-king", "expedia_group", 60): ("King Suite", "2026-10-17"),
        ("套房, 1 間臥室", "expedia:42515940:one-bedroom-suite", "expedia_group", 73): ("One Bedroom Suite", "2026-10-17"),
    }

    for (label, code, platform, size), (official_name, observed_at) in expected.items():
        matched = match_room_type({
            "hotel_id": "indigo_taipei_north",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == observed_at
        assert matched["room_match_status"] == "matched_evidenced_source_code"


def test_landis_taipei_dated_ota_codes_match_official_room_categories():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "the_landis_taipei"
    }
    expected = {
        ("高級雙人房", "booking:24067801", "booking_com", 26): ("Superior Room", "2026-10-14"),
        ("高級雙床房", "booking:24067818", "booking_com", 26): ("Superior Room", "2026-10-14"),
        ("雙人房－無障礙空間", "booking:24067813", "booking_com", 26): ("Superior Room", "2026-10-14"),
        ("無障礙房, 1 張標準雙人床", "expedia:13043:accessible-double", "expedia_group", 26): ("Superior Room", "2026-10-17"),
        ("豪華雙人房", "booking:24067802", "booking_com", 43): ("Deluxe Room", "2026-10-14"),
        ("豪華雙人房－附加床", "booking:24067806", "booking_com", 43): ("Deluxe Room", "2026-10-14"),
        ("行政客房, 1 張特大雙人床", "expedia:13043:executive-king", "expedia_group", 53): ("Executive Suite", "2026-10-17"),
        ("轉角套房", "booking:24067805", "booking_com", 56): ("Corner Suite", "2026-10-14"),
        ("套房－附加床", "booking:24067821", "booking_com", 56): ("Corner Suite", "2026-10-14"),
    }

    for (label, code, platform, size), (official_name, observed_at) in expected.items():
        matched = match_room_type({
            "hotel_id": "the_landis_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == observed_at
        assert matched["room_match_status"] == "matched_evidenced_source_code"


def test_radium_kagaya_dated_ota_codes_match_balcony_and_no_view_categories_conservatively():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "radium_kagaya_taipei"
    }
    expected = {
        ("溫馨和洋標準套房(兩張加大單人床 有陽台)", "expedia:5978371:standard-twin-balcony", "expedia_group", 43): ("Mixed Standard Suite Twin (With Terrace)", "2026-10-16"),
        ("溫馨和洋標準套房(一張特大雙人床)", "expedia:5978371:standard-king", "expedia_group", 43): ("Mixed Standard Suite (No View)", "2026-10-16"),
        ("標準雙人房－無窗", "booking:505734804", "booking_com", 43): ("Mixed Standard Suite (No View)", "2026-10-14"),
        ("標準雙床房－無窗", "booking:505734813", "booking_com", 43): ("Mixed Standard Suite (No View)", "2026-10-14"),
        ("園景和洋雅緻套房(兩張加大單人床 有陽台)", "expedia:5978371:elegant-garden-twin-balcony", "expedia_group", 50): ("Park Side View Mixed Deluxe Suite (With Terrace)", "2026-10-16"),
        ("園景和洋雅緻套房(一張特大雙人床)", "expedia:5978371:elegant-garden-king", "expedia_group", 43): ("Park Side View Mixed Deluxe Suite", "2026-10-16"),
    }

    for (label, code, platform, size), (official_name, observed_at) in expected.items():
        matched = match_room_type({
            "hotel_id": "radium_kagaya_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == observed_at
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    for label, code in (
        ("豪華雙人房", "booking:505734801"),
        ("豪華雙床房", "booking:505734802"),
    ):
        unmatched = match_room_type({
            "hotel_id": "radium_kagaya_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "booking_com",
            "room_size_sqm": 43,
        }, lookup)
        assert unmatched["stable_room_type_id"] is None


def test_grand_view_resort_dated_ota_codes_match_official_rooms_and_leave_area_mismatch_unmapped():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "grand_view_resort_beitou"
    }
    expected = {
        ("高級雙人房", "booking:29809403", "booking_com", 50): ("Superior Room", "2026-10-14"),
        ("豪華雙人房", "booking:29809404", "booking_com", 50): ("Deluxe Room", "2026-10-14"),
        ("豪華雙床房", "booking:29809402", "booking_com", 50): ("Deluxe Room", "2026-10-14"),
        ("豪華雙人房", "expedia:391029:deluxe-double", "expedia_group", 49): ("Deluxe Room", "2026-10-16"),
        ("Deluxe Double Room", "expedia:391029:deluxe-double-50", "expedia_group", 50): ("Deluxe Room", "2026-10-16"),
        ("豪華雙床房", "expedia:391029:deluxe-twin", "expedia_group", 49): ("Deluxe Room", "2026-10-16"),
        ("Deluxe Twin Room", "expedia:391029:deluxe-twin-50", "expedia_group", 50): ("Deluxe Room", "2026-10-16"),
        ("豪華四人房", "booking:29809408", "booking_com", 50): ("Deluxe Family Room", "2026-10-14"),
        ("套房－附陽台", "booking:29809410", "booking_com", 63): ("You-Ya Suite", "2026-10-14"),
    }

    for (label, code, platform, size), (official_name, observed_at) in expected.items():
        matched = match_room_type({
            "hotel_id": "grand_view_resort_beitou",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": platform,
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == observed_at
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    area_mismatch = match_room_type({
        "hotel_id": "grand_view_resort_beitou",
        "room_type_name": "雅緻家庭房",
        "room_type_code": "expedia:391029:elegant-family",
        "source_platform": "expedia_group",
        "room_size_sqm": 56,
    }, lookup)
    assert area_mismatch["stable_room_type_id"] is None


def test_royal_nikko_dated_hotels_codes_match_official_rooms_by_name_and_area():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "royal_nikko_taipei"
    }
    expected = {
        ("豪華雙人房(一大床)", "expedia:2839:deluxe-king", 32): "Deluxe Room",
        ("豪華雙床房(二小床)", "expedia:2839:deluxe-twin", 32): "Deluxe Room",
        ("尊爵雙人房(一大床)", "expedia:2839:premier-king", 38): "Premier Room",
        ("尊爵雙人房(一大床) 含Royal VIP Lounge", "expedia:2839:premier-king-lounge", 38): "Premier Room",
        ("尊爵雙床房(二小床)", "expedia:2839:premier-twin", 38): "Premier Room",
        ("尊爵雙床房(二小床) 含Royal VIP Lounge", "expedia:2839:premier-twin-lounge", 38): "Premier Room",
        ("景隅套房", "expedia:2839:corner-suite-king", 65): "Corner Suite",
    }

    for (label, code, size), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "royal_nikko_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "expedia_group",
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == "2026-10-18"
        assert matched["room_match_status"] == "matched_evidenced_source_code"


def test_metropolitan_connecting_room_codes_use_area_to_disambiguate_official_labels():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "hotel_metropolitan_premier_taipei"
    }
    expected = {
        ("EPC", 86): "Deluxe Premier Connecting",
        ("ECC", 105): "Executive Corner Connecting",
    }

    for (code, size), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "hotel_metropolitan_premier_taipei",
            "room_type_name": "連通客房",
            "room_type_code": code,
            "source_platform": "official",
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == "2026-10-21"
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    ambiguous = match_room_type({
        "hotel_id": "hotel_metropolitan_premier_taipei",
        "room_type_name": "都會客房",
        "room_type_code": "DXK",
        "source_platform": "official",
        "room_size_sqm": 36,
    }, lookup)
    assert ambiguous["stable_room_type_id"] is None


def test_capella_skyline_synxis_codes_match_official_pool_terrace_rooms():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "capella_taipei"
    }
    expected = {
        ("璀璨景觀客房一大床", "RT1S", 78): "Pool Terrace Skyline Room",
        ("璀璨景觀客房兩小床", "RT2S", 78): "Pool Terrace Skyline Room",
        ("璀璨景觀套房一大床", "ST1S", 270): "Pool Terrace Skyline Suite",
    }

    for (label, code, size), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "capella_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "official",
            "room_size_sqm": size,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == "2026-10-21"
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    for label, code, size in (
        ("高級特大雙人床房", "booking:1331864201", 48),
        ("雙人房－附陽台", "booking:1331864231", 60),
    ):
        ambiguous = match_room_type({
            "hotel_id": "capella_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "booking_com",
            "room_size_sqm": size,
        }, lookup)
        assert ambiguous["stable_room_type_id"] is None


def test_grand_hyatt_hotels_view_codes_match_only_supported_101_view_rooms():
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    dimension = build_room_type_dimension(profiles)
    lookup = build_room_type_lookup(dimension)
    rooms = {
        room["stable_room_type_id"]: room
        for room in dimension["room_types"]
        if room["hotel_id"] == "grand_hyatt_taipei"
    }
    expected = {
        ("君悅景觀客房(特大床)", "expedia:21035:view-king"): "1 King Bed 101 View",
        ("客房－2 張單人床 (101 View)", "expedia:21035:view-twin"): "2 Twin Beds 101 View",
        ("嘉賓軒景觀客房(特大床)", "expedia:21035:club-view-king"): "1 King Bed 101 View Club Access",
    }

    for (label, code), official_name in expected.items():
        matched = match_room_type({
            "hotel_id": "grand_hyatt_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "expedia_group",
            "room_size_sqm": 33,
        }, lookup)
        room = rooms[matched["stable_room_type_id"]]
        alias = next(item for item in room["aliases"] if item["room_type_code"] == code)

        assert room["name_en"] == official_name
        assert alias["observed_at"] == "2026-10-16"
        assert matched["room_match_status"] == "matched_evidenced_source_code"

    for label, code, size in (
        ("101 景觀特大雙人床房", "booking:134101245", 30),
        ("嘉賓軒尊尚客房(特大床)", "expedia:21035:club-premium-king", 50),
        ("嘉賓軒尊尚客房(雙床)", "expedia:21035:club-premium-twin", 50),
    ):
        unsupported = match_room_type({
            "hotel_id": "grand_hyatt_taipei",
            "room_type_name": label,
            "room_type_code": code,
            "source_platform": "booking_com" if code.startswith("booking:") else "expedia_group",
            "room_size_sqm": size,
        }, lookup)
        assert unsupported["stable_room_type_id"] is None
