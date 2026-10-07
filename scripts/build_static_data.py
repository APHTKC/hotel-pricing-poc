import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from services.deduplication import deduplicate_observations
from services.market_metrics import calculate_market_summary
from services.rate_parity import calculate_rate_parity, comparison_metadata


SOURCE = Path("data/rates.jsonl")
HEALTH_SOURCE = Path("data/adapter_health.json")
RATES_DIR = Path("public/data/rates")
HISTORY_SUMMARY_TARGET = Path("public/data/history_summary.json")
RATES_INDEX_TARGET = RATES_DIR / "index.json"
LATEST_SUMMARY_TARGET = Path("public/data/latest_summary.json")
LATEST_HEATMAP_TARGET = Path("public/data/latest_heatmap.json")
LATEST_DETAILS_TARGET = Path("public/data/latest_details.json")
LEGACY_LATEST_TARGET = Path("public/data/latest.json")
HEALTH_TARGET = Path("public/data/adapter_health.json")
DIGEST_TARGET = Path("public/data/digest.json")
HOTEL_NAMES_SOURCE = Path("public/data/hotel_names_zh.json")
LEGACY_TARGET = Path("public/data/rates.json")

DASHBOARD_FIELDS = (
    "run_id", "scheduled_for", "hotel_id", "hotel_name", "city", "district", "room_type_code", "room_type_name",
    "room_size_sqm", "check_in", "check_out", "lead_days", "nights", "rooms", "adults", "children",
    "rate_plan_name", "breakfast_included", "cancellation_policy", "price_before_tax",
    "service_charge", "tax", "tax_inclusion", "total_price", "total_twd",
    "price_per_sqm", "queried_at", "currency", "source_platform",
    "source_method", "source_property_id", "source_url",
    "size_band", "occupancy", "cancellation_class", "comparison_key", "comparison_status",
)

HEATMAP_FIELDS = (
    "hotel_id", "hotel_name", "city", "district", "room_type_code",
    "room_type_name", "room_size_sqm", "check_in", "lead_days",
    "rate_plan_name", "total_price", "total_twd", "price_per_sqm",
    "queried_at", "source_platform", "comparison_key",
)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _dashboard_row(row: dict) -> dict:
    published = {field: row.get(field) for field in DASHBOARD_FIELDS}
    # Observations written before schema 1.1 are all official-site records.
    # Backfill them so source filtering and exports remain consistent across
    # the full history after OTA records are introduced.
    published["source_platform"] = row.get("source_platform") or "official"
    published["source_method"] = row.get("source_method") or "public_booking_page"
    published.update(comparison_metadata(row))
    return published


def _plausible_luxury_rate(row: dict) -> bool:
    """Fail closed when a foreign price was accidentally labelled as TWD."""
    total_twd = row.get("total_twd")
    try:
        return total_twd is not None and 3000 <= float(total_twd) <= 2_000_000
    except (TypeError, ValueError):
        return False


def _publishable_live_rate(row: dict) -> bool:
    """Publish only explicit live observations with a plausible TWD total."""
    return row.get("status") == "live" and _plausible_luxury_rate(row)


def _latest_batch(rows: list[dict]) -> list[dict]:
    """Group the observations created by the most recent workflow run."""
    timestamped = [row for row in rows if row.get("queried_at")]
    if not timestamped:
        return []
    latest = max(_parse_timestamp(row["queried_at"]) for row in timestamped)
    cutoff = latest - timedelta(minutes=30)
    return [row for row in timestamped if _parse_timestamp(row["queried_at"]) >= cutoff]


def _month_key(row: dict) -> str | None:
    value = row.get("queried_at")
    if not value:
        return None
    try:
        return _parse_timestamp(value).date().strftime("%Y-%m")
    except (TypeError, ValueError):
        return None


