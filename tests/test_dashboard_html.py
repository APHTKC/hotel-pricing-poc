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
    assert "import { average, median, roomSizeBand, formatMoney }" in html


def test_history_has_visible_export_tools():
    html = Path("public/history.html").read_text(encoding="utf-8")

    assert '<section class="data-tools"' in html
    assert 'id="exportJson"' in html
    assert 'id="exportExcel"' in html
    assert 'id="exportPdf"' in html
    assert 'id="exportA4Pdf"' in html
    assert html.count('id="exportA4Pdf"') == 1
    assert "function exportHistoryJson()" in html
    assert "function exportHistoryExcel()" in html
    assert html.index('<section class="data-tools"') < html.index('<section class="panel filters"')
    assert 'aria-label="資料匯出與列印"' in html
    assert ".export-controls{grid-template-columns:repeat(4,1fr)}" in html
    assert "@media(max-width:760px){.export-controls{grid-template-columns:repeat(2,1fr)}.export-controls button:last-child{grid-column:auto}}" in html


def test_history_shows_preaggregated_weekly_executive_digest():
    html = Path("public/history.html").read_text(encoding="utf-8")

    assert 'id="weeklyDigest"' in html
    assert 'data-i18n="weeklyTitle">本週市場摘要' in html
    assert "function renderWeeklyDigest()" in html
    assert "historySummary?.weekly_digest" in html
    assert "hotel_equal_weight_median" not in html
    assert "weekly_digest:historySummary?.weekly_digest||null" in html
    assert "較前 7 日" in html
    assert "週間マーケット概要" in html


def test_home_distinguishes_skipped_automation_candidates():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert "automation_status==='skipped'" in html
    assert "暫不支援" in html
    assert "status-skipped" in html


def test_dashboard_uses_flexible_competitor_room_size_bands():
    home = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")

    metrics = Path("public/assets/js/metrics.js").read_text(encoding="utf-8")
    for html in (home, history):
        assert 'value="45–59㎡" data-i18n="sizeCore"' in html
        assert "45–59㎡（核心比較）" in html
        assert "roomSizeBand" in html
        assert "50–69㎡" not in html
    assert "if (size === null || size <= 0) return 'unknown'" in metrics


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
    assert "const optionRows=optionBase.filter(r=>(!cv||r.city===cv)&&(!district.value||r.district===district.value))" in history
    for html in (home, history):
        assert "hotels.some(([id])=>id===hv)?hv:''" in html
    assert "document.querySelector('#district').addEventListener('change',()=>{setOptions(" in home
    assert "document.querySelector('#district').addEventListener('change',()=>{if(detailMode)resetHistoryDetails();else{setOptions();render()}})" in history


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
    chart = Path("public/assets/js/charts.js").read_text(encoding="utf-8")

    assert "renderLineChart({root:'#chart'" in html
    assert 'class="chart-series-hit"' in chart
    assert 'data-tooltip="${escapeHtml(item.name)}"' in chart
    assert "element.addEventListener('pointerenter', show)" in chart
    assert ".chart-series:hover .chart-series-line" in html
    assert "hover a line to identify the hotel" in html


