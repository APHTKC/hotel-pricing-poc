import json
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


def test_k_hotel_songjiang_is_prepared_but_not_enabled_before_remote_probe():
    prop = PROPERTIES["k_hotel_taipei_songjiang"]
    assert prop == {
        "slug": "K-TPSJ",
        "plan_code": "013df7da-d214-4904-aa73-eda5ac62575d",
        "plan_name": "一般訂房含早餐",
        "cancellation": "入住前至少14天取消可全額退款",
        "breakfast_included": True,
        "tax_inclusion": prop["tax_inclusion"],
        "tax_components_verified": False,
    }
    assert prop["tax_inclusion"].value == "included"

    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )
    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "k_hotel_taipei_songjiang"
    )
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    assert candidate["enabled"] is False
    assert candidate["automation_status"] == "skipped"
    assert "collected 7 live +30-day breakfast-included rates" in candidate[
        "automation_note"
    ]
    assert "GitHub Linux run 42060318442" in candidate["automation_note"]
    assert "Automatic push-triggered probes are disabled" in candidate[
        "automation_note"
    ]
    assert all(row["id"] != candidate["id"] for row in daily["hotels"])


def test_k_hotel_songjiang_probe_diagnostic_records_clean_local_result():
    diagnostic = json.loads(
        Path("artifacts/k-hotel-songjiang-probe-diagnostic.json").read_text(
            encoding="utf-8"
        )
    )
    assert diagnostic["status"] == "remote_probe_failed"
    assert diagnostic["probe_limit"] == {
        "candidate_attempts_this_batch": 1,
        "retried": False,
    }
    assert diagnostic["result"]["observations"] == 7
    assert diagnostic["result"]["external_request_started"] is True
    assert diagnostic["result"]["failures"] == 0
    assert diagnostic["result"]["room_size_sqm_min"] == 23.14
    assert diagnostic["result"]["room_size_sqm_max"] == 39.67
    assert diagnostic["remote_probe"]["status"] == "failed"
    assert diagnostic["remote_probe"]["automatic_trigger_enabled"] is False
    assert diagnostic["remote_probe"]["attempts"][0] == {
        "run_id": 42049772324,
        "conclusion": "cancelled",
        "reason": "The 10-minute job timeout left only 31 seconds after dependency installation, so the collection step was cancelled before it could complete.",
        "artifact_created": False,
    }
    failed_attempt = diagnostic["remote_probe"]["attempts"][1]
    assert failed_attempt["run_id"] == 42060318442
    assert failed_attempt["job_id"] == 127359828307
    assert failed_attempt["conclusion"] == "failure"
    assert failed_attempt["observations"] == 0
    assert failed_attempt["error_type"] == "playwright_timeout"
    assert failed_attempt["timeout_ms"] == 45000
    assert failed_attempt["artifact_id"] == 13432191209
    assert diagnostic["remote_probe"]["workflow_timeout_minutes"] == 20
    workflow = Path(".github/workflows/probe-k-hotel-songjiang.yml").read_text(
        encoding="utf-8"
    )
    assert "timeout-minutes: 20" in workflow
    assert "push:" not in workflow
    assert diagnostic["published_contract"]["tax_components_verified"] is False
    assert diagnostic["decision"].startswith("Keep the candidate disabled")


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


def test_tango_jiantan_uses_verified_breakfast_plan_without_inferred_components():
    prop = PROPERTIES["tango_hotel_taipei_jiantan"]
    assert prop["slug"] == "TANGO-TPJT"
    assert prop["plan_code"] == "4e9c7413-136c-40ec-ba0f-4baaab70cc2f"
    assert prop["breakfast_included"] is True
    assert prop["tax_inclusion"].value == "included"
    assert prop["tax_components_verified"] is False
    assert prop["cancellation"] == "入住14天前取消可全額退款"


def test_tango_jiantan_is_enabled_after_clean_single_probe():
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )

    daily_row = next(
        row
        for row in daily["hotels"]
        if row["id"] == "tango_hotel_taipei_jiantan"
    )
    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "tango_hotel_taipei_jiantan"
    )

    assert daily_row["adapter"] == "gobooking"
    assert candidate["enabled"] is True
    assert candidate["automation_status"] == "verified"
    assert "collected 8 live +30-day breakfast-included rates" in candidate[
        "automation_note"
    ]
    assert "component percentages are not published" in candidate["automation_note"]


def test_tango_xinyi_uses_official_annual_plan_without_inferred_components():
    prop = PROPERTIES["tango_hotel_taipei_xinyi"]
    assert prop["slug"] == "TANGO-TPXY"
    assert prop["plan_code"] == "beaf45ef-4e92-48cd-8244-ecd4a8a934f4"
    assert prop["breakfast_included"] is True
    assert prop["tax_inclusion"].value == "included"
    assert prop["tax_components_verified"] is False
    assert prop["cancellation"] == "入住14天前取消可全額退款"


