import json
from pathlib import Path


def test_episode_daan_official_403_remains_audited_after_gds_evidence_is_added():
    diagnostic = json.loads(
        Path("artifacts/episode-daan-profile-evidence-diagnostic.json").read_text(
            encoding="utf-8"
        )
    )
    profiles = json.loads(
        Path("public/data/hotel_profiles.json").read_text(encoding="utf-8")
    )
    episode = next(
        profile
        for profile in profiles["profiles"]
        if profile["hotel_id"] == "episode_daan_taipei"
    )

    assert diagnostic["status"] == "blocked_http_403"
    assert diagnostic["missing_fields"] == ["check_in", "check_out"]
    assert {row["http_status"] for row in diagnostic["outcomes"]} == {403}
    assert diagnostic["cooldown"]["until"] == "2026-12-06T01:42:43Z"
    assert diagnostic["safety"] == {
        "bypass_attempted": False,
        "cross_property_inference_allowed": False,
        "unknown_values_preserved": True,
    }
    assert episode["stay_times"] == {
        "check_in": "15:00",
        "check_out": "12:00",
        "source_type": "gds_directory",
        "source_url": "https://www.travelweekly.com/Hotels/Taipei-Taiwan/EPISODE-Daan-Taipei-p59542287",
        "observed_at": "2026-11-09",
    }
