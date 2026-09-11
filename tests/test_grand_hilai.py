from decimal import Decimal

from scrapers.adapters.grand_hilai import ping_to_sqm


def test_ping_to_sqm():
    assert ping_to_sqm("9坪") == Decimal("29.8")
    assert ping_to_sqm("客房面積 18坪") == Decimal("59.5")
    assert ping_to_sqm("unknown") is None
