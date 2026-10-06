import json
from pathlib import Path

import yaml


SOURCES = (Path("config/hotels.daily.yaml"), Path("config/hotels.candidates.yaml"))
OPENINGS_SOURCE = Path("config/hotel_openings.yaml")
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
    openings = yaml.safe_load(OPENINGS_SOURCE.read_text(encoding="utf-8"))["hotels"]
    opening_by_id = {row["id"]: row for row in openings}
    unknown_ids = sorted(set(opening_by_id) - set(hotels))
    if unknown_ids:
        raise ValueError(f"Opening-year records reference unknown hotels: {', '.join(unknown_ids)}")
    for hotel_id, hotel in hotels.items():
        opening = opening_by_id.get(hotel_id)
        if opening:
            hotel.update({key: value for key, value in opening.items() if key != "id"})
    rows = sorted(hotels.values(), key=lambda row: (row.get("city", ""), row["name"]))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps({"hotels": rows}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Published {len(rows)} registered hotels")


if __name__ == "__main__":
    main()
