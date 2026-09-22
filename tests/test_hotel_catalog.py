import json
from pathlib import Path

import yaml


NEW_TAIPEI_HOTELS = {
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
    assert len(payload["hotels"]) == 63


def test_published_catalog_contains_hotel_royal_hsinchu_manual_link():
    payload = json.loads(Path("public/data/hotels.json").read_text(encoding="utf-8"))
    hotel = next(item for item in payload["hotels"] if item["id"] == "hotel_royal_hsinchu")

    assert hotel["city"] == "Hsinchu"
    assert hotel["enabled"] is False
    assert hotel["automation_status"] == "skipped"
    assert "webhotel-v4/0232" in hotel["booking_url"]
