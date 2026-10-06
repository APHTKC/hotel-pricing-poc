# 台灣飯店房價查詢平台

以公開訂房資訊建立的高端飯店房價觀察平台。目前 Catalog 收錄 **67 家**飯店，
其中 **19 家**進入每日自動追蹤清單；每天查詢未來 `+1/+7/+14/+30/+60/+90`
天的一晚房價，並透過 GitHub Actions 更新 GitHub Pages。

公開網站：<https://aphtkc.github.io/hotel-pricing-poc/>

## 技術架構

- 前台：原生 HTML、CSS、JavaScript、SVG 圖表與 Leaflet／OpenStreetMap 地圖，提供繁中／英文／日文及 TWD／USD／JPY 切換。
- API：Python 3.12、FastAPI、Pydantic。
- 抓價：可插拔 Python adapter；依訂房引擎使用 HTTPX 或 Playwright。
- 儲存：正式歷史保存在 `data/rates.jsonl`；Google Sheets 模組保留為選用後端。
- 自動化：GitHub Actions 每日執行抓價、去重、靜態資料建置及 GitHub Pages 發布。
- 測試：pytest，涵蓋資料模型、adapter、指標、去重、靜態建置與前台結構。

## 公開資料結構

大型房價檔已改為首頁分層、歷史資料按月份與飯店載入：

```text
public/data/latest_summary.json          首頁 KPI 與市場摘要
public/data/latest_heatmap.json          首頁趨勢圖與熱力圖輕量資料
public/data/latest_details.json          最新完整明細，展開／捲動／匯出時才載入
public/data/history_summary.json         輕量預聚合歷史趨勢與每週市場摘要
public/data/rates/index.json             可用月份與飯店明細索引
public/data/rates/YYYY-MM/HOTEL_ID.json  選定月份與單一飯店後才載入
public/data/hotels.json                  67 家飯店 Catalog 與設施／房型快照
public/data/hotel_locations.json         67 家飯店的快取座標、城市、台北行政區及追蹤狀態
```

`index.html` 首屏只下載 summary 與 heatmap，完整 details 採按需載入。`history.html`
首次只下載 `history_summary.json` 與輕量索引，選定月份和單一飯店後才下載對應明細；
不再發布舊的 `latest.json`、單月巨型 JSON 或單一 `rates.json`。

### 靜態資料效能基準

以下為 2026-10-05 以 repository 內實際檔案量測的未壓縮大小，供後續資料成長時回歸比較：

| 頁面 | 拆分前主要資料 | 拆分後首屏資料 | 首屏請求 | 結果 |
|---|---:|---:|---:|---:|
| 即時總覽 | `latest.json` 3,880,910 bytes | 1,552,544 bytes | 6 個 JSON | 約減少 60.0% |
| 歷史分析 | `rates/2026-09.json` 56,005,329 bytes | 190,359 bytes | 4 個 JSON | 約減少 99.7% |

即時總覽首屏數字包含 `latest_summary`、`latest_heatmap`、匯率、飯店目錄、adapter
健康度及市場摘要；3,880,962-byte 的 `latest_details.json` 不在首屏下載。歷史首屏數字包含
`history_summary`、`rates/index`、匯率及飯店目錄；2026-09 的 18 個飯店分片總計
56,011,071 bytes，只在使用者選定月份及單一飯店後下載其中一個分片。

歷史分析頁同時提供「每週市場摘要」：以最近 7 個日曆日對比前 7 日，先計算各飯店
的中位房價，再以飯店等權方式彙整市場中位數與平均數。摘要也會列出共同飯店的主要
漲跌、各提前訂房天數的等權價格曲線，以及目前相對低價的 lead time；資料不足時不
推估，直接顯示無可用比較。

`map.html` 提供全台飯店分布及台北行政區兩種視圖，可依地區、每日追蹤狀態與是否已有
歷史房價篩選。座標保存在 `hotel_locations.json`，使用者開頁時不會逐家呼叫地理搜尋
服務；OpenStreetMap 僅提供底圖圖磚。

## OTA 同商品比價

官網與 OTA 不會只用「飯店＋入住日」比價。兩筆價格必須在下列條件完全一致，
才會計算 Rate Parity：

```text
hotel_id + check_in/check_out + occupancy + size_band
+ breakfast_included + cancellation_class + tax_inclusion
```

任一必要條件缺失或不一致，就標示為「無可比資料」，避免拿套房與標準房、含早餐與
不含早餐或含稅與未稅價格互相比較。Booking.com Demand API 只有在合作夥伴憑證與
飯店代碼均設定時才執行；未設定時會安全略過。

## Adapter 健康度與退避

每個 `adapter + hotel_id` 都會記錄嘗試次數、成功率、平均回應時間、403／429 次數、
每日統計與冷卻期限。連續失敗達門檻後採指數退避；403／429 立即進入較長冷卻，
避免每天重複消耗 GitHub Actions 額度。

- 可提交的健康彙整：`data/adapter_health.json`
- 錯誤快照：`data/diagnostics/YYYY-MM-DD.jsonl`

錯誤快照會遮蔽 token、API key 與 Authorization，只以 GitHub Actions artifact 保存
7 天，不提交到公開 repository。

## Demo 模式採 Fail-closed

`DEMO_MODE` 預設為 `false`。未明確設定時，系統不會讀取或寫入測試 Demo 房價。
只有刻意設定 `DEMO_MODE=true` 才會啟用示範 adapter；正式排程固定使用 `false`。

## 本機啟動

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

開啟 <http://localhost:8000>。執行每日官網與 OTA 工作：

```powershell
python -m scripts.run_daily_once
python -m scripts.run_ota_once
python -m scripts.deduplicate_rate_history
python -m scripts.build_static_data
```

若未設定 Google Sheets 憑證，資料寫入 `data/rates.jsonl`。完整部署步驟見
[docs/deployment.md](docs/deployment.md)，欄位定義見 [docs/schema.md](docs/schema.md)，
OTA 啟用條件見 [docs/ota-integration.md](docs/ota-integration.md)。

## API

- `GET /healthz`：健康檢查
- `GET /api/hotels`：飯店清單
- `GET /api/rates`：房價明細，可依飯店、房型級距及 lead time 篩選
- `GET /api/market-summary`：飯店等權市場指標
- `POST /jobs/daily-rates`：每日抓價入口，可用 `X-Job-Token` 保護

## 目錄

```text
app/                    FastAPI、資料模型與 API
config/                 67 家 Catalog、19 家每日追蹤與 OTA 對照設定
scrapers/               官網 adapter 與 OTA provider
jobs/                   官網／OTA 每日工作
services/               市場指標、去重、同商品比價、健康度、FX／CPI
storage/                JSONL 與 Google Sheets 儲存
scripts/                靜態資料建置及維護工具
public/                 GitHub Pages 前台與按月 JSON
docs/                   schema、部署與 OTA 文件
tests/                  自動測試
```
