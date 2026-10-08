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
