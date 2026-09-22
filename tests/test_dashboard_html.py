from pathlib import Path


def test_home_separates_primary_navigation_locale_and_exports():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert '<div class="locale-controls">' in html
    assert html.count('class="locale-control"') == 2
    assert '<nav class="section-nav"' in html
    assert '<section class="data-tools"' in html
    assert 'data-i18n="historyPage">歷史房價分析</strong>' in html
    assert 'data-i18n="historyNavHint">長期趨勢與提前訂房曲線</small>' in html
    assert html.index('<section class="data-tools"') < html.index('<section class="panel filters"')
    assert 'aria-label="資料匯出與列印"' in html


def test_history_uses_the_same_primary_navigation_and_separate_locale_controls():
    html = Path("public/history.html").read_text(encoding="utf-8")

    assert html.count('class="locale-control"') == 2
    assert '<nav class="section-nav"' in html
    assert '<span class="active"><b class="nav-index">02</b>' in html


def test_history_supports_average_and_median_analysis():
    html = Path("public/history.html").read_text(encoding="utf-8")

    assert 'id="average"' in html
    assert 'id="metricMode"' in html
    assert '<option value="average"' in html
    assert '<option value="median"' in html
    assert "const average=" in html


def test_history_has_visible_export_tools():
    html = Path("public/history.html").read_text(encoding="utf-8")

    assert '<section class="data-tools"' in html
    assert 'id="exportJson"' in html
    assert 'id="exportExcel"' in html
    assert 'id="exportPdf"' in html
    assert "function exportHistoryJson()" in html
    assert "function exportHistoryExcel()" in html
    assert html.index('<section class="data-tools"') < html.index('<section class="panel filters"')
    assert 'aria-label="資料匯出與列印"' in html


def test_home_distinguishes_skipped_automation_candidates():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert "automation_status==='skipped'" in html
    assert "暫不支援" in html
    assert "status-skipped" in html


def test_dashboard_uses_flexible_competitor_room_size_bands():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    for html in (home, history):
        assert 'value="45–59㎡" data-i18n="sizeCore"' in html
        assert "45–59㎡（核心比較）" in html
        assert "n<45?'<45㎡':n<60?'45–59㎡':n<80?'60–79㎡':'80㎡+'" in html
        assert "50–69㎡" not in html


def test_both_dashboards_support_dependent_taipei_district_filtering():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    for html in (home, history):
        assert 'id="district" disabled' in html
        assert "cv==='Taipei'" in html
        assert "r.district===district" in html
        assert "allDistricts:'所有行政區'" in html
        assert "district:document.querySelector('#district').value" in html

    assert history.count("if(district)rows=rows.filter(r=>r.district===district)") == 2


def test_both_dashboards_share_a_persistent_competitor_hotel_set():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    for html in (home, history):
        assert 'id="competitorSet"' in html
        assert 'id="competitorGrid"' in html
        assert "localStorage.getItem('hotel-comp-set')" in html
        assert "localStorage.setItem('hotel-comp-set'" in html
        assert "if(compSetConfigured)rows=rows.filter(r=>compSetIds.has(r.hotel_id))" in html
        assert "function selectAllCompHotels()" in html
        assert "function clearCompHotels()" in html
        assert "competitor_hotels:activeCompHotelIds()" in html
        assert "競合ホテルセット" in html

    assert history.count("if(compSetConfigured)rows=rows.filter(r=>compSetIds.has(r.hotel_id))") == 2


def test_both_dashboards_repair_empty_or_stale_competitor_sets_on_load():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    for html in (home, history):
        assert "function repairCompSet(rows)" in html
        assert "localStorage.removeItem('hotel-comp-set')" in html
        assert "some(id=>liveIds.has(id))" in html

    assert "repairCompSet(latestRows)" in home
    assert "repairCompSet(allRows)" in history


def test_ota_controls_stay_hidden_until_real_ota_rates_exist():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    for html in (home, history):
        assert 'id="rateSourceFilter"' in html
        assert "const hasOtaData=rows=>rows.some(r=>sourceOf(r)!=='official')" in html
        assert "function updateOtaVisibility(rows)" in html
        assert "document.querySelector('#rateSourceFilter').hidden=!visible" in html
        assert "localStorage.removeItem('hotel-rate-source')" in html
        assert "const officialSourceNote=" in html
        assert "document.querySelector('.source-note').textContent=officialSourceNote[lang]" in html

    assert 'id="otaComparisonSection"' in home
    assert "document.querySelector('#otaComparisonSection').hidden=!visible" in home
    assert "hasOtaData(latestRows)?`<p class=\"ota-status\"" in home


