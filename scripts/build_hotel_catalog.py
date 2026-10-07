import json
from datetime import UTC, datetime
from pathlib import Path

import yaml


SOURCES = (Path("config/hotels.daily.yaml"), Path("config/hotels.candidates.yaml"))
OPENINGS_SOURCE = Path("config/hotel_openings.yaml")
TARGET = Path("public/data/hotels.json")
LOCATION_TARGET = Path("public/data/hotel_locations.json")


def sync_location_tracking(rows: list[dict], target: Path = LOCATION_TARGET) -> None:
    """Keep cached map coordinates while deriving tracking state from Catalog."""

    if not target.exists():
        return
    payload = json.loads(target.read_text(encoding="utf-8"))
    locations = payload.get("locations") or []
    enabled_by_id = {row["id"]: bool(row.get("enabled")) for row in rows}
    location_ids = {row.get("hotel_id") for row in locations}
    if location_ids != set(enabled_by_id):
        missing = sorted(set(enabled_by_id) - location_ids)
        extra = sorted(location_ids - set(enabled_by_id))
        raise ValueError(
            f"Hotel-location cache mismatch; missing={missing}, extra={extra}"
        )
    changed = False
    for location in locations:
        tracked = enabled_by_id[location["hotel_id"]]
        if location.get("daily_tracked") is not tracked:
            location["daily_tracked"] = tracked
            changed = True
    if changed:
        payload["updated_at"] = datetime.now(UTC).isoformat()
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


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
    sync_location_tracking(rows)
    print(f"Published {len(rows)} registered hotels")


if __name__ == "__main__":
    main()