def test_history_charts_identify_hotels_and_rates_on_hover():
    html = Path("public/history.html").read_text(encoding="utf-8")
    chart = Path("public/assets/js/charts.js").read_text(encoding="utf-8")

    assert "function interactiveLineChart(" not in html
    assert "function lineChart(" not in html
    assert 'class="chart-series-hit"' in chart
    assert 'class="chart-tooltip"' in chart
    assert "rootElement.querySelectorAll('[data-tooltip]')" in chart
    assert ".chart-series:hover .chart-series-line" in html
    assert "hover a line to identify the hotel and rate" in html
    assert "renderLineChart({root:'#dailyChart'" in html
    assert "renderLineChart({root:'#curveChart'" in html


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
    assert "catalog=[...(hotelsData.hotels||[]),...(upcomingData.hotels||[])]" in html
    assert "function roomRows(id)" in html
    assert "function renderDetail()" in html
    assert "function facilityValue(profile,key)" in html
    assert "T[lang].unknown" in html
    assert 'id="comparison"' in html
    assert 'id="detail"' in html
    assert "hotel_profiles.json" in html
    assert "hotel_names_zh.json" in html
    assert "function stayTimeItems(profile)" in html
    assert "staySection.id='stayTimes'" in html
    assert "T[lang].stayTimes" in html
    assert len(names["names"]) >= 65

    by_id = {profile["hotel_id"]: profile for profile in profiles["profiles"]}
    assert by_id["regent_taipei"]["stay_times"]["check_in"] == "15:00"
    assert by_id["regent_taipei"]["stay_times"]["check_out"] == "11:00"
    expected_ota_stay_times = {
        "grand_mayfull_taipei": ("16:00", "11:00"),
        "grand_hyatt_taipei": ("15:00", "12:00"),
        "solaria_nishitetsu_taipei": ("15:00", "11:00"),
        "royal_nikko_taipei": ("15:00", "11:00"),
    }
    for hotel_id, (check_in, check_out) in expected_ota_stay_times.items():
        stay_times = by_id[hotel_id]["stay_times"]
        assert stay_times["check_in"] == check_in
        assert stay_times["check_out"] == check_out
        assert stay_times["source_type"] == "ota"
        assert stay_times["source_url"].startswith("https://www.booking.com/")
    assert set(by_id) >= {"capella_taipei", "mo_taipei", "grand_hilai_taipei", "okura_prestige_taipei", "shangrila_taipei", "grand_mayfull_taipei", "grand_hyatt_taipei", "w_taipei", "regent_taipei", "hotel_metropolitan_premier_taipei", "eslite_hotel", "solaria_nishitetsu_taipei", "taipei_marriott", "palais_de_chine", "the_gaia_taipei", "grand_hotel_taipei", "hotel_gracery_taipei", "royal_nikko_taipei", "le_meridien_taipei", "hoshinoya_guguan", "intercontinental_taichung", "windsor_taichung", "grand_hilai_kaohsiung", "intercontinental_kaohsiung", "kaohsiung_marriott", "hotel_nikko_kaohsiung", "silks_club_kaohsiung", "tai_urban_resort", "sheraton_hsinchu", "radium_kagaya_taipei", "grand_view_resort_beitou", "kimpton_da_an", "humble_house_taipei", "indigo_taipei_north", "sheraton_grand_taipei", "courtyard_taipei", "hotel_resonance_taipei", "renaissance_taipei_shihlin", "hotel_proverbs_taipei", "mitsui_garden_taipei_zhongxiao", "doubletree_taipei_zhongshan", "courtyard_taipei_downtown", "the_landis_taipei", "taipei_garden_hotel", "miramar_garden_taipei", "howard_plaza_taipei", "le_meridien_taichung", "millennium_taichung", "the_lin_taichung"}
    assert "hotel_royal_hsinchu" in by_id
    assert "eda_royal" in by_id
    mitsui = by_id["mitsui_garden_taipei_zhongxiao"]
    assert mitsui["room_inventory"] == 297
    assert mitsui["stay_times"]["source_type"] == "official"
    assert mitsui["stay_times"]["check_in"] == "15:00"
    assert mitsui["stay_times"]["check_out"] == "12:00"
    assert len(mitsui["room_snapshot"]["rooms"]) == 14
    assert min(room["size_sqm"] for room in mitsui["room_snapshot"]["rooms"]) == 21
    assert max(room["size_sqm"] for room in mitsui["room_snapshot"]["rooms"]) == 60.4
    assert "大浴場" in mitsui["facility_notes"]["zh"]
    doubletree = by_id["doubletree_taipei_zhongshan"]
    assert doubletree["room_inventory"] == 106
    assert doubletree["stay_times"]["source_type"] == "official"
    assert doubletree["facilities"]["fitness"] is True
    assert doubletree["room_snapshot"]["source_type"] == "ota"
    assert {room["size_sqm"] for room in doubletree["room_snapshot"]["rooms"]} == {33, 36, 46, 60}
    courtyard_downtown = by_id["courtyard_taipei_downtown"]
    assert courtyard_downtown["room_inventory"] == 227
    assert courtyard_downtown["service_charge_percent"] == 10
    assert courtyard_downtown["stay_times"]["check_in"] == "15:00"
    assert courtyard_downtown["stay_times"]["check_out"] == "12:00"
    assert len(courtyard_downtown["room_snapshot"]["rooms"]) == 6
    assert max(room["size_sqm"] for room in courtyard_downtown["room_snapshot"]["rooms"]) == 119
    landis = by_id["the_landis_taipei"]
    assert landis["room_inventory"] == 219
    assert landis["service_charge_percent"] == 10
    assert landis["stay_times"]["check_in"] == "15:00"
    assert landis["stay_times"]["check_out"] == "11:00"
    assert [room["size_sqm"] for room in landis["room_snapshot"]["rooms"]] == [26, 43, 53, 56]
    assert landis["lounge"]["available"] is None
    taipei_garden = by_id["taipei_garden_hotel"]
    assert taipei_garden["room_inventory"] == 241
    assert taipei_garden["service_charge_percent"] == 10
    assert taipei_garden["stay_times"]["check_in"] == "15:00"
    assert taipei_garden["stay_times"]["check_out"] == "12:00"
    assert len(taipei_garden["room_snapshot"]["rooms"]) == 7
    assert [room["size_sqm"] for room in taipei_garden["room_snapshot"]["rooms"]] == [22, 25, 25, 25, 25, 43, 63]
    assert taipei_garden["facilities"]["fitness"] is True
    assert taipei_garden["facilities"]["spa"] is True
    assert taipei_garden["facilities"]["pool"] is None
    miramar = by_id["miramar_garden_taipei"]
    assert miramar["room_inventory"] == 203
    assert miramar["service_charge_percent"] == 10
    assert miramar["stay_times"]["check_in"] == "15:00"
    assert miramar["stay_times"]["check_out"] == "11:00"
    assert len(miramar["room_snapshot"]["rooms"]) == 11
    assert miramar["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": True,
    }
    assert miramar["lounge"]["available"] is True
    howard = by_id["howard_plaza_taipei"]
    assert howard["room_inventory"] == 606
    assert howard["restaurant_count"] == 10
    assert howard["stay_times"]["check_in"] == "15:00"
    assert howard["stay_times"]["check_out"] == "12:00"
    assert len(howard["room_snapshot"]["rooms"]) == 3
    assert howard["room_snapshot"]["rooms"][0]["size_sqm_min"] == 20
    assert howard["room_snapshot"]["rooms"][2]["size_sqm_max"] == 27
    assert howard["facilities"]["pool"] is True
    assert howard["facilities"]["fitness"] is True
    assert howard["facilities"]["sauna"] is True
    assert "p.restaurant_count??p.restaurants.length" in html
    le_meridien_taichung = by_id["le_meridien_taichung"]
    assert le_meridien_taichung["room_inventory"] == 228
    assert le_meridien_taichung["stay_times"]["check_in"] == "16:00"
    assert le_meridien_taichung["stay_times"]["check_out"] == "12:00"
    assert len(le_meridien_taichung["room_snapshot"]["rooms"]) == 10
    assert [room["size_sqm"] for room in le_meridien_taichung["room_snapshot"]["rooms"]] == [45, 45, 45, 45, 45, 45, 45, 103, 140, 270]
    assert le_meridien_taichung["facilities"]["pool"] is True
    assert le_meridien_taichung["facilities"]["fitness"] is True
    assert le_meridien_taichung["facilities"]["sauna"] is True
    assert le_meridien_taichung["lounge"]["available"] is True
    millennium_taichung = by_id["millennium_taichung"]
    assert millennium_taichung["room_inventory"] == 243
    assert millennium_taichung["stay_times"]["check_in"] == "15:00"
    assert millennium_taichung["stay_times"]["check_out"] == "12:00"
    assert len(millennium_taichung["room_snapshot"]["rooms"]) == 9
    assert [room["size_sqm"] for room in millennium_taichung["room_snapshot"]["rooms"]] == [32, 36, 36, 53, 77, 77, 53, 98, 168]
    assert millennium_taichung["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": None,
    }
    assert millennium_taichung["lounge"]["available"] is True
    assert "service_charge_percent" not in millennium_taichung
    the_lin_taichung = by_id["the_lin_taichung"]
    assert the_lin_taichung["room_inventory"] == 295
    assert the_lin_taichung["service_charge_percent"] == 10
    assert the_lin_taichung["stay_times"]["check_in"] == "15:00"
    assert the_lin_taichung["stay_times"]["check_out"] == "11:00"
    assert len(the_lin_taichung["room_snapshot"]["rooms"]) == 19
    assert min(room["size_sqm"] for room in the_lin_taichung["room_snapshot"]["rooms"]) == 43
    assert max(room["size_sqm"] for room in the_lin_taichung["room_snapshot"]["rooms"]) == 218
    assert the_lin_taichung["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": True,
    }
    assert the_lin_taichung["lounge"]["available"] is True
    the_amnis = by_id["silks_club_kaohsiung"]
    assert the_amnis["room_inventory"] == 147
    assert the_amnis["restaurant_count"] == 4
    assert the_amnis["stay_times"]["check_in"] == "15:00"
    assert the_amnis["stay_times"]["check_out"] == "12:00"
    assert len(the_amnis["room_snapshot"]["rooms"]) == 13
    assert min(room["size_sqm"] for room in the_amnis["room_snapshot"]["rooms"]) == 59
    assert max(room["size_sqm"] for room in the_amnis["room_snapshot"]["rooms"]) == 685
    assert the_amnis["facilities"]["pool"] is True
    assert the_amnis["facilities"]["fitness"] is True
    assert the_amnis["facilities"]["spa"] is True
    assert the_amnis["facilities"]["sauna"] is True
    assert the_amnis["facilities"]["steam_room"] is None
    assert the_amnis["lounge"]["available"] is None
    assert "service_charge_percent" not in the_amnis
    tai_urban = by_id["tai_urban_resort"]
    assert tai_urban["room_inventory"] == 208
    assert tai_urban["restaurant_count"] == 6
    assert tai_urban["stay_times"]["check_in"] == "15:00"
    assert tai_urban["stay_times"]["check_out"] == "12:00"
    assert len(tai_urban["room_snapshot"]["rooms"]) == 26
    tai_urban_rooms = tai_urban["room_snapshot"]["rooms"]
    assert min(room.get("size_sqm_min", room.get("size_sqm")) for room in tai_urban_rooms) == 40
    assert max(room.get("size_sqm_max", room.get("size_sqm")) for room in tai_urban_rooms) == 93
    assert tai_urban["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": None,
        "steam_room": None,
    }
    assert tai_urban["lounge"]["available"] is True
    assert "service_charge_percent" not in tai_urban
    hotel_royal_hsinchu = by_id["hotel_royal_hsinchu"]
    assert hotel_royal_hsinchu["room_inventory"] == 208
    assert hotel_royal_hsinchu["service_charge_percent"] == 10
    assert hotel_royal_hsinchu["restaurant_count"] == 6
    assert hotel_royal_hsinchu["stay_times"]["check_in"] == "15:00"
    assert hotel_royal_hsinchu["stay_times"]["check_out"] == "11:00"
    assert [room["size_sqm"] for room in hotel_royal_hsinchu["room_snapshot"]["rooms"]] == [36, 39, 43, 43, 40, 56]
    assert hotel_royal_hsinchu["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": True,
        "steam_room": None,
    }
    assert hotel_royal_hsinchu["lounge"]["available"] is None
    eda_royal = by_id["eda_royal"]
    assert eda_royal["room_inventory"] == 650
    assert eda_royal["service_charge_percent"] == 10
    assert eda_royal["restaurant_count"] == 5
    assert eda_royal["stay_times"]["check_in"] == "15:00"
    assert eda_royal["stay_times"]["check_out"] == "11:00"
    assert len(eda_royal["room_snapshot"]["rooms"]) == 13
    assert min(room["size_sqm"] for room in eda_royal["room_snapshot"]["rooms"]) == 36
    assert max(room["size_sqm"] for room in eda_royal["room_snapshot"]["rooms"]) == 321
    assert all(eda_royal["facilities"].values())
    assert eda_royal["lounge"]["available"] is True
    hilton_sinban = by_id["hilton_taipei_sinban"]
    assert hilton_sinban["room_inventory"] == 399
    assert hilton_sinban["restaurant_count"] == 3
    assert hilton_sinban["stay_times"]["check_in"] == "15:00"
    assert hilton_sinban["stay_times"]["check_out"] == "12:00"
    assert hilton_sinban["room_snapshot"]["source_type"] == "ota"
    assert hilton_sinban["room_snapshot"]["observed_at"] == "2026-10-06"
    assert len(hilton_sinban["room_snapshot"]["rooms"]) == 13
    assert hilton_sinban["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": None,
        "steam_room": None,
    }
    assert hilton_sinban["lounge"]["available"] is True
    presidential = hilton_sinban["room_snapshot"]["rooms"][-1]
    assert presidential["size_sqm_min"] == 146
    assert presidential["size_sqm_max"] == 185
    caesar_banqiao = by_id["caesar_park_banqiao"]
    assert caesar_banqiao["room_inventory"] == 400
    assert caesar_banqiao["restaurant_count"] == 4
    assert caesar_banqiao["stay_times"]["check_in"] == "15:00"
    assert caesar_banqiao["stay_times"]["check_out"] == "12:00"
    assert caesar_banqiao["room_snapshot"]["source_type"] == "official"
    assert caesar_banqiao["room_snapshot"]["observed_at"] == "2026-10-06"
    assert len(caesar_banqiao["room_snapshot"]["rooms"]) == 9
    assert {room["size_sqm"] for room in caesar_banqiao["room_snapshot"]["rooms"]} == {
        40,
        45,
        50,
        60,
        265,
    }
    assert caesar_banqiao["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": None,
        "steam_room": None,
    }
    assert caesar_banqiao["lounge"]["available"] is True
    assert "Prestige Lounge" in caesar_banqiao["lounge"]["name"]
    fleur = by_id["fleur_de_chine"]
    assert fleur["room_inventory"] == 207
    assert fleur["service_charge_percent"] == 10
    assert fleur["restaurant_count"] == 6
    assert fleur["stay_times"]["check_in"] == "15:00"
    assert fleur["stay_times"]["check_out"] == "11:00"
    assert fleur["room_snapshot"]["source_type"] == "official"
    assert fleur["room_snapshot"]["observed_at"] == "2026-10-06"
    assert len(fleur["room_snapshot"]["rooms"]) == 18
    assert min(
        room.get("size_sqm", room.get("size_sqm_min"))
        for room in fleur["room_snapshot"]["rooms"]
    ) == 42
    assert max(
        room.get("size_sqm", room.get("size_sqm_max"))
        for room in fleur["room_snapshot"]["rooms"]
    ) == 331
    assert fleur["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": True,
        "steam_room": None,
    }
    assert fleur["lounge"]["available"] is True
    assert fleur["lounge"]["name"] == "Ciao Club"
    shangrila_tainan = by_id["shangrila_tainan"]
    assert shangrila_tainan["room_inventory"] == 331
    assert shangrila_tainan["service_charge_percent"] == 10
    assert shangrila_tainan["restaurant_count"] == 4
    assert shangrila_tainan["stay_times"]["check_in"] == "15:00"
    assert shangrila_tainan["stay_times"]["check_out"] == "12:00"
    assert shangrila_tainan["room_snapshot"]["source_type"] == "official"
    assert shangrila_tainan["room_snapshot"]["observed_at"] == "2026-10-06"
    assert len(shangrila_tainan["room_snapshot"]["rooms"]) == 10
    assert min(
        room.get("size_sqm", room.get("size_sqm_min"))
        for room in shangrila_tainan["room_snapshot"]["rooms"]
    ) == 39
    assert max(
        room.get("size_sqm", room.get("size_sqm_max"))
        for room in shangrila_tainan["room_snapshot"]["rooms"]
    ) == 196
    assert all(shangrila_tainan["facilities"].values())
    assert shangrila_tainan["lounge"]["available"] is True
    assert "Horizon Club" in shangrila_tainan["lounge"]["name"]
    silks_yilan = by_id["silks_place_yilan"]
    assert silks_yilan["room_inventory"] == 193
    assert "service_charge_percent" not in silks_yilan
    assert silks_yilan["restaurant_count"] == 2
    assert silks_yilan["stay_times"]["check_in"] == "15:00"
    assert silks_yilan["stay_times"]["check_out"] == "11:00"
    assert silks_yilan["room_snapshot"]["source_type"] == "ota"
    assert silks_yilan["room_snapshot"]["observed_at"] == "2026-10-06"
    assert len(silks_yilan["room_snapshot"]["rooms"]) == 11
    assert min(
        room.get("size_sqm", room.get("size_sqm_min"))
        for room in silks_yilan["room_snapshot"]["rooms"]
    ) == 36
    assert max(
        room.get("size_sqm", room.get("size_sqm_max"))
        for room in silks_yilan["room_snapshot"]["rooms"]
    ) == 80
    assert silks_yilan["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": True,
    }
    assert silks_yilan["lounge"]["available"] is None
    crowne_tainan = by_id["crowne_plaza_tainan"]
    assert crowne_tainan["room_inventory"] == 231
    assert "service_charge_percent" not in crowne_tainan
    assert crowne_tainan["restaurant_count"] == 4
    assert crowne_tainan["stay_times"]["check_in"] == "15:00"
    assert crowne_tainan["stay_times"]["check_out"] == "11:00"
    assert crowne_tainan["room_snapshot"]["source_type"] == "official"
    assert crowne_tainan["room_snapshot"]["observed_at"] == "2026-10-06"
    assert len(crowne_tainan["room_snapshot"]["rooms"]) == 16
    assert min(room["size_sqm"] for room in crowne_tainan["room_snapshot"]["rooms"]) == 40
    assert max(room["size_sqm"] for room in crowne_tainan["room_snapshot"]["rooms"]) == 182
    assert crowne_tainan["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": None,
    }
    assert crowne_tainan["lounge"]["available"] is True
    assert "Crowne Plaza" in crowne_tainan["lounge"]["name"]
    formosa_yacht = by_id["formosa_yacht_resort"]
    assert formosa_yacht["room_inventory"] == 237
    assert formosa_yacht["service_charge_percent"] == 10
    assert formosa_yacht["service_charge_source_type"] == "official"
    assert formosa_yacht["restaurant_count"] == 3
    assert formosa_yacht["room_snapshot"]["source_type"] == "official"
    assert formosa_yacht["room_snapshot"]["observed_at"] == "2026-10-06"
    assert len(formosa_yacht["room_snapshot"]["rooms"]) == 9
    assert min(room["size_sqm"] for room in formosa_yacht["room_snapshot"]["rooms"]) == 40
    assert max(room["size_sqm"] for room in formosa_yacht["room_snapshot"]["rooms"]) == 152
    assert all(formosa_yacht["facilities"].values())
    assert formosa_yacht["lounge"]["available"] is None
    silks_tainan = by_id["silks_place_tainan"]
    assert silks_tainan["room_inventory"] == 255
    assert "service_charge_percent" not in silks_tainan
    assert silks_tainan["restaurant_count"] == 9
    assert silks_tainan["stay_times"]["check_in"] == "16:00"
    assert silks_tainan["stay_times"]["check_out"] == "12:00"
    assert silks_tainan["room_snapshot"]["source_type"] == "official"
    assert silks_tainan["room_snapshot"]["observed_at"] == "2026-10-06"
    assert len(silks_tainan["room_snapshot"]["rooms"]) == 9
    assert min(room["size_sqm"] for room in silks_tainan["room_snapshot"]["rooms"]) == 39.7
    assert max(room["size_sqm"] for room in silks_tainan["room_snapshot"]["rooms"]) == 152.1
    assert silks_tainan["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": None,
        "steam_room": None,
    }
    assert silks_tainan["lounge"]["available"] is True
    assert "Silks Lounge" in silks_tainan["lounge"]["name"]
    lalu = by_id["the_lalu_sun_moon_lake"]
    assert lalu["room_inventory"] == 96
    assert lalu["service_charge_percent"] == 10
    assert lalu["service_charge_source_type"] == "official"
    assert lalu["restaurant_count"] == 5
    assert lalu["room_snapshot"]["source_type"] == "ota"
    assert lalu["room_snapshot"]["observed_at"] == "2026-10-06"
    assert len(lalu["room_snapshot"]["rooms"]) == 6
    assert min(room["size_sqm"] for room in lalu["room_snapshot"]["rooms"]) == 83
    assert max(room["size_sqm"] for room in lalu["room_snapshot"]["rooms"]) == 333
    assert lalu["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": True,
        "steam_room": None,
    }
    assert lalu["lounge"]["available"] is None
    chihpen = by_id["hotel_royal_chihpen"]
    assert chihpen["room_inventory"] == 183
    assert chihpen["service_charge_percent"] == 10
    assert chihpen["restaurant_count"] == 4
    assert chihpen["stay_times"] == {
        "check_in": "15:00",
        "check_out": "12:00",
        "source_type": "official",
        "source_url": "https://www.hotelroyal.com.tw/zh-tw/chihpen/Rooms",
    }
    assert chihpen["room_snapshot"]["source_type"] == "official"
    assert len(chihpen["room_snapshot"]["rooms"]) == 8
    assert min(room["size_sqm"] for room in chihpen["room_snapshot"]["rooms"]) == 29
    assert max(room["size_sqm"] for room in chihpen["room_snapshot"]["rooms"]) == 85
    assert chihpen["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": None,
        "steam_room": None,
    }
    mu_jiaoxi = by_id["mu_jiaoxi_reserve"]
    assert mu_jiaoxi["room_inventory"] == 190
    assert mu_jiaoxi["service_charge_percent"] == 10
    assert mu_jiaoxi["restaurant_count"] == 4
    assert mu_jiaoxi["room_snapshot"]["source_type"] == "official"
    assert len(mu_jiaoxi["room_snapshot"]["rooms"]) == 7
    assert min(room["size_sqm"] for room in mu_jiaoxi["room_snapshot"]["rooms"]) == 39.7
    assert max(room["size_sqm"] for room in mu_jiaoxi["room_snapshot"]["rooms"]) == 297.5
    assert mu_jiaoxi["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": None,
        "steam_room": None,
    }
    assert mu_jiaoxi["lounge"]["available"] is True
    assert "MU TOP" in mu_jiaoxi["lounge"]["name"]
    wyndham = by_id["wyndham_sun_moon_lake"]
    assert wyndham["room_inventory"] == 197
    assert wyndham["service_charge_percent"] is None
    assert wyndham["restaurant_count"] == 4
    assert wyndham["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": None,
        "steam_room": None,
    }
    assert wyndham["lounge"]["available"] is True
    assert wyndham["room_snapshot"]["source_type"] == "official"
    assert len(wyndham["room_snapshot"]["rooms"]) == 15
    assert min(room["size_sqm"] for room in wyndham["room_snapshot"]["rooms"]) == 36
    assert max(room["size_sqm"] for room in wyndham["room_snapshot"]["rooms"]) == 102
    four_points_penghu = by_id["four_points_penghu"]
    assert four_points_penghu["room_inventory"] == 331
    assert four_points_penghu["service_charge_percent"] is None
    assert four_points_penghu["restaurant_count"] == 5
    assert four_points_penghu["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": True,
    }
    assert len(four_points_penghu["room_snapshot"]["rooms"]) == 8
    assert four_points_penghu["room_snapshot"]["rooms"][-1]["size_sqm_max"] == 106
    grand_cosmos = by_id["grand_cosmos_ruisui"]
    assert grand_cosmos["room_inventory"] == 198
    assert grand_cosmos["service_charge_percent"] == 10
    assert grand_cosmos["restaurant_count"] == 6
    assert grand_cosmos["stay_times"]["check_in"] == "15:00"
    assert grand_cosmos["stay_times"]["check_out"] == "11:00"
    assert grand_cosmos["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": True,
        "steam_room": True,
    }
    assert len(grand_cosmos["room_snapshot"]["rooms"]) == 15
    assert max(room["size_sqm"] for room in grand_cosmos["room_snapshot"]["rooms"]) == 2148.7
    assert "facility_notes" in html
    gaia = by_id["the_gaia_taipei"]
    assert gaia["room_inventory"] == 48
    assert gaia["service_charge_percent"] == 10
    assert gaia["stay_times"]["source_type"] == "ota"
    assert gaia["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": True,
        "steam_room": True,
    }
    assert len(gaia["restaurants"]) == 3
    assert [room["size_sqm"] for room in gaia["room_snapshot"]["rooms"]] == [33, 36, 43, 50, 66, 33]
    grand_hotel = by_id["grand_hotel_taipei"]
    assert grand_hotel["room_inventory"] == 500
    assert grand_hotel["stay_times"]["source_type"] == "official"
    assert grand_hotel["service_charge_percent"] == 10
    assert len(grand_hotel["restaurants"]) == 6
    assert grand_hotel["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": True,
    }
    grand_hotel_rooms = grand_hotel["room_snapshot"]["rooms"]
    assert len(grand_hotel_rooms) == 15
    assert min(room["size_sqm"] for room in grand_hotel_rooms) == 20
    assert max(room["size_sqm"] for room in grand_hotel_rooms) == 926
    gracery = by_id["hotel_gracery_taipei"]
    assert gracery["room_inventory"] == 248
    assert gracery["stay_times"] == {
        "check_in": "15:00",
        "check_out": "12:00",
        "source_type": "official",
        "source_url": "https://tw.gracery.com/taipei/",
    }
    assert len(gracery["room_snapshot"]["rooms"]) == 15
    assert {room["size_sqm"] for room in gracery["room_snapshot"]["rooms"]} == {25, 26, 50}
    assert len(by_id["capella_taipei"]["restaurants"]) == 5
    capella_rooms = by_id["capella_taipei"]["room_snapshot"]["rooms"]
    assert len(capella_rooms) == 13
    assert min(room["size_sqm"] for room in capella_rooms) == 48
    assert max(room["size_sqm"] for room in capella_rooms) == 270
    assert next(room for room in capella_rooms if room["name_en"] == "Capella Suite")["size_sqm"] == 228
    assert by_id["mo_taipei"]["lounge"]["name"] == "The Oriental Lounge"
    mo_rooms = by_id["mo_taipei"]["room_snapshot"]["rooms"]
    assert len(mo_rooms) == 15
    assert min(room["size_sqm"] for room in mo_rooms) == 55
    assert max(room["size_sqm"] for room in mo_rooms) == 376
    assert next(room for room in mo_rooms if room["name_en"] == "Club City Suite Connecting")["size_sqm"] == 141
    assert next(room for room in mo_rooms if room["name_en"] == "Club Premier Suite Connecting")["size_sqm"] == 243
    assert by_id["grand_hilai_taipei"]["facilities"]["pool"] is True
    hilai_taipei_rooms = by_id["grand_hilai_taipei"]["room_snapshot"]["rooms"]
    assert len(hilai_taipei_rooms) == 9
    assert min(room["size_sqm"] for room in hilai_taipei_rooms) == 31
    assert max(room["size_sqm"] for room in hilai_taipei_rooms) == 521
    assert by_id["grand_hilai_taipei"]["service_charge_percent"] == 10
    assert by_id["grand_hilai_taipei"]["service_charge_source_type"] == "official"
    assert by_id["okura_prestige_taipei"]["room_inventory"] == 207
    assert len(by_id["okura_prestige_taipei"]["restaurants"]) == 5
    okura_rooms = by_id["okura_prestige_taipei"]["room_snapshot"]["rooms"]
    assert len(okura_rooms) == 8
    assert {room["size_sqm"] for room in okura_rooms} == {44, 56, 75, 82, 228}
    assert {room["name_ja"] for room in okura_rooms} >= {"プレステージルーム", "ロイヤルスイート"}
    assert "合計 15%" in by_id["okura_prestige_taipei"]["service_charge_note_zh"]
    assert "service_charge_note_" in html
    assert by_id["shangrila_taipei"]["room_inventory"] == 420
    assert by_id["shangrila_taipei"]["lounge"]["name"] == "Horizon Club Lounge"
    shangrila_rooms = by_id["shangrila_taipei"]["room_snapshot"]["rooms"]
    assert len(shangrila_rooms) == 14
    assert min(room["size_sqm"] for room in shangrila_rooms) == 36
    assert max(room["size_sqm"] for room in shangrila_rooms) == 226
    assert next(room for room in shangrila_rooms if room["name_en"] == "Two Deluxe Rooms Inter-Connecting")["size_sqm"] == 80
    assert by_id["grand_mayfull_taipei"]["room_inventory"] == 146
    assert by_id["grand_mayfull_taipei"]["lounge"]["kind"] == "members_club"
    mayfull_rooms = by_id["grand_mayfull_taipei"]["room_snapshot"]["rooms"]
    assert len(mayfull_rooms) == 9
    assert min(room["size_sqm"] for room in mayfull_rooms) == 50
    assert max(room["size_sqm"] for room in mayfull_rooms) == 250
    assert by_id["grand_mayfull_taipei"]["service_charge_percent"] == 10
    assert by_id["grand_mayfull_taipei"]["service_charge_source_type"] == "official"
    assert by_id["grand_hyatt_taipei"]["room_inventory"] == 850
    assert len(by_id["grand_hyatt_taipei"]["restaurants"]) == 8
    assert by_id["grand_hyatt_taipei"]["lounge"]["name"] == "Grand Club Lounge"
    grand_hyatt_rooms = by_id["grand_hyatt_taipei"]["room_snapshot"]["rooms"]
    assert by_id["grand_hyatt_taipei"]["room_snapshot"]["source_type"] == "official"
    assert len(grand_hyatt_rooms) == 22
    assert min(room.get("size_sqm_min", room.get("size_sqm")) for room in grand_hyatt_rooms) == 33
    assert max(room.get("size_sqm_max", room.get("size_sqm")) for room in grand_hyatt_rooms) == 221
    hyatt_101_king = next(room for room in grand_hyatt_rooms if room["name_en"] == "1 King Bed 101 View")
    assert (hyatt_101_king["size_sqm_min"], hyatt_101_king["size_sqm_max"]) == (33, 40)
    assert next(room for room in grand_hyatt_rooms if room["name_en"] == "Diplomat Suite")["size_sqm"] == 188
    assert {room["name_zh"] for room in grand_hyatt_rooms} >= {"總裁套房", "總統套房"}
    assert "service_charge_percent" not in by_id["grand_hyatt_taipei"]
    assert by_id["w_taipei"]["room_inventory"] == 405
    assert len(by_id["w_taipei"]["restaurants"]) == 4
    assert by_id["w_taipei"]["facilities"]["sauna"] is None
    assert by_id["w_taipei"]["lounge"]["available"] is None
    w_rooms = by_id["w_taipei"]["room_snapshot"]["rooms"]
    assert by_id["w_taipei"]["room_snapshot"]["source_type"] == "ota"
    assert by_id["w_taipei"]["room_snapshot"]["observed_at"] == "2026-10-02"
    assert len(w_rooms) == 8
    assert min(room["size_sqm"] for room in w_rooms) == 43
    assert max(room["size_sqm"] for room in w_rooms) == 365
    assert {room["name_zh"] for room in w_rooms} >= {"奇妙客房", "壯美客房", "絕佳客房", "酷角客房", "頂級驚喜套房"}
    assert next(room for room in w_rooms if room["name_en"] == "WOW Suite")["size_sqm"] == 116
    assert "service_charge_percent" not in by_id["w_taipei"]
    regent = by_id["regent_taipei"]
    regent_rooms = regent["room_snapshot"]["rooms"]
    assert regent["room_snapshot"]["source_type"] == "official"
    assert len(regent_rooms) == 11
    assert min(room["size_sqm"] for room in regent_rooms) == 39
    assert max(room["size_sqm"] for room in regent_rooms) == 210
    assert {room["name_zh"] for room in regent_rooms} >= {"精緻客房", "雲天露臺家庭房", "大班豪華客房", "總統套房"}
    assert next(room for room in regent_rooms if room["name_en"] == "Corner Suite")["size_sqm"] == 110
    assert "service_charge_percent" not in regent
    assert "合計 15.5%" in regent["service_charge_note_zh"]
    assert by_id["eslite_hotel"]["room_inventory"] == 104
    assert len(by_id["eslite_hotel"]["restaurants"]) == 3
    assert by_id["eslite_hotel"]["facilities"]["fitness"] is True
    assert by_id["eslite_hotel"]["facilities"]["pool"] is None
    eslite_rooms = by_id["eslite_hotel"]["room_snapshot"]["rooms"]
    assert len(eslite_rooms) == 5
    assert eslite_rooms[-1]["size_sqm_min"] == 89
    assert eslite_rooms[-1]["size_sqm_max"] == 182
    assert "room.size_sqm_min??room.size_sqm" in html
    assert "r.sizeMax!==r.sizeMin" in html
    assert "function rateRoomLabel(row)" in html
    assert "item.sourceName.includes(room.name_zh)" in html
    assert "['愛心房','Accessible']" in html
    assert by_id["hotel_metropolitan_premier_taipei"]["room_inventory"] == 288
    assert len(by_id["hotel_metropolitan_premier_taipei"]["restaurants"]) == 7
    assert by_id["hotel_metropolitan_premier_taipei"]["facilities"] == {"pool": True, "fitness": True, "spa": True, "sauna": True, "steam_room": True}
    assert by_id["hotel_metropolitan_premier_taipei"]["lounge"]["kind"] == "executive_club"
    jr_rooms = by_id["hotel_metropolitan_premier_taipei"]["room_snapshot"]["rooms"]
    assert len(jr_rooms) == 21
    assert min(room.get("size_sqm_min", room.get("size_sqm")) for room in jr_rooms) == 36
    assert max(room.get("size_sqm_max", room.get("size_sqm")) for room in jr_rooms) == 210
    assert by_id["solaria_nishitetsu_taipei"]["room_inventory"] == 298
    assert len(by_id["solaria_nishitetsu_taipei"]["restaurants"]) == 1
    assert by_id["solaria_nishitetsu_taipei"]["facilities"]["fitness"] is True
    assert by_id["solaria_nishitetsu_taipei"]["facilities"]["pool"] is None
    solaria_rooms = by_id["solaria_nishitetsu_taipei"]["room_snapshot"]["rooms"]
    assert len(solaria_rooms) == 15
    assert min(room["size_sqm"] for room in solaria_rooms) == 18
    assert max(room["size_sqm"] for room in solaria_rooms) == 39
    assert {room["name_ja"] for room in solaria_rooms} >= {"コンパクトクイーン", "プレミアムルーム"}
    assert by_id["regent_taipei"]["room_inventory"] == 538
    assert len(by_id["regent_taipei"]["restaurants"]) == 8
    assert by_id["regent_taipei"]["facilities"]["sauna"] is True
    assert by_id["regent_taipei"]["facilities"]["steam_room"] is None
    assert by_id["regent_taipei"]["lounge"]["name"] == "Silks Club"
    assert by_id["taipei_marriott"]["room_inventory"] == 318
    assert any("taiwanstay.net.tw" in url for url in by_id["taipei_marriott"]["source_urls"])
    assert len(by_id["taipei_marriott"]["restaurants"]) == 6
    assert by_id["taipei_marriott"]["facilities"]["sauna"] is True
    assert by_id["taipei_marriott"]["lounge"]["name"] == "Executive Lounge"
    snapshot = by_id["taipei_marriott"]["room_snapshot"]
    assert snapshot["observed_at"] == "2026-09-23"
    assert snapshot["source_type"] == "official"
    assert len(snapshot["rooms"]) == 7
    assert {room["name_en"] for room in snapshot["rooms"]} >= {"Classic Room", "Brilliant Suite"}
    assert {room["size_sqm"] for room in snapshot["rooms"]} >= {40, 51, 65, 80}
    palais = by_id["palais_de_chine"]
    assert palais["room_inventory"] == 286
    assert any("media.taiwan.net.tw" in url for url in palais["source_urls"])
    assert len(palais["restaurants"]) == 3
    assert palais["facilities"] == {"pool": None, "fitness": True, "spa": None, "sauna": None, "steam_room": None}
    assert palais["lounge"]["name"] == "Le Salon VIP Lounge"
    assert palais["room_snapshot"]["source_type"] == "official"
    assert len(palais["room_snapshot"]["rooms"]) == 9
    assert {room["size_sqm"] for room in palais["room_snapshot"]["rooms"]} == {30, 37, 50, 67}
    royal_nikko = by_id["royal_nikko_taipei"]
    assert royal_nikko["room_inventory"] == 202
    assert len(royal_nikko["restaurants"]) == 5
    assert royal_nikko["facilities"] == {"pool": None, "fitness": None, "spa": True, "sauna": None, "steam_room": None}
    assert royal_nikko["lounge"]["name"] == "Royal VIP Lounge"
    assert royal_nikko["room_snapshot"]["source_type"] == "official"
    assert len(royal_nikko["room_snapshot"]["rooms"]) == 7
    assert {room["name_ja"] for room in royal_nikko["room_snapshot"]["rooms"]} >= {"スーペリアルーム", "ロイヤルスイート"}
    assert {room["size_sqm"] for room in royal_nikko["room_snapshot"]["rooms"]} == {26, 32, 38, 50, 65, 89, 125}
    le_meridien = by_id["le_meridien_taipei"]
    assert le_meridien["room_inventory"] == 160
    assert le_meridien["service_charge_percent"] == 10
    assert len(le_meridien["restaurants"]) == 4
    assert le_meridien["facilities"] == {"pool": True, "fitness": True, "spa": False, "sauna": True, "steam_room": None}
    assert le_meridien["lounge"]["name"] == "Le Méridien Club Lounge"
    assert le_meridien["room_snapshot"]["source_type"] == "official"
    assert len(le_meridien["room_snapshot"]["rooms"]) == 11
    assert {room["size_sqm"] for room in le_meridien["room_snapshot"]["rooms"]} == {38, 60, 75, 157, 223}
    assert "serviceChargeInfo" in html
    assert 'data-i18n="serviceCharge"' in html
    assert "service_charge_percent" in html
    assert "observedMatch.name=roomLabel(room)" in html
    hoshinoya = by_id["hoshinoya_guguan"]
    assert hoshinoya["room_inventory"] == 49
    assert hoshinoya["service_charge_percent"] == 10
    assert len(hoshinoya["restaurants"]) == 2
    assert hoshinoya["facilities"] == {
        "pool": True,
        "fitness": None,
        "spa": True,
        "sauna": True,
        "steam_room": None,
    }
    assert hoshinoya["lounge"] == {"available": False, "name": None, "kind": "none"}
    assert hoshinoya["room_snapshot"]["source_type"] == "official"
    assert [room["name_zh"] for room in hoshinoya["room_snapshot"]["rooms"]] == [
        "水明",
        "風音",
        "月見",
        "山霞",
        "森羅",
    ]
    assert {room["size_sqm"] for room in hoshinoya["room_snapshot"]["rooms"]} == {
        75,
        87,
        105,
        112,
        216,
    }
    windsor = by_id["windsor_taichung"]
    assert windsor["room_inventory"] == 149
    assert windsor["service_charge_percent"] == 10
    assert len(windsor["restaurants"]) == 5
    assert windsor["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": True,
        "steam_room": True,
    }
    assert windsor["lounge"] == {"available": False, "name": None, "kind": "none"}
    assert windsor["room_snapshot"]["source_type"] == "official"
    assert len(windsor["room_snapshot"]["rooms"]) == 10
    assert {room["name_en"] for room in windsor["room_snapshot"]["rooms"]} >= {
        "Superior King Bed Room",
        "Windsor Suite",
    }
    assert min(room["size_sqm"] for room in windsor["room_snapshot"]["rooms"]) == 31
    assert max(room["size_sqm"] for room in windsor["room_snapshot"]["rooms"]) == 165
    intercontinental_taichung = by_id["intercontinental_taichung"]
    assert intercontinental_taichung["room_inventory"] == 206
    assert "service_charge_percent" not in intercontinental_taichung
    assert len(intercontinental_taichung["restaurants"]) == 5
    assert intercontinental_taichung["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": True,
    }
    assert intercontinental_taichung["lounge"] == {
        "available": True,
        "name": "洲際行政俱樂部",
        "kind": "executive_lounge",
    }
    assert intercontinental_taichung["room_snapshot"]["source_type"] == "official"
    assert len(intercontinental_taichung["room_snapshot"]["rooms"]) == 6
    assert {room["name_en"] for room in intercontinental_taichung["room_snapshot"]["rooms"]} == {
        "Classic Room",
        "Premium Room",
        "Midtown Suite",
        "Vista Suite",
        "Royal Suite",
        "Presidential Suite",
    }
    assert min(room["size_sqm"] for room in intercontinental_taichung["room_snapshot"]["rooms"]) == 40
    assert max(room["size_sqm"] for room in intercontinental_taichung["room_snapshot"]["rooms"]) == 173
    grand_hilai_kaohsiung = by_id["grand_hilai_kaohsiung"]
    assert grand_hilai_kaohsiung["room_inventory"] == 540
    assert grand_hilai_kaohsiung["service_charge_percent"] == 10
    assert len(grand_hilai_kaohsiung["restaurants"]) == 13
    assert grand_hilai_kaohsiung["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": False,
        "sauna": True,
        "steam_room": True,
    }
    assert grand_hilai_kaohsiung["lounge"] == {
        "available": True,
        "name": "商務貴賓軒",
        "kind": "executive_lounge",
    }
    assert grand_hilai_kaohsiung["room_snapshot"]["source_type"] == "official"
    assert len(grand_hilai_kaohsiung["room_snapshot"]["rooms"]) == 29
    assert {room["name_en"] for room in grand_hilai_kaohsiung["room_snapshot"]["rooms"]} >= {
        "Superior Room",
        "Presidential Suite",
        "Hello Kitty Parisian Chic Premium Family Room",
    }
    assert min(room["size_sqm"] for room in grand_hilai_kaohsiung["room_snapshot"]["rooms"]) == 33
    assert max(room["size_sqm"] for room in grand_hilai_kaohsiung["room_snapshot"]["rooms"]) == 510
    intercontinental_kaohsiung = by_id["intercontinental_kaohsiung"]
    assert intercontinental_kaohsiung["room_inventory"] == 253
    assert "service_charge_percent" not in intercontinental_kaohsiung
    assert len(intercontinental_kaohsiung["restaurants"]) == 6
    assert intercontinental_kaohsiung["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": True,
    }
    assert intercontinental_kaohsiung["lounge"] == {
        "available": True,
        "name": "洲際行政俱樂部",
        "kind": "executive_lounge",
    }
    assert intercontinental_kaohsiung["room_snapshot"]["source_type"] == "official"
    assert len(intercontinental_kaohsiung["room_snapshot"]["rooms"]) == 5
    classic = intercontinental_kaohsiung["room_snapshot"]["rooms"][0]
    assert classic["name_en"] == "Classic Room"
    assert classic["size_sqm_min"] == 36
    assert classic["size_sqm_max"] == 46
    assert max(room.get("size_sqm_max", room.get("size_sqm")) for room in intercontinental_kaohsiung["room_snapshot"]["rooms"]) == 210
    kaohsiung_marriott = by_id["kaohsiung_marriott"]
    assert kaohsiung_marriott["room_inventory"] == 700
    assert "service_charge_percent" not in kaohsiung_marriott
    assert len(kaohsiung_marriott["restaurants"]) == 10
    assert kaohsiung_marriott["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": True,
        "steam_room": True,
    }
    assert kaohsiung_marriott["lounge"] == {
        "available": True,
        "name": "行政酒廊 Executive Lounge",
        "kind": "executive_lounge",
    }
    assert kaohsiung_marriott["room_snapshot"]["source_type"] == "official"
    assert len(kaohsiung_marriott["room_snapshot"]["rooms"]) == 7
    assert {room["name_en"] for room in kaohsiung_marriott["room_snapshot"]["rooms"]} >= {
        "Classic Room",
        "Premier Suite",
        "Executive Grand Suite",
    }
    assert min(room["size_sqm"] for room in kaohsiung_marriott["room_snapshot"]["rooms"]) == 46
    assert max(room["size_sqm"] for room in kaohsiung_marriott["room_snapshot"]["rooms"]) == 92
    hotel_nikko_kaohsiung = by_id["hotel_nikko_kaohsiung"]
    assert hotel_nikko_kaohsiung["room_inventory"] == 260
    assert hotel_nikko_kaohsiung["service_charge_percent"] == 10
    assert len(hotel_nikko_kaohsiung["restaurants"]) == 5
    assert hotel_nikko_kaohsiung["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": None,
    }
    assert hotel_nikko_kaohsiung["lounge"] == {
        "available": True,
        "name": "日航行政酒廊",
        "kind": "executive_lounge",
    }
    assert hotel_nikko_kaohsiung["room_snapshot"]["source_type"] == "official"
    assert len(hotel_nikko_kaohsiung["room_snapshot"]["rooms"]) == 16
    assert {room["name_en"] for room in hotel_nikko_kaohsiung["room_snapshot"]["rooms"]} >= {
        "Classic King Room",
        "Nikko Club King Room",
        "Grand Corner Twin Suite",
    }
    assert min(room["size_sqm"] for room in hotel_nikko_kaohsiung["room_snapshot"]["rooms"]) == 36
    assert max(room["size_sqm"] for room in hotel_nikko_kaohsiung["room_snapshot"]["rooms"]) == 126
    sheraton_hsinchu = by_id["sheraton_hsinchu"]
    assert sheraton_hsinchu["room_inventory"] == 770
    assert sheraton_hsinchu["service_charge_percent"] == 10
    assert len(sheraton_hsinchu["restaurants"]) == 7
    assert sheraton_hsinchu["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": True,
    }
    assert sheraton_hsinchu["lounge"] == {
        "available": True,
        "name": "行政貴賓廳 Sheraton Club",
        "kind": "executive_lounge",
    }
    assert sheraton_hsinchu["room_snapshot"]["source_type"] == "official"
    assert len(sheraton_hsinchu["room_snapshot"]["rooms"]) == 8
    assert {room["name_en"] for room in sheraton_hsinchu["room_snapshot"]["rooms"]} >= {
        "Deluxe Room",
        "Sheraton Suite",
        "Presidential Suite",
        "BoBo Themed Room",
    }
    assert min(room["size_sqm"] for room in sheraton_hsinchu["room_snapshot"]["rooms"]) == 40
    assert max(room["size_sqm"] for room in sheraton_hsinchu["room_snapshot"]["rooms"]) == 231
    radium_kagaya = by_id["radium_kagaya_taipei"]
    assert radium_kagaya["room_inventory"] == 90
    assert radium_kagaya["service_charge_percent"] == 10
    assert len(radium_kagaya["restaurants"]) == 3
    assert radium_kagaya["facilities"] == {
        "pool": None,
        "fitness": None,
        "spa": True,
        "sauna": True,
        "steam_room": True,
    }
    assert radium_kagaya["lounge"] == {
        "available": False,
        "name": None,
        "kind": "none",
    }
    assert radium_kagaya["room_snapshot"]["source_type"] == "official"
    assert len(radium_kagaya["room_snapshot"]["rooms"]) == 9
    assert {room["name_en"] for room in radium_kagaya["room_snapshot"]["rooms"]} >= {
        "Mixed Standard Suite (No View)",
        "Semi-Open Hot Spring Executive Suite",
        "Grand Special Suite",
    }
    assert min(room.get("size_sqm_min", room.get("size_sqm")) for room in radium_kagaya["room_snapshot"]["rooms"]) == 43
    assert max(room.get("size_sqm_max", room.get("size_sqm")) for room in radium_kagaya["room_snapshot"]["rooms"]) == 105
    grand_view = by_id["grand_view_resort_beitou"]
    assert grand_view["room_inventory"] == 66
    assert grand_view["service_charge_percent"] == 10
    assert len(grand_view["restaurants"]) == 3
    assert grand_view["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": True,
        "steam_room": True,
    }
    assert grand_view["lounge"] == {
        "available": False,
        "name": None,
        "kind": "none",
    }
    assert grand_view["room_snapshot"]["source_type"] == "official"
    assert len(grand_view["room_snapshot"]["rooms"]) == 8
    assert {room["name_en"] for room in grand_view["room_snapshot"]["rooms"]} >= {
        "Superior Room",
        "You-Ya Suite",
        "Grand View Suite 503",
    }
    assert min(room["size_sqm"] for room in grand_view["room_snapshot"]["rooms"]) == 50
    assert max(room["size_sqm"] for room in grand_view["room_snapshot"]["rooms"]) == 116
    kimpton = by_id["kimpton_da_an"]
    assert kimpton["room_inventory"] == 129
    assert "service_charge_percent" not in kimpton
    assert len(kimpton["restaurants"]) == 1
    assert kimpton["facilities"] == {
        "pool": None,
        "fitness": True,
        "spa": None,
        "sauna": None,
        "steam_room": None,
    }
    assert kimpton["lounge"] == {"available": False, "name": None, "kind": "none"}
    assert kimpton["room_snapshot"]["source_type"] == "official"
    assert len(kimpton["room_snapshot"]["rooms"]) == 3
    assert {room["name_en"] for room in kimpton["room_snapshot"]["rooms"]} == {
        "Essential Room",
        "Premium Room",
        "Suite",
    }
    assert min(room.get("size_sqm_min", room.get("size_sqm")) for room in kimpton["room_snapshot"]["rooms"]) == 32
    assert max(room.get("size_sqm_max", room.get("size_sqm")) for room in kimpton["room_snapshot"]["rooms"]) == 58
    humble_house = by_id["humble_house_taipei"]
    assert humble_house["room_inventory"] == 235
    assert humble_house["service_charge_percent"] == 10
    assert len(humble_house["restaurants"]) == 1
    assert humble_house["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": None,
        "steam_room": None,
    }
    assert humble_house["lounge"] == {"available": False, "name": None, "kind": "none"}
    assert humble_house["room_snapshot"]["source_type"] == "official"
    assert len(humble_house["room_snapshot"]["rooms"]) == 10
    assert {room["name_zh"] for room in humble_house["room_snapshot"]["rooms"]} >= {
        "豪華客房",
        "景隅尊貴客房",
        "艾麗套房",
        "寒舍套房",
    }
    assert min(room["size_sqm"] for room in humble_house["room_snapshot"]["rooms"]) == 26
    assert max(room["size_sqm"] for room in humble_house["room_snapshot"]["rooms"]) == 136
    indigo = by_id["indigo_taipei_north"]
    assert indigo["room_inventory"] == 149
    assert "service_charge_percent" not in indigo
    assert len(indigo["restaurants"]) == 2
    assert indigo["facilities"] == {
        "pool": False,
        "fitness": True,
        "spa": None,
        "sauna": None,
        "steam_room": None,
    }
    assert indigo["lounge"] == {"available": False, "name": None, "kind": "none"}
    assert indigo["room_snapshot"]["source_type"] == "ota"
    assert len(indigo["room_snapshot"]["rooms"]) == 5
    assert {room["size_sqm"] for room in indigo["room_snapshot"]["rooms"]} == {35, 40, 60, 73, 135}
    sheraton_taipei = by_id["sheraton_grand_taipei"]
    assert sheraton_taipei["room_inventory"] == 683
    assert sheraton_taipei["service_charge_percent"] == 10
    assert len(sheraton_taipei["restaurants"]) == 10
    assert sheraton_taipei["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": True,
        "sauna": True,
        "steam_room": True,
    }
    assert sheraton_taipei["lounge"] == {
        "available": True,
        "name": "Sheraton Club Lounge",
        "kind": "executive_lounge",
    }
    assert sheraton_taipei["room_snapshot"]["source_type"] == "official"
    assert len(sheraton_taipei["room_snapshot"]["rooms"]) == 14
    assert min(room["size_sqm"] for room in sheraton_taipei["room_snapshot"]["rooms"]) == 32
    assert max(room["size_sqm"] for room in sheraton_taipei["room_snapshot"]["rooms"]) == 562
    courtyard_taipei = by_id["courtyard_taipei"]
    assert courtyard_taipei["room_inventory"] == 465
    assert "service_charge_percent" not in courtyard_taipei
    assert len(courtyard_taipei["restaurants"]) == 3
    assert courtyard_taipei["facilities"] == {
        "pool": False,
        "fitness": True,
        "spa": True,
        "sauna": None,
        "steam_room": None,
    }
    assert courtyard_taipei["lounge"] == {
        "available": True,
        "name": "行政貴賓廳 Executive Lounge",
        "kind": "executive_lounge",
    }
    assert courtyard_taipei["room_snapshot"]["source_type"] == "official"
    assert len(courtyard_taipei["room_snapshot"]["rooms"]) == 7
    assert min(room["size_sqm"] for room in courtyard_taipei["room_snapshot"]["rooms"]) == 35
    assert max(room["size_sqm"] for room in courtyard_taipei["room_snapshot"]["rooms"]) == 168
    resonance = by_id["hotel_resonance_taipei"]
    assert resonance["room_inventory"] == 175
    assert resonance["service_charge_percent"] == 10
    assert resonance["service_charge_source_type"] == "observed"
    assert len(resonance["restaurants"]) == 1
    assert resonance["facilities"] == {
        "pool": False,
        "fitness": True,
        "spa": True,
        "sauna": None,
        "steam_room": None,
    }
    assert resonance["lounge"] == {"available": False, "name": None, "kind": "none"}
    assert resonance["room_snapshot"]["source_type"] == "ota"
    assert len(resonance["room_snapshot"]["rooms"]) == 8
    assert {room["size_sqm"] for room in resonance["room_snapshot"]["rooms"]} == {30, 34, 40, 45, 52}
    renaissance = by_id["renaissance_taipei_shihlin"]
    assert renaissance["room_inventory"] == 104
    assert "service_charge_percent" not in renaissance
    assert len(renaissance["restaurants"]) == 4
    assert renaissance["facilities"] == {
        "pool": True,
        "fitness": True,
        "spa": None,
        "sauna": True,
        "steam_room": None,
    }
    assert renaissance["lounge"] == {
        "available": True,
        "name": "行政酒廊 Executive Lounge",
        "kind": "executive_lounge",
    }
    assert renaissance["room_snapshot"]["source_type"] == "official"
    assert len(renaissance["room_snapshot"]["rooms"]) == 7
    assert {room["size_sqm"] for room in renaissance["room_snapshot"]["rooms"]} == {31, 86, 126}
    proverbs = by_id["hotel_proverbs_taipei"]
    assert proverbs["room_inventory"] == 42
    assert proverbs["service_charge_percent"] == 10
    assert len(proverbs["restaurants"]) == 2
    assert proverbs["facilities"] == {
        "pool": True,
        "fitness": None,
        "spa": None,
        "sauna": None,
        "steam_room": None,
    }
    assert proverbs["lounge"] == {"available": False, "name": None, "kind": "none"}
    assert proverbs["room_snapshot"]["source_type"] == "official"
    assert len(proverbs["room_snapshot"]["rooms"]) == 5
    assert {room["size_sqm"] for room in proverbs["room_snapshot"]["rooms"]} == {33, 37, 38, 41, 49}
    assert "service_charge_source_type==='observed'?'observed':'official'" in html
    assert "room.aliases_zh||[]" in html
    assert "Math.abs(item.sizeMin-min)<=1" in html


