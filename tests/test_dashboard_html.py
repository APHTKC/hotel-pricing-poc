from pathlib import Path


def test_home_separates_primary_navigation_locale_and_exports():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert '<div class="locale-controls">' in html
    assert '<nav class="primary-nav"' in html
    assert '<section class="data-tools">' in html
    assert 'data-i18n="historyPage">歷史分析</a></nav>' in html


def test_history_supports_average_and_median_analysis():
    html = Path("public/history.html").read_text(encoding="utf-8")

    assert 'id="average"' in html
    assert 'id="metricMode"' in html
    assert '<option value="average"' in html
    assert '<option value="median"' in html
    assert "const average=" in html
