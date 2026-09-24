import json
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
LATEST_TARGET = Path("public/data/latest.json")
HEALTH_TARGET = Path("public/data/adapter_health.json")
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


def _public_adapter_health(payload: dict) -> dict:
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
    }


def main() -> None:
    source_rows = []
    if SOURCE.exists():
        for line in SOURCE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if _plausible_luxury_rate(row):
                    source_rows.append(row)
    source_rows = deduplicate_observations(source_rows, keep="latest")
    rows = [_dashboard_row(row) for row in source_rows]
    rows.sort(key=lambda row: row.get("queried_at", ""), reverse=True)
    RATES_DIR.mkdir(parents=True, exist_ok=True)
    partitions: dict[str, list[dict]] = defaultdict(list)
    source_partitions: dict[str, list[dict]] = defaultdict(list)
    for source_row in source_rows:
        month = _month_key(source_row)
        if month:
            source_partitions[month].append(source_row)
            partitions[month].append(_dashboard_row(source_row))
    for stale in RATES_DIR.glob("????-??.json"):
        if stale.stem not in partitions:
            stale.unlink()
    for month, month_rows in partitions.items():
        month_rows.sort(key=lambda row: row.get("queried_at", ""), reverse=True)
        (RATES_DIR / f"{month}.json").write_text(
            json.dumps({
                "month": month,
                "generated_from": "data/rates.jsonl",
                "market_summary": calculate_market_summary(source_partitions[month]),
                "rate_parity": calculate_rate_parity(source_partitions[month]),
                "rates": month_rows,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
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
        json.dumps(_public_adapter_health(health_payload), ensure_ascii=False),
        encoding="utf-8",
    )
    if LEGACY_TARGET.exists():
        LEGACY_TARGET.unlink()
    latest_rows = _latest_batch(rows)
    latest_timestamps = {row["queried_at"] for row in latest_rows}
    latest_source_rows = [
        row for row in source_rows if row.get("queried_at") in latest_timestamps
    ]
    LATEST_TARGET.write_text(
        json.dumps(
            {
                "generated_from": "data/rates.jsonl",
                "market_summary": calculate_market_summary(latest_source_rows),
                "rate_parity": calculate_rate_parity(latest_source_rows),
                "rates": latest_rows,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        f"Published {len(rows)} historical observations across {len(partitions)} monthly files, "
        f"a summary to {HISTORY_SUMMARY_TARGET}, and {len(latest_rows)} latest observations"
    )


if __name__ == "__main__":
    main()