def test_hotel_profile_page_supports_sorting_rate_filter_and_city_colors():
    html = Path("public/hotels.html").read_text(encoding="utf-8")

    assert 'id="rateStatus"' in html
    assert 'id="sort"' in html
    assert 'class="sort-button" data-sort="name"' in html
    assert 'class="sort-button" data-sort="geo"' in html
    assert "function sortHotels(items)" in html
    assert "CITY_COLORS=" in html
    assert 'class="city-row ${upcoming' in html
    assert 'class="city-badge"' in html
    assert "rateStatus==='with'" in html
    assert "function loungeDetail(profile)" in html


def test_hotel_profile_comparison_rows_open_details_without_horizontal_scrolling():
    html = Path("public/hotels.html").read_text(encoding="utf-8")

    assert ".hotel-select-row{cursor:pointer" in html
    assert "#hotelComparison th:first-child,#hotelComparison td:first-child{position:sticky;left:0" in html
    assert ".hotel-row-actions{display:flex" in html
    assert ".table-wrap>table{min-width:0;table-layout:fixed}" in html
    assert ".table-wrap>table{min-width:1280px}" not in html
    assert "@media(max-width:980px)" in html
    assert "${T[lang].hotel}／${T[lang].dataStatus}／${T[lang].view}" in html
    assert "while(statusCell.firstChild)actions.appendChild(statusCell.firstChild)" in html
    assert "actions.appendChild(button)" in html
    assert 'colspan="11"' in html
    assert "function bindCurrentComparisonControls()" in html
    assert "event.stopImmediatePropagation();renderTable()},{capture:true}" in html
    assert ".hotel-select-row:hover,.hotel-select-row:focus" in html
    assert "function activateComparisonRows()" in html
    assert "row.tabIndex=0" in html
    assert "row.setAttribute('role','button')" in html
    assert "event.target.closest('a,button,input,select,textarea,label,summary')" in html
    assert "event.key!=='Enter'&&event.key!==' '" in html
    assert "history.replaceState(null,'',`#${encodeURIComponent(hotelId)}`)" in html
    assert "membersOnlyLounge" in html
    assert "value==null" in html


