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
public/data/latest_summary.json
  latest_queried_at + record_count + hotel_count + room_type_count + market_summary + rate_parity

public/data/latest_heatmap.json
  latest_queried_at + rates（首頁趨勢與熱力圖所需欄位）

public/data/latest_details.json
  latest_queried_at + market_summary + rate_parity + rates（最新批次完整明細）

public/data/history_summary.json
  available_months + market_summary + daily + hotels + lead_curve + weekly_digest

public/data/rates/index.json
  months[] + hotels[] + observations + path

public/data/rates/YYYY-MM/HOTEL_ID.json
  month + hotel_id + hotel_name + market_summary + rate_parity + rates（單月單飯店明細）

public/data/hotel_locations.json
  schema_version + updated_at + source_note + locations（67 家飯店快取座標）
```

歷史頁首頁只讀取 `history_summary.json` 與 `rates/index.json`；特定月份、特定飯店的
明細才按需載入。舊的 `public/data/latest.json`、單月巨型 JSON 與單一
`public/data/rates.json` 均不再發布。

`hotel_locations.json` 的每筆 `locations` 包含 `hotel_id`、繁中／英文名、`city`、
台北飯店的 `district`、`latitude`、`longitude`、官方訂房連結、`daily_tracked`、
座標來源與精度標記。前台 `map.html` 只讀取此快取檔，不在瀏覽器端批次地理編碼。

### `weekly_digest`

`weekly_digest` 是供歷史分析頁快速顯示的預聚合 Executive Digest，不需要下載單月
明細。其期間定義與計算方式如下：

- `current_period`：資料中最新日期往前 7 個日曆日（含首尾）。
- `previous_period`：緊接在 current period 前的 7 個日曆日。
- `market`：各期間先計算每家飯店的房價中位數，再對飯店中位數取市場中位數與平均數，
  避免房型或觀測筆數較多的飯店取得較高權重。
- `movers`：只比較兩個期間都有資料的飯店，依漲跌幅絕對值排序。
- `lead_time_curve`：最近 7 日按提前訂房天數分組，各組同樣採飯店等權彙整。

若不存在可比較的前一期間，變動率與 movers 維持空值／空陣列；系統不以單期資料推估
歷史漲跌。

## HotelProfile 與服務費比較

`public/data/hotel_profiles.json` 保存經來源核實的飯店基本資料、房型快照、設施、餐飲與
行政／貴賓廳資訊。`service_charge_percent` 僅在官方頁面或官方文件明確公告時填入；
不得由品牌慣例或其他飯店推測。

比較頁顯示服務費時採以下優先順序：

1. 已核實的 `service_charge_percent`（標示「官方」）。
2. 若官方資料未提供，且最新公開房價同時有 `price_before_tax > 0` 與
   `service_charge`，以各觀測值的 `service_charge / price_before_tax × 100` 中位數顯示
   （標示「房價觀測」）。
3. 兩者皆無時顯示「待核實」，不以 0% 代替。

## AdapterHealth

`data/adapter_health.json` 以 `adapter:hotel_id` 為鍵，保存：

- `attempts`, `successes`, `failures`, `success_rate`
- `average_response_ms`
- `blocked_count`, `consecutive_failures`
- `last_status`, `last_attempt_at`, `last_success_at`, `cooldown_until`
- `daily` 每日嘗試、成功、失敗、Blocked 及回應時間彙整

連續一般失敗達門檻後進入指數退避；HTTP 403／429 立即冷卻。詳細錯誤另寫入
`data/diagnostics/YYYY-MM-DD.jsonl`，內容會遮蔽憑證，且不提交至公開 Git。
