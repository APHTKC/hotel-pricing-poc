# 台灣飯店房價查詢平台：技術與架構摘要報告

> 審查基準：Git commit `2221e95`（2026-09-23）  
> 專案：`APHTKC/hotel-pricing-poc`  
> 用途：提供 Gemini 進行架構審查、資料邏輯檢查與後續優化建議。

## 執行摘要

目前正式公開服務不是典型的「前端呼叫即時後端 API」，而是以下混合架構：

```text
官方訂房頁／訂房引擎／授權 OTA API
                  ↓
       Python + Playwright/httpx adapters
                  ↓
      data/rates.jsonl（append-only 原始歷史）
                  ↓
       Python build scripts（清理、裁切欄位）
                  ↓
 public/data/*.json → 原生 HTML/CSS/JS → GitHub Pages
```

FastAPI、Google Sheets、Cloud Run 與 Cloud Scheduler 仍保留在程式中，但現行公開網站的主路徑是 **GitHub Actions + JSONL + GitHub Pages**。前端沒有 React、Vue、D3.js 或 Chart.js；圖表由原生 JavaScript 直接產生 SVG。

截至本次盤點：

- 飯店 Catalog：67 家，其中 21 家啟用每日資料管線；其餘候選來源依健康狀態與可行性檢查結果暫緩。
- 原始歷史資料：56,216 筆、18 家已有歷史房價；新增的第 19 至 21 家會由下一次每日工作開始累積。
- 最新完整明細：2,735 筆，`public/data/latest_details.json` 約 3.56 MB，首頁採按需載入。
- 飯店基本資料：67 家皆有已核實 profile 與獨立 `room_snapshot`；來源不足的欄位維持待核實。
- 籌備中飯店：8 家，獨立存放於 `upcoming_hotels.json`，不參與 ADR 計算。
- OTA：Booking.com Demand API client 已完成，但目前沒有可發布的 OTA 房價；現有歷史資料皆標記為 `official`。

---

## 1. 專案整體架構與技術棧

### 1.1 前端

| 項目 | 現況 |
|---|---|
| 語言 | 原生 HTML、CSS、JavaScript |
| UI 架構 | 三個獨立靜態頁面，各自包含大量 inline CSS 與 inline JS |
| 圖表 | 原生 JavaScript 產生 inline SVG；沒有 D3.js／Chart.js |
| 部署 | GitHub Pages |
| 多語系 | 繁中／英文／日文辭典直接硬編碼於每個 HTML |
| 幣別 | TWD／USD／JPY；前端以 `fx.json` 進行顯示換算 |
| 匯出 | JSON、UTF-8 CSV（按鈕稱 Excel）、瀏覽器列印（作為 PDF） |

主要頁面：

- `public/index.html`：即時總覽、篩選、未來入住日趨勢、同期間飯店比較、房型明細、官網／OTA 價差區塊。
- `public/history.html`：歷史平均／中位數、查價日趨勢、booking curve、匯出與列印。
- `public/hotels.html`：飯店基本資料、房型面積、餐飲、設施、行政／貴賓廳、籌備中飯店。

### 1.2 Python 應用與後端

| 套件／技術 | 用途 |
|---|---|
| Python 3.12 | GitHub Actions 執行環境 |
| FastAPI 0.115 | 可選的 API 與 job HTTP 入口 |
| Uvicorn | FastAPI ASGI server |
| Pydantic 2 | `Hotel`、`RateObservation`、`JobResult` schema 與 computed fields |
| Playwright 1.52 | JavaScript 訂房頁、動態房型與價格擷取 |
| httpx | Booking.com API、Google Finance、HTTP 資料來源 |
| PyYAML | 飯店與 OTA mapping 設定 |
| gspread + google-auth | 可選的 Google Sheets 儲存後端 |
| pytest | adapters、schema、jobs、靜態資料與 dashboard 行為測試 |

FastAPI 提供：

- `GET /healthz`
- `GET /api/hotels`
- `GET /api/rates`
- `GET /api/market-summary`
- `POST /jobs/daily-rates`

但 GitHub Pages 不會呼叫這些 API。FastAPI 是另一套可選部署路徑，與正式靜態網站存在部分語意差異。

### 1.3 主要目錄分工

