from decimal import Decimal
from pathlib import Path

import yaml

from scrapers.adapters.gobooking import PROPERTIES, parse_room_size, split_tax_inclusive_total


def test_parse_room_size():
    assert parse_room_size("9坪/30平方公尺") == Decimal("30")
    assert parse_room_size("房間佔地約11坪(37 平方公尺)") == Decimal("37")
    assert parse_room_size("房間大小：6.5坪 / 21平方米") == Decimal("21")
    assert parse_room_size("房型介紹：8坪") == Decimal("26.45")
    assert parse_room_size("unknown") is None


def test_split_tax_inclusive_total():
    assert split_tax_inclusive_total(Decimal("5544")) == (
        Decimal("4800"),
        Decimal("480"),
        Decimal("264"),
    )


def test_solaria_uses_verified_gobooking_property():
    assert PROPERTIES["solaria_nishitetsu_taipei"]["slug"] == "SOLARIA-TPXM"
    assert PROPERTIES["solaria_nishitetsu_taipei"]["plan_code"] == (
        "a25b928f-1de1-4e85-af69-2b62e246fd25"
    )


def test_fleur_de_chine_uses_verified_breakfast_plan():
    assert PROPERTIES["fleur_de_chine"]["slug"] == "FLEUR-NT"
    assert PROPERTIES["fleur_de_chine"]["plan_code"] == (
        "148573a7-09c7-4330-9af6-73d0d11156ac"
    )
    assert PROPERTIES["fleur_de_chine"]["breakfast_included"] is True
    assert PROPERTIES["fleur_de_chine"]["cancellation"] == (
        "入住 14 天前取消可全額退款"
    )


def test_united_hotel_uses_verified_room_only_plan_without_inferred_tax_components():
    prop = PROPERTIES["united_hotel_taipei"]
    assert prop["slug"] == "UNITED-TP"
    assert prop["plan_code"] == "4351f17b-a94d-4615-b7e1-fa5b9e2c30d4"
    assert prop["breakfast_included"] is False
    assert prop["tax_inclusion"].value == "included"
    assert prop["tax_components_verified"] is False
    assert "第三日以前" in prop["cancellation"]


def test_united_hotel_is_enabled_in_daily_and_candidate_catalogs():
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )

    daily_row = next(
        row for row in daily["hotels"] if row["id"] == "united_hotel_taipei"
    )
    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "united_hotel_taipei"
    )

    assert daily_row["adapter"] == "gobooking"
    assert candidate["enabled"] is True
    assert candidate["automation_status"] == "verified"
    assert "component tax percentages are not exposed" in candidate["automation_note"]


def test_k_hotel_changan_keeps_unpublished_tax_basis_unknown():
    prop = PROPERTIES["k_hotel_taipei_changan"]
    assert prop["slug"] == "K-TPCA"
    assert prop["plan_code"] == "2734b789-d6b0-4eac-8963-e742908e4cea"
    assert prop["breakfast_included"] is False
    assert prop["tax_inclusion"].value == "unknown"
    assert prop["tax_components_verified"] is False
    assert prop["cancellation"] == "入住前至少14天取消可全額退款"


def test_k_hotel_changan_is_enabled_in_daily_and_candidate_catalogs():
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )

    daily_row = next(
        row for row in daily["hotels"] if row["id"] == "k_hotel_taipei_changan"
    )
    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "k_hotel_taipei_changan"
    )

    assert daily_row["adapter"] == "gobooking"
    assert candidate["enabled"] is True
    assert candidate["automation_status"] == "verified"
    assert "tax_inclusion remains unknown" in candidate["automation_note"]


def test_tango_taichung_uses_verified_breakfast_plan_without_inferred_components():
    prop = PROPERTIES["tango_hotel_taichung"]
    assert prop["slug"] == "TANGO-TC"
    assert prop["plan_code"] == "fbc0ffb6-f5fa-44df-b2ec-efe74822b2f6"
    assert prop["breakfast_included"] is True
    assert prop["tax_inclusion"].value == "included"
    assert prop["tax_components_verified"] is False
    assert prop["cancellation"] == "入住14天前取消可全額退款"


def test_tango_taichung_is_enabled_after_clean_single_probe():
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )

    daily_row = next(
        row for row in daily["hotels"] if row["id"] == "tango_hotel_taichung"
    )
    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "tango_hotel_taichung"
    )

    assert daily_row["adapter"] == "gobooking"
    assert candidate["enabled"] is True
    assert candidate["automation_status"] == "verified"
    assert "collected 11 live +30-day breakfast-included rates" in candidate[
        "automation_note"
    ]
    assert "component percentages are not published" in candidate["automation_note"]


def test_property_probe_workflows_do_not_fan_out_on_shared_adapter_changes():
    expected_paths = {
        "probe-united-hotel-taipei.yml": (
            "scripts/run_united_once.py",
            "config/hotels.united-only.yaml",
        ),
        "probe-k-hotel-changan.yml": (
            "scripts/run_k_hotel_changan_once.py",
            "config/hotels.k-hotel-changan-only.yaml",
        ),
        "probe-tango-taichung.yml": (
            "scripts/run_tango_taichung_once.py",
            "config/hotels.tango-taichung-only.yaml",
        ),
    }
    for workflow, paths in expected_paths.items():
        text = Path(".github/workflows", workflow).read_text(encoding="utf-8")
        assert "scrapers/adapters/gobooking.py" not in text
        for path in paths:
            assert path in text