def _partition_id(value: str) -> str:
    """Return a URL-safe catalog id and fail closed for unexpected input."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value or ""):
        raise ValueError(f"Unsafe hotel id for static partition: {value!r}")
    return value


def _heatmap_row(row: dict) -> dict:
    return {field: row.get(field) for field in HEATMAP_FIELDS}


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _average(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _period_market(rows: list[dict]) -> dict:
    """Summarize a period after giving each hotel one equal-weight value."""
    by_hotel: dict[str, list[float]] = defaultdict(list)
    names: dict[str, str | None] = {}
    for row in rows:
        hotel_id = row.get("hotel_id")
        value = _number(row.get("total_twd"))
        if not hotel_id or value is None:
            continue
        by_hotel[hotel_id].append(value)
        names[hotel_id] = row.get("hotel_name")
    hotel_medians = {
        hotel_id: _median(values) for hotel_id, values in by_hotel.items()
    }
    values = [value for value in hotel_medians.values() if value is not None]
    return {
        "market_median_twd": _median(values),
        "market_average_twd": _average(values),
        "hotels": len(values),
        "observations": sum(len(values) for values in by_hotel.values()),
        "hotel_medians": [
            {
                "hotel_id": hotel_id,
                "hotel_name": names.get(hotel_id),
                "median_twd": value,
            }
            for hotel_id, value in sorted(hotel_medians.items())
            if value is not None
        ],
    }


def _weekly_digest(rows: list[dict]) -> dict:
    """Compare the latest seven calendar days with the preceding seven days."""
    dated_rows = []
    for row in rows:
        if not row.get("queried_at") or _number(row.get("total_twd")) is None:
            continue
        try:
            day = _parse_timestamp(row["queried_at"]).date()
        except (TypeError, ValueError):
            continue
        dated_rows.append((day, row))
    if not dated_rows:
        return {
            "available": False,
            "reason": "no_history",
            "currency": "TWD",
        }

    latest_end = max(day for day, _ in dated_rows)
    latest_start = latest_end - timedelta(days=6)
    previous_end = latest_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    current_rows = [row for day, row in dated_rows if latest_start <= day <= latest_end]
    previous_rows = [row for day, row in dated_rows if previous_start <= day <= previous_end]
    current = _period_market(current_rows)
    previous = _period_market(previous_rows)
    previous_value = previous["market_median_twd"]
    current_value = current["market_median_twd"]
    change_pct = None
    if current_value is not None and previous_value:
        change_pct = (current_value - previous_value) / previous_value

    current_by_hotel = {
        item["hotel_id"]: item for item in current["hotel_medians"]
    }
    previous_by_hotel = {
        item["hotel_id"]: item for item in previous["hotel_medians"]
    }
    movers = []
    for hotel_id in sorted(current_by_hotel.keys() & previous_by_hotel.keys()):
        current_item = current_by_hotel[hotel_id]
        previous_item = previous_by_hotel[hotel_id]
        baseline = previous_item["median_twd"]
        if not baseline:
            continue
        movers.append({
            "hotel_id": hotel_id,
            "hotel_name": current_item.get("hotel_name") or previous_item.get("hotel_name"),
            "current_median_twd": current_item["median_twd"],
            "previous_median_twd": baseline,
            "change_pct": (current_item["median_twd"] - baseline) / baseline,
        })
    movers.sort(key=lambda item: abs(item["change_pct"]), reverse=True)

    lead_hotel_values: dict[int, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in current_rows:
        try:
            lead = int(row.get("lead_days"))
        except (TypeError, ValueError):
            continue
        hotel_id = row.get("hotel_id")
        value = _number(row.get("total_twd"))
        if hotel_id and value is not None:
            lead_hotel_values[lead][hotel_id].append(value)
    lead_time_curve = []
    for lead, hotels in sorted(lead_hotel_values.items()):
        hotel_medians = [_median(values) for values in hotels.values()]
        hotel_medians = [value for value in hotel_medians if value is not None]
        lead_time_curve.append({
            "lead_days": lead,
            "market_median_twd": _median(hotel_medians),
            "hotels": len(hotel_medians),
        })

    return {
        "available": current_value is not None,
        "currency": "TWD",
        "method": "hotel_equal_weight_median",
        "current_period": {
            "start": latest_start.isoformat(),
            "end": latest_end.isoformat(),
            **current,
        },
        "previous_period": {
            "start": previous_start.isoformat(),
            "end": previous_end.isoformat(),
            **previous,
        },
        "change_pct": change_pct,
        "comparable_hotels": len(movers),
        "movers": movers[:5],
        "lead_time_curve": lead_time_curve,
    }


def _rows_for_day(rows: list[dict], day) -> list[dict]:
    selected = []
    for row in rows:
        try:
            observed = _parse_timestamp(row.get("queried_at", "")).date()
        except (TypeError, ValueError):
            continue
        if observed == day:
            selected.append(row)
    return selected


def _equal_weight_median(rows: list[dict], *, core_only: bool = False) -> float | None:
    by_hotel: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if core_only:
            size = _number(row.get("room_size_sqm"))
            if size is None or not 45 <= size < 60:
                continue
        value = _number(row.get("total_twd"))
        if row.get("hotel_id") and value is not None:
            by_hotel[row["hotel_id"]].append(value)
    return _median([_median(values) for values in by_hotel.values() if values])


def _hotel_forward_medians(rows: list[dict], start, end) -> dict[str, dict]:
    grouped: dict[str, list[float]] = defaultdict(list)
    names: dict[str, str | None] = {}
    for row in rows:
        try:
            check_in = datetime.fromisoformat(str(row.get("check_in"))).date()
        except (TypeError, ValueError):
            continue
        value = _number(row.get("total_twd"))
        hotel_id = row.get("hotel_id")
        if hotel_id and value is not None and start <= check_in <= end:
            grouped[hotel_id].append(value)
            names[hotel_id] = row.get("hotel_name")
    return {
        hotel_id: {"hotel_id": hotel_id, "hotel_name": names.get(hotel_id), "median_twd": _median(values)}
        for hotel_id, values in grouped.items()
    }


def _daily_market_digest(rows: list[dict], names_zh: dict[str, str] | None = None) -> dict:
    """Build concise, traceable insights for the latest observation day."""
    valid_days = []
    for row in rows:
        try:
            valid_days.append(_parse_timestamp(row.get("queried_at", "")).date())
        except (TypeError, ValueError):
            continue
    if not valid_days:
        return {"updated_at": None, "insights": [], "available": False, "reason": "no_history"}
    latest_day = max(valid_days)
    comparison_day = latest_day - timedelta(days=7)
    current = _rows_for_day(rows, latest_day)
    previous = _rows_for_day(rows, comparison_day)
    current_core = _equal_weight_median(current, core_only=True)
    previous_core = _equal_weight_median(previous, core_only=True)
    core_change = (
        (current_core - previous_core) / previous_core
        if current_core is not None and previous_core
        else None
    )

    window_end = latest_day + timedelta(days=30)
    current_hotels = _hotel_forward_medians(current, latest_day, window_end)
    previous_hotels = _hotel_forward_medians(previous, latest_day, window_end)
    movers = []
    for hotel_id in current_hotels.keys() & previous_hotels.keys():
        present, past = current_hotels[hotel_id], previous_hotels[hotel_id]
        if not past["median_twd"]:
            continue
        movers.append({
            "hotel_id": hotel_id,
            "hotel_name": present.get("hotel_name") or past.get("hotel_name"),
            "change_pct": (present["median_twd"] - past["median_twd"]) / past["median_twd"],
            "current_median_twd": present["median_twd"],
            "previous_median_twd": past["median_twd"],
        })
    largest_increase = max(movers, key=lambda item: item["change_pct"], default=None)
    largest_decrease = min(movers, key=lambda item: item["change_pct"], default=None)

    parity = calculate_rate_parity(current)
    comparable = [item for item in parity if item.get("gap_percent") is not None]
    normal = [item for item in comparable if abs(item["gap_percent"]) <= .05]
    parity_rate = len(normal) / len(comparable) if comparable else None

    percent = lambda value: f"{value:+.1%}"
    names_zh = names_zh or {}
    display_name = lambda item: names_zh.get(item["hotel_id"]) or item["hotel_name"]
    insights = []
    if core_change is not None:
        direction = "上漲" if core_change > 0 else "下降" if core_change < 0 else "持平"
        insights.append(f"45–59㎡核心客房 ADR 較 7 天前{direction} {abs(core_change):.1%}。")
    if largest_increase and largest_increase["change_pct"] > 0:
        insights.append(f"未來 30 天漲幅最大為 {display_name(largest_increase)}（{percent(largest_increase['change_pct'])}）。")
    if largest_decrease and largest_decrease["change_pct"] < 0:
        insights.append(f"未來 30 天降價最多為 {display_name(largest_decrease)}（{percent(largest_decrease['change_pct'])}）。")
    if parity_rate is not None:
        insights.append(f"官網與 OTA 嚴格同商品價差在 ±5% 內的比例為 {parity_rate:.0%}（{len(normal)}/{len(comparable)} 組）。")
    else:
        insights.append("目前沒有條件完整一致的官網與 OTA 商品可計算價差正常率。")
    return {
        "updated_at": max(row.get("queried_at") for row in current if row.get("queried_at")),
        "latest_date": latest_day.isoformat(),
        "comparison_date": comparison_day.isoformat(),
        "available": bool(insights),
        "method": "hotel_equal_weight_median",
        "insights": insights[:4],
        "metrics": {
            "core_adr_change_pct": core_change,
            "largest_increase": largest_increase,
            "largest_decrease": largest_decrease,
            "rate_parity_normal_rate": parity_rate,
            "rate_parity_comparable_products": len(comparable),
        },
    }


def _data_quality_warnings(rows: list[dict]) -> dict:
    """Detect volume drops and day-over-day ADR spikes without guessing."""
    dated: dict = defaultdict(lambda: defaultdict(list))
    names: dict[str, str | None] = {}
    days = set()
    for row in rows:
        hotel_id = row.get("hotel_id")
        value = _number(row.get("total_twd"))
        try:
            day = _parse_timestamp(row.get("queried_at", "")).date()
        except (TypeError, ValueError):
            continue
        if not hotel_id or value is None:
            continue
        days.add(day)
        dated[hotel_id][day].append(value)
        names[hotel_id] = row.get("hotel_name")
    if not days:
        return {"as_of": None, "hotels": []}
    latest = max(days)
    yesterday = latest - timedelta(days=1)
    prior_days = [latest - timedelta(days=offset) for offset in range(1, 8)]
    warnings = []
    for hotel_id, daily in sorted(dated.items()):
        current = daily.get(latest, [])
        issues = []
        historical_counts = [len(daily[day]) for day in prior_days if daily.get(day)]
        baseline_volume = _average(historical_counts)
        if baseline_volume and len(current) < baseline_volume * .5:
            issues.append({
                "code": "low_volume", "severity": "warning",
                "current_count": len(current), "baseline_count": baseline_volume,
                "message_zh": "筆數偏少，資料核實中",
            })
        current_adr, previous_adr = _median(current), _median(daily.get(yesterday, []))
        if current_adr is not None and previous_adr:
            change = (current_adr - previous_adr) / previous_adr
            if abs(change) > .5:
                issues.append({
                    "code": "price_spike", "severity": "warning",
                    "change_pct": change, "current_adr_twd": current_adr,
                    "previous_adr_twd": previous_adr,
                    "message_zh": "房價變動超過 50%，資料核實中",
                })
        if issues:
            warnings.append({"hotel_id": hotel_id, "hotel_name": names.get(hotel_id), "warnings": issues})
    return {"as_of": latest.isoformat(), "hotels": warnings}


def _history_summary(rows: list[dict]) -> dict:
    """Build the small, chart-ready payload loaded by the history landing page."""
    daily_groups: dict[tuple, list[dict]] = defaultdict(list)
    lead_groups: dict[tuple, list[dict]] = defaultdict(list)
    hotel_groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        queried_at = row.get("queried_at")
        total = _number(row.get("total_twd"))
        if not queried_at or total is None:
            continue
        queried_date = _parse_timestamp(queried_at).date().isoformat()
        identity = (
            row.get("hotel_id"), row.get("hotel_name"), row.get("city"), row.get("district")
        )
        daily_groups[(queried_date, *identity)].append(row)
        hotel_groups[identity].append(row)
        lead = row.get("lead_days")
        if lead is not None:
            lead_groups[(*identity, int(lead))].append(row)

    def stats(group: list[dict]) -> dict:
        values = [_number(row.get("total_twd")) for row in group]
        values = [value for value in values if value is not None]
        core = [
            _number(row.get("total_twd"))
            for row in group
            if _number(row.get("room_size_sqm")) is not None
            and 45 <= float(row["room_size_sqm"]) < 60
        ]
        core = [value for value in core if value is not None]
        unit = [_number(row.get("price_per_sqm")) for row in group]
        unit = [value for value in unit if value is not None]
        return {
            "observations": len(values),
            "average_twd": _average(values),
            "median_twd": _median(values),
            "core_median_twd": _median(core),
            "median_per_sqm_twd": _median(unit),
        }

    daily = []
    sort_key = lambda item: tuple("" if value is None else str(value) for value in item[0])
    for (day, hotel_id, hotel_name, city, district), group in sorted(daily_groups.items(), key=sort_key):
        daily.append({
            "queried_date": day, "hotel_id": hotel_id, "hotel_name": hotel_name,
            "city": city, "district": district, **stats(group),
        })
    hotels = []
    for (hotel_id, hotel_name, city, district), group in sorted(hotel_groups.items(), key=sort_key):
        days = {_parse_timestamp(row["queried_at"]).date().isoformat() for row in group}
        hotels.append({
            "hotel_id": hotel_id, "hotel_name": hotel_name, "city": city,
            "district": district, "days": len(days), **stats(group),
        })
    lead_curve = []
    for (hotel_id, hotel_name, city, district, lead), group in sorted(lead_groups.items(), key=sort_key):
        lead_curve.append({
            "hotel_id": hotel_id, "hotel_name": hotel_name, "city": city,
            "district": district, "lead_days": lead, **stats(group),
        })
    return {
        "generated_from": "data/rates.jsonl",
        "available_months": sorted({key for row in rows if (key := _month_key(row))}, reverse=True),
        "market_summary": calculate_market_summary(rows),
        "weekly_digest": _weekly_digest(rows),
        "daily": daily,
        "hotels": hotels,
        "lead_curve": lead_curve,
    }


def _public_adapter_health(payload: dict, data_quality: dict | None = None) -> dict:
    """Publish operational aggregates without diagnostic messages or URLs."""
    allowed = (
        "adapter", "hotel_id", "attempts", "successes", "failures",
        "blocked_count", "success_rate", "average_response_ms", "last_status",
        "last_attempt_at", "last_success_at", "cooldown_until",
    )
    adapters = []
    for record in (payload.get("adapters") or {}).values():
        adapters.append({field: record.get(field) for field in allowed})
    adapters.sort(key=lambda row: (row.get("hotel_id") or "", row.get("adapter") or ""))
    attempts = [row.get("last_attempt_at") for row in adapters if row.get("last_attempt_at")]
    return {
        "schema_version": "1.0",
        "generated_at": max(attempts) if attempts else None,
        "adapters": adapters,
        "data_quality": data_quality or {"as_of": None, "hotels": []},
    }


def main() -> None:
    source_rows = []
    if SOURCE.exists():
        for line in SOURCE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if _publishable_live_rate(row):
                    source_rows.append(row)
    source_rows = deduplicate_observations(source_rows, keep="latest")
    rows = [_dashboard_row(row) for row in source_rows]
    rows.sort(key=lambda row: row.get("queried_at", ""), reverse=True)
    RATES_DIR.mkdir(parents=True, exist_ok=True)
    partitions: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    source_partitions: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for source_row in source_rows:
        month = _month_key(source_row)
        hotel_id = source_row.get("hotel_id")
        if month and hotel_id:
            safe_hotel_id = _partition_id(str(hotel_id))
            source_partitions[month][safe_hotel_id].append(source_row)
            partitions[month][safe_hotel_id].append(_dashboard_row(source_row))

    # The old month-wide JSON files were tens of megabytes. Publish only
    # month/hotel partitions and a small manifest used for lazy loading.
    for legacy_month_file in RATES_DIR.glob("????-??.json"):
        legacy_month_file.unlink()
    expected_months = set(partitions)
    for stale_month_dir in RATES_DIR.iterdir():
        if stale_month_dir.is_dir() and re.fullmatch(r"\d{4}-\d{2}", stale_month_dir.name):
            if stale_month_dir.name not in expected_months:
                for stale_file in stale_month_dir.glob("*.json"):
                    stale_file.unlink()
                stale_month_dir.rmdir()

    rate_index = {"generated_from": "data/rates.jsonl", "months": []}
    partition_count = 0
    for month in sorted(partitions, reverse=True):
        month_dir = RATES_DIR / month
        month_dir.mkdir(parents=True, exist_ok=True)
        expected_files = {f"{hotel_id}.json" for hotel_id in partitions[month]}
        for stale_file in month_dir.glob("*.json"):
            if stale_file.name not in expected_files:
                stale_file.unlink()
        hotels = []
        for hotel_id in sorted(partitions[month]):
            month_rows = partitions[month][hotel_id]
            month_rows.sort(key=lambda row: row.get("queried_at", ""), reverse=True)
            month_source_rows = source_partitions[month][hotel_id]
            hotel_name = next((row.get("hotel_name") for row in month_rows if row.get("hotel_name")), hotel_id)
            relative_path = f"rates/{month}/{hotel_id}.json"
            (month_dir / f"{hotel_id}.json").write_text(
                json.dumps({
                    "month": month,
                    "hotel_id": hotel_id,
                    "hotel_name": hotel_name,
                    "generated_from": "data/rates.jsonl",
                    "market_summary": calculate_market_summary(month_source_rows),
                    "rate_parity": calculate_rate_parity(month_source_rows),
                    "rates": month_rows,
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            hotels.append({
                "hotel_id": hotel_id,
                "hotel_name": hotel_name,
                "observations": len(month_rows),
                "path": relative_path,
            })
            partition_count += 1
        rate_index["months"].append({"month": month, "hotels": hotels})
    RATES_INDEX_TARGET.write_text(json.dumps(rate_index, ensure_ascii=False), encoding="utf-8")
    HISTORY_SUMMARY_TARGET.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_SUMMARY_TARGET.write_text(
        json.dumps(_history_summary(source_rows), ensure_ascii=False), encoding="utf-8"
    )
    health_payload = {"adapters": {}}
    if HEALTH_SOURCE.exists():
        try:
            health_payload = json.loads(HEALTH_SOURCE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    HEALTH_TARGET.write_text(
        json.dumps(_public_adapter_health(health_payload, _data_quality_warnings(source_rows)), ensure_ascii=False),
        encoding="utf-8",
    )
    names_zh = {}
    if HOTEL_NAMES_SOURCE.exists():
        try:
            names_zh = json.loads(HOTEL_NAMES_SOURCE.read_text(encoding="utf-8")).get("names", {})
        except (json.JSONDecodeError, OSError):
            pass
    DIGEST_TARGET.write_text(
        json.dumps(_daily_market_digest(source_rows, names_zh), ensure_ascii=False),
        encoding="utf-8",
    )
    if LEGACY_TARGET.exists():
        LEGACY_TARGET.unlink()
    latest_rows = _latest_batch(rows)
    latest_timestamps = {row["queried_at"] for row in latest_rows}
    latest_source_rows = [
        row for row in source_rows if row.get("queried_at") in latest_timestamps
    ]
    latest_summary = calculate_market_summary(latest_source_rows)
    latest_parity = calculate_rate_parity(latest_source_rows)
    latest_queried_at = max((row.get("queried_at") or "" for row in latest_rows), default=None)
    LATEST_SUMMARY_TARGET.write_text(
        json.dumps(
            {
                "generated_from": "data/rates.jsonl",
                "latest_queried_at": latest_queried_at,
                "record_count": len(latest_rows),
                "hotel_count": len({row.get("hotel_id") for row in latest_rows if row.get("hotel_id")}),
                "room_type_count": len({
                    (row.get("hotel_id"), row.get("room_type_code"))
                    for row in latest_rows if row.get("hotel_id") and row.get("room_type_code")
                }),
                "market_summary": latest_summary,
                "rate_parity": latest_parity,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    LATEST_HEATMAP_TARGET.write_text(
        json.dumps(
            {
                "generated_from": "data/rates.jsonl",
                "latest_queried_at": latest_queried_at,
                "rates": [_heatmap_row(row) for row in latest_rows],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    LATEST_DETAILS_TARGET.write_text(
        json.dumps(
            {
                "generated_from": "data/rates.jsonl",
                "latest_queried_at": latest_queried_at,
                "market_summary": latest_summary,
                "rate_parity": latest_parity,
                "rates": latest_rows,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if LEGACY_LATEST_TARGET.exists():
        LEGACY_LATEST_TARGET.unlink()
    print(
        f"Published {len(rows)} historical observations across {partition_count} month/hotel files, "
        f"a summary to {HISTORY_SUMMARY_TARGET}, and {len(latest_rows)} latest observations "
        "split into summary, heatmap, and details payloads"
    )


if __name__ == "__main__":
    main()