```text
.github/workflows/       每日排程、單飯店 probe、GitHub Pages 發布
app/                     FastAPI、Pydantic models、settings、舊版 template
config/                  每日飯店、候選飯店、單飯店測試、OTA mapping
data/                    append-only JSONL 原始房價及本機 probe 結果
docs/                    schema、部署、OTA 計畫與本報告
jobs/                    官網每日抓價與 OTA 抓價協調流程
public/                  GitHub Pages 前端與已建置 JSON
scrapers/adapters/       各訂房引擎／品牌 adapter
scrapers/ota/            OTA provider 介面與 Booking.com Demand API client
scripts/                 執行 job、probe、建置靜態資料與更新 FX
services/                FX、CPI provider 介面
storage/                 JSONL／Google Sheets 儲存 adapter
tests/                   28 個 pytest 測試檔
```

### 1.4 部署與執行模式

**現行正式模式**

- GitHub Actions 每日台北時間名義上 06:00 排程。
- Ubuntu runner 安裝 Python、套件與 Chromium。
- 抓官網房價、嘗試 Booking.com partner API、建置 JSON、commit 新資料、部署 GitHub Pages。

**保留但非目前主要模式**

- Docker image 使用 Microsoft Playwright Python base image。
- Cloud Run 執行 FastAPI。
- Cloud Scheduler 呼叫 `/jobs/daily-rates`。
- Google Sheets 可作為 `RateStore`。

---

## 2. 資料處理與正規化邏輯

### 2.1 房價事實表

`RateObservation` 的一列代表：

> 某次查詢 × 某飯店 × 某入住日 × 某房型 × 某 rate plan × 某來源平台

主要欄位：

- 查詢：`observation_id`、`queried_at`、`status`
- 入住：`check_in`、`check_out`、`lead_days`、`nights`、`adults`
- 飯店：`hotel_id`、`hotel_name`、`city`、`district`
- 房型：`room_type_code`、`room_type_name`、`room_size_sqm`
- 方案：`rate_plan_code`、`rate_plan_name`、`breakfast_included`、`cancellation_policy`
- 價格：`price_before_tax`、`service_charge`、`tax`、`total_price`、`currency`
- 來源：`source_platform`、`source_method`、`source_property_id`、`source_url`
- 分析：`fx_rate_to_twd`、`total_twd`、`price_per_sqm`、CPI 欄位

### 2.2 房型面積與級距

房型面積主要由各 adapter 從訂房頁文字或 DOM 解析；無法取得時保留 `null`。飯店資料頁另可用人工核實的 `room_snapshot` 補充官網／OTA 房型資料，不要求房價爬蟲成功。

現行級距：

```text
room_size_sqm < 45       → <45㎡
45 <= room_size_sqm < 60 → 45–59㎡
60 <= room_size_sqm < 80 → 60–79㎡
room_size_sqm >= 80      → 80㎡+
null / 0 / 非數字         → unknown
```

每㎡價格：

```text
price_per_sqm = total_twd / room_size_sqm
```

只有 `room_size_sqm` 與 `total_twd` 都有效時才計算。

### 2.3 稅費與早餐

- `breakfast_included` 是三態：`true`、`false`、`null`（來源沒有清楚說明）。
- 原則上總價使用訂房完成前可確認的一晚、兩位成人公開價格。
- 若來源只顯示含稅總價，部分 adapter 將拆分欄位保留 `null`；部分 adapter 則依頁面聲明的固定比例反推。
- SynXis／Gobooking 的部分飯店使用 `total = base × 1.155`，即 10% 服務費，再對 base + service 計 5% 稅。
- Mandarin Oriental adapter 使用 base + 10% service + base 的 5.5% 稅，總乘數同為 1.155。
- Okura adapter 使用 base + 10% service + base 的 5% 稅，總乘數為 1.15。
- Capella 等無法可靠拆分的來源只保存含稅總價，不臆測拆分。

此處不是單一中央 tax engine，而是 adapter 各自處理，因此必須逐飯店驗證。

### 2.4 幣別、FX 與 CPI

```text
若 currency == TWD：total_twd = total_price
否則：total_twd = total_price × fx_rate_to_twd

cpi_adjusted_twd = total_twd × cpi_base_index / cpi_index
```