def test_profile_and_map_summary_metrics_use_compact_layout():
    profiles_html = Path("public/hotels.html").read_text(encoding="utf-8")
    map_html = Path("public/map.html").read_text(encoding="utf-8")

    assert ".metric{display:flex;align-items:baseline;justify-content:center;gap:10px;padding:8px 14px" in profiles_html
    assert ".metric-value{margin:0;font:20px/1.15" in profiles_html
    assert 'id="compact-map-summary"' in map_html
    assert ".metric{display:flex;align-items:baseline;justify-content:center;gap:9px;padding:8px 10px}" in map_html
    assert ".metric-value{margin:0;font-size:20px;line-height:1.15}" in map_html


def test_hotel_profile_page_lists_upcoming_luxury_hotels_separately():
    html = Path("public/hotels.html").read_text(encoding="utf-8")
    upcoming = json.loads(Path("public/data/upcoming_hotels.json").read_text(encoding="utf-8"))
    by_id = {hotel["id"]: hotel for hotel in upcoming["hotels"]}

    assert set(by_id) >= {
        "four_seasons_taipei",
        "park_hyatt_taipei",
        "andaz_taipei",
        "ambassador_palace_hotel_taipei",
        "jw_marriott_taichung",
        "andaz_taichung",
        "kempinski_taichung",
        "hyatt_regency_kaohsiung",
    }
    assert all(hotel["opening_status"] == "upcoming" for hotel in by_id.values())
    assert by_id["four_seasons_taipei"]["planned_rooms"] == 260
    assert "2028" in by_id["four_seasons_taipei"]["expected_opening_zh"]
    assert by_id["kempinski_taichung"]["planned_rooms"] == 312
    assert "2027" in by_id["kempinski_taichung"]["expected_opening_zh"]
    ambassador_palace = by_id["ambassador_palace_hotel_taipei"]
    assert ambassador_palace["name_zh"] == "台北國賓皇宮酒店"
    assert ambassador_palace["district"] == "Zhongshan"
    assert ambassador_palace["planned_rooms"] == 106
    assert ambassador_palace["planned_room_size_min_sqm"] == 50
    assert ambassador_palace["planned_room_size_max_sqm"] == 240
    assert ambassador_palace["planned_restaurants_bars"] == 7
    assert ambassador_palace["planned_facilities"] == [
        "Garden Lounge",
        "SPA",
        "Fitness gym",
    ]
    assert "2028" in ambassador_palace["expected_opening_zh"]
    assert len(ambassador_palace["project_highlights_zh"]) == 4
    assert "Palace Hotel" in ambassador_palace["project_highlights_zh"][0]
    assert "106" in ambassador_palace["project_highlights_zh"][1]
    assert "50–240㎡" in ambassador_palace["project_highlights_zh"][1]
    assert ambassador_palace["source_urls"][0].startswith(
        "https://www.palacehoteltokyo.com/"
    )
    assert all(hotel["source_urls"] for hotel in by_id.values())
    assert "upcoming_hotels.json" in html
    assert "hotelDisplayName" in html
    assert "opening_status==='upcoming'" in html
    assert "upcomingOnly:'尚未開幕'" in html
    assert "noUpcomingRates" in html
    assert "PROJECT_HIGHLIGHT_LABELS" in html
    assert "project_highlights_${lang}" in html
    assert "id='projectHighlights'" in html
    assert "item.sourceName.includes('�')" in html


