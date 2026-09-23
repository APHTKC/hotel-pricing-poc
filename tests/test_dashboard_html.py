import json
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

    assert history.count("if(district)rows=rows.filter(r=>r.district===district)") == 1


def test_city_and_district_limit_the_hotel_selector_options():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    assert "const optionRows=rows.filter(r=>(!cv||r.city===cv)&&(!d.value||r.district===d.value))" in home
    assert "const optionRows=allRows.filter(r=>(!cv||r.city===cv)&&(!district.value||r.district===district.value))" in history
    for html in (home, history):
        assert "hotels.some(([id])=>id===hv)?hv:''" in html
        assert "document.querySelector('#district').addEventListener('change',()=>{setOptions(" in html


def test_city_and_taipei_district_options_use_geographic_order_and_counts():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    for html in (home, history):
        assert "const CITY_ORDER=['Taipei','New Taipei','NewTaipei','Hsinchu','Taichung'" in html
        assert "DISTRICT_ORDER=['Beitou','Shilin','Zhongshan','Songshan'" in html
        assert "districtHotelIds.get(" in html
        assert "taipeiHotelCount" in html
        assert "geoRank(a,CITY_ORDER)-geoRank(b,CITY_ORDER)" in html
        assert "geoRank(a,DISTRICT_ORDER)-geoRank(b,DISTRICT_ORDER)" in html


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

    assert history.count("if(compSetConfigured)rows=rows.filter(r=>compSetIds.has(r.hotel_id))") == 1


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


def test_history_explains_suite_skew_and_has_room_type_quality_table():
    html = Path("public/history.html").read_text(encoding="utf-8")

    assert 'id="coreRoom"' in html
    assert 'id="priceExplanation"' in html
    assert "function renderHistoryPriceExplanation(rows)" in html
    assert "function renderHistoryRoomCatalog(rows)" in html
    assert 'id="roomCatalog"' in html
    assert "filteredHistoryRows({ignoreSize:true})" in html
    assert "item.size>=80" in html
    assert "invalidUnitPrice" in html
    assert "106㎡與270㎡套房會明顯拉高歷史平均" in html


def test_hotel_profile_page_lists_all_hotels_and_verified_official_profiles():
    html = Path("public/hotels.html").read_text(encoding="utf-8")
    profiles = json.loads(Path("public/data/hotel_profiles.json").read_text(encoding="utf-8"))
    names = json.loads(Path("public/data/hotel_names_zh.json").read_text(encoding="utf-8"))

    assert '<span class="active"><b class="nav-index">03</b>' in html
    assert "catalog=hotelsData.hotels||[]" in html
    assert "function roomRows(id)" in html
    assert "function renderDetail()" in html
    assert "function facilityValue(profile,key)" in html
    assert "T[lang].unknown" in html
    assert 'id="comparison"' in html
    assert 'id="detail"' in html
    assert "hotel_profiles.json" in html
    assert "hotel_names_zh.json" in html
    assert len(names["names"]) >= 65

    by_id = {profile["hotel_id"]: profile for profile in profiles["profiles"]}
    assert set(by_id) >= {"capella_taipei", "mo_taipei", "grand_hilai_taipei", "okura_prestige_taipei", "shangrila_taipei", "grand_mayfull_taipei", "grand_hyatt_taipei", "w_taipei", "regent_taipei", "taipei_marriott"}
    assert len(by_id["capella_taipei"]["restaurants"]) == 5
    assert by_id["mo_taipei"]["lounge"]["name"] == "The Oriental Lounge"
    assert by_id["grand_hilai_taipei"]["facilities"]["pool"] is True
    assert by_id["okura_prestige_taipei"]["room_inventory"] == 207
    assert len(by_id["okura_prestige_taipei"]["restaurants"]) == 5
    assert by_id["shangrila_taipei"]["room_inventory"] == 420
    assert by_id["shangrila_taipei"]["lounge"]["name"] == "Horizon Club Lounge"
    assert by_id["grand_mayfull_taipei"]["room_inventory"] == 146
    assert by_id["grand_mayfull_taipei"]["lounge"]["kind"] == "members_club"
    assert by_id["grand_hyatt_taipei"]["room_inventory"] == 850
    assert len(by_id["grand_hyatt_taipei"]["restaurants"]) == 8
    assert by_id["grand_hyatt_taipei"]["lounge"]["name"] == "Grand Club Lounge"
    assert by_id["w_taipei"]["room_inventory"] == 405
    assert len(by_id["w_taipei"]["restaurants"]) == 4
    assert by_id["w_taipei"]["facilities"]["sauna"] is None
    assert by_id["w_taipei"]["lounge"]["available"] is None
    assert by_id["regent_taipei"]["room_inventory"] == 538
    assert len(by_id["regent_taipei"]["restaurants"]) == 8
    assert by_id["regent_taipei"]["facilities"]["sauna"] is True
    assert by_id["regent_taipei"]["facilities"]["steam_room"] is None
    assert by_id["regent_taipei"]["lounge"]["name"] == "Silks Club"
    assert by_id["taipei_marriott"]["room_inventory"] is None
    assert len(by_id["taipei_marriott"]["restaurants"]) == 6
    assert by_id["taipei_marriott"]["facilities"]["sauna"] is True
    assert by_id["taipei_marriott"]["lounge"]["name"] == "Executive Lounge"
    snapshot = by_id["taipei_marriott"]["room_snapshot"]
    assert snapshot["observed_at"] == "2026-09-23"
    assert snapshot["source_type"] == "official"
    assert len(snapshot["rooms"]) == 7
    assert {room["name_en"] for room in snapshot["rooms"]} >= {"Classic Room", "Brilliant Suite"}
    assert {room["size_sqm"] for room in snapshot["rooms"]} >= {40, 51, 65, 80}


