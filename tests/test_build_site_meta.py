import json
from datetime import datetime, timezone

import scripts.build_site_meta as build_site_meta


def test_site_meta_uses_taipei_release_date_and_short_commit(monkeypatch, tmp_path):
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({"rates": [
        {"queried_at": "2026-09-30T22:28:44Z"},
        {"queried_at": "2026-10-01T01:00:00Z"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(build_site_meta, "LATEST_SOURCE", latest)
    monkeypatch.setenv("GITHUB_SHA", "1234567890abcdef")
    monkeypatch.setenv("GITHUB_RUN_ID", "987")

    payload = build_site_meta.build_site_meta(
        datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc)
    )

    assert payload["version"] == "v2026.10.01"
    assert payload["build"] == "1234567"
    assert payload["deployment_run"] == "987"
    assert payload["data_updated_at"] == "2026-10-01T01:00:00Z"


def test_site_meta_fails_closed_when_latest_data_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(build_site_meta, "LATEST_SOURCE", tmp_path / "missing.json")
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    payload = build_site_meta.build_site_meta(
        datetime(2026, 10, 1, tzinfo=timezone.utc)
    )

    assert payload["build"] == "local"
    assert payload["data_updated_at"] is None
