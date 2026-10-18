import json
from decimal import Decimal
from pathlib import Path

import scripts.build_static_data as build_static_data
from scripts.build_static_data import (
    DASHBOARD_FIELDS,
    _dashboard_row,
    _daily_market_digest,
    _data_quality_warnings,
    _history_summary,
    _heatmap_row,
    _latest_batch,
    _latest_batches_by_platform,
    _load_browser_snapshot_rows,
    _month_key,
    _partition_id,
    _plausible_luxury_rate,
    _publishable_live_rate,
    _public_adapter_health,
    _room_type_match_quality,
    _weekly_digest,
)


def _load_latest_details_payload():
    index = json.loads(
        build_static_data.LATEST_DETAILS_INDEX_TARGET.read_text(encoding="utf-8")
    )
    rates = []
    for item in index["hotels"]:
        rates.extend(
            json.loads(
                (build_static_data.LATEST_DETAILS_DIR / Path(item["path"]).name).read_text(
                    encoding="utf-8"
                )
            )["rates"]
        )
    return {**index, "rates": rates}


def _assert_strict_comparison_contract(rows):
    """Complete OTA snapshots remain visible; only evidenced rooms are comparable."""
    assert rows
    assert all(
        row["comparison_status"] in {"comparable", "insufficient_product_metadata"}
        for row in rows
    )
    assert all(
        row["comparison_status"] != "comparable"
        or (
            row["strict_parity_eligible"] is True
            and row["stable_room_type_id"]
            and row["comparison_key"]
        )
        for row in rows
    )


def test_room_type_match_quality_prioritizes_unresolved_evidence_candidates():
    rows = [
        {
            "hotel_id": "hotel-a",
            "hotel_name": "Hotel A",
            "city": "Taipei",
            "room_type_name": "Deluxe King",
            "room_type_code": "OTA-1",
            "room_size_sqm": "45",
            "source_platform": "booking_com",
            "source_url": "https://example.com/latest",
            "queried_at": "2026-10-18T01:00:00Z",
            "room_match_status": "unmatched_label",
            "strict_parity_eligible": False,
        },
        {
            "hotel_id": "hotel-a",
            "hotel_name": "Hotel A",
            "city": "Taipei",
            "room_type_name": "Deluxe King",
            "room_type_code": "OTA-1",
            "room_size_sqm": "45",
            "source_platform": "booking_com",
            "source_url": "https://example.com/older",
            "queried_at": "2026-10-17T01:00:00Z",
            "room_match_status": "unmatched_label",
            "strict_parity_eligible": False,
        },
        {
            "hotel_id": "hotel-a",
            "hotel_name": "Hotel A",
            "city": "Taipei",
            "stable_room_type_id": "rt-1",
            "room_match_status": "matched_exact_evidenced_label",
            "strict_parity_eligible": True,
        },
    ]

    quality = _room_type_match_quality(rows)

    assert quality["observation_count"] == 3
    assert quality["mapped_observations"] == 1
    assert quality["strict_parity_eligible_observations"] == 1
    assert quality["hotels_requiring_evidence"] == 1
    hotel = quality["hotels"][0]
    assert hotel["unresolved_observations"] == 2
    assert hotel["top_unresolved_room_labels"] == [{
        "room_match_status": "unmatched_label",
        "room_type_name": "Deluxe King",
        "room_type_code": "OTA-1",
        "source_platform": "booking_com",
        "room_size_sqm": "45",
        "observations": 2,
        "latest_queried_at": "2026-10-18T01:00:00Z",
        "sample_source_url": "https://example.com/latest",
    }]


def test_latest_batch_uses_recent_workflow_window():
    rows = [
        {"queried_at": "2026-09-07T03:31:00+00:00", "hotel_name": "old"},
        {"queried_at": "2026-09-07T22:09:00+00:00", "hotel_name": "Capella"},
        {"queried_at": "2026-09-07T22:11:00+00:00", "hotel_name": "Okura"},
    ]

    latest = _latest_batch(rows)

    assert [row["hotel_name"] for row in latest] == ["Capella", "Okura"]


def test_latest_batch_prefers_exact_run_id_over_time_window():
    rows = [
        {
            "run_id": "older-run",
            "queried_at": "2026-09-07T22:09:00+00:00",
            "hotel_name": "Older",
        },
        {
            "run_id": "latest-run",
            "queried_at": "2026-09-07T22:10:00+00:00",
            "hotel_name": "First in latest run",
        },
        {
            "run_id": "latest-run",
            "queried_at": "2026-09-07T23:01:00+00:00",
            "hotel_name": "Last in latest run",
        },
    ]

    latest = _latest_batch(rows)

    assert [row["hotel_name"] for row in latest] == [
        "First in latest run",
        "Last in latest run",
    ]


def test_latest_batches_keep_official_and_independent_ota_runs():
    rows = [
        {"run_id": "official-old", "source_platform": "official", "queried_at": "2026-10-07T01:00:00+00:00", "hotel_name": "Old"},
        {"run_id": "official-new", "source_platform": "official", "queried_at": "2026-10-08T01:00:00+00:00", "hotel_name": "Official"},
        {"run_id": "ota-a-old", "source_platform": "booking_com", "hotel_id": "hotel-a", "queried_at": "2026-10-07T12:00:00+00:00", "hotel_name": "OTA A old"},
        {"run_id": "ota-a-new", "source_platform": "booking_com", "hotel_id": "hotel-a", "queried_at": "2026-10-08T12:00:00+00:00", "hotel_name": "OTA A"},
        {"run_id": "ota-b-new", "source_platform": "booking_com", "hotel_id": "hotel-b", "queried_at": "2026-10-08T13:00:00+00:00", "hotel_name": "OTA B"},
    ]

    latest = _latest_batches_by_platform(rows)

    assert {row["hotel_name"] for row in latest} == {"Official", "OTA A", "OTA B"}


def test_browser_snapshot_loader_requires_complete_canonical_product(tmp_path):
    valid = {
        "observation_id": "ota-1", "queried_at": "2026-10-08T12:00:00Z",
        "check_in": "2026-11-06", "check_out": "2026-11-07", "lead_days": 29,
        "hotel_id": "capella_taipei", "hotel_name": "Capella Taipei",
        "room_type_code": "booking:room-1", "room_type_name": "Superior King Room",
        "room_size_sqm": 48, "rate_plan_code": "booking:plan-1",
        "rate_plan_name": "Breakfast and free cancellation", "breakfast_included": True,
        "cancellation_policy": "Free cancellation before 2026-11-05",
        "tax_inclusion": "included", "total_price": 30800, "currency": "TWD",
        "source_platform": "booking_com", "source_method": "visible_browser_snapshot",
        "source_property_id": "capella-taipei", "source_url": "https://www.booking.com/hotel/tw/capella-taipei.html",
        "status": "live",
    }
    path = tmp_path / "ota.jsonl"
    path.write_text(json.dumps(valid) + "\n", encoding="utf-8")
    assert _load_browser_snapshot_rows(path)[0]["total_twd"] == "30800"

    invalid = {**valid, "breakfast_included": None}
    path.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
    try:
        _load_browser_snapshot_rows(path)
    except ValueError as error:
        assert "required product fields" in str(error)
    else:
        raise AssertionError("incomplete OTA browser products must fail closed")


