# Luxury Hotel Pricing Intelligence System

第一版可執行骨架，追蹤台北高端飯店未來 `+1/+7/+14/+30/+60/+90` 天的官網房價。目前提供不需信用卡與本機 Python 的 **GitHub Actions + GitHub Pages** 模式，先正式追蹤 Capella Taipei。

## GitHub 免費模式（建議）

1. 建立一個公開 GitHub repository，例如 `hotel-pricing-poc`。
2. 將本專案所有檔案上傳至 repository；不要上傳 `.env` 或任何帳密。
3. 在 repository 的 **Settings → Pages → Build and deployment**，Source 選 **GitHub Actions**。
4. 到 **Actions → Daily Capella Taipei rates → Run workflow** 執行第一次抓價。
5. 成功後，GitHub Pages 網址會出現在 workflow 結果與 repository 的 Pages 設定中。

排程每天台北時間約 06:00 執行。GitHub 的排程可能因平台負載延遲數分鐘。每次完成會把公開房價歷史寫入 `data/rates.jsonl`，dashboard 使用 `public/data/rates.json`。

Capella Taipei 已有第一個 SynXis live adapter，其餘飯店仍是明確標示的 stub。預設 `DEMO_MODE=true` 會產生可重現的示範資料，讓 dashboard、API、Google Sheets 寫入與排程流程可先完整驗證。

## 本機啟動

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

開啟 <http://localhost:8000>。執行一次每日工作：

```powershell
python -m jobs.daily_rates
```

### 只測試 Capella Taipei 正式資料

將 `.env` 設為 `DEMO_MODE=false` 及 `HOTELS_CONFIG_PATH=config/hotels.capella-only.yaml`，再執行每日工作。這會只查 Capella Taipei 的六個入住日，正式結果標記為 `status=live`。SynXis 搜尋結果只顯示含稅總價；未稅價、服務費與稅額不會臆測，會保留空值。

如未設定 Google Sheets 憑證，資料會寫入 `data/rates.jsonl`，dashboard 仍可使用。完整部署步驟見 [docs/deployment.md](docs/deployment.md)。

## API

- `GET /healthz`：健康檢查
- `GET /api/hotels`：飯店清單
- `GET /api/rates`：明細，可用 `hotel_id`、`size_band`、`lead_days` 篩選
- `GET /api/market-summary`：市場中位 ADR 與比較指標
- `POST /jobs/daily-rates`：Cloud Scheduler 觸發入口（可用 `X-Job-Token` 保護）

## 專案結構

```text
app/                  FastAPI、API、dashboard
config/hotels.yaml    台北 9 家飯店設定
scrapers/             adapter 介面、stub、示範 adapter
jobs/                 每日抓價工作
storage/              Google Sheets 與本機 JSONL 儲存
services/             FX / CPI 介面
docs/                  schema 與部署說明
tests/                 基本測試
```
