from services.market_metrics import calculate_market_summary


def test_market_adr_is_median_of_each_hotel_median():
    rows = [
        {"hotel_id": "many", "total_twd": 100, "price_per_sqm": 2},
        {"hotel_id": "many", "total_twd": 200, "price_per_sqm": 4},
        {"hotel_id": "many", "total_twd": 300, "price_per_sqm": 6},
        {"hotel_id": "few", "total_twd": 1000, "price_per_sqm": 20},
        {"hotel_id": "third", "total_twd": 5000, "price_per_sqm": 100},
    ]

    result = calculate_market_summary(rows)

    # Hotel medians are 200, 1000, and 5000; the market median is 1000.
    assert result["median_adr_twd"] == 1000
    assert result["median_per_sqm_twd"] == 20
    assert result["observations"] == 5
    assert result["hotels"] == 3


def test_market_summary_accepts_missing_optional_analysis_values():
    result = calculate_market_summary([{"hotel_id": "hotel", "total_twd": 12000}])

    assert result["median_adr_twd"] == 12000
    assert result["median_per_sqm_twd"] is None
    assert result["median_cpi_adjusted_twd"] is None