def test_browser_snapshot_loader_accepts_unknown_tax_but_keeps_it_non_comparable(tmp_path):
    row = {
        "observation_id": "ota-tax-unknown", "queried_at": "2026-10-12T01:00:00Z",
        "check_in": "2026-10-19", "check_out": "2026-10-20", "lead_days": 7,
        "rooms": 1, "adults": 2, "children": 0,
        "hotel_id": "mo_taipei", "hotel_name": "Mandarin Oriental Taipei",
        "room_type_code": "booking:room-1", "room_type_name": "Deluxe King",
        "room_size_sqm": 55, "rate_plan_code": "booking:plan-1",
        "rate_plan_name": "Room only with dated free cancellation",
        "breakfast_included": False,
        "cancellation_policy": "Free cancellation before 2026-10-18",
        "tax_inclusion": "unknown", "total_price": 12705, "currency": "TWD",
        "source_platform": "booking_com", "source_method": "visible_browser_snapshot",
        "source_property_id": "mandarin-oriental-taipei",
        "source_url": "https://www.booking.com/hotel/tw/mandarin-oriental-taipei.html",
        "status": "live",
    }
    path = tmp_path / "ota-tax-unknown.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    loaded = _load_browser_snapshot_rows(path)

    assert len(loaded) == 1
    assert build_static_data.canonical_comparison_key(loaded[0]) is None
    assert loaded[0]["total_twd"] == "12705"


def test_regent_visible_booking_snapshot_has_complete_dated_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    regent = [row for row in rows if row["hotel_id"] == "regent_taipei"]

    assert len(regent) == 34
    assert {float(row["room_size_sqm"]) for row in regent} == {45.0, 56.0, 65.0, 111.0}
    assert {row["check_in"] for row in regent} == {"2026-12-16", "2026-12-18", "2026-12-20"}
    latest_query = max(row["queried_at"] for row in regent)
    latest = [row for row in regent if row["queried_at"] == latest_query]
    assert len(latest) == 5
    assert len({row["room_type_code"] for row in latest}) == 5
    assert {float(row["room_size_sqm"]) for row in latest} == {45.0, 56.0, 65.0, 111.0}
    assert min(float(row["total_price"]) for row in latest) == 9615
    assert max(float(row["total_price"]) for row in latest) == 25716
    assert {row["breakfast_included"] for row in latest} == {False, True}
    assert {row["source_platform"] for row in latest} == {"expedia_group"}
    assert all(row["tax_inclusion"] == "included" for row in latest)
    assert all(build_static_data.canonical_comparison_key(row) is not None for row in latest)


def test_taipei_marriott_visible_booking_snapshot_has_complete_dated_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    marriott = [
        row for row in rows
        if row["hotel_id"] == "taipei_marriott"
        and row["source_platform"] == "booking_com"
    ]

    assert len(marriott) == 31
    assert len({row["room_type_code"] for row in marriott}) == 14
    assert {float(row["room_size_sqm"]) for row in marriott} == {40.0, 43.0, 51.0, 65.0, 80.0}
    assert min(float(row["total_price"]) for row in marriott) == 8538
    assert max(float(row["total_price"]) for row in marriott) == 48395
    assert {row["check_in"] for row in marriott} == {"2026-12-16"}
    assert all(build_static_data.canonical_comparison_key(row) is None for row in marriott)


def test_courtyard_taipei_visible_booking_snapshot_has_strict_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    courtyard = [
        row for row in rows
        if row["hotel_id"] == "courtyard_taipei"
        and row["source_platform"] == "booking_com"
    ]

    assert len(courtyard) == 9
    assert len({row["room_type_code"] for row in courtyard}) == 7
    assert {float(row["room_size_sqm"]) for row in courtyard} == {36.0, 43.0, 69.0, 82.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in courtyard} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in courtyard) == 6988.3
    assert max(float(row["total_price"]) for row in courtyard) == 21598.5
    assert {row["tax_inclusion"] for row in courtyard} == {"excluded"}
    assert all(
        Decimal(str(row["service_charge"]))
        == Decimal(str(row["price_before_tax"])) * Decimal("0.1")
        for row in courtyard
    )
    assert all(build_static_data.canonical_comparison_key(row) is not None for row in courtyard)


def test_latest_payload_keeps_hotels_com_courtyard_taipei_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "courtyard_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 2
    assert {float(row["room_size_sqm"]) for row in hotel} == {62.0, 90.0}
    assert {row["breakfast_included"] for row in hotel} == {True}
    assert min(float(row["total_price"]) for row in hotel) == 18480
    assert max(float(row["total_price"]) for row in hotel) == 20790
    _assert_strict_comparison_contract(hotel)


def test_grand_view_resort_visible_booking_snapshot_replaces_empty_date_with_live_rates():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    grand_view = [
        row for row in rows
        if row["hotel_id"] == "grand_view_resort_beitou"
        and row["source_platform"] == "booking_com"
    ]

    assert len(grand_view) == 5
    assert len({row["room_type_code"] for row in grand_view}) == 5
    assert {float(row["room_size_sqm"]) for row in grand_view} == {50.0, 63.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in grand_view} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in grand_view) == 13860
    assert max(float(row["total_price"]) for row in grand_view) == 28160
    assert {row["tax_inclusion"] for row in grand_view} == {"included"}
    assert {row["breakfast_included"] for row in grand_view} == {True}
    assert all(float(row["total_price"]) > float(row["price_before_tax"]) for row in grand_view)
    assert all(build_static_data.canonical_comparison_key(row) is not None for row in grand_view)


def test_latest_payload_keeps_hotels_com_grand_view_resort_snapshot():
    payload = _load_latest_details_payload()
    grand_view = [
        row for row in payload["rates"]
        if row["hotel_id"] == "grand_view_resort_beitou"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(grand_view) == 7
    assert {float(row["room_size_sqm"]) for row in grand_view} == {
        49.0,
        50.0,
        56.0,
        63.0,
    }
    assert {row["breakfast_included"] for row in grand_view} == {True}
    assert min(float(row["total_twd"]) for row in grand_view) == 15725
    assert max(float(row["total_twd"]) for row in grand_view) == 27572
    _assert_strict_comparison_contract(grand_view)


def test_miramar_garden_visible_booking_snapshot_has_strict_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    miramar = [
        row for row in rows
        if row["hotel_id"] == "miramar_garden_taipei"
        and row["source_platform"] == "booking_com"
    ]

    assert len(miramar) == 23
    assert len({row["room_type_code"] for row in miramar}) == 12
    assert {float(row["room_size_sqm"]) for row in miramar} == {42.0, 80.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in miramar} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in miramar) == 4333
    assert max(float(row["total_price"]) for row in miramar) == 8222
    assert {row["tax_inclusion"] for row in miramar} == {"unknown"}
    assert {row["breakfast_included"] for row in miramar} == {False, True}
    assert all(build_static_data.canonical_comparison_key(row) is None for row in miramar)


def test_miramar_garden_visible_expedia_snapshot_has_comparable_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    miramar = [
        row for row in rows
        if row["hotel_id"] == "miramar_garden_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(miramar) == 9
    assert {float(row["room_size_sqm"]) for row in miramar} == {42.0, 89.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in miramar} == {(2, 0, 1)}
    assert {row["breakfast_included"] for row in miramar} == {False, True}
    assert min(float(row["total_twd"]) for row in miramar) == 3671
    assert max(float(row["total_twd"]) for row in miramar) == 6257
    assert all(build_static_data.canonical_comparison_key(row) is not None for row in miramar)


def test_hotel_gracery_visible_booking_snapshot_has_strict_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    gracery = [
        row for row in rows
        if row["hotel_id"] == "hotel_gracery_taipei"
        and row["source_platform"] == "booking_com"
    ]

    assert len(gracery) == 24
    assert len({row["room_type_code"] for row in gracery}) == 12
    assert {float(row["room_size_sqm"]) for row in gracery} == {25.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in gracery} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in gracery) == 5200
    assert max(float(row["total_price"]) for row in gracery) == 8710
    assert {row["tax_inclusion"] for row in gracery} == {"unknown"}
    assert {row["breakfast_included"] for row in gracery} == {False, True}
    assert all(build_static_data.canonical_comparison_key(row) is None for row in gracery)