現行 dashboard 匯率由 GitHub Actions 抓 Google Finance，保存為「1 TWD 可換多少外幣」，前端顯示時用：

```text
display_price = TWD price × fx[currency]
```

CPI 只有抽象介面與 `NullCPIProvider`，尚未接入台灣主計總處或其他正式 CPI 資料源；公開頁面目前沒有實際 CPI-adjusted 分析。

### 2.5 官網與 OTA 正規化

官網與 OTA 共用 `RateObservation`，以以下欄位區分：

- 官網：`source_platform=official`、`source_method=public_booking_page`
- Booking.com：`source_platform=booking_com`、`source_method=partner_api`
- `source_property_id` 保存 OTA 內部飯店代碼

Booking.com parser 會讀取：

- room ID／名稱／面積
- product ID
- meal plan
- cancellation policy
- base price／total price
- 幣別與 deep link

**目前比價實作：**

1. `services/rate_parity.py` 先建立嚴格 Canonical Comparison Key。
2. Key 同時包含 `hotel_id`、`check_in`、`check_out`、`rooms/adults/children`、`size_band`、`breakfast_included`、`cancellation_class` 與 `tax_inclusion`。
3. 任一必要條件缺失或無效時採 fail-closed，標記 `insufficient_product_metadata`，不產生比價。
4. 靜態建置將相同 Key 的官網與各 OTA 價格分別取中位數；首頁只以已產出的 `comparison_key` 分組，並選出最低 OTA 中位數。
5. 價差：

```text
gap = (lowest_ota_median - official_median) / official_median
```

入住晚數由完全一致的 `check_in + check_out` 保證。房型目前採面積級距匹配；尚未取得可靠正規化房型 ID 時，不跨級距比較。價格方案名稱本身不作 Key，避免各來源命名不同，但早餐、取消與稅別條件必須一致。

### 2.6 Lead time

預設：`1, 7, 14, 30, 60, 90` 天。

每個 observation 同時保存：

- `queried_at`
- `check_in`
- `check_out`
- `lead_days`
- `nights=1`
- `adults=2`

每日 job 對每家啟用飯店逐一查六個日期。連續兩個日期無資料或失敗後會跳過該飯店剩餘日期，避免浪費 Actions 額度。

### 2.7 靜態發布前處理

`scripts/build_static_data.py` 會：

1. 逐行讀取 `data/rates.jsonl`。
2. 只保留 `3,000 <= total_twd <= 2,000,000` 的資料。
3. 裁成 dashboard 所需欄位。
4. 依 `queried_at` 新到舊排序。
5. 產出 `latest_summary.json`、`latest_heatmap.json` 與按需載入的 `latest_details.json`。
6. 產出 `history_summary.json`，並將歷史明細拆成 `rates/YYYY-MM/<hotel_id>.json`；`rates/index.json` 保存可用月份與飯店索引。

公開明細保留同商品比價所需欄位；首屏摘要只保存 KPI、趨勢與熱力圖需要的輕量資料。

### 2.8 飯店、房型與籌備中飯店主檔

目前已有三種獨立資料：

- `hotels.json`：67 家營運中／候選飯店與自動化狀態。
- `hotel_profiles.json`：67 家已核實飯店的客房總數、餐飲、設施、lounge、服務費、房型快照與來源；未取得可靠證據者維持待核實。
- `upcoming_hotels.json`：8 家籌備中飯店、預計開幕文字、規劃房數與來源。

這個方向正確：抓不到房價不等於抓不到房型。被擋住的飯店仍可由官網客房介紹、官方 factsheet，必要時再由可信 OTA 靜態頁面補充房型名稱與面積，並保存 `source_type`、`source_url`、`observed_at`。房型主檔不應依賴每日房價成功與否。

籌備中飯店也獨立維護，不產生假房價、不進入 ADR 統計。現有 8 家包含台北四季、台北柏悅、台北安達仕、台中 JW 萬豪、台中安達仕、台中凱賓斯基、高雄凱悅與國賓皇宮酒店；部分規劃房數及開幕日期仍為待公布。

---

## 3. 爬蟲與自動化流程

### 3.1 現有資料來源

**正式／已實作的官網來源類型**

