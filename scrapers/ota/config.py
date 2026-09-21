from pathlib import Path

import yaml


def load_ota_property_mappings(
    path: Path, platform: str
) -> tuple[bool, dict[str, str]]:
    """Load one provider's enable flag and hotel-to-property mappings."""
    if not path.exists():
        return False, {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    provider = (raw.get("providers") or {}).get(platform) or {}
    properties = {
        str(hotel_id): str(property_id).strip()
        for hotel_id, property_id in (provider.get("properties") or {}).items()
        if str(property_id).strip()
    }
    return bool(provider.get("enabled", False)), properties
