import json
from pathlib import Path


def test_episode_daan_stay_times_403_is_fail_closed_and_cooled_down():
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
    assert "stay_times" not in episode