def test_hotel_comparison_shows_compact_opening_years_and_sticky_headers():
    html = Path("public/hotels.html").read_text(encoding="utf-8")

    assert "openingYearLabel" in html
    assert "openingYearTitle" in html
    assert 'class="hotel-opening-line"' in html
    assert ".hotel-opening-line{display:block;max-width:100%" in html
    assert "text-overflow:ellipsis;white-space:nowrap" in html
    assert "#hotelComparison{position:relative;isolation:isolate;overflow:visible}" in html
    assert "#hotelComparison>table{border-collapse:separate;border-spacing:0}" in html
    assert "#hotelComparison thead th{position:sticky;top:0;z-index:20" in html
    assert "#hotelComparison thead th:first-child{left:0;z-index:21}" in html
    assert "status=upcoming?`<span class=\"status upcoming\">${T[lang].upcoming}</span>`" in html


def test_missing_room_area_is_not_treated_as_under_45_sqm():
    overview = Path("public/index.html").read_text(encoding="utf-8")
    history = Path("public/history.html").read_text(encoding="utf-8")
    metrics = Path("public/assets/js/metrics.js").read_text(encoding="utf-8")

    assert "const band=roomSizeBand" in overview
    assert "band=roomSizeBand" in history
    assert "value === null || value === undefined || value === ''" in metrics
    assert "size === null || size <= 0" in metrics
    assert "hasSize=Number.isFinite(size)&&size>0" in overview
    assert "band(Number(r.room_size_sqm))" not in overview
    assert "band(Number(r.room_size_sqm))" not in history


