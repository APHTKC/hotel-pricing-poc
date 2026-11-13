import json
from pathlib import Path

from services.hotel_profile_quality import build_hotel_profile_quality


def _profile(hotel_id="hotel-a", *, verified_at="2026-10-01"):
    return {
        "hotel_id": hotel_id,
        "verified_at": verified_at,
        "stay_times": {
            "check_in": "15:00",
            "check_out": "11:00",
            "source_type": "official",
            "source_url": "https://example.com/stay",
        },
        "room_inventory": 100,
        "restaurants": [{"name": "Restaurant"}],
        "facilities": {"pool": True, "fitness": False},
        "lounge": {"available": False},
        "room_snapshot": {
            "observed_at": "2026-10-01",
            "source_type": "official",
            "source_url": "https://example.com/rooms",
            "rooms": [
                {
                    "name_zh": "豪華客房",
                    "name_en": "Deluxe Room",
                    "name_ja": "デラックスルーム",
                    "size_sqm": 40,
                }
            ],
        },
        "source_urls": ["https://example.com/hotel"],
    }


def test_profile_quality_counts_only_explicit_evidence():
    complete = _profile()
    complete["michelin_restaurants"] = [
        {
            "name": "Restaurant",
            "guide_year": 2026,
            "distinction": "one_star",
            "verified_at": "2026-10-01",
            "source_url": "https://guide.michelin.com/example",
        },
        {"name": "Incomplete entry", "distinction": "selected"},
    ]
    incomplete = _profile("hotel-b", verified_at="2026-08-01")
    incomplete.pop("stay_times")
    incomplete["lounge"] = {}
    incomplete["room_snapshot"]["rooms"][0]["name_ja"] = None
    incomplete["room_snapshot"]["rooms"][0].pop("size_sqm")

    report = build_hotel_profile_quality(
        {"updated_at": "2026-10-15", "profiles": [complete, incomplete]}
    )

    assert report["as_of"] == "2026-10-15"
    assert report["profile_count"] == 2
    assert report["room_count"] == 2
    assert report["profile_coverage"]["monthly_review_current"]["count"] == 1
    assert report["profile_coverage"]["stay_times_sourced"]["count"] == 1
    assert report["profile_coverage"]["lounge_status_explicit"]["count"] == 1
    assert report["room_coverage"]["trilingual_names"]["count"] == 1
    assert report["room_coverage"]["area_documented"]["count"] == 1
    assert report["facility_evidence"]["pool"]["count"] == 2
    assert report["facility_evidence"]["spa"]["count"] == 0
    assert report["michelin"]["restaurant_count"] == 1
    assert report["michelin"]["hotel_count"] == 1
    assert report["michelin"]["latest_guide_year"] == 2026
    assert report["michelin"]["distinction_counts"] == {"one_star": 1}
    assert report["hotels"][0]["hotel_id"] == "hotel-b"
    assert "stay_times_sourced" in report["hotels"][0]["missing_evidence"]


def test_profile_quality_uses_latest_source_evidence_date_deterministically():
    older = _profile("hotel-old", verified_at="2026-09-01")
    newer = _profile("hotel-new", verified_at="2026-10-10")

    report = build_hotel_profile_quality(
        {"updated_at": "2026-10-01", "profiles": [older, newer]}, review_days=31
    )

    assert report["as_of"] == "2026-10-10"
    assert report["profile_coverage"]["monthly_review_current"]["count"] == 1
    old_row = next(row for row in report["hotels"] if row["hotel_id"] == "hotel-old")
    assert old_row["review_age_days"] == 39
    assert "monthly_review_current" in old_row["missing_evidence"]