- SynXis booking engine
- FastBooking／D-EDGE 公開報價元件
- IHG booking pages
- Shangri-La booking flow
- SiteMinder／DirectOnline
- Gobooking
- Tripla
- 品牌／飯店專用流程：Capella、Mandarin Oriental、Okura、HOSHINOYA、Grand Hi-Lai、Grand Mayfull、Royal-Nikko 等

**OTA**

- Booking.com Demand API：程式已實作，需合作夥伴 API key、affiliate ID 與逐飯店 property mapping。
- Agoda、Expedia／Hotels.com、Rakuten 等目前只有計畫或停用設定，沒有可執行 provider。
- 系統明確不應繞過 CAPTCHA、登入、付費牆或反機器人機制。

**其他來源**

- Google Finance：TWD／USD／JPY 顯示匯率。
- 飯店官網／官方 factsheet：飯店設施與房型靜態主檔。
- 政府／開發商／品牌公告：部分籌備中飯店資訊。
- 政府 CPI：尚未串接。

### 3.2 每日 GitHub Actions

`.github/workflows/daily-capella.yml` 雖沿用早期檔名，workflow 名稱已是 `Daily Taiwan hotel rates`。流程：

```text
schedule 22:00 UTC
→ checkout
→ git pull --rebase
→ Python 3.12 + pip cache
→ 安裝 requirements + Chromium
→ 更新 Google Finance FX
→ run_daily_once（21 家啟用飯店 × 六個 lead dates）
→ run_ota_once（有憑證及 mapping 才執行）
→ build_static_data + build_hotel_catalog
→ commit/pull --rebase/push 資料
→ upload public/
→ deploy-pages
```

另有多個 `workflow_dispatch` probe workflow，用於單飯店、單 adapter 的低成本驗證；不會每天全部執行。

### 3.3 失敗控制

- 官網 job：同飯店連續 2 次空結果／錯誤即跳過剩餘日期。
- Booking.com：連續 2 次空結果或一般失敗跳過該飯店。
- OTA HTTP 400／404／422：跳過該 property 剩餘日期。
- OTA HTTP 401／403／429：停止整個 provider run，避免無效憑證或限流造成重複請求。
- 各飯店 scraper 在 `finally` 關閉 browser/client。

### 3.4 儲存

- 正式 GitHub 模式：`LocalJsonlStore` 逐行 append 至 `data/rates.jsonl`。
- Google Sheets 模式：確保 `rates` 工作表與 schema 欄位後，使用 `append_rows`；讀取時載入整張表。
- 沒有資料庫索引、唯一鍵 constraint、upsert 或 partition。

---

## 4. 核心演算法與計算指標

### 4.1 飯店內指標

對目前篩選後的某家飯店 `h`：

```text
HotelAverage(h) = mean(該飯店全部有效 total_twd)
HotelMedian(h)  = median(該飯店全部有效 total_twd)
HotelSqmMedian(h) = median(該飯店全部有效 price_per_sqm)
CoreMedian(h) = median(該飯店 45 <= room_size_sqm < 60 的 total_twd)
```

同一房型若同時有多個 rate plan、入住日或 lead time，每筆都會進入飯店內統計，除非使用者先篩選。

### 4.2 市場指標：飯店等權

現行 dashboard 與 FastAPI 已改為先算各飯店，再進行市場彙整，避免房型或方案較多的飯店權重過高：

```text
市場平均房價 = mean(每家飯店的 HotelAverage)
市場中位 ADR = median(每家飯店的 HotelMedian)
市場每㎡中位價 = median(每家飯店的 HotelSqmMedian)
45–59㎡核心客房中位價 = median(每家飯店的 CoreMedian)
```

這是「飯店等權」而非「所有 observation 的整體中位數」。

### 4.3 趨勢與 booking curve

- 即時未來入住日圖：每家飯店、每個 `check_in` 取房價中位數。
- 歷史圖：可切平均或中位數；以查價日分組。
- Booking curve：每家飯店、每個 `lead_days` 取平均或中位數。
- 圖例可切換個別飯店線條；線條與點支援 hover tooltip。

### 4.4 極端值處理

目前只有發布前的絕對範圍 gate：

```text
3,000 TWD <= total_twd <= 2,000,000 TWD
```

沒有：

- 飯店內 IQR／MAD outlier detection
- winsorization
- 同房型日增幅警示
- 幣別錯標以外的 anomaly detection
- 觀測品質分數

