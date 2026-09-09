import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx


TARGET = Path("public/data/fx.json")
QUOTES = {"USD": "USD-TWD", "JPY": "TWD-JPY"}


def google_price(html: str) -> float:
    match = re.search(r'data-last-price="([0-9.]+)"', html)
    if not match:
        raise ValueError("Google Finance price was not found")
    return float(match.group(1))


def main() -> None:
    headers = {"User-Agent": "Mozilla/5.0 hotel-market-dashboard/1.0"}
    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=30) as client:
            usd_twd = google_price(client.get(f"https://www.google.com/finance/quote/{QUOTES['USD']}?hl=en").text)
            twd_jpy = google_price(client.get(f"https://www.google.com/finance/quote/{QUOTES['JPY']}?hl=en").text)
    except (httpx.HTTPError, ValueError) as exc:
        if TARGET.exists():
            print(f"Google Finance was temporarily unavailable; preserving the last published rates: {exc}")
            return
        raise
    payload = {
        "base": "TWD", "source": "Google Finance", "updated_at": datetime.now(UTC).isoformat(),
        "rates": {"TWD": 1, "USD": 1 / usd_twd, "JPY": twd_jpy},
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Google Finance: 1 TWD = {payload['rates']['USD']:.6f} USD = {twd_jpy:.4f} JPY")


if __name__ == "__main__":
    main()
