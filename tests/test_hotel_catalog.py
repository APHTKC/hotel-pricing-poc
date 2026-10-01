import json
from pathlib import Path

import yaml


NEW_TAIPEI_HOTELS = {
    "episode_daan_taipei": "Da'an",
    "courtyard_taipei_downtown": "Zhongshan",
    "hotel_proverbs_taipei": "Da'an",
    "renaissance_taipei_shihlin": "Shilin",
    "doubletree_taipei_zhongshan": "Zhongshan",
    "howard_plaza_taipei": "Da'an",
}


def test_new_taipei_high_end_hotels_are_registered_once_and_marked_skipped():
    payload = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )
    hotels = payload["hotels"]
    ids = [hotel["id"] for hotel in hotels]

    assert len(ids) == len(set(ids))
    for hotel_id, district in NEW_TAIPEI_HOTELS.items():
        hotel = next(hotel for hotel in hotels if hotel["id"] == hotel_id)
        assert hotel["city"] == "Taipei"
        assert hotel["district"] == district
        assert hotel["enabled"] is False
        assert hotel["automation_status"] == "skipped"
        assert hotel["automation_note"]


def test_published_hotel_catalog_contains_all_new_taipei_hotels():
    payload = json.loads(Path("public/data/hotels.json").read_text(encoding="utf-8"))
    ids = {hotel["id"] for hotel in payload["hotels"]}

    assert set(NEW_TAIPEI_HOTELS) <= ids
    assert len(payload["hotels"]) == 67


def test_episode_hotels_are_registered_with_official_profiles_but_not_reprobed():
    catalog = json.loads(Path("public/data/hotels.json").read_text(encoding="utf-8"))["hotels"]
    profiles = json.loads(
        Path("public/data/hotel_profiles.json").read_text(encoding="utf-8")
    )["profiles"]
    hotels = {row["id"]: row for row in catalog}
    profile_by_id = {row["hotel_id"]: row for row in profiles}

    for hotel_id, inventory, room_types in (
        ("episode_daan_taipei", 136, 10),
        ("episode_hsinchu", 140, 7),
    ):
        assert hotels[hotel_id]["enabled"] is False
        assert hotels[hotel_id]["automation_status"] == "skipped"
        assert "without repeating" in hotels[hotel_id]["automation_note"]
        assert profile_by_id[hotel_id]["room_inventory"] == inventory
        assert len(profile_by_id[hotel_id]["room_snapshot"]["rooms"]) == room_types
        assert profile_by_id[hotel_id]["room_snapshot"]["source_type"] == "official"


def test_published_catalog_contains_hotel_royal_hsinchu_manual_link():
    payload = json.loads(Path("public/data/hotels.json").read_text(encoding="utf-8"))
    hotel = next(item for item in payload["hotels"] if item["id"] == "hotel_royal_hsinchu")

    assert hotel["city"] == "Hsinchu"
    assert hotel["enabled"] is False
    assert hotel["automation_status"] == "skipped"
    assert "webhotel-v4/0232" in hotel["booking_url"]


def test_published_catalog_contains_gaia_as_one_time_failed_candidate():
    payload = json.loads(Path("public/data/hotels.json").read_text(encoding="utf-8"))
    hotel = next(item for item in payload["hotels"] if item["id"] == "the_gaia_taipei")

    assert hotel["district"] == "Beitou"
    assert hotel["enabled"] is False
    assert hotel["automation_status"] == "skipped"
    assert "one-time" in hotel["automation_note"].lower()


def test_published_catalog_contains_miramar_after_single_403_check():
    payload = json.loads(Path("public/data/hotels.json").read_text(encoding="utf-8"))
    hotel = next(item for item in payload["hotels"] if item["id"] == "miramar_garden_taipei")

    assert hotel["district"] == "Zhongshan"
    assert hotel["enabled"] is False
    assert hotel["automation_status"] == "skipped"
    assert "403" in hotel["automation_note"]