def test_tango_nanshi_uses_official_annual_plan_without_inferred_components():
    prop = PROPERTIES["tango_hotel_taipei_nanshi"]
    assert prop["slug"] == "TANGO-TPNS"
    assert prop["plan_code"] == "e93e3c23-51d8-4086-b338-cd48064010fb"
    assert prop["breakfast_included"] is True
    assert prop["tax_inclusion"].value == "included"
    assert prop["tax_components_verified"] is False
    assert prop["cancellation"] == "入住14天前取消可全額退款"


def test_tango_shilin_uses_official_annual_plan_without_inferred_components():
    prop = PROPERTIES["tango_hotel_taipei_shilin"]
    assert prop["slug"] == "TANGO-TPSL"
    assert prop["plan_code"] == "8103c234-319d-484f-8792-53c871cc124f"
    assert prop["breakfast_included"] is True
    assert prop["tax_inclusion"].value == "included"
    assert prop["tax_components_verified"] is False
    assert prop["cancellation"] == "入住14天前取消可全額退款"


def test_tango_fuhsing_uses_official_annual_plan_without_inferred_components():
    prop = PROPERTIES["tango_hotel_taipei_fuhsing"]
    assert prop["slug"] == "TANGO-TPFH"
    assert prop["plan_code"] == "70bafbb8-0069-4c3d-80b2-2a177f1073d4"
    assert prop["breakfast_included"] is True
    assert prop["tax_inclusion"].value == "included"
    assert prop["tax_components_verified"] is False
    assert prop["cancellation"] == "入住14天前取消可全額退款"


def test_tango_linsen_uses_official_early_bird_plan_without_inferred_components():
    prop = PROPERTIES["tango_hotel_taipei_linsen"]
    assert prop["slug"] == "TANGO-TPLS"
    assert prop["plan_code"] == "7ee53cc4-7955-482e-aafd-e9bfd3664a5d"
    assert prop["plan_name"] == "早鳥住房專案"
    assert prop["breakfast_included"] is False
    assert prop["tax_inclusion"].value == "included"
    assert prop["tax_components_verified"] is False
    assert prop["cancellation"] == "入住前至少14天取消可全額退款"


def test_tango_changan_uses_official_annual_plan_without_inferred_components():
    prop = PROPERTIES["tango_hotel_taipei_changan"]
    assert prop["slug"] == "TANGO-TPCA"
    assert prop["plan_code"] == "91eb7239-4c52-49ca-9527-86108843020d"
    assert prop["plan_name"] == "【年度住房】優惠專案"
    assert prop["breakfast_included"] is True
    assert prop["tax_inclusion"].value == "included"
    assert prop["tax_components_verified"] is False
    assert prop["cancellation"] == "入住前至少14天取消可全額退款"


def test_tango_changan_is_enabled_after_cross_environment_validation():
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )
    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "tango_hotel_taipei_changan"
    )

    daily_row = next(row for row in daily["hotels"] if row["id"] == candidate["id"])
    assert daily_row["adapter"] == "gobooking"
    assert candidate["enabled"] is True
    assert candidate["automation_status"] == "verified"
    assert "collected 13 live +30-day breakfast-included rates" in candidate[
        "automation_note"
    ]
    assert "GitHub Linux probe 40982344337" in candidate["automation_note"]
    assert "same 13 clean rows" in candidate["automation_note"]
    assert "remain null rather than inferred" in candidate["automation_note"]


def test_tango_linsen_is_enabled_after_cross_environment_validation():
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )
    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "tango_hotel_taipei_linsen"
    )

    daily_row = next(row for row in daily["hotels"] if row["id"] == candidate["id"])
    assert daily_row["adapter"] == "gobooking"
    assert candidate["enabled"] is True
    assert candidate["automation_status"] == "verified"
    assert "collected 4 live +30-day room-only rates" in candidate["automation_note"]
    assert "GitHub Linux probe 40981716960" in candidate["automation_note"]
    assert "same 4 clean rows" in candidate["automation_note"]
    assert "remain null rather than inferred" in candidate["automation_note"]


def test_tango_xinyi_is_enabled_after_clean_single_probe():
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )

    daily_row = next(
        row for row in daily["hotels"] if row["id"] == "tango_hotel_taipei_xinyi"
    )
    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "tango_hotel_taipei_xinyi"
    )

    assert daily_row["adapter"] == "gobooking"
    assert candidate["enabled"] is True
    assert candidate["automation_status"] == "verified"
    assert "collected 11 live +30-day breakfast-included rates" in candidate[
        "automation_note"
    ]
    assert "component percentages are not published" in candidate["automation_note"]