def test_history_loads_summary_first_and_month_details_on_demand():
    html = Path("public/history.html").read_text(encoding="utf-8")

    assert "./data/history_summary.json" in html
    assert "./data/rates/index.json" in html
    assert "indexedHistoryFile(month,hotelId)" in html
    assert "loadJson(`./data/${path}`)" in html
    assert "./data/rates/${month}.json" not in html
    assert "./data/rates.json" not in html
    assert 'id="historyMonth"' in html
    assert 'id="loadMonth"' in html


def test_home_loads_lightweight_payloads_before_details():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert "./data/latest_summary.json" in html
    assert "./data/latest_heatmap.json" in html
    assert "loadJson('./data/latest_details.json')" in html
    assert "./data/latest.json" not in html
    assert 'id="loadLatestDetails"' in html
    assert "IntersectionObserver" in html


def test_hotel_detail_has_return_to_list_control():
    html = Path("public/hotels.html").read_text(encoding="utf-8")

    assert 'id="hotelComparison"' in html
    assert 'id="backToHotelList"' in html
    assert "backToList:'返回飯店一覽'" in html
    assert "scrollIntoView({behavior:'smooth',block:'start'})" in html


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
    assert "comparison_key" in html
    assert "條件完全一致" in html
    assert "renderSourceComparison();" in html


