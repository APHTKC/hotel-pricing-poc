from datetime import date

from scrapers.adapters.mandarin_oriental import (
    MandarinOrientalScraper,
    is_comparable_public_plan,
)


def test_mo_booking_url_contains_official_ids_and_dates():
    url = MandarinOrientalScraper().booking_url(
        date(2026, 10, 9), date(2026, 10, 10), 2
    )
    assert "Hotel=59555" in url
    assert "Chain=507" in url
    assert "arrive=2026-10-09" in url
    assert "depart=2026-10-10" in url
    assert "currency=TWD" in url


def test_mo_excludes_non_public_member_plans():
    assert is_comparable_public_plan("Best Available Rate") is True
    assert is_comparable_public_plan("Plan Ahead") is True
    assert is_comparable_public_plan("Fans of M.O. Member Rate") is False
