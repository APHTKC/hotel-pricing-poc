from decimal import Decimal
from scrapers.adapters.synxis import tax_components

def test_tax_components_match_public_synxis_total():
    assert tax_components(Decimal("4450")) == (Decimal("445"), Decimal("245"), Decimal("5140"))
