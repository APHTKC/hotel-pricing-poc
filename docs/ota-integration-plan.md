# OTA 房價來源整合計畫

本系統不規避 CAPTCHA、登入、付費牆或反機器人機制。官網自動取價受阻時，優先改用正式 API、聯盟 feed 或取得授權的資料供應商，避免浪費 GitHub Actions 額度並降低資料中斷風險。

## 優先順序

| 平台 | 正式路徑 | 狀態 | 用途 |
|---|---|---|---|
| Booking.com | [Demand API](https://developers.booking.com/demand/docs/accommodations/about-accommodation) | 需合作夥伴資格與憑證 | 房型、即時供應、價格、餐食與取消政策 |
| Agoda | [Affiliate API](https://partners.agoda.com/DeveloperPortal/APIDoc/SearchJsonAPIChanges) | 需聯盟夥伴資格與憑證 | 飯店供應與公開價格 |
| Hotels.com / Expedia Group | [Rapid Lodging Shopping API](https://developers.expediagroup.com/rapid/lodging/shopping/about-shopping-api) | 需合作夥伴審核與憑證 | 即時房型、含稅價格、退款條件與費用明細 |
| Rakuten Travel | [Vacant Hotel Search API](https://webservice.rakuten.co.jp/documentation) | 需 App ID 核准 | 即時空房與日本市場價格；先確認台灣飯店覆蓋率 |
| Yahoo! Travel | 商務合作或授權 feed | 待確認 | 無適合本用途的公開正式價格 API 時不自動抓取 |
| 一休.com | 商務合作或授權 feed | 待確認 | 無適合本用途的公開正式價格 API 時不自動抓取 |

## 共通資料規格

每筆價格除了既有飯店、房型、日期、早餐、取消政策、稅費與總價外，必須保存：

- `source_platform`：`official`、`booking_com`、`agoda`、`expedia_group`、`rakuten_travel` 等。
- `source_method`：`public_booking_page`、`partner_api` 或 `licensed_feed`。
- `source_property_id`：平台內部的飯店代碼，用於穩定對應同一家飯店。
- `source_url`：可回查的飯店或價格頁面。

比較時只合併相同入住日、晚數、入住人數、房型級距、早餐與取消條件。會員價、行動裝置價與不可取消價需分開標示，不直接當成一般公開彈性價。

## 執行原則

1. 先申請一個正式來源並以一間已知官網受阻的飯店做低成本驗證。
2. 一次只測一個平台與一間飯店；失敗即記錄原因並停止，不重複耗用 Actions。
3. 驗證稅費、幣別、房型對應與取消條件後，才加入每日排程。
4. Dashboard 增加來源平台篩選與「官網／OTA 價差」比較，但不把不同條件的最低價混為同一指標。
