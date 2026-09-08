import json
from datetime import datetime, timedelta
from pathlib import Path


SOURCE = Path("data/rates.jsonl")
TARGET = Path("public/data/rates.json")
LATEST_TARGET = Path("public/data/latest.json")

DASHBOARD_FIELDS = (
    "hotel_id", "hotel_name", "room_type_code", "room_type_name",
    "room_size_sqm", "check_in", "lead_days", "rate_plan_name",
    "breakfast_included", "price_before_tax", "total_price", "total_twd",
    "price_per_sqm", "queried_at", "currency", "source_url",
)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _dashboard_row(row: dict) -> dict:
    return {field: row.get(field) for field in DASHBOARD_FIELDS}


def _latest_batch(rows: list[dict]) -> list[dict]:
    """Group the observations created by the most recent workflow run."""
    timestamped = [row for row in rows if row.get("queried_at")]
    if not timestamped:
        return []
    latest = max(_parse_timestamp(row["queried_at"]) for row in timestamped)
    cutoff = latest - timedelta(minutes=30)
    return [row for row in timestamped if _parse_timestamp(row["queried_at"]) >= cutoff]


def main() -> None:
    rows = []
    if SOURCE.exists():
        for line in SOURCE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(_dashboard_row(json.loads(line)))
    rows.sort(key=lambda row: row.get("queried_at", ""), reverse=True)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps({"generated_from": "data/rates.jsonl", "rates": rows}, ensure_ascii=False),
        encoding="utf-8",
    )
    latest_rows = _latest_batch(rows)
    LATEST_TARGET.write_text(
        json.dumps(
            {"generated_from": "data/rates.jsonl", "rates": latest_rows},
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
