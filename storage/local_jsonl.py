import json
from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from app.models import RateObservation
from services.deduplication import deduplicate_observations, observation_natural_key
from storage.base import RateStore


def jsonl_partition_paths(path: Path) -> list[Path]:
    """Return deterministic JSONL inputs for a legacy file or shard directory."""
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.glob("????-??.jsonl"))
    return []


def iter_jsonl_records(path: Path) -> Iterator[dict]:
    for shard in jsonl_partition_paths(path):
        with shard.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON in {shard} line {line_number}: {exc.msg}"
                    ) from exc


def observation_month(row: RateObservation) -> str:
    queried_at = row.queried_at
    if not isinstance(queried_at, datetime):
        raise ValueError("queried_at must be a datetime")
    return queried_at.strftime("%Y-%m")


class LocalJsonlStore(RateStore):
    def __init__(self, path: Path):
        self.path = path

    def append(self, rows: list[RateObservation]) -> int:
        # A .jsonl path remains supported for tests and one-off tools. The
        # production path is a directory whose files are bounded by query
        # month so no append-only Git object can approach the 100 MiB limit.
        if self.path.suffix == ".jsonl":
            groups = {self.path: rows}
            self.path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.path.mkdir(parents=True, exist_ok=True)
            grouped: dict[str, list[RateObservation]] = defaultdict(list)
            for row in rows:
                grouped[observation_month(row)].append(row)
            groups = {
                self.path / f"{month}.jsonl": month_rows
                for month, month_rows in grouped.items()
            }

        written = 0
        for shard, shard_rows in sorted(groups.items(), key=lambda item: str(item[0])):
            existing_keys = {
                observation_natural_key(record)
                for record in iter_jsonl_records(shard)
            }
            new_rows = []
            for row in shard_rows:
                key = observation_natural_key(row)
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                new_rows.append(row)
            with shard.open("a", encoding="utf-8") as handle:
                for row in new_rows:
                    handle.write(row.model_dump_json() + "\n")
            written += len(new_rows)
        return written

    def read_all(self) -> list[RateObservation]:
        rows = [
            RateObservation.model_validate(record)
            for record in iter_jsonl_records(self.path)
        ]
        return deduplicate_observations(rows, keep="latest")
