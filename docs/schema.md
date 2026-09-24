# 資料 Schema v1.3

一列代表「某批次、某飯店、某入住區間、某房型、某價格方案」的一筆公開報價。
新寫入資料使用 `run_id` 追蹤批次，並以自然鍵去重。

## RateObservation

| 欄位群組 | 主要欄位 | 說明 |
|---|---|---|
| 批次 | `schema_version`, `observation_id`, `run_id`, `scheduled_for`, `queried_at` | `run_id` 為一次 job 共用 UUID |
| 入住 | `check_in`, `check_out`, `lead_days`, `nights` | 預設一晚 |
| 人數 | `rooms`, `adults`, `children` | 預設 1 房、2 成人、0 兒童 |
| 飯店 | `hotel_id`, `hotel_name`, `city`, `district` | `hotel_id` 為穩定識別碼 |
| 房型 | `room_type_code`, `room_type_name`, `room_size_sqm`, `size_band` | 無面積一律為 `unknown` |
| 方案 | `rate_plan_code`, `rate_plan_name`, `breakfast_included`, `cancellation_policy` | 無可靠資訊保留空值 |
| 價格 | `price_before_tax`, `service_charge`, `tax`, `tax_inclusion`, `total_price`, `currency` | 不可臆測稅費拆分 |
| 來源 | `source_platform`, `source_method`, `source_property_id`, `source_url`, `status` | 官網預設 `official` |
| 分析 | `price_per_sqm`, `fx_rate_to_twd`, `total_twd`, `cpi_index`, `cpi_base_index`, `cpi_adjusted_twd` | 衍生欄位 |

`total_price` 必須是完成訂房前可確認的完整住宿總價。無法可靠拆分未稅價、服務費或
稅額時，相關欄位維持空值。`status=demo` 永遠只代表測試資料；預設 Demo 關閉。

## 面積級距

```text
<45㎡ | 45–59㎡ | 60–79㎡ | 80㎡+ | unknown
```

`room_size_sqm` 為 `null`、`undefined`、非數字或小於等於零時均歸為 `unknown`，
不得透過 `Number(null) === 0` 誤歸到 `<45㎡`。

## 去重

寫入 `data/rates.jsonl` 及產生公開 JSON 前，以每日自然鍵去重：

```text
hotel_id + check_in + room_type_code + rate_plan_code + queried_at_date
```

訂房引擎未提供 code 時，才使用正規化房型／方案名稱作 fallback；相同自然鍵保留
`queried_at` 較新的 observation。

## 市場指標

市場 ADR 與每㎡指標採飯店等權：先計算每家飯店在目前篩選範圍內的中位數，
再取所有飯店中位數的中位數。FastAPI 與靜態 JSON 共用 `services/market_metrics.py`，
避免兩套算法不一致。無效、非正數或缺少 TWD 換算值的資料不納入。

## OTA Canonical Comparison Key

只有下列 Canonical Key 完全相同的官網與 OTA 商品才可計算價差：

```text
hotel_id
+ check_in + check_out
+ occupancy (rooms/adults/children)
+ size_band（或後續可用的正規化房型）
+ breakfast_included
+ cancellation_class
+ tax_inclusion
```

必要欄位不足時 `comparison_key=null`、`comparison_status=insufficient_product_metadata`；
不產生 Rate Parity 結果。`cancellation_class` 正規化為 `free_cancellation`、
`conditional`、`non_refundable` 或 `unknown`；`tax_inclusion` 為 `included`、
`excluded` 或 `unknown`。

## 靜態發布資料

```text
public/data/latest.json
  market_summary + rate_parity + rates（最新批次）

public/data/history_summary.json
  available_months + market_summary + daily + hotels + lead_curve

public/data/rates/YYYY-MM.json
  month + market_summary + rate_parity + rates（單月明細）
```

歷史頁首頁只讀取 `history_summary.json`；特定月份明細採按需載入。舊的單一
`public/data/rates.json` 不再發布。

## AdapterHealth

`data/adapter_health.json` 以 `adapter:hotel_id` 為鍵，保存：

- `attempts`, `successes`, `failures`, `success_rate`
- `average_response_ms`
- `blocked_count`, `consecutive_failures`
- `last_status`, `last_attempt_at`, `last_success_at`, `cooldown_until`
- `daily` 每日嘗試、成功、失敗、Blocked 及回應時間彙整

連續一般失敗達門檻後進入指數退避；HTTP 403／429 立即冷卻。詳細錯誤另寫入
`data/diagnostics/YYYY-MM-DD.jsonl`，內容會遮蔽憑證，且不提交至公開 Git。
