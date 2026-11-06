import json

import pytest

from scripts import verify_pages_deployment


class _Response:
    def __init__(self, body: str):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.body


def test_verify_once_checks_homepage_and_exact_build(monkeypatch):
    requested = []

    def fake_open(url, timeout):
        requested.append((url, timeout))
        if url.endswith("site_meta.json"):
            return _Response(json.dumps({"build": "abcdef1"}))
        return _Response(verify_pages_deployment.HOME_MARKER)

    monkeypatch.setattr(verify_pages_deployment, "urlopen", fake_open)

    verify_pages_deployment.verify_once(
        "https://example.github.io/project", "abcdef1", timeout=7
    )

    assert requested == [
        ("https://example.github.io/project/", 7),
        ("https://example.github.io/project/data/site_meta.json", 7),
    ]


def test_verify_once_rejects_stale_build(monkeypatch):
    def fake_open(url, timeout):
        if url.endswith("site_meta.json"):
            return _Response(json.dumps({"build": "old0000"}))
        return _Response(verify_pages_deployment.HOME_MARKER)

    monkeypatch.setattr(verify_pages_deployment, "urlopen", fake_open)

    with pytest.raises(ValueError, match="expected 'new0000'"):
        verify_pages_deployment.verify_once(
            "https://example.github.io/project/", "new0000"
        )


def test_verify_with_retries_allows_transient_failure(monkeypatch):
    calls = []

    def fake_verify(*_args, **_kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise OSError("temporary reset")

    sleeps = []
    monkeypatch.setattr(verify_pages_deployment, "verify_once", fake_verify)

    verify_pages_deployment.verify_with_retries(
        "https://example.github.io/project/",
        "abcdef1",
        attempts=2,
        delay_seconds=3,
        sleep=sleeps.append,
    )

    assert len(calls) == 2
    assert sleeps == [3]


def test_verify_with_retries_fails_closed(monkeypatch):
    monkeypatch.setattr(
        verify_pages_deployment,
        "verify_once",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("reset")),
    )

    with pytest.raises(RuntimeError, match="not publicly readable"):
        verify_pages_deployment.verify_with_retries(
            "https://example.github.io/project/",
            "abcdef1",
            attempts=2,
            delay_seconds=0,
            sleep=lambda _seconds: None,
        )
