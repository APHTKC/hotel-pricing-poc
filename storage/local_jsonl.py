import json
from pathlib import Path

from app.models import RateObservation
from services.deduplication import deduplicate_observations, observation_natural_key
from storage.base import RateStore


class LocalJsonlStore(RateStore):
    def __init__(self, path: Path):
        self.path = path

    def append(self, rows: list[RateObservation]) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing_keys = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    existing_keys.add(observation_natural_key(json.loads(line)))
        new_rows = []
        for row in rows:
            key = observation_natural_key(row)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            new_rows.append(row)
        with self.path.open("a", encoding="utf-8") as handle:
            for row in new_rows:
                handle.write(row.model_dump_json() + "\n")
        return len(new_rows)

    def read_all(self) -> list[RateObservation]:
        if not self.path.exists():
            return []
        rows = [
            RateObservation.model_validate(json.loads(line))
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return deduplicate_observations(rows, keep="latest")
