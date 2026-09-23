import json
from datetime import datetime, timedelta
from pathlib import Path

from services.deduplication import deduplicate_observations
from services.market_metrics import calculate_market_summary


SOURCE = Path("data/rates.jsonl")
TARGET = Path("public/data/rates.json")
LATEST_TARGET = Path("public/data/latest.json")

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
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(
            {
                "generated_from": "data/rates.jsonl",
                "market_summary": calculate_market_summary(source_rows),
                "rates": rows,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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
        f"Published {len(rows)} historical observations to {TARGET} and "
        f"{len(latest_rows)} latest observations to {LATEST_TARGET}"
    )


if __name__ == "__main__":
    main()
