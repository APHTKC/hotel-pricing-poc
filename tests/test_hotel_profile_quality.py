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
    }

    for hotel_id, (check_in, check_out, source_host) in expected.items():
        stay_times = profiles[hotel_id]["stay_times"]
        assert stay_times["check_in"] == check_in
        assert stay_times["check_out"] == check_out
        assert stay_times["source_type"] == "official"
        assert source_host in stay_times["source_url"]
