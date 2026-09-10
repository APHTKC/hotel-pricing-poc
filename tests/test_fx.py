import json
from decimal import Decimal

from services.fx import published_rate_to_twd


def test_published_google_rate_converts_foreign_currency_to_twd(tmp_path):
    path = tmp_path / "fx.json"
    path.write_text(
        json.dumps({"base": "TWD", "rates": {"TWD": 1, "USD": 0.03125}}),
        encoding="utf-8",
    )

    assert published_rate_to_twd("USD", path) == Decimal("32")
    assert published_rate_to_twd("NTD", path) == Decimal("1")