def test_hotel_gracery_visible_expedia_snapshot_has_comparable_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    gracery = [
        row for row in rows
        if row["hotel_id"] == "hotel_gracery_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(gracery) == 2
    assert len({row["room_type_code"] for row in gracery}) == 2
    assert {float(row["room_size_sqm"]) for row in gracery} == {25.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in gracery} == {(2, 0, 1)}
    assert {float(row["total_twd"]) for row in gracery} == {6184.0}
    assert {row["breakfast_included"] for row in gracery} == {False}
    assert {row["tax_inclusion"] for row in gracery} == {"included"}
    assert all(build_static_data.canonical_comparison_key(row) is not None for row in gracery)


def test_mitsui_garden_visible_booking_snapshot_has_strict_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    mitsui = [
        row for row in rows
        if row["hotel_id"] == "mitsui_garden_taipei_zhongxiao"
        and row["source_platform"] == "booking_com"
    ]

    assert len(mitsui) == 14
    assert len({row["room_type_code"] for row in mitsui}) == 8
    assert {float(row["room_size_sqm"]) for row in mitsui} == {22.0, 25.0, 26.0, 28.0, 30.0, 35.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in mitsui} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in mitsui) == 6290
    assert max(float(row["total_price"]) for row in mitsui) == 10098
    assert {row["tax_inclusion"] for row in mitsui} == {"unknown"}
    assert {row["breakfast_included"] for row in mitsui} == {False, True}
    assert all(build_static_data.canonical_comparison_key(row) is None for row in mitsui)


def test_mitsui_garden_visible_expedia_snapshot_has_comparable_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    mitsui = [
        row for row in rows
        if row["hotel_id"] == "mitsui_garden_taipei_zhongxiao"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(mitsui) == 6
    assert len({row["room_type_code"] for row in mitsui}) == 6
    assert {float(row["room_size_sqm"]) for row in mitsui} == {25.0, 26.0, 28.0, 30.0, 35.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in mitsui} == {(2, 0, 1)}
    assert min(float(row["total_twd"]) for row in mitsui) == 5248
    assert max(float(row["total_twd"]) for row in mitsui) == 7100
    assert {row["breakfast_included"] for row in mitsui} == {False}
    assert {row["tax_inclusion"] for row in mitsui} == {"included"}
    assert all(build_static_data.canonical_comparison_key(row) is not None for row in mitsui)


def test_radium_kagaya_visible_booking_snapshot_excludes_four_person_product():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    kagaya = [
        row for row in rows
        if row["hotel_id"] == "radium_kagaya_taipei"
        and row["source_platform"] == "booking_com"
    ]

    assert len(kagaya) == 6
    assert len({row["room_type_code"] for row in kagaya}) == 4
    assert {float(row["room_size_sqm"]) for row in kagaya} == {43.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in kagaya} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in kagaya) == 12272
    assert max(float(row["total_price"]) for row in kagaya) == 15836
    assert {row["breakfast_included"] for row in kagaya} == {False, True}
    assert all("505734817" not in row["room_type_code"] for row in kagaya)
    assert all(build_static_data.canonical_comparison_key(row) is None for row in kagaya)


def test_latest_payload_keeps_hotels_com_radium_kagaya_snapshot():
    payload = _load_latest_details_payload()
    kagaya = [
        row for row in payload["rates"]
        if row["hotel_id"] == "radium_kagaya_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(kagaya) == 11
    assert {float(row["room_size_sqm"]) for row in kagaya} == {
        43.0,
        50.0,
        52.0,
        53.0,
    }
    assert {row["breakfast_included"] for row in kagaya} == {False, True}
    assert min(float(row["total_twd"]) for row in kagaya) == 15447
    assert max(float(row["total_twd"]) for row in kagaya) == 38144
    _assert_strict_comparison_contract(kagaya)


def test_landis_visible_booking_snapshot_uses_two_adult_baseline_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    landis = [
        row for row in rows
        if row["hotel_id"] == "the_landis_taipei"
        and row["source_platform"] == "booking_com"
    ]

    assert len(landis) == 8
    assert len({row["room_type_code"] for row in landis}) == 8
    assert {float(row["room_size_sqm"]) for row in landis} == {26.0, 43.0, 53.0, 56.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in landis} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in landis) == 5450
    assert max(float(row["total_price"]) for row in landis) == 9260
    assert {row["breakfast_included"] for row in landis} == {False}
    assert all(build_static_data.canonical_comparison_key(row) is None for row in landis)


def test_landis_visible_expedia_snapshot_has_comparable_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    landis = [
        row for row in rows
        if row["hotel_id"] == "the_landis_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(landis) == 5
    assert len({row["room_type_code"] for row in landis}) == 5
    assert {float(row["room_size_sqm"]) for row in landis} == {26.0, 53.0, 56.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in landis} == {(2, 0, 1)}
    assert min(float(row["total_twd"]) for row in landis) == 4691
    assert max(float(row["total_twd"]) for row in landis) == 7957
    assert {row["breakfast_included"] for row in landis} == {False}
    assert {row["tax_inclusion"] for row in landis} == {"included"}
    assert all(build_static_data.canonical_comparison_key(row) is not None for row in landis)


def test_grand_hilai_kaohsiung_visible_expedia_snapshot_has_comparable_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    hilai = [
        row for row in rows
        if row["hotel_id"] == "grand_hilai_kaohsiung"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hilai) == 4
    assert len({row["room_type_code"] for row in hilai}) == 4
    assert {float(row["room_size_sqm"]) for row in hilai} == {30.0, 33.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in hilai} == {(2, 0, 1)}
    assert min(float(row["total_twd"]) for row in hilai) == 4104
    assert max(float(row["total_twd"]) for row in hilai) == 8358
    assert {row["breakfast_included"] for row in hilai} == {False, True}
    assert {row["tax_inclusion"] for row in hilai} == {"included"}
    assert all(build_static_data.canonical_comparison_key(row) is not None for row in hilai)


def test_kimpton_visible_booking_snapshot_uses_two_adult_baseline_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    kimpton = [
        row for row in rows
        if row["hotel_id"] == "kimpton_da_an"
        and row["source_platform"] == "booking_com"
    ]
    latest_query = max(row["queried_at"] for row in kimpton)
    kimpton = [row for row in kimpton if row["queried_at"] == latest_query]

    assert len(kimpton) == 11
    assert len({row["room_type_code"] for row in kimpton}) == 11
    assert {float(row["room_size_sqm"]) for row in kimpton} == {32.0, 37.0, 38.0, 58.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in kimpton} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in kimpton) == 11689
    assert max(float(row["total_price"]) for row in kimpton) == 24394
    assert {row["breakfast_included"] for row in kimpton} == {False}
    assert all(build_static_data.canonical_comparison_key(row) is None for row in kimpton)