def test_priority_central_taiwan_profiles_have_official_stay_times():
    payload = json.loads(
        Path("public/data/hotel_profiles.json").read_text(encoding="utf-8")
    )
    profiles = {item["hotel_id"]: item for item in payload["profiles"]}
    expected = {
        "grand_hilai_kaohsiung": ("15:00", "11:00", "grand-hilai.com"),
        "hotel_nikko_kaohsiung": ("15:00", "12:00", "nikkokaohsiung.com"),
        "intercontinental_kaohsiung": ("15:00", "12:00", "ihg.com"),
        "hoshinoya_guguan": ("15:00", "12:00", "hoshinoresorts.com"),
        "sheraton_hsinchu": ("16:00", "11:00", "marriott.com"),
        "windsor_taichung": ("16:00", "11:00", "windsortaiwan.com"),
        "kaohsiung_marriott": ("15:00", "12:00", "marriott.com"),
        "mu_jiaoxi_reserve": ("15:00", "11:00", "muhotels.com"),
        "wyndham_sun_moon_lake": ("15:00", "11:00", "ezhotel.cloud"),
        "the_lalu_sun_moon_lake": ("14:30", "12:00", "thelalu.com.tw"),
    }

    for hotel_id, (check_in, check_out, source_host) in expected.items():
        stay_times = profiles[hotel_id]["stay_times"]
        assert stay_times["check_in"] == check_in
        assert stay_times["check_out"] == check_out
        assert stay_times["source_type"] == "official"
        assert source_host in stay_times["source_url"]


