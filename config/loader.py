import os
from pathlib import Path

import yaml

from app.models import Hotel


def load_hotels(path: Path | None = None) -> list[Hotel]:
    path = path or Path(os.getenv("HOTELS_CONFIG_PATH", "config/hotels.yaml"))
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Hotel(**item) for item in raw["hotels"]]