def test_hotel_profile_page_supports_sorting_rate_filter_and_city_colors():
    html = Path("public/hotels.html").read_text(encoding="utf-8")

    assert 'id="rateStatus"' in html
    assert 'id="sort"' in html
    assert 'class="sort-button" data-sort="name"' in html
    assert 'class="sort-button" data-sort="geo"' in html
    assert "function sortHotels(items)" in html
    assert "CITY_COLORS=" in html
    assert 'class="city-row"' in html
    assert 'class="city-badge"' in html
    assert "rateStatus==='with'" in html
    assert "function loungeDetail(profile)" in html
    assert "membersOnlyLounge" in html
    assert "value==null" in html


def test_all_primary_pages_link_to_hotel_profile_comparison():
    for path in ("public/index.html", "public/history.html", "public/hotels.html"):
        html = Path(path).read_text(encoding="utf-8")
        assert "飯店資料比較" in html
        assert "hotels.html" in html or path.endswith("hotels.html")


def test_missing_per_square_meter_values_never_render_or_export_as_zero():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    assert "money(Number(r.price_per_sqm))" not in home
    assert "r.price_per_sqm!=null&&Number.isFinite(unit)&&unit>0" in home
    assert "r.price_per_sqm!=null&&Number.isFinite(unit)&&unit>0" in history


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

    assert history.count("if(source)rows=rows.filter(r=>sourceOf(r)===source)") == 1


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


def test_room_size_options_show_unique_room_type_counts_for_current_scope():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    for html in (home, history):
        assert "function updateSizeOptions" in html
        assert "const key=`${r.hotel_id}|${r.room_type_code||r.room_type_name}|${size}`" in html
        assert "counts[band(size)]++" in html
        assert "suffix(total)" in html
        assert "updateSizeOptions" in html


def test_room_names_are_localized_and_profile_snapshots_show_source_date():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")
    profiles = Path("public/hotels.html").read_text(encoding="utf-8")

    for html in (home, history):
        assert "function roomName(row)" in html
        assert "room_type_name_en" in html
        assert "roomName(r)" in html

    assert "room_snapshot" in profiles
    assert "roomLabel(room)" in profiles
    assert "roomSnapshot:'房型資料快照'" in profiles
    assert "snapshot.observed_at" in profiles
    assert "snapshot.source_url" in profiles