def test_tango_nanshi_stays_disabled_after_remote_timeout():
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )

    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "tango_hotel_taipei_nanshi"
    )
    diagnostic = json.loads(
        Path("artifacts/tango-nanshi-github-probe-diagnostic.json").read_text(
            encoding="utf-8"
        )
    )

    assert not any(
        row["id"] == "tango_hotel_taipei_nanshi" for row in daily["hotels"]
    )
    assert candidate["enabled"] is False
    assert candidate["automation_status"] == "skipped"
    assert "GitHub Linux probe timed out" in candidate["automation_note"]
    assert diagnostic["status"] == "cooldown"
    assert diagnostic["probe_limit"] == {
        "candidate_attempts_this_batch": 1,
        "retried": False,
    }
    assert diagnostic["remote_probe"]["observations"] == 0
    assert diagnostic["local_probe"]["observations"] == 7
    assert diagnostic["cooldown_until"] == "2026-11-05T09:25:43Z"


def test_tango_shilin_is_enabled_after_cross_environment_validation():
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )
    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "tango_hotel_taipei_shilin"
    )

    daily_row = next(row for row in daily["hotels"] if row["id"] == candidate["id"])
    assert daily_row["adapter"] == "gobooking"
    assert candidate["enabled"] is True
    assert candidate["automation_status"] == "verified"
    assert "collected 7 live +30-day breakfast-included rates" in candidate[
        "automation_note"
    ]
    assert "GitHub Linux probe 40850372740 independently succeeded" in candidate[
        "automation_note"
    ]


def test_tango_fuhsing_stays_disabled_after_remote_timeout():
    daily = yaml.safe_load(Path("config/hotels.daily.yaml").read_text(encoding="utf-8"))
    candidates = yaml.safe_load(
        Path("config/hotels.candidates.yaml").read_text(encoding="utf-8")
    )
    candidate = next(
        row
        for row in candidates["hotels"]
        if row["id"] == "tango_hotel_taipei_fuhsing"
    )
    diagnostic = json.loads(
        Path("artifacts/tango-fuhsing-github-probe-diagnostic.json").read_text(
            encoding="utf-8"
        )
    )

    assert not any(
        row["id"] == "tango_hotel_taipei_fuhsing" for row in daily["hotels"]
    )
    assert candidate["enabled"] is False
    assert candidate["automation_status"] == "skipped"
    assert "collected 10 live +30-day breakfast-included rates" in candidate[
        "automation_note"
    ]
    assert "GitHub Linux probe 40980271037 timed out" in candidate["automation_note"]
    assert diagnostic["status"] == "cooldown"
    assert diagnostic["probe_limit"] == {
        "candidate_attempts_this_batch": 1,
        "retried": False,
    }
    assert diagnostic["remote_probe"]["observations"] == 0
    assert diagnostic["local_probe"]["observations"] == 10
    assert diagnostic["cooldown_until"] == "2026-11-06T00:33:54Z"


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
        "probe-tango-jiantan.yml": (
            "scripts/run_tango_jiantan_once.py",
            "config/hotels.tango-jiantan-only.yaml",
        ),
        "probe-tango-xinyi.yml": (
            "scripts/run_tango_xinyi_once.py",
            "config/hotels.tango-xinyi-only.yaml",
        ),
        "probe-tango-nanshi.yml": (
            "scripts/run_tango_nanshi_once.py",
            "config/hotels.tango-nanshi-only.yaml",
        ),
        "probe-tango-shilin.yml": (
            "scripts/run_tango_shilin_once.py",
            "config/hotels.tango-shilin-only.yaml",
        ),
        "probe-tango-fuhsing.yml": (
            "scripts/run_tango_fuhsing_once.py",
            "config/hotels.tango-fuhsing-only.yaml",
        ),
        "probe-tango-linsen.yml": (
            "scripts/run_tango_linsen_once.py",
            "config/hotels.tango-linsen-only.yaml",
        ),
        "probe-tango-changan.yml": (
            "scripts/run_tango_changan_once.py",
            "config/hotels.tango-changan-only.yaml",
        ),
    }
    for workflow, paths in expected_paths.items():
        text = Path(".github/workflows", workflow).read_text(encoding="utf-8")
        assert "scrapers/adapters/gobooking.py" not in text
        for path in paths:
            assert path in text

    songjiang_workflow = Path(
        ".github/workflows/probe-k-hotel-songjiang.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in songjiang_workflow
    assert "push:" not in songjiang_workflow
    assert "python -m scripts.run_k_hotel_songjiang_once" in songjiang_workflow
