# 資料 Schema v1.0

一列代表「某次查詢、某飯店、某入住日、某房型、某 rate plan」的報價。唯一鍵建議使用 `observation_id`，正式 adapter 應避免同一輪重複寫入。

| 欄位群組 | 主要欄位 |
|---|---|
| 查詢 | schema_version, observation_id, queried_at, source_url, status |
| 入住 | check_in, check_out, lead_days, nights, adults |
| 飯店 | hotel_id, hotel_name, city |
| 房型 | room_type_code, room_type_name, room_size_sqm, size_band |
| 方案 | rate_plan_code, rate_plan_name, breakfast_included, cancellation_policy |
| 原始價格 | price_before_tax, service_charge, tax, total_price, currency |
| 分析欄位 | price_per_sqm, fx_rate_to_twd, total_twd, cpi_index, cpi_base_index, cpi_adjusted_twd |

價格以一晚、兩位成人為預設查詢條件；`total_price` 必須是完成訂房前可確認的完整一晚總價。無法可靠拆分未稅價、服務費或稅時，不可臆測，相關欄位應保留空值並在 adapter 記錄來源限制。

`status=demo` 永遠代表測試資料；正式官網驗證通過後才可寫入 `status=live`。