def test_home_shows_sanitized_adapter_health_summary():
    html = Path("public/index.html").read_text(encoding="utf-8")

    assert "./data/adapter_health.json" in html
    assert "collectionHealth" in html
    assert "本次完全成功" in html
    assert "冷卻中" in html


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


def test_hotel_map_covers_catalog_and_taipei_districts():
    catalog = json.loads(Path("public/data/hotels.json").read_text(encoding="utf-8"))["hotels"]
    location_data = json.loads(
        Path("public/data/hotel_locations.json").read_text(encoding="utf-8")
    )
    locations = location_data["locations"]

    assert len(catalog) == 67
    assert len(locations) == len(catalog)
    assert {row["hotel_id"] for row in locations} == {row["id"] for row in catalog}
    assert all(21.5 <= row["latitude"] <= 26.5 for row in locations)
    assert all(118 <= row["longitude"] <= 123 for row in locations)
    assert sum(row["city"] == "Taipei" for row in locations) == 37
    tracked = {row["id"] for row in catalog if row.get("enabled")}
    assert {row["hotel_id"] for row in locations if row["daily_tracked"]} == tracked
    assert all(row["district"] for row in locations if row["city"] == "Taipei")


def test_hotel_map_is_linked_and_localized_across_static_pages():
    map_html = Path("public/map.html").read_text(encoding="utf-8")

    for page in ("index.html", "history.html", "hotels.html"):
        html = Path("public", page).read_text(encoding="utf-8")
        assert 'href="./map.html"' in html
        assert 'data-i18n="mapPage"' in html

    assert "./assets/vendor/leaflet/leaflet.css" in map_html
    assert "./assets/vendor/leaflet/leaflet.js" in map_html
    assert "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" in map_html
    assert "./data/hotel_locations.json" in map_html
    assert "./data/history_summary.json" in map_html
    assert "taipeiView:'台北行政區地圖'" in map_html
    assert "taipeiView:'Taipei district map'" in map_html
    assert "taipeiView:'台北市行政区マップ'" in map_html
    assert "DISTRICT_COLORS" in map_html
    assert "hotel-lang" in map_html
    assert "hotel-currency" in map_html


