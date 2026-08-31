import json
from pathlib import Path

from app.models import RateObservation
from storage.base import RateStore


class LocalJsonlStore(RateStore):
    def __init__(self, path: Path):
        self.path = path

    def append(self, rows: list[RateObservation]) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(row.model_dump_json() + "\n")
        return len(rows)

    def read_all(self) -> list[RateObservation]:
        if not self.path.exists():
            return []
        return [
            RateObservation.model_validate(json.loads(line))
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