def test_latest_payload_keeps_hotels_com_kimpton_snapshot():
    payload = _load_latest_details_payload()
    kimpton = [
        row for row in payload["rates"]
        if row["hotel_id"] == "kimpton_da_an"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(kimpton) == 4
    assert {float(row["room_size_sqm"]) for row in kimpton} == {37.0, 38.0}
    assert {row["breakfast_included"] for row in kimpton} == {False}
    assert min(float(row["total_price"]) for row in kimpton) == 22061
    assert max(float(row["total_price"]) for row in kimpton) == 29395
    _assert_strict_comparison_contract(kimpton)


def test_latest_payload_keeps_hotels_com_taipei_garden_snapshot():
    payload = _load_latest_details_payload()
    garden = [
        row for row in payload["rates"]
        if row["hotel_id"] == "taipei_garden_hotel"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(garden) == 9
    assert {float(row["room_size_sqm"]) for row in garden} == {31.0, 34.0, 35.0}
    assert {row["breakfast_included"] for row in garden} == {False}
    assert min(float(row["total_price"]) for row in garden) == 13855
    assert max(float(row["total_price"]) for row in garden) == 16957
    _assert_strict_comparison_contract(garden)


def test_latest_payload_keeps_hotels_com_intercontinental_taichung_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "intercontinental_taichung"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 9
    assert {float(row["room_size_sqm"]) for row in hotel} == {40.0, 55.0}
    assert {row["breakfast_included"] for row in hotel} == {False}
    assert min(float(row["total_price"]) for row in hotel) == 11907
    assert max(float(row["total_price"]) for row in hotel) == 18664
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_the_lin_taichung_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "the_lin_taichung"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 13
    assert {float(row["room_size_sqm"]) for row in hotel} == {50.0, 53.0, 56.0, 63.0}
    assert {row["breakfast_included"] for row in hotel} == {False, True}
    assert min(float(row["total_price"]) for row in hotel) == 4748
    assert max(float(row["total_price"]) for row in hotel) == 10633
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_millennium_taichung_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "millennium_taichung"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 6
    assert {float(row["room_size_sqm"]) for row in hotel} == {32.0, 36.0, 53.0}
    assert {row["breakfast_included"] for row in hotel} == {False, True}
    assert min(float(row["total_price"]) for row in hotel) == 3690
    assert max(float(row["total_price"]) for row in hotel) == 8735
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_le_meridien_taichung_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "le_meridien_taichung"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 2
    assert {float(row["room_size_sqm"]) for row in hotel} == {43.0}
    assert {row["breakfast_included"] for row in hotel} == {False}
    assert {float(row["total_price"]) for row in hotel} == {7277}
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_windsor_taichung_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "windsor_taichung"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 5
    assert {float(row["room_size_sqm"]) for row in hotel} == {31.0, 37.0, 41.0, 76.0}
    assert {row["breakfast_included"] for row in hotel} == {False, True}
    assert min(float(row["total_price"]) for row in hotel) == 5848
    assert max(float(row["total_price"]) for row in hotel) == 14553
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_intercontinental_kaohsiung_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "intercontinental_kaohsiung"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 9
    assert {float(row["room_size_sqm"]) for row in hotel} == {36.0, 46.0, 56.0}
    assert {row["breakfast_included"] for row in hotel} == {False}
    assert min(float(row["total_price"]) for row in hotel) == 7830
    assert max(float(row["total_price"]) for row in hotel) == 16860
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_kaohsiung_marriott_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "kaohsiung_marriott"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 8
    assert {float(row["room_size_sqm"]) for row in hotel} == {46.0, 69.0, 92.0}
    assert {row["breakfast_included"] for row in hotel} == {False}
    assert min(float(row["total_price"]) for row in hotel) == 5387
    assert max(float(row["total_price"]) for row in hotel) == 16364
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_courtyard_taipei_downtown_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "courtyard_taipei_downtown"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 4
    assert {float(row["room_size_sqm"]) for row in hotel} == {30.0}
    assert {row["breakfast_included"] for row in hotel} == {False}
    assert min(float(row["total_price"]) for row in hotel) == 10973
    assert max(float(row["total_price"]) for row in hotel) == 15362
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_renaissance_taipei_shihlin_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "renaissance_taipei_shihlin"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 2
    assert {float(row["room_size_sqm"]) for row in hotel} == {31.0}
    assert {row["breakfast_included"] for row in hotel} == {False}
    assert min(float(row["total_price"]) for row in hotel) == 12689
    assert max(float(row["total_price"]) for row in hotel) == 13489
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_hotel_proverbs_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "hotel_proverbs_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 3
    assert {float(row["room_size_sqm"]) for row in hotel} == {37.0, 38.0, 41.0}
    assert {row["breakfast_included"] for row in hotel} == {False}
    assert min(float(row["total_price"]) for row in hotel) == 14621
    assert max(float(row["total_price"]) for row in hotel) == 17363
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_grand_mayfull_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "grand_mayfull_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 5
    assert {float(row["room_size_sqm"]) for row in hotel} == {
        50.0, 60.0, 70.0, 105.0
    }
    assert {row["breakfast_included"] for row in hotel} == {False, True}
    assert min(float(row["total_price"]) for row in hotel) == 20561
    assert max(float(row["total_price"]) for row in hotel) == 54830
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_grand_hilai_taipei_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "grand_hilai_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 4
    assert {float(row["room_size_sqm"]) for row in hotel} == {44.0, 59.0}
    assert {row["breakfast_included"] for row in hotel} == {False, True}
    assert min(float(row["total_price"]) for row in hotel) == 7488
    assert max(float(row["total_price"]) for row in hotel) == 16416
    _assert_strict_comparison_contract(hotel)


def test_latest_payload_keeps_hotels_com_episode_daan_snapshot():
    payload = _load_latest_details_payload()
    hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "episode_daan_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(hotel) == 5
    assert {float(row["room_size_sqm"]) for row in hotel} == {30.0, 36.0}
    assert {row["breakfast_included"] for row in hotel} == {False}
    assert min(float(row["total_price"]) for row in hotel) == 13052
    assert max(float(row["total_price"]) for row in hotel) == 13629
    _assert_strict_comparison_contract(hotel)


def test_sheraton_visible_booking_snapshot_keeps_breakfast_products_separate():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    sheraton = [
        row for row in rows
        if row["hotel_id"] == "sheraton_grand_taipei"
        and row["source_platform"] == "booking_com"
    ]
    latest_query = max(row["queried_at"] for row in sheraton)
    sheraton = [row for row in sheraton if row["queried_at"] == latest_query]

    assert len(sheraton) == 14
    assert len({row["room_type_code"] for row in sheraton}) == 7
    assert {float(row["room_size_sqm"]) for row in sheraton} == {32.0, 35.0, 40.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in sheraton} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in sheraton) == 9240
    assert max(float(row["total_price"]) for row in sheraton) == 12821
    assert {row["breakfast_included"] for row in sheraton} == {False, True}
    assert all(build_static_data.canonical_comparison_key(row) is None for row in sheraton)


def test_okura_visible_booking_snapshot_keeps_free_cancellation_products_separate():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    okura = [
        row for row in rows
        if row["hotel_id"] == "okura_prestige_taipei"
        and row["source_platform"] == "booking_com"
    ]
    latest_query = max(row["queried_at"] for row in okura)
    okura = [row for row in okura if row["queried_at"] == latest_query]

    assert len(okura) == 8
    assert len({row["room_type_code"] for row in okura}) == 4
    assert {float(row["room_size_sqm"]) for row in okura} == {44.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in okura} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in okura) == 8384
    assert max(float(row["total_price"]) for row in okura) == 12181
    assert {row["breakfast_included"] for row in okura} == {False, True}
    assert all("可免費取消" in row["cancellation_policy"] for row in okura)
    assert all(build_static_data.canonical_comparison_key(row) is None for row in okura)


def test_okura_visible_expedia_snapshot_has_comparable_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    okura = [
        row for row in rows
        if row["hotel_id"] == "okura_prestige_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(okura) == 4
    assert len({row["room_type_code"] for row in okura}) == 4
    assert {float(row["room_size_sqm"]) for row in okura} == {44.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in okura} == {(2, 0, 1)}
    assert {row["breakfast_included"] for row in okura} == {False}
    assert min(float(row["total_twd"]) for row in okura) == 8384
    assert max(float(row["total_twd"]) for row in okura) == 9419
    assert all(build_static_data.canonical_comparison_key(row) is not None for row in okura)


def test_palais_visible_booking_snapshot_uses_two_adult_breakfast_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    palais = [
        row for row in rows
        if row["hotel_id"] == "palais_de_chine"
        and row["source_platform"] == "booking_com"
    ]
    latest_query = max(row["queried_at"] for row in palais)
    palais = [row for row in palais if row["queried_at"] == latest_query]

    assert len(palais) == 9
    assert len({row["room_type_code"] for row in palais}) == 9
    assert {float(row["room_size_sqm"]) for row in palais} == {30.0, 37.0, 50.0, 67.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in palais} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in palais) == 11829
    assert max(float(row["total_price"]) for row in palais) == 20372
    assert {row["breakfast_included"] for row in palais} == {True}
    assert all("可免費取消" in row["cancellation_policy"] for row in palais)
    assert all(build_static_data.canonical_comparison_key(row) is None for row in palais)