def test_primary_pages_share_one_desktop_shell():
    shell = Path("public/assets/css/shell.css").read_text(encoding="utf-8")

    for page in ("index.html", "history.html", "hotels.html", "map.html"):
        html = Path("public", page).read_text(encoding="utf-8")
        assert './assets/css/shell.css' in html

    assert "html{overflow-y:scroll}" in shell
    assert "max-width:1240px!important" in shell
    assert "min-height:76px" in shell


def test_hotel_map_includes_upcoming_properties_without_rate_history():
    map_html = Path("public/map.html").read_text(encoding="utf-8")
    upcoming = json.loads(
        Path("public/data/upcoming_hotels.json").read_text(encoding="utf-8")
    )["hotels"]
    locations = json.loads(
        Path("public/data/upcoming_hotel_locations.json").read_text(encoding="utf-8")
    )["locations"]

    assert len(locations) == len(upcoming)
    assert {row["hotel_id"] for row in locations} == {row["id"] for row in upcoming}
    assert all(21.5 <= row["latitude"] <= 26.5 for row in locations)
    assert all(118 <= row["longitude"] <= 123 for row in locations)
    assert "./data/upcoming_hotels.json" in map_html
    assert "./data/upcoming_hotel_locations.json" in map_html
    assert "opening_status==='upcoming'" in map_html
    assert 'value="upcoming"' in map_html
    assert "upcoming-key" in map_html


def test_home_a4_briefing_export_is_print_only_and_localized():
    shell = Path("public/assets/css/shell.css").read_text(encoding="utf-8")
    charts = Path("public/assets/js/charts.js").read_text(encoding="utf-8")
    script = Path("public/assets/js/print-report.js").read_text(encoding="utf-8")

    assert 'import "./print-report.js"' in charts
    assert "@page{size:A4 landscape" in shell
    assert "body>*:not(#a4BriefingPrint)" in shell
    assert "匯出 A4 簡報 PDF" in script
    assert "Export A4 Briefing PDF" in script
    assert "A4 PDFを出力" in script
    assert "window.print()" in script
    assert ".slice(4)" in script
    assert 'document.querySelector(".export-controls")' in script
    assert "cloneSection('h2[data-i18n=\"trend\"]','.chart-panel')" in script
    assert "cloneSection('h2[data-i18n=\"heatmapTitle\"]','#priceHeatmap')" in script
    assert "requestAnimationFrame(()=>requestAnimationFrame(()=>window.print()))" in script
    assert 'button.dataset.printBound==="true"' in script
    assert 'button.dataset.printBound="true"' in script
    assert "button:not(.heatmap-cell)" in shell
    assert "#a4BriefingPrint .heatmap-cell{display:block!important" in shell
    assert "#a4BriefingPrint .price-heatmap-table{width:100%!important;min-width:0!important" in shell


def test_home_price_heatmap_is_interactive_and_mobile_scrollable():
    html = Path("public/index.html").read_text(encoding="utf-8")
    charts = Path("public/assets/js/charts.js").read_text(encoding="utf-8")

    assert 'id="priceHeatmap"' in html
    assert "renderPriceHeatmap" in html
    assert ".price-heatmap-scroll{overflow-x:auto}" in html
    assert "export function renderPriceHeatmap" in charts
    assert "data-tooltip" in charts
    assert "roomCountLabel" in charts
    assert "onSelect({ hotelId:" in charts
    assert "Math.round(120 * (1 - ratio))" in charts
    assert 'id="clearHeatmapSelection"' in html
    assert "function clearHeatmapSelection" in html
    assert "heatmapDrilldownActive=false" in html
    assert "heatmapDrilldownSnapshot={hotel:hotel.value,lead:lead.value}" in html
    assert "hotel.value=snapshot?.hotel??''" in html
    assert "function resetHeatmapDrilldown" in html
    assert "返回完整熱力圖" in html


def test_primary_pages_show_deployment_meta_and_simple_view_counter():
    analytics = json.loads(
        Path("public/data/analytics.json").read_text(encoding="utf-8")
    )
    script = Path("public/assets/js/site-meta.js").read_text(encoding="utf-8")

    for page in ("index.html", "history.html", "hotels.html", "map.html"):
        html = Path("public", page).read_text(encoding="utf-8")
        assert './assets/js/site-meta.js' in html

    assert analytics["provider"] == "librecounter"
    assert analytics["enabled"] is True
    assert analytics["site"] == "aphtkc.github.io"
    assert "https://librecounter.org/counter.svg" in script
    assert "image.referrerPolicy='unsafe-url'" in script
    assert "site-counter-label" in script
    assert "new MutationObserver" in script
    assert "if(!node.isConnected)footer.appendChild(node)" in script
    assert "localStorage" not in script
    assert "版本" in script and "Version" in script and "バージョン" in script


def test_home_loads_daily_market_digest_and_quality_warnings():
    home = Path("public/index.html").read_text(encoding="utf-8")
    hotels = Path("public/hotels.html").read_text(encoding="utf-8")

    assert "./data/digest.json" in home
    assert "marketInsights" in home
    assert "今日市場動態摘要" in home
    assert "healthData.data_quality?.hotels" in home
    assert "qualityBadge" in home
    assert "healthData.data_quality?.hotels" in hotels
    assert "qualityBadge" in hotels
    assert "資料核實中" in home and "資料核實中" in hotels


def test_hotel_comparison_shows_brand_positioning_and_loyalty_programs():
    html = Path("public/hotels.html").read_text(encoding="utf-8")
    data = json.loads(
        Path("public/data/hotel_affiliations.json").read_text(encoding="utf-8")
    )
    affiliations = {row["hotel_id"]: row for row in data["affiliations"]}

    assert len(affiliations) >= 20
    assert affiliations["kimpton_da_an"]["loyalty_program"] == "IHG One Rewards"
    assert "生活風格" in affiliations["kimpton_da_an"]["positioning_zh"]
    assert affiliations["hotel_proverbs_taipei"]["loyalty_program"] == "Marriott Bonvoy"
    assert "Design Hotels" in affiliations["hotel_proverbs_taipei"]["brand"]
    assert affiliations["hotel_resonance_taipei"]["loyalty_program"] == "Hilton Honors"
    assert affiliations["hilton_taipei_sinban"]["loyalty_program"] == "Hilton Honors"
    assert affiliations["hilton_taipei_sinban"]["brand"] == "Hilton Hotels & Resorts"
    assert affiliations["caesar_park_banqiao"]["loyalty_program"] == "凱撒 VIP"
    assert affiliations["caesar_park_banqiao"]["brand"] == "Caesar Park Hotels & Resorts"
    assert affiliations["fleur_de_chine"]["loyalty_program"] == "雲品假期常客回饋計畫"
    assert affiliations["fleur_de_chine"]["network"] == "LDC Hotels & Resorts"
    assert affiliations["silks_place_yilan"]["loyalty_program"] == "晶華會"
    assert affiliations["silks_place_yilan"]["network"] == "Silks Hotel Group"
    assert affiliations["crowne_plaza_tainan"]["loyalty_program"] == "IHG One Rewards"
    assert affiliations["crowne_plaza_tainan"]["network"] == "IHG Hotels & Resorts"
    assert affiliations["silks_place_tainan"]["loyalty_program"] == "點十成晶回饋計畫"
    assert affiliations["silks_place_tainan"]["network"] == "Silks Hotel Group"
    assert affiliations["the_lalu_sun_moon_lake"]["loyalty_program"] == "涵碧樓會員專屬"
    assert affiliations["the_lalu_sun_moon_lake"]["brand"] == "The Lalu"
    assert affiliations["hotel_royal_chihpen"]["brand"] == "Hotel Royal"
    assert affiliations["hotel_royal_chihpen"]["network"] == "Hotel Royal Group"
    assert affiliations["mu_jiaoxi_reserve"]["loyalty_program"] == "MU CLUB 寒沐會館"
    assert affiliations["mu_jiaoxi_reserve"]["network"] == "My Humble House Hospitality Group"
    assert affiliations["wyndham_sun_moon_lake"]["loyalty_program"] == "Wyndham Rewards"
    assert affiliations["wyndham_sun_moon_lake"]["network"] == "Wyndham Hotels & Resorts"
    assert affiliations["four_points_penghu"]["loyalty_program"] == "Marriott Bonvoy"
    assert affiliations["four_points_penghu"]["network"] == "Marriott International"
    assert affiliations["grand_cosmos_ruisui"]["loyalty_program"] == "COSMOS CLUB／天合尊寵卡"
    assert affiliations["grand_cosmos_ruisui"]["network"] == "Cosmos Hotels & Resorts"
    assert "Tapestry Collection" in affiliations["hotel_resonance_taipei"]["brand"]
    assert affiliations["doubletree_taipei_zhongshan"]["loyalty_program"] == "Hilton Honors"
    assert affiliations["mitsui_garden_taipei_zhongxiao"]["loyalty_program"] == "MGH Rewards Club"
    assert affiliations["the_landis_taipei"]["loyalty_program"] == "Landis Club"
    assert affiliations["taipei_garden_hotel"]["loyalty_program"] == "COSMOS CLUB"
    assert affiliations["silks_club_kaohsiung"]["brand"] == "The Luxury Collection"
    assert affiliations["silks_club_kaohsiung"]["loyalty_program"] == "Marriott Bonvoy"
    assert affiliations["tai_urban_resort"]["loyalty_program"] == "承億酒店會員俱樂部"
    assert all(row["source_url"].startswith("https://") for row in affiliations.values())

    assert "./data/hotel_affiliations.json" in html
    assert 'id="affiliation"' in html
    assert "brandLoyalty:'品牌定位／會員體系'" in html
    assert "affiliationCell" in html
    assert "loyalty-badge" in html
    assert "program==='__pending__'" in html
    assert "affiliation.source_url" in html