def test_home_chart_identifies_hotels_when_hovering_lines_and_points():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert 'class="chart-series-hit"' in html
    assert 'data-tooltip="${esc(s.name)}"' in html
    assert 'id="chartTooltip"' in html
    assert "element.addEventListener('pointerenter',showTooltip)" in html
    assert ".chart-series:hover .chart-series-line" in html
    assert "hover a line to identify the hotel" in html


def test_history_charts_identify_hotels_and_rates_on_hover():
    html = Path("public/history.html").read_text(encoding="utf-8")

    assert "function interactiveLineChart(" in html
    assert 'class="chart-series-hit"' in html
    assert 'class="chart-tooltip"' in html
    assert "root.querySelectorAll('[data-tooltip]')" in html
    assert "element.addEventListener('pointerenter',showTooltip)" in html
    assert ".chart-series:hover .chart-series-line" in html
    assert "hover a line to identify the hotel and rate" in html
    assert "interactiveLineChart('#dailyChart'" in html
    assert "interactiveLineChart('#curveChart'" in html


def test_home_shows_per_hotel_last_success_and_freshness():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert "const stampsByHotel=new Map()" in html
    assert "age<=36?'fresh':age<=72?'aging':'stale'" in html
    assert 'class="freshness freshness-${info.state}"' in html
    assert 'class="data-health"' in html
    assert "最近成功" in html


def test_home_explains_suite_skew_and_compares_room_types_and_sizes():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert 'id="coreRoom"' in html
    assert 'data-sort="core"' in html
    assert 'id="priceExplanation"' in html
    assert "function renderPriceExplanation(rows)" in html
    assert "selectedHotel==='capella_taipei'" in html
    assert "106㎡與270㎡套房會明顯拉高整體平均" in html
    assert 'id="roomCatalog"' in html
    assert "function renderRoomCatalog(rows)" in html
    assert "Math.min(...item.values)" in html
    assert "median(item.values)" in html
    assert "Math.max(...item.values)" in html
    assert "filteredRows({ignoreSize:true})" in html


def test_home_overview_stays_below_the_desktop_banner():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert ".theme-wsj main{margin:24px auto 60px}" in html
    assert "@media(max-width:760px){.theme-wsj main{margin-top:16px}}" in html


def test_both_dashboards_filter_and_export_rate_sources():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    for html in (home, history):
        assert 'id="source"' in html
        assert "row.source_platform||'official'" in html
        assert "if(source)rows=rows.filter(r=>sourceOf(r)===source)" in html
        assert "source_platform:document.querySelector('#source').value" in html
        assert "officialSource:'飯店官網'" in html
        assert "rakuten_travel:'Rakuten Travel'" in html

    assert history.count("if(source)rows=rows.filter(r=>sourceOf(r)===source)") == 2


def test_both_dashboards_default_to_official_rates_and_remember_source_choice():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    for html in (home, history):
        assert "preferredSource=localStorage.getItem('hotel-rate-source')" in html
        assert "if(preferredSource===null)preferredSource='official'" in html
        assert "localStorage.setItem('hotel-rate-source',preferredSource)" in html


def test_market_kpis_equal_weight_each_hotel():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    assert 'data-i18n="marketAverageRate">市場平均房價' in home
    assert "average(hotels.map(h=>h.avg).filter(Number.isFinite))" in home
    assert "median(hotels.map(h=>h.adr).filter(Number.isFinite))" in home
    assert "市場指標先按飯店計算再等權彙整" in home

    assert 'data-i18n="marketHistoryAverage">市場歷史平均房價' in history
    assert "hotelStats=hotels.map" in history
    assert "average(hotelStats.map(h=>h.average).filter(Number.isFinite))" in history
    assert "median(hotelStats.map(h=>h.median).filter(Number.isFinite))" in history
    assert "市場指標先按飯店計算再等權彙整" in history


def test_home_has_official_vs_ota_rate_gap_comparison():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert 'id="sourceComparison"' in html
    assert 'data-i18n="sourceCompare">官網與 OTA 價差' in html
    assert "function renderSourceComparison()" in html
    assert "sourceOf(r)==='official'" in html
    assert "noOtaComparison:'尚未收到已授權 OTA 的實際房價" in html
    assert "renderSourceComparison();" in html
