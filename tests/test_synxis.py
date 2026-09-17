from decimal import Decimal
from datetime import date
from decimal import Decimal

from scrapers.adapters.synxis import booking_url, split_tax_inclusive_total, tax_components

def test_tax_components_match_public_synxis_total():
    assert tax_components(Decimal("4450")) == (Decimal("445"), Decimal("245"), Decimal("5140"))


def test_jr_east_booking_url_uses_official_property_ids():
    url = booking_url(
        "hotel_metropolitan_premier_taipei",
        date(2026, 10, 17),
        date(2026, 10, 18),
    )
    assert "chain=10197" in url
    assert "hotel=99659" in url


def test_tax_inclusive_synxis_total_is_not_added_twice():
    base, service, tax = split_tax_inclusive_total(Decimal("10890"))
    assert base + service + tax == Decimal("10890")
