"""Materialize legacy defaults required by the expanded rate natural key."""

import json
from collections import Counter
from pathlib import Path

from services.deduplication import observation_natural_key
from storage.local_jsonl import jsonl_partition_paths


SOURCE = Path("data/rates")
LEGACY_DEFAULTS = {
    "source_platform": "official",
    "rooms": 1,
    "adults": 2,
    "children": 0,
}
REQUIRED_WITHOUT_SAFE_DEFAULT = ("check_out", "currency")


def migrate_file(path: Path) -> tuple[int, Counter[str]]:
    rows: list[dict] = []
    backfilled: Counter[str] = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            for field in REQUIRED_WITHOUT_SAFE_DEFAULT:
                if row.get(field) in (None, ""):
                    raise ValueError(f"{path} line {line_number} is missing {field}")
            for field, default in LEGACY_DEFAULTS.items():
                if row.get(field) in (None, ""):
                    row[field] = default
                    backfilled[field] += 1
            rows.append(row)

    keys = [observation_natural_key(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise RuntimeError(f"Expanded natural key collision detected in {path}")
    if not backfilled:
        return len(rows), backfilled

    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )

    verified = []
    with temporary.open("r", encoding="utf-8") as handle:
        verified = [json.loads(line) for line in handle if line.strip()]
    if len(verified) != len(rows):
        raise RuntimeError(f"Row-count verification failed in {path}")
    if any(
        row.get(field) in (None, "")
        for row in verified
        for field in (*LEGACY_DEFAULTS, *REQUIRED_WITHOUT_SAFE_DEFAULT)
    ):
        raise RuntimeError(f"Natural-key dimension verification failed in {path}")
    temporary.replace(path)
    return len(rows), backfilled


def main() -> None:
    paths = jsonl_partition_paths(SOURCE)
    if not paths:
        print(f"No rate history found at {SOURCE}")
        return
    total = 0
    totals: Counter[str] = Counter()
    for path in paths:
        count, backfilled = migrate_file(path)
        total += count
        totals.update(backfilled)
    detail = ", ".join(f"{field}={totals[field]}" for field in LEGACY_DEFAULTS)
    print(f"Verified {total} observations across {len(paths)} shards; backfilled {detail}")


if __name__ == "__main__":
    main()
