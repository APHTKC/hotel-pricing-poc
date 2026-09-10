import json
from pathlib import Path

import yaml


SOURCES = (Path("config/hotels.daily.yaml"), Path("config/hotels.candidates.yaml"))
TARGET = Path("public/data/hotels.json")


def main() -> None:
    hotels: dict[str, dict] = {}
    for source in SOURCES:
        is_daily = source.name == "hotels.daily.yaml"
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
        for hotel in payload["hotels"]:
            current = hotels.get(hotel["id"], {})
            hotels[hotel["id"]] = {
                **current,
                **hotel,
                "enabled": bool(current.get("enabled") or hotel.get("enabled") or is_daily),
            }
    rows = sorted(hotels.values(), key=lambda row: (row.get("city", ""), row["name"]))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps({"hotels": rows}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Published {len(rows)} registered hotels")


if __name__ == "__main__":
    main()
