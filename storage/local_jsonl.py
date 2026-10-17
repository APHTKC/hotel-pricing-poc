import json
from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from app.models import RateObservation
from services.deduplication import deduplicate_observations, observation_natural_key
from storage.base import RateStore


def jsonl_partition_paths(path: Path) -> list[Path]:
    """Return deterministic inputs for legacy, monthly, or bounded daily shards."""
    if path.is_file():
        return [path]
    if path.is_dir():
        monthly = path.glob("????-??.jsonl")
        daily = path.glob("????-??/????-??-??.jsonl")
        return sorted([*monthly, *daily])
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


def observation_partition(row: RateObservation) -> tuple[str, str]:
    queried_at = row.queried_at
    if not isinstance(queried_at, datetime):
        raise ValueError("queried_at must be a datetime")
    return queried_at.strftime("%Y-%m"), queried_at.strftime("%Y-%m-%d")


class LocalJsonlStore(RateStore):
    def __init__(self, path: Path):
        self.path = path

    def append(self, rows: list[RateObservation]) -> int:
        # A .jsonl path remains supported for tests and one-off tools. The
        # production path is a month/day hierarchy. Daily files keep every Git
        # object bounded even when a high-volume month continues to grow.
        if self.path.suffix == ".jsonl":
            groups = {self.path: rows}
            self.path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.path.mkdir(parents=True, exist_ok=True)
            grouped: dict[tuple[str, str], list[RateObservation]] = defaultdict(list)
            for row in rows:
                grouped[observation_partition(row)].append(row)
            groups = {
                self.path / month / f"{day}.jsonl": partition_rows
                for (month, day), partition_rows in grouped.items()
            }

        written = 0
        for shard, shard_rows in sorted(groups.items(), key=lambda item: str(item[0])):
            shard.parent.mkdir(parents=True, exist_ok=True)
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
