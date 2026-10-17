"""One-time, verified migration from one large JSONL file to monthly shards."""

import json
from collections import defaultdict
from pathlib import Path


SOURCE = Path("data/rates.jsonl")
TARGET = Path("data/rates")


def month_of(row: dict, line_number: int) -> str:
    value = str(row.get("queried_at") or "")
    if len(value) < 7 or value[4] != "-" or value[7:8] not in {"-", ""}:
        raise ValueError(f"Line {line_number} has invalid queried_at: {value!r}")
    return value[:7]


def main() -> None:
    if not SOURCE.exists():
        print(f"Legacy source is absent; nothing to migrate: {SOURCE}")
        return
    if TARGET.exists() and any(TARGET.iterdir()):
        raise RuntimeError(f"Target must be empty before migration: {TARGET}")

    grouped: dict[str, list[str]] = defaultdict(list)
    source_count = 0
    for line_number, line in enumerate(SOURCE.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        grouped[month_of(row, line_number)].append(
            json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        )
        source_count += 1

    TARGET.mkdir(parents=True, exist_ok=True)
    written = 0
    for month, lines in sorted(grouped.items()):
        temporary = TARGET / f".{month}.jsonl.tmp"
        final = TARGET / f"{month}.jsonl"
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        verified = sum(1 for line in temporary.read_text(encoding="utf-8").splitlines() if line.strip())
        if verified != len(lines):
            raise RuntimeError(f"Shard verification failed for {month}: {verified} != {len(lines)}")
        temporary.replace(final)
        written += verified

    if written != source_count:
        raise RuntimeError(f"Migration verification failed: {written} != {source_count}")
    SOURCE.unlink()
    print(f"Migrated {source_count} observations into {len(grouped)} monthly shards")


if __name__ == "__main__":
    main()
