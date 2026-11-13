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


def test_grand_mayfull_alternative_official_flow_is_fail_closed():
    diagnostic = json.loads(
        Path(
            "artifacts/grand-mayfull-alternative-official-flow-diagnostic.json"
        ).read_text(encoding="utf-8")
    )

    assert diagnostic["hotel_id"] == "grand_mayfull_taipei"
    assert diagnostic["status"] == "not_suitable_for_daily_rates"
    assert diagnostic["probe_limit"] == {
        "candidate_attempts_this_batch": 1,
        "retried": False,
    }
    assert diagnostic["outcome"]["http_status"] == 200
    assert diagnostic["outcome"]["has_legacy_2016_offer_copy"] is True
    assert diagnostic["outcome"]["has_current_breakfast_product_metadata"] is False
    assert diagnostic["missing_canonical_fields"] == [
        "current_live_room_product",
        "room_type_code",
        "breakfast_included_per_product",
        "cancellation_class_per_product",
        "cancellation_deadline_per_product",
        "queried_at_price_per_product",
    ]
    assert diagnostic["safety"] == {
        "bypass_attempted": False,
        "cross_source_inference_allowed": False,
        "unknown_values_preserved": True,
    }
    assert "materially changes" in diagnostic["cooldown"]["retry_condition"]


def test_hotel_royal_hsinchu_fastbooking_alternative_is_fail_closed():
    diagnostic = json.loads(
        Path(
            "artifacts/hotel-royal-hsinchu-fastbooking-alternative-diagnostic.json"
        ).read_text(encoding="utf-8")
    )

    assert diagnostic["hotel_id"] == "hotel_royal_hsinchu"
    assert diagnostic["status"] == "blocked_tls_handshake"
    assert diagnostic["probe_limit"] == {
        "candidate_attempts_this_batch": 1,
        "retried": False,
    }
    assert diagnostic["outcome"] == {
        "http_status": None,
        "final_url": None,
        "tls_connection_established": False,
        "error_class": "ssl_connection_failed",
        "room_product_received": False,
    }
    assert "tax_inclusion_per_product" in diagnostic["missing_canonical_fields"]
    assert diagnostic["safety"] == {
        "bypass_attempted": False,
        "cross_source_inference_allowed": False,
        "unknown_values_preserved": True,
    }
    assert "materially changes" in diagnostic["cooldown"]["retry_condition"]
