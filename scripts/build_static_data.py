import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from services.deduplication import deduplicate_observations
from services.market_metrics import calculate_market_summary


SOURCE = Path("data/rates.jsonl")
RATES_DIR = Path("public/data/rates")
HISTORY_SUMMARY_TARGET = Path("public/data/history_summary.json")
LATEST_TARGET = Path("public/data/latest.json")
LEGACY_TARGET = Path("public/data/rates.json")

DASHBOARD_FIELDS = (
    "run_id", "scheduled_for", "hotel_id", "hotel_name", "city", "district", "room_type_code", "room_type_name",
    "room_size_sqm", "check_in", "lead_days", "rate_plan_name",
    "breakfast_included", "price_before_tax", "total_price", "total_twd",
    "price_per_sqm", "queried_at", "currency", "source_platform",
    "source_method", "source_property_id", "source_url",
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
        "daily": daily,
        "hotels": hotels,
        "lead_curve": lead_curve,
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
                "rates": month_rows,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    HISTORY_SUMMARY_TARGET.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_SUMMARY_TARGET.write_text(
        json.dumps(_history_summary(source_rows), ensure_ascii=False), encoding="utf-8"
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