因此極高價大型套房仍是有效資料，會影響「平均房價」；UI 以核心房型中位價、每㎡價格與套房占比說明降低誤讀，但未在演算法中排除。

---

## 5. 待解決問題與開發瓶頸

### P0：資料正確性／統計語意

1. **台北時區的 lead date 可能差一天。**  
   workflow 在 22:00 UTC（台北次日 06:00）執行，但 job 使用 `datetime.now(UTC).date()` 當 today。台北 06:00 的 `+1` 實際可能成為台北當日入住。應以飯店 timezone 或 `Asia/Taipei` 計算查價基準日。

2. **Demo 資料可能被錯誤發布。**  
   原始 schema 有 `status=demo/live`，但 `build_static_data.py` 不篩除 demo，且發布時移除 `status`。若 demo 曾寫入正式 JSONL，只要價格落在 3,000–2,000,000 就會混入公開統計且無法辨識。建議 build fail-closed：只發布 `status=live`。

3. **IHG 稅費邏輯疑似不一致。**  
   `TOTAL_MULTIPLIER=1.155` 被宣告但未使用；目前 `_collect` 只加 10% service、`tax=0`。需要逐品牌／飯店核對頁面顯示究竟已含稅，不能用同一規則套 Regent、Kimpton 與 InterContinental。

4. **OTA 正式資料覆蓋仍不足。**
   Canonical Comparison Key 已強制匹配飯店、入住／退房日、人數、面積級距、早餐、取消及含稅條件；條件缺失時不比較。目前瓶頸是尚未取得足夠的正式 OTA partner 資料，而不是匹配邏輯。

5. **「最新批次」是 30 分鐘時間窗，不是真正 run ID。**  
   相鄰 workflow 可能被合併，超過 30 分鐘的同一輪可能被截斷。應新增 `scrape_run_id`／`batch_id` 與 run metadata。

### P1：主檔與資料治理

1. **飯店設定仍有多份，但 API 預設來源已修正。**
   FastAPI 與每日 job 現在預設讀取 `config/hotels.daily.yaml`；公開 catalog 則合併 daily + candidates。早期 `config/hotels.yaml` 僅保留相容性，不再是執行預設值。後續仍可把 daily 與 candidates 改為單一主檔加狀態欄位。

2. **抓不到房價的飯店，房型主檔覆蓋不足。**  
   目前 67 家飯店皆已有 profile 與房型快照；後續仍應將房型主檔正式獨立於 rate observation：
   - 優先官方客房頁／官方 factsheet。
   - 官方缺失時才用 OTA 靜態介紹頁。
   - 每個房型保存中英日名稱、精確／最小／最大面積、source type、URL、核實日期、備註。
   - 不因自動房價被擋就把房型留白。

3. **籌備中飯店資料仍偏薄。**  
   現有 8 家已有名稱、地點、預計開幕文字、規劃房數及 URL。後續宜增加：品牌、業主／開發商、專案位置、公告日期、預計開幕年月（結構化）、日期可信度、已公布餐飲／設施及狀態歷程，並持續與 ADR fact table 隔離。

4. **來源證據粒度不足。**  
   profile 的 `source_urls` 是整家飯店層級，無法知道哪個 URL 支持哪個欄位。應改成 field-level provenance，例如 `evidence[{field, value, source_url, published_at, verified_at}]`。

5. **房型翻譯為前端 heuristic。**  
   英／日文目前靠中文字串替換及移除漢字，並非可靠的多語主檔。應在 room type dimension 保存 `name_zh`、`name_en`、`name_ja`，來源不明時明示 fallback。

### P1：效能與擴充性

1. **歷史 JSON 分片已完成，最新明細仍會成長。**  
   history 首屏已改用預聚合摘要，月份明細按飯店下載；首頁的 `latest_details.json` 亦採懶載入。後續仍需監控單一飯店月分片與最新完整明細的成長速度。

2. **前端多次 O(H × D × N) 掃描。**  
   各飯店、日期、lead time 都重新 `rows.filter`。資料量增加後，互動與重繪會明顯變慢。

3. **Google Sheets 不適合長期 fact table。**  
   `read_all()` 讀整張表，append 無去重；當資料達數十萬列時，速度、quota 與維護性都會惡化。

