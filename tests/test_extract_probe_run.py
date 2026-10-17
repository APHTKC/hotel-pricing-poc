import json

import pytest

from scripts.extract_probe_run import extract_probe_run


def test_extract_probe_run_preserves_other_jsonl_rows(tmp_path):
    source = tmp_path / "rates.jsonl"
    target = tmp_path / "gaia-local-probe.jsonl"
    rows = [
        {"run_id": "daily", "hotel_id": "a"},
        {"run_id": "probe", "hotel_id": "b"},
        {"run_id": "daily", "hotel_id": "c"},
    ]
    source.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    assert extract_probe_run(source, target, "probe") == 1
    assert [json.loads(line) for line in source.read_text().splitlines()] == [
        rows[0], rows[2]
    ]
    assert [json.loads(line) for line in target.read_text().splitlines()] == [rows[1]]


def test_extract_probe_run_requires_ignored_probe_suffix(tmp_path):
    source = tmp_path / "rates.jsonl"
    source.write_text('{"run_id":"probe"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="-local-probe.jsonl"):
        extract_probe_run(source, tmp_path / "probe.jsonl", "probe")


def test_extract_probe_run_scans_bounded_daily_shards(tmp_path):
    source = tmp_path / "rates"
    first = source / "2026-09" / "2026-09-30.jsonl"
    second = source / "2026-10" / "2026-10-01.jsonl"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text('{"run_id":"daily","hotel_id":"a"}\n', encoding="utf-8")
    second.write_text(
        '{"run_id":"probe","hotel_id":"b"}\n'
        '{"run_id":"daily","hotel_id":"c"}\n',
        encoding="utf-8",
    )
    target = tmp_path / "daily-local-probe.jsonl"

    assert extract_probe_run(source, target, "probe") == 1
    assert json.loads(target.read_text()) == {"run_id": "probe", "hotel_id": "b"}
    assert json.loads(first.read_text()) == {"run_id": "daily", "hotel_id": "a"}
    assert json.loads(second.read_text()) == {"run_id": "daily", "hotel_id": "c"}
