"""Verified migration from legacy/monthly JSONL into bounded daily shards."""

import hashlib
import json
from pathlib import Path
from typing import TextIO

from storage.local_jsonl import jsonl_partition_paths


LEGACY_SOURCE = Path("data/rates.jsonl")
SOURCE = Path("data/rates")
TEMP_TARGET = Path("data/rates_daily_tmp")


def day_of(row: dict, source: Path, line_number: int) -> tuple[str, str]:
    value = str(row.get("queried_at") or "")
    if len(value) < 10 or value[4] != "-" or value[7] != "-":
        raise ValueError(
            f"{source} line {line_number} has invalid queried_at: {value!r}"
        )
    return value[:7], value[:10]


def record_digest(row: dict) -> str:
    canonical = json.dumps(
        row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> None:
    source_paths = jsonl_partition_paths(LEGACY_SOURCE)
    source_paths.extend(SOURCE.glob("????-??.jsonl"))
    source_paths = sorted(set(source_paths))
    daily_paths = sorted(SOURCE.glob("????-??/????-??-??.jsonl"))
    if not source_paths:
        if daily_paths:
            print(f"Rate history already uses {len(daily_paths)} bounded daily shards")
            return
        print("No legacy or monthly rate history found")
        return
    if daily_paths:
        raise RuntimeError("Refusing to mix monthly inputs with existing daily shards")
    if TEMP_TARGET.exists():
        raise RuntimeError(f"Temporary target already exists: {TEMP_TARGET}")

    source_digests: list[str] = []
    handles: dict[Path, TextIO] = {}
    try:
        for source_path in source_paths:
            with source_path.open("r", encoding="utf-8") as source_handle:
                for line_number, line in enumerate(source_handle, 1):
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    month, day = day_of(row, source_path, line_number)
                    source_digests.append(record_digest(row))
                    target = TEMP_TARGET / month / f"{day}.jsonl"
                    if target not in handles:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        handles[target] = target.open(
                            "a", encoding="utf-8", newline="\n"
                        )
                    handles[target].write(
                        json.dumps(
                            row, ensure_ascii=False, separators=(",", ":")
                        )
                        + "\n"
                    )
    finally:
        for handle in handles.values():
            handle.close()

    target_digests: list[str] = []
    target_paths = sorted(TEMP_TARGET.glob("????-??/????-??-??.jsonl"))
    for target_path in target_paths:
        with target_path.open("r", encoding="utf-8") as target_handle:
            target_digests.extend(
                record_digest(json.loads(line))
                for line in target_handle
                if line.strip()
            )
    if sorted(target_digests) != sorted(source_digests):
        raise RuntimeError("Migration verification failed: record sets differ")

    SOURCE.mkdir(parents=True, exist_ok=True)
    for source_path in source_paths:
        source_path.unlink()
    for month_dir in sorted(TEMP_TARGET.iterdir()):
        destination = SOURCE / month_dir.name
        destination.mkdir(parents=True, exist_ok=True)
        for shard in sorted(month_dir.iterdir()):
            shard.replace(destination / shard.name)
        month_dir.rmdir()
    TEMP_TARGET.rmdir()
    print(
        f"Migrated {len(source_digests)} observations into "
        f"{len(target_paths)} bounded daily shards"
    )


if __name__ == "__main__":
    main()
