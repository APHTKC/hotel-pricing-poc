"""Verify that a GitHub Pages deployment is publicly readable and current."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from urllib.parse import urljoin
from urllib.request import urlopen


HOME_MARKER = "<title>台灣飯店房價查詢平台</title>"


def _read_text(url: str, timeout: float) -> str:
    with urlopen(url, timeout=timeout) as response:  # noqa: S310 - URL is workflow output
        return response.read().decode("utf-8")


def verify_once(page_url: str, expected_build: str, timeout: float = 15) -> None:
    base_url = page_url.rstrip("/") + "/"
    home = _read_text(base_url, timeout)
    if HOME_MARKER not in home:
        raise ValueError(f"published homepage is missing the expected title: {base_url}")

    meta_url = urljoin(base_url, "data/site_meta.json")
    metadata = json.loads(_read_text(meta_url, timeout))
    actual_build = metadata.get("build")
    if actual_build != expected_build:
        raise ValueError(
            f"published build is {actual_build!r}; expected {expected_build!r}: {meta_url}"
        )


def verify_with_retries(
    page_url: str,
    expected_build: str,
    *,
    attempts: int = 12,
    delay_seconds: float = 5,
    timeout: float = 15,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            verify_once(page_url, expected_build, timeout)
            print(f"Verified public Pages build {expected_build} at {page_url}")
            return
        except Exception as exc:  # Retry transient CDN propagation and network failures.
            last_error = exc
            if attempt == attempts:
                break
            print(f"Pages verification attempt {attempt}/{attempts} failed: {exc}")
            sleep(delay_seconds)

    raise RuntimeError(
        f"Pages was not publicly readable with build {expected_build} after "
        f"{attempts} attempts"
    ) from last_error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-build", required=True)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--delay-seconds", type=float, default=5)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    verify_with_retries(
        args.url,
        args.expected_build,
        attempts=args.attempts,
        delay_seconds=args.delay_seconds,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