def test_palais_visible_expedia_snapshot_has_comparable_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    palais = [
        row for row in rows
        if row["hotel_id"] == "palais_de_chine"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(palais) == 8
    assert len({row["room_type_code"] for row in palais}) == 8
    assert {float(row["room_size_sqm"]) for row in palais} == {30.0, 36.0, 50.0, 66.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in palais} == {(2, 0, 1)}
    assert {row["breakfast_included"] for row in palais} == {False, True}
    assert min(float(row["total_twd"]) for row in palais) == 9556
    assert max(float(row["total_twd"]) for row in palais) == 17672
    assert all(build_static_data.canonical_comparison_key(row) is not None for row in palais)


def test_jr_east_visible_booking_snapshot_excludes_non_two_adult_products():
    rows = _load_browser_snapshot_rows(build_static_data.OTA_BROWSER_SOURCE)
    jr = [
        row for row in rows
        if row["hotel_id"] == "hotel_metropolitan_premier_taipei"
        and row["source_platform"] == "booking_com"
    ]
    latest_query = max(row["queried_at"] for row in jr)
    jr = [row for row in jr if row["queried_at"] == latest_query]

    assert len(jr) == 14
    assert len({row["room_type_code"] for row in jr}) == 10
    assert {float(row["room_size_sqm"]) for row in jr} == {36.0, 43.0, 62.0}
    assert {(row["adults"], row["children"], row["rooms"]) for row in jr} == {(2, 0, 1)}
    assert min(float(row["total_price"]) for row in jr) == 6975
    assert max(float(row["total_price"]) for row in jr) == 13485
    assert {row["breakfast_included"] for row in jr} == {False, True}
    assert all(row["room_type_code"] not in {"booking:715720913", "booking:715720937"} for row in jr)
    assert all(build_static_data.canonical_comparison_key(row) is None for row in jr)


def test_first_screen_payload_includes_validated_ota_snapshot_hotels():
    payload = json.loads(
        build_static_data.LATEST_HEATMAP_TARGET.read_text(encoding="utf-8")
    )
    ota_hotel_ids = {
        row["hotel_id"]
        for row in payload["rates"]
        if row.get("source_platform") != "official"
    }

    assert {
        "regent_taipei",
        "w_taipei",
        "mitsui_garden_taipei_zhongxiao",
        "radium_kagaya_taipei",
        "the_landis_taipei",
        "kimpton_da_an",
        "sheraton_grand_taipei",
        "okura_prestige_taipei",
        "palais_de_chine",
        "hotel_metropolitan_premier_taipei",
    } <= ota_hotel_ids


def test_latest_payload_keeps_each_ota_platforms_newest_w_taipei_snapshot():
    payload = _load_latest_details_payload()
    w_rows = [row for row in payload["rates"] if row["hotel_id"] == "w_taipei"]
    hotels_com = [
        row for row in w_rows if row["source_platform"] == "expedia_group"
    ]

    assert {row["source_platform"] for row in w_rows} == {
        "booking_com",
        "expedia_group",
    }
    assert len(hotels_com) == 7
    assert {float(row["room_size_sqm"]) for row in hotels_com} == {
        43.0,
        46.0,
        70.0,
        95.0,
    }
    assert min(float(row["total_twd"]) for row in hotels_com) == 13860
    assert max(float(row["total_twd"]) for row in hotels_com) == 25410
    _assert_strict_comparison_contract(hotels_com)


def test_latest_payload_keeps_booking_and_hotels_com_regent_snapshots():
    payload = _load_latest_details_payload()
    regent = [
        row for row in payload["rates"] if row["hotel_id"] == "regent_taipei"
    ]
    hotels_com = [
        row for row in regent if row["source_platform"] == "expedia_group"
    ]

    assert {row["source_platform"] for row in regent} == {
        "booking_com",
        "expedia_group",
    }
    assert len(hotels_com) == 5
    assert {float(row["room_size_sqm"]) for row in hotels_com} == {
        45.0,
        56.0,
        65.0,
        111.0,
    }
    assert min(float(row["total_twd"]) for row in hotels_com) == 9615
    assert max(float(row["total_twd"]) for row in hotels_com) == 25716
    _assert_strict_comparison_contract(hotels_com)


def test_latest_payload_keeps_booking_and_hotels_com_mandarin_snapshots():
    payload = _load_latest_details_payload()
    mandarin = [
        row for row in payload["rates"] if row["hotel_id"] == "mo_taipei"
    ]
    hotels_com = [
        row for row in mandarin if row["source_platform"] == "expedia_group"
    ]

    assert {"booking_com", "expedia_group"}.issubset(
        {row["source_platform"] for row in mandarin}
    )
    assert len(hotels_com) == 15
    assert {float(row["room_size_sqm"]) for row in hotels_com} == {
        55.0,
        70.0,
        86.0,
        110.0,
        133.0,
    }
    assert min(float(row["total_twd"]) for row in hotels_com) == 14079
    assert max(float(row["total_twd"]) for row in hotels_com) == 60684
    _assert_strict_comparison_contract(hotels_com)


def test_latest_payload_keeps_booking_and_hotels_com_grand_hyatt_snapshots():
    payload = _load_latest_details_payload()
    grand_hyatt = [
        row for row in payload["rates"]
        if row["hotel_id"] == "grand_hyatt_taipei"
    ]
    hotels_com = [
        row for row in grand_hyatt
        if row["source_platform"] == "expedia_group"
    ]

    assert {row["source_platform"] for row in grand_hyatt} == {
        "booking_com",
        "expedia_group",
    }
    assert len(hotels_com) == 10
    assert {float(row["room_size_sqm"]) for row in hotels_com} == {
        33.0,
        40.0,
        50.0,
        60.0,
        83.0,
    }
    assert min(float(row["total_twd"]) for row in hotels_com) == 12017
    assert max(float(row["total_twd"]) for row in hotels_com) == 25156
    _assert_strict_comparison_contract(hotels_com)


def test_latest_payload_keeps_three_shangrila_taipei_sources():
    payload = _load_latest_details_payload()
    shangrila = [
        row for row in payload["rates"]
        if row["hotel_id"] == "shangrila_taipei"
    ]
    hotels_com = [
        row for row in shangrila if row["source_platform"] == "expedia_group"
    ]

    assert {row["source_platform"] for row in shangrila} == {
        "official",
        "booking_com",
        "expedia_group",
    }
    assert len(hotels_com) == 18
    assert {float(row["room_size_sqm"]) for row in hotels_com} == {
        36.0,
        40.0,
        41.0,
        56.0,
        60.0,
        75.0,
    }
    assert min(float(row["total_twd"]) for row in hotels_com) == 8830
    assert max(float(row["total_twd"]) for row in hotels_com) == 27203
    _assert_strict_comparison_contract(hotels_com)


def test_latest_payload_keeps_hotels_com_royal_nikko_snapshot():
    payload = _load_latest_details_payload()
    royal_nikko = [
        row for row in payload["rates"]
        if row["hotel_id"] == "royal_nikko_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(royal_nikko) == 7
    assert {float(row["room_size_sqm"]) for row in royal_nikko} == {
        32.0,
        38.0,
        65.0,
    }
    assert {row["breakfast_included"] for row in royal_nikko} == {False, True}
    assert min(float(row["total_twd"]) for row in royal_nikko) == 6732
    assert max(float(row["total_twd"]) for row in royal_nikko) == 13690
    _assert_strict_comparison_contract(royal_nikko)


def test_latest_payload_keeps_hotels_com_eslite_snapshot():
    payload = _load_latest_details_payload()
    eslite = [
        row for row in payload["rates"]
        if row["hotel_id"] == "eslite_hotel"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(eslite) == 5
    assert {float(row["room_size_sqm"]) for row in eslite} == {
        43.0,
        53.0,
        69.0,
    }
    assert {row["breakfast_included"] for row in eslite} == {False}
    assert min(float(row["total_twd"]) for row in eslite) == 7708
    assert max(float(row["total_twd"]) for row in eslite) == 12987
    _assert_strict_comparison_contract(eslite)


def test_latest_payload_keeps_hotels_com_gaia_snapshot():
    payload = _load_latest_details_payload()
    gaia = [
        row for row in payload["rates"]
        if row["hotel_id"] == "the_gaia_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(gaia) == 4
    assert {float(row["room_size_sqm"]) for row in gaia} == {
        36.0,
        50.0,
        66.0,
    }
    assert {row["breakfast_included"] for row in gaia} == {True}
    assert min(float(row["total_twd"]) for row in gaia) == 10292
    assert max(float(row["total_twd"]) for row in gaia) == 61358
    _assert_strict_comparison_contract(gaia)


def test_latest_payload_keeps_hotels_com_solaria_snapshot():
    payload = _load_latest_details_payload()
    solaria = [
        row for row in payload["rates"]
        if row["hotel_id"] == "solaria_nishitetsu_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(solaria) == 8
    assert {float(row["room_size_sqm"]) for row in solaria} == {
        21.0,
        23.0,
        24.0,
        26.0,
        33.0,
    }
    assert {row["breakfast_included"] for row in solaria} == {False}
    assert min(float(row["total_twd"]) for row in solaria) == 7645
    assert max(float(row["total_twd"]) for row in solaria) == 12385
    _assert_strict_comparison_contract(solaria)


def test_latest_payload_keeps_hotels_com_grand_hotel_snapshot():
    payload = _load_latest_details_payload()
    grand_hotel = [
        row for row in payload["rates"]
        if row["hotel_id"] == "grand_hotel_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(grand_hotel) == 4
    assert {float(row["room_size_sqm"]) for row in grand_hotel} == {
        20.0,
        36.0,
        79.0,
    }
    assert {row["breakfast_included"] for row in grand_hotel} == {False, True}
    assert min(float(row["total_twd"]) for row in grand_hotel) == 4487
    assert max(float(row["total_twd"]) for row in grand_hotel) == 11928
    _assert_strict_comparison_contract(grand_hotel)


def test_latest_payload_keeps_hotels_com_le_meridien_snapshot():
    payload = _load_latest_details_payload()
    le_meridien = [
        row for row in payload["rates"]
        if row["hotel_id"] == "le_meridien_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(le_meridien) == 9
    assert {float(row["room_size_sqm"]) for row in le_meridien} == {
        35.0,
        38.0,
        60.0,
        75.0,
    }
    assert {row["breakfast_included"] for row in le_meridien} == {False}
    assert min(float(row["total_twd"]) for row in le_meridien) == 15015
    assert max(float(row["total_twd"]) for row in le_meridien) == 56364
    _assert_strict_comparison_contract(le_meridien)


def test_latest_payload_keeps_hotels_com_intercontinental_taipei_snapshot():
    payload = _load_latest_details_payload()
    intercontinental = [
        row for row in payload["rates"]
        if row["hotel_id"] == "intercontinental_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(intercontinental) == 6
    assert {float(row["room_size_sqm"]) for row in intercontinental} == {
        38.0,
        48.0,
    }
    assert {row["breakfast_included"] for row in intercontinental} == {False}
    assert min(float(row["total_twd"]) for row in intercontinental) == 16262
    assert max(float(row["total_twd"]) for row in intercontinental) == 22107
    _assert_strict_comparison_contract(intercontinental)


def test_latest_payload_keeps_hotels_com_humble_house_snapshot():
    payload = _load_latest_details_payload()
    humble_house = [
        row for row in payload["rates"]
        if row["hotel_id"] == "humble_house_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(humble_house) == 8
    assert {float(row["room_size_sqm"]) for row in humble_house} == {
        26.0,
        36.0,
        53.0,
    }
    assert {row["breakfast_included"] for row in humble_house} == {False}
    assert min(float(row["total_twd"]) for row in humble_house) == 10395
    assert max(float(row["total_twd"]) for row in humble_house) == 20790
    _assert_strict_comparison_contract(humble_house)


def test_latest_payload_keeps_hotels_com_taipei_marriott_snapshot():
    payload = _load_latest_details_payload()
    marriott = [
        row for row in payload["rates"]
        if row["hotel_id"] == "taipei_marriott"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(marriott) == 16
    assert {float(row["room_size_sqm"]) for row in marriott} == {
        40.0,
        43.0,
        51.0,
        66.0,
        79.0,
    }
    assert {row["breakfast_included"] for row in marriott} == {False}
    assert min(float(row["total_twd"]) for row in marriott) == 7928
    assert max(float(row["total_twd"]) for row in marriott) == 47702
    _assert_strict_comparison_contract(marriott)


def test_latest_payload_keeps_hotels_com_sheraton_taipei_snapshot():
    payload = _load_latest_details_payload()
    sheraton = [
        row for row in payload["rates"]
        if row["hotel_id"] == "sheraton_grand_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(sheraton) == 7
    assert {float(row["room_size_sqm"]) for row in sheraton} == {
        32.0,
        35.0,
        40.0,
    }
    assert {row["breakfast_included"] for row in sheraton} == {False}
    assert min(float(row["total_twd"]) for row in sheraton) == 8501
    assert max(float(row["total_twd"]) for row in sheraton) == 11550
    _assert_strict_comparison_contract(sheraton)


def test_latest_payload_keeps_hotels_com_hotel_indigo_snapshot():
    payload = _load_latest_details_payload()
    indigo = [
        row for row in payload["rates"]
        if row["hotel_id"] == "indigo_taipei_north"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(indigo) == 6
    assert {float(row["room_size_sqm"]) for row in indigo} == {
        36.0,
        40.0,
        60.0,
        73.0,
    }
    assert {row["breakfast_included"] for row in indigo} == {False}
    assert min(float(row["total_twd"]) for row in indigo) == 5523
    assert max(float(row["total_twd"]) for row in indigo) == 11298
    _assert_strict_comparison_contract(indigo)


def test_latest_payload_keeps_hotels_com_doubletree_zhongshan_snapshot():
    payload = _load_latest_details_payload()
    doubletree = [
        row for row in payload["rates"]
        if row["hotel_id"] == "doubletree_taipei_zhongshan"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(doubletree) == 6
    assert {float(row["room_size_sqm"]) for row in doubletree} == {
        33.0,
        35.0,
        36.0,
        46.0,
    }
    assert {row["breakfast_included"] for row in doubletree} == {False}
    assert min(float(row["total_twd"]) for row in doubletree) == 6699
    assert max(float(row["total_twd"]) for row in doubletree) == 12243
    _assert_strict_comparison_contract(doubletree)


def test_latest_payload_keeps_hotels_com_howard_plaza_snapshot():
    payload = _load_latest_details_payload()
    howard = [
        row for row in payload["rates"]
        if row["hotel_id"] == "howard_plaza_taipei"
        and row["source_platform"] == "expedia_group"
    ]

    assert len(howard) == 2
    assert {float(row["room_size_sqm"]) for row in howard} == {20.0, 26.0}
    assert {row["breakfast_included"] for row in howard} == {False}
    assert {float(row["total_twd"]) for row in howard} == {5350}
    _assert_strict_comparison_contract(howard)


def test_implausibly_low_twd_rate_is_not_published():
    assert _plausible_luxury_rate({"total_twd": "350"}) is False
    assert _plausible_luxury_rate({"total_twd": "12300"}) is True


def test_static_publication_requires_explicit_live_status():
    assert _publishable_live_rate({"status": "live", "total_twd": "12300"}) is True
    assert _publishable_live_rate({"status": "demo", "total_twd": "12300"}) is False
    assert _publishable_live_rate({"total_twd": "12300"}) is False


def test_dashboard_row_drops_large_internal_fields():
    source = {
        "hotel_id": "okura-taipei",
        "hotel_name": "The Okura Prestige Taipei",
        "city": "Taipei",
        "district": "Zhongshan",
        "queried_at": "2026-09-07T22:11:00+00:00",
        "raw_payload": "not for the browser",
        "cancellation_policy": "kept in the JSONL source",
    }

    published = _dashboard_row(source)

    assert set(published) == set(DASHBOARD_FIELDS)
    assert published["city"] == "Taipei"
    assert published["district"] == "Zhongshan"
    assert "raw_payload" not in published
    assert published["cancellation_policy"] == "kept in the JSONL source"
    assert published["comparison_status"] == "insufficient_product_metadata"


def test_dashboard_row_preserves_and_backfills_rate_source_metadata():
    ota = _dashboard_row(
        {
            "source_platform": "booking_com",
            "source_method": "partner_api",
            "source_property_id": "property-123",
        }
    )
    legacy_official = _dashboard_row({})

    assert ota["source_platform"] == "booking_com"
    assert ota["source_method"] == "partner_api"
    assert ota["source_property_id"] == "property-123"
    assert legacy_official["source_platform"] == "official"
    assert legacy_official["source_method"] == "public_booking_page"
    assert legacy_official["source_property_id"] is None


def test_static_build_deduplicates_and_embeds_shared_market_summary(
    monkeypatch, tmp_path
):
    source = tmp_path / "rates.jsonl"
    rates_dir = tmp_path / "rates"
    summary = tmp_path / "history_summary.json"
    rates_index = rates_dir / "index.json"
    latest_summary = tmp_path / "latest_summary.json"
    latest_heatmap = tmp_path / "latest_heatmap.json"
    latest_details_dir = tmp_path / "latest_details"
    latest_details_index = latest_details_dir / "index.json"
    legacy_latest_details = tmp_path / "latest_details.json"
    legacy_latest = tmp_path / "latest.json"
    legacy_latest.write_text("legacy", encoding="utf-8")
    health_source = tmp_path / "adapter_health.json"
    health_target = tmp_path / "public_health.json"
    digest_target = tmp_path / "digest.json"
    room_type_match_quality_target = tmp_path / "room_type_match_quality.json"
    legacy = tmp_path / "rates.json"
    legacy.write_text("legacy", encoding="utf-8")
    common = {
        "status": "live",
        "check_in": "2026-10-01",
        "room_type_code": "ROOM",
        "room_type_name": "Room",
        "rate_plan_code": "BAR",
        "rate_plan_name": "Best Available Rate",
        "price_per_sqm": "200",
        "currency": "TWD",
        "source_url": "https://example.com",
    }
    rows = [
        {
            **common,
            "observation_id": "old",
            "hotel_id": "hotel-a",
            "hotel_name": "Hotel A",
            "queried_at": "2026-09-24T01:00:00+00:00",
            "total_price": "9000",
            "total_twd": "9000",
        },
        {
            **common,
            "observation_id": "new",
            "hotel_id": "hotel-a",
            "hotel_name": "Hotel A",
            "queried_at": "2026-09-24T20:00:00+00:00",
            "total_price": "10000",
            "total_twd": "10000",
        },
        {
            **common,
            "observation_id": "other",
            "hotel_id": "hotel-b",
            "hotel_name": "Hotel B",
            "queried_at": "2026-09-24T20:01:00+00:00",
            "total_price": "20000",
            "total_twd": "20000",
        },
        {
            **common,
            "status": "demo",
            "observation_id": "demo",
            "hotel_id": "hotel-c",
            "hotel_name": "Hotel C",
            "queried_at": "2026-09-24T20:02:00+00:00",
            "total_price": "30000",
            "total_twd": "30000",
        },
    ]
    source.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(build_static_data, "SOURCE", source)
    monkeypatch.setattr(build_static_data, "OTA_BROWSER_SOURCE", tmp_path / "missing-ota.jsonl")
    monkeypatch.setattr(build_static_data, "RATES_DIR", rates_dir)
    monkeypatch.setattr(build_static_data, "HISTORY_SUMMARY_TARGET", summary)
    monkeypatch.setattr(build_static_data, "RATES_INDEX_TARGET", rates_index)
    monkeypatch.setattr(build_static_data, "LATEST_SUMMARY_TARGET", latest_summary)
    monkeypatch.setattr(build_static_data, "LATEST_HEATMAP_TARGET", latest_heatmap)
    monkeypatch.setattr(build_static_data, "LATEST_DETAILS_DIR", latest_details_dir)
    monkeypatch.setattr(build_static_data, "LATEST_DETAILS_INDEX_TARGET", latest_details_index)
    monkeypatch.setattr(build_static_data, "LEGACY_LATEST_DETAILS_TARGET", legacy_latest_details)
    monkeypatch.setattr(build_static_data, "LEGACY_LATEST_TARGET", legacy_latest)
    monkeypatch.setattr(build_static_data, "HEALTH_SOURCE", health_source)
    monkeypatch.setattr(build_static_data, "HEALTH_TARGET", health_target)
    monkeypatch.setattr(build_static_data, "DIGEST_TARGET", digest_target)
    monkeypatch.setattr(
        build_static_data,
        "ROOM_TYPE_MATCH_QUALITY_TARGET",
        room_type_match_quality_target,
    )
    monkeypatch.setattr(build_static_data, "LEGACY_TARGET", legacy)

    build_static_data.main()

    hotel_a = json.loads((rates_dir / "2026-09" / "hotel-a.json").read_text(encoding="utf-8"))
    hotel_b = json.loads((rates_dir / "2026-09" / "hotel-b.json").read_text(encoding="utf-8"))
    assert len(hotel_a["rates"]) == 1
    assert len(hotel_b["rates"]) == 1
    assert {hotel_a["rates"][0]["total_twd"], hotel_b["rates"][0]["total_twd"]} == {"10000", "20000"}
    assert hotel_a["market_summary"]["median_adr_twd"] == 10000
    index_payload = json.loads(rates_index.read_text(encoding="utf-8"))
    assert index_payload["months"][0]["month"] == "2026-09"
    assert {item["path"] for item in index_payload["months"][0]["hotels"]} == {
        "rates/2026-09/hotel-a.json", "rates/2026-09/hotel-b.json"
    }
    details_index = json.loads(latest_details_index.read_text(encoding="utf-8"))
    detail_rows = []
    for item in details_index["hotels"]:
        detail_rows.extend(
            json.loads((tmp_path / item["path"]).read_text(encoding="utf-8"))["rates"]
        )
    summary_latest_payload = json.loads(latest_summary.read_text(encoding="utf-8"))
    heatmap_payload = json.loads(latest_heatmap.read_text(encoding="utf-8"))
    assert details_index["record_count"] == 2
    assert len(detail_rows) == 2
    assert summary_latest_payload["market_summary"]["median_adr_twd"] == 15000
    assert summary_latest_payload["record_count"] == 2
    assert len(heatmap_payload["rates"]) == 2
    assert "cancellation_policy" not in heatmap_payload["rates"][0]
    summary_payload = json.loads(summary.read_text(encoding="utf-8"))
    assert summary_payload["available_months"] == ["2026-09"]
    assert not legacy.exists()
    assert not legacy_latest.exists()
    assert len(summary_payload["daily"]) == 2
    assert {row["hotel_id"] for row in summary_payload["hotels"]} == {
        "hotel-a", "hotel-b"
    }
    assert digest_target.exists()
    quality_payload = json.loads(room_type_match_quality_target.read_text(encoding="utf-8"))
    assert quality_payload["schema_version"] == "1.0"
    assert quality_payload["latest"]["observation_count"] == 2


def test_static_partition_ids_fail_closed_and_heatmap_rows_are_lightweight():
    assert _partition_id("hotel-safe_123") == "hotel-safe_123"
    try:
        _partition_id("../unsafe")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe hotel ids must not become output paths")

    row = _heatmap_row({"hotel_id": "hotel-a", "total_twd": 10000, "source_url": "secret", "comparison_key": "same-product"})
    assert row["hotel_id"] == "hotel-a"
    assert "total_twd" not in row
    assert row["comparison_group_id"] == "6966aafb2ab4821d"
    assert "source_url" not in row


def test_dashboard_row_publishes_nightly_adr_and_nightly_unit_price():
    row = _dashboard_row({
        "hotel_id": "hotel-a", "check_in": "2026-10-01",
        "check_out": "2026-10-03", "nights": 1,
        "total_twd": 24000, "room_size_sqm": 50,
    })

    assert row["nights"] == 2
    assert row["total_twd"] == 24000
    assert row["nightly_adr_twd"] == 12000
    assert row["price_per_sqm"] == 240


def test_month_key_uses_observation_month_and_rejects_missing_timestamp():
    assert _month_key({"queried_at": "2026-09-30T23:59:00+00:00"}) == "2026-09"
    assert _month_key({}) is None


def test_history_summary_preaggregates_daily_and_lead_metrics():
    rows = [
        {
            "hotel_id": "hotel-a", "hotel_name": "Hotel A", "city": "Taipei",
            "district": "Xinyi", "queried_at": "2026-09-24T01:00:00+00:00",
            "lead_days": 7, "room_size_sqm": 50, "total_twd": 10000,
            "price_per_sqm": 200,
        },
        {
            "hotel_id": "hotel-a", "hotel_name": "Hotel A", "city": "Taipei",
            "district": "Xinyi", "queried_at": "2026-09-24T20:00:00+00:00",
            "lead_days": 7, "room_size_sqm": 70, "total_twd": 14000,
            "price_per_sqm": 200,
        },
    ]

    payload = _history_summary(rows)

    assert payload["daily"][0]["average_twd"] == 12000
    assert payload["daily"][0]["median_twd"] == 12000
    assert payload["daily"][0]["core_median_twd"] == 10000
    assert payload["lead_curve"][0]["median_twd"] == 12000


def test_history_and_weekly_market_metrics_exclude_ota_rows():
    official = {
        "hotel_id": "hotel-a", "hotel_name": "Hotel A", "city": "Taipei",
        "district": "Xinyi", "queried_at": "2026-09-24T01:00:00+00:00",
        "check_in": "2026-10-01", "lead_days": 7, "room_size_sqm": 50,
        "total_twd": 10000, "price_per_sqm": 200,
        "source_platform": "official",
    }
    ota = {
        **official, "source_platform": "booking_com", "total_twd": 50000,
        "price_per_sqm": 1000,
    }

    payload = _history_summary([official, ota])

    assert payload["metric_scope"] == "verified_official_only"
    assert payload["verified_market_metrics"]["observations"] == 1
    assert payload["market_summary"]["median_adr_twd"] == 10000
    assert payload["daily"][0]["observations"] == 1
    assert payload["daily"][0]["median_twd"] == 10000
    assert payload["weekly_digest"]["current_period"]["observations"] == 1


def test_weekly_digest_uses_equal_weight_hotel_medians_and_previous_week():
    rows = []
    for day, hotel_id, values in [
        ("2026-09-10", "hotel-a", [8000, 12000]),
        ("2026-09-10", "hotel-b", [20000]),
        ("2026-09-17", "hotel-a", [10000, 14000]),
        ("2026-09-17", "hotel-b", [24000]),
    ]:
        for index, value in enumerate(values):
            rows.append({
                "hotel_id": hotel_id,
                "hotel_name": hotel_id.title(),
                "queried_at": f"{day}T0{index}:00:00+00:00",
                "lead_days": 7 if index == 0 else 30,
                "total_twd": value,
            })

    digest = _weekly_digest(rows)

    assert digest["available"] is True
    assert digest["current_period"]["market_median_twd"] == 18000
    assert digest["previous_period"]["market_median_twd"] == 15000
    assert digest["change_pct"] == 0.2
    assert digest["comparable_hotels"] == 2
    assert {item["lead_days"] for item in digest["lead_time_curve"]} == {7, 30}


def test_weekly_digest_fails_closed_without_history():
    assert _weekly_digest([]) == {
        "available": False,
        "reason": "no_history",
        "currency": "TWD",
    }


def test_public_adapter_health_excludes_diagnostics_and_daily_details():
    payload = _public_adapter_health({"adapters": {"stub:hotel-a": {
        "adapter": "stub", "hotel_id": "hotel-a", "attempts": 3,
        "successes": 2, "failures": 1, "blocked_count": 0,
        "success_rate": 0.6667, "average_response_ms": 1200,
        "last_status": "failed", "last_attempt_at": "2026-09-24T01:00:00+00:00",
        "last_success_at": "2026-09-23T01:00:00+00:00", "cooldown_until": None,
        "daily": {"2026-09-24": {"attempts": 3}}, "reason": "private detail",
    }}})

    assert payload["generated_at"] == "2026-09-24T01:00:00+00:00"
    assert payload["adapters"][0]["success_rate"] == 0.6667
    assert "daily" not in payload["adapters"][0]
    assert "reason" not in payload["adapters"][0]


def test_daily_market_digest_uses_core_rooms_movers_and_strict_parity():
    rows = []
    for day, hotel_id, value in [
        ("2026-09-23", "hotel-a", 10000),
        ("2026-09-23", "hotel-b", 20000),
        ("2026-09-30", "hotel-a", 12000),
        ("2026-09-30", "hotel-b", 18000),
    ]:
        rows.append({
            "hotel_id": hotel_id, "hotel_name": hotel_id.title(),
            "queried_at": f"{day}T01:00:00+00:00", "check_in": "2026-10-07",
            "check_out": "2026-10-08", "room_size_sqm": 50,
            "total_twd": value, "rooms": 1, "adults": 2, "children": 0,
            "breakfast_included": True, "cancellation_policy": "Free cancellation",
            "tax_inclusion": "included", "source_platform": "official",
            "stable_room_type_id": f"rt_{hotel_id}_core_room",
        })
    rows.append({
        **rows[-2], "source_platform": "booking_com", "total_twd": 12300,
    })

    digest = _daily_market_digest(rows)

    assert digest["available"] is True
    # OTA rows are excluded from the verified market movement calculation.
    assert digest["metrics"]["core_adr_change_pct"] == 0.0
    assert digest["metrics"]["largest_increase"]["hotel_id"] == "hotel-a"
    assert digest["metrics"]["largest_decrease"]["hotel_id"] == "hotel-b"
    assert digest["metrics"]["rate_parity_normal_rate"] == 1
    assert 3 <= len(digest["insights"]) <= 4


def test_data_quality_flags_low_volume_and_large_price_change():
    rows = []
    for index in range(1, 8):
        day = f"2026-09-{30-index:02d}"
        rows.extend({
            "hotel_id": "hotel-a", "hotel_name": "Hotel A",
            "queried_at": f"{day}T01:00:00+00:00", "total_twd": 10000,
        } for _ in range(10))
    rows.extend({
        "hotel_id": "hotel-a", "hotel_name": "Hotel A",
        "queried_at": "2026-09-30T01:00:00+00:00", "total_twd": 20000,
    } for _ in range(4))

    quality = _data_quality_warnings(rows)

    assert quality["as_of"] == "2026-09-30"
    codes = {item["code"] for item in quality["hotels"][0]["warnings"]}
    assert codes == {"low_volume", "price_spike"}


def test_history_row_chunks_stay_bounded_without_losing_rows():
    from scripts.build_static_data import _chunk_rate_rows

    rows = [{"id": index, "value": "房價" * 30} for index in range(20)]
    chunks = _chunk_rate_rows(rows, max_bytes=400)

    assert len(chunks) > 1
    assert [row for chunk in chunks for row in chunk] == rows
    assert all(chunk for chunk in chunks)
