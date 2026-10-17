"""Content-version manifest for cacheable public JSON assets."""

from __future__ import annotations

import hashlib
from pathlib import Path


EXCLUDED_NAMES = {"asset_manifest.json", "site_meta.json"}


def build_asset_manifest(public_root: Path) -> dict:
    assets = {}
    data_root = public_root / "data"
    for path in sorted(data_root.rglob("*.json")):
        if path.name in EXCLUDED_NAMES:
            continue
        relative = path.relative_to(public_root).as_posix()
        content = path.read_bytes()
        assets[relative] = {
            "sha256": hashlib.sha256(content).hexdigest()[:16],
            "bytes": len(content),
        }
    return {"schema_version": "1.0", "assets": assets}