def test_committed_profile_quality_has_complete_sourced_stay_times():
    profiles = json.loads(
        Path("public/data/hotel_profiles.json").read_text(encoding="utf-8")
    )
    report = build_hotel_profile_quality(profiles)
    lalu_row = next(
        hotel
        for hotel in report["hotels"]
        if hotel["hotel_id"] == "the_lalu_sun_moon_lake"
    )
    episode = next(
        profile
        for profile in profiles["profiles"]
        if profile["hotel_id"] == "episode_daan_taipei"
    )
    fuhsing = next(
        profile
        for profile in profiles["profiles"]
        if profile["hotel_id"] == "tango_hotel_taipei_fuhsing"
    )
    changan = next(
        profile
        for profile in profiles["profiles"]
        if profile["hotel_id"] == "k_hotel_taipei_changan"
    )
    united = next(
        profile
        for profile in profiles["profiles"]
        if profile["hotel_id"] == "united_hotel_taipei"
    )
    eslite = next(
        profile
        for profile in profiles["profiles"]
        if profile["hotel_id"] == "eslite_hotel"
    )
    w_taipei = next(
        profile
        for profile in profiles["profiles"]
        if profile["hotel_id"] == "w_taipei"
    )

    assert "stay_times_sourced" not in lalu_row["missing_evidence"]
    assert episode["stay_times"] == {
        "check_in": "15:00",
        "check_out": "12:00",
        "source_type": "gds_directory",
        "source_url": "https://www.travelweekly.com/Hotels/Taipei-Taiwan/EPISODE-Daan-Taipei-p59542287",
        "observed_at": "2026-11-09",
    }
    assert fuhsing["room_inventory"] == 70
    assert fuhsing["stay_times"] == {
        "check_in": "16:00",
        "check_out": "11:00",
        "source_type": "official",
        "source_url": "https://fh.tango-hotels.com/_tw/06faq/faq.php",
    }
    assert len(fuhsing["room_snapshot"]["rooms"]) == 9
    assert {room["size_sqm"] for room in fuhsing["room_snapshot"]["rooms"]} == {
        23,
        26,
        33,
        39,
    }
    assert fuhsing["service_charge_source_type"] == "pending"
    assert changan["room_inventory"] == 103
    assert changan["stay_times"] == {
        "check_in": "15:00",
        "check_out": "12:00",
        "source_type": "official",
        "source_url": "https://changan.khotels.com.tw/zh-TW/about-us",
    }
    assert changan["service_charge_percent"] is None
    assert changan["service_charge_source_type"] == "pending"
    assert len(changan["room_snapshot"]["rooms"]) == 5
    assert {room["size_sqm"] for room in changan["room_snapshot"]["rooms"]} == {
        26,
        30,
        46,
    }
    assert all(
        room["name_zh"] and room["name_en"] and room["name_ja"]
        for room in changan["room_snapshot"]["rooms"]
    )
    assert united["room_inventory"] == 228
    assert united["stay_times"] == {
        "check_in": "15:00",
        "check_out": "12:00",
        "source_type": "official_booking",
        "source_url": "https://hotel.gobooking.com.tw/zh-TW/UNITED-TP/Booking",
    }
    assert united["service_charge_percent"] is None
    assert united["service_charge_source_type"] == "pending"
    assert len(united["room_snapshot"]["rooms"]) == 9
    assert {room["size_sqm"] for room in united["room_snapshot"]["rooms"]} == {
        26,
        30,
        33,
        53,
    }
    assert all(
        room["name_zh"] and room["name_en"] and room["name_ja"]
        for room in united["room_snapshot"]["rooms"]
    )
    assert eslite["verified_at"] == "2026-11-12"
    assert eslite["room_inventory"] == 104
    assert eslite["lounge"] == {
        "available": True,
        "name": "The Lounge",
        "kind": "lobby_lounge",
    }
    assert eslite["facilities"] == {
        "pool": None,
        "fitness": True,
        "spa": None,
        "sauna": None,
        "steam_room": None,
    }
    assert "06:00" in eslite["facility_notes"]["en"]
    assert "22:00" in eslite["facility_notes"]["en"]
    assert "24-hour" not in eslite["facility_notes"]["en"]
    eslite_rooms = eslite["room_snapshot"]["rooms"]
    assert len(eslite_rooms) == 5
    assert sum(room["room_count"] for room in eslite_rooms) == 104
    assert {
        room["name_en"]: room["name_ja"]
        for room in eslite_rooms
        if room["name_en"] != "Family Suite"
    } == {
        "Deluxe": "デラックスルーム",
        "Studio": "スタジオルーム",
        "Suite": "スイートルーム",
        "Library Suite": "ライブラリールーム",
    }
    assert w_taipei["verified_at"] == "2026-11-12"
    assert w_taipei["lounge"] == {
        "available": True,
        "name": "WOOBAR",
        "kind": "bar_lounge",
    }
    yen = next(
        restaurant
        for restaurant in w_taipei["restaurants"]
        if restaurant["name"] == "YEN Chinese Restaurant"
    )
    assert yen["status"] == "temporarily_closed"
    assert yen["expected_reopening"] == "2027-06"
    w_room_names = {
        room["name_en"]: room["name_ja"]
        for room in w_taipei["room_snapshot"]["rooms"]
    }
    assert w_room_names == {
        "Wonderful Room": "ワンダフルルーム",
        "Spectacular Room": "スペクタキュラールーム",
        "Fabulous Room": "ファビュラスルーム",
        "Cool Corner Room": "クールコーナールーム",
        "Fantastic Suite": "Fantastic Suite",
        "Marvelous Suite": "マーヴェラススイート",
        "WOW Suite": "WOWスイート",
        "Extreme WOW Suite": "エクストリームWOWスイート",
    }
    assert report["profile_coverage"]["monthly_review_current"] == {
        "count": 36,
        "total": 71,
        "percent": 50.7,
    }
    assert report["profile_coverage"]["lounge_status_explicit"] == {
        "count": 59,
        "total": 71,
        "percent": 83.1,
    }
    library_suite = next(
        room for room in eslite_rooms if room["name_en"] == "Library Suite"
    )
    assert (library_suite["size_sqm_min"], library_suite["size_sqm_max"]) == (
        89,
        182,
    )
    assert report["profile_coverage"]["stay_times_sourced"] == {
        "count": 71,
        "total": 71,
        "percent": 100.0,
    }
