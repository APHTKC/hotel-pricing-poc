# GitHub 免費部署操作

此模式不需要 Google Cloud、信用卡或本機 Python。

## 建立 repository

1. 登入 GitHub，右上角 `+` → `New repository`。
2. Repository name 填 `hotel-pricing-poc`。
3. 選 `Public`。不要勾選新增 README、`.gitignore` 或 license，以免和現有專案衝突。
4. 建立後上傳本專案檔案。

## 開啟 Pages

1. Repository → `Settings` → `Pages`。
2. `Build and deployment` 的 Source 選 `GitHub Actions`。
3. Repository → `Actions`。
4. 左側選 `Daily Capella Taipei rates`，按 `Run workflow`。
5. 首次執行通常需要數分鐘。完成後從 `Settings → Pages` 開啟網址。

## 權限檢查

若 workflow 無法把資料寫回 repository：

1. `Settings` → `Actions` → `General`。
2. 在 `Workflow permissions` 選 `Read and write permissions`。
3. 儲存後重新執行 workflow。

## 安全原則

- Repository 不放公司名稱、內部資料、email、密碼或金鑰。
- 房價紀錄與 dashboard 都是公開的。
- 不要上傳 `.env`、service-account JSON 或瀏覽器 cookie。
- 若未來改成 private repository，先確認 GitHub Pages 與 Actions 的方案限制。
