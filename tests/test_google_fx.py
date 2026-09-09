from scripts.update_google_fx import google_price


def test_google_price_reads_quote_attribute():
    assert google_price('<div data-last-price="31.4655"></div>') == 31.4655