目前已完成依年月／飯店 partition 及預聚合 summary。中期可改 SQLite／DuckDB／Parquet 或 PostgreSQL／BigQuery，再由 API 或 build job 輸出小型前端資料。

### P2：工程品質與產品完整度

1. 三個頁面的 CSS、i18n、篩選與圖表函式大量重複，應拆成共用 JS/CSS modules。
2. `observation_id` 包含查詢時間，JSONL append 沒有唯一 constraint；重跑同日期會留下新 observation，沒有 idempotency。
3. 公開 JSON 移除取消條件、稅、服務費與 status，限制稽核與 OTA 公平比較。
4. 主頁明細只顯示前 300 筆，沒有分頁或虛擬列表。
5. 「Excel」實際輸出 CSV，不是 `.xlsx`；「PDF」是 `window.print()`，不是固定版型 PDF。
6. CPI provider 未完成，UI 尚不能真正顯示 CPI-adjusted 價格。
7. Agoda、Expedia／Hotels.com、Rakuten、Yahoo Travel、Ikyu 尚未實作正式 provider。
8. GitHub daily workflow 發布前沒有固定執行完整 pytest；單一 probe workflow 才偶爾執行測試。
9. FastAPI summary 讀取 storage 全歷史資料；靜態首頁使用 latest batch，兩者雖公式接近但資料時間範圍不同。
10. 本次環境沒有可用 Python executable，因此未重新執行 pytest；repo 內有 28 個測試檔，最近一次專案驗證紀錄為 98 tests passed。

### Hardcode 盤點

**合理但需集中管理的硬編碼**

- 飯店／chain／property ID
- 固定 booking URL 與 DOM selector
- 飯店特定 tax／service 規則
- 六個 lead days
- 房型級距門檻
- 飯店中文名稱、城市／行政區排序

**風險較高的硬編碼**

- Gobooking plan code 與 plan 名稱
- IHG／SynXis 稅費假設
- 前端中文房型名稱替換表
- 3,000–2,000,000 TWD 的全市場固定 gate
- latest batch 的 30 分鐘窗
- 籌備中開幕文字而非結構化 date/status

**測試／示範資料**

- `DemoScraper` 固定產生 45㎡、55㎡、82㎡三種房型及可重現價格，用於 pipeline/UI 測試。
- `.env.example` 預設 `DEMO_MODE=true`。
- 現行公開資料沒有 OTA rows；raw JSONL 搜尋到的正式資料為 `status=live`，但建置程式本身沒有防止 demo 混入的保護。

---

## 建議的目標資料模型

```text
hotel_dimension
  └─ hotel_id, multilingual names, geography, brand, operating status

room_type_dimension
  └─ hotel_id, stable room_type_id, multilingual names, size min/max,
     source type/url, verified_at

hotel_profile_snapshot
  └─ inventory, dining, facilities, lounge, field-level evidence

rate_observation
  └─ run_id, hotel_id, room_type_id, stay dates, lead days, terms,
     tax components, total, currency, source platform

scrape_run
  └─ run_id, started/finished time, timezone basis, adapter version,
     successes, failures, GitHub run URL

upcoming_hotel_project
  └─ project_id, brand/developer, location, structured target opening,
     confidence/status history, planned inventory, evidence

fx_observation / cpi_observation
  └─ value, effective date, source, retrieved_at
```

此模型可讓「被擋住但官網仍有客房介紹的飯店」完整出現在飯店比較頁，也能讓籌備中飯店持續補充資料，而不污染每日房價事實表。

## 建議優先執行順序

1. 修正台北時區 lead date、只發布 `status=live`、核實 IHG 稅費。
2. 加入 `scrape_run_id`、真正的 latest run 與去重策略。
3. 把房型主檔從房價 observation 解耦，優先補台北高價飯店與目前被擋飯店。
4. 擴充籌備中飯店 schema 及 field-level evidence。
5. 嚴格定義 OTA comparability key，再開啟 UI 比價。
6. 持續監控已完成的歷史 JSON partition／預聚合，設定分片大小回歸門檻。
7. 抽離共用前端 modules，再導入真 `.xlsx` 與固定版 PDF 匯出。
8. 完成官方 CPI provider 與 CPI-adjusted 指標。

