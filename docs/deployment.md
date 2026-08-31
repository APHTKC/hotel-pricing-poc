# Cloud Run 與 Cloud Scheduler 部署

## 1. Google Sheets

1. 建立一份試算表，複製網址中的 Sheet ID。
2. 在 Google Cloud 建立 service account，授予可使用 Sheets API 的權限並建立 JSON 金鑰。
3. 將試算表分享給 service account 的 email（編輯者）。
4. 不要把 JSON 金鑰放進專案；部署時將完整 JSON 存在 Secret Manager。

## 2. 建置與部署 Cloud Run

以下以 `PROJECT_ID`、`REGION`、`SERVICE` 作為佔位值。先啟用 Cloud Run、Cloud Build、Artifact Registry、Secret Manager、Sheets API 與 Cloud Scheduler。

```bash
gcloud artifacts repositories create hotel-pricing --repository-format=docker --location=REGION
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT_ID/hotel-pricing/app:latest
gcloud run deploy SERVICE \
  --image REGION-docker.pkg.dev/PROJECT_ID/hotel-pricing/app:latest \
  --region REGION \
  --allow-unauthenticated \
  --set-env-vars DEMO_MODE=true,STORAGE_BACKEND=google_sheets,GOOGLE_SHEET_ID=YOUR_SHEET_ID \
  --set-secrets GOOGLE_SERVICE_ACCOUNT_JSON=hotel-sheets-service-account:latest,JOB_TOKEN=hotel-job-token:latest \
  --memory 2Gi --cpu 1 --timeout 900 --concurrency 1
```

部署前先在 Secret Manager 建立 `hotel-sheets-service-account`（內容為完整 service-account JSON）與 `hotel-job-token`。Cloud Run 執行身分需有讀取這兩個 secret 的權限。

第一輪建議保留 `DEMO_MODE=true`，確認試算表和 dashboard 正常後，再逐一完成並驗證 adapter；不要直接將所有飯店切成 live。

> 正式環境較建議讓 Cloud Run 維持私有，dashboard 前方加 Identity-Aware Proxy 或改成兩個 service（公開 dashboard、私有 job）。此 MVP 的 `X-Job-Token` 是簡化措施。

## 3. Cloud Scheduler

建立每日台北時間 06:00 的 HTTP 工作，呼叫 Cloud Run：

```bash
gcloud scheduler jobs create http hotel-daily-rates \
  --location REGION \
  --schedule "0 6 * * *" \
  --time-zone "Asia/Taipei" \
  --uri "https://YOUR_CLOUD_RUN_URL/jobs/daily-rates" \
  --http-method POST \
  --headers "X-Job-Token=YOUR_JOB_TOKEN"
```

若 Cloud Run 設為私有，請改用 Scheduler 的 OIDC service account 驗證，並授予該帳號 Cloud Run Invoker；這比在 header 放 token 更適合正式環境。

## 4. 上線檢查

- `/healthz` 回傳 `status: ok`
- `rates` 工作表出現 9 × 6 × 3 = 162 筆 demo rows
- dashboard 顯示 9 家飯店，可依大小與 lead time 篩選
- 關閉 demo 前，各 adapter 都必須針對日期、稅費、取消政策與房型名稱做人工對照測試
- Cloud Scheduler 的時區為 `Asia/Taipei`，且失敗有告警

## 已知限制

- Google Sheets 適合 MVP，但大量歷史資料與多人查詢後應移至 Cloud SQL / BigQuery。
- booking engine 可能有 bot protection、地區價格、cookie、會員價與版面更新；adapter 必須保存來源 URL 並監控失敗率。
- CPI 為月資料、FX 為日資料，正式 provider 應保存資料日期與來源版本，避免把缺值誤當 1。
