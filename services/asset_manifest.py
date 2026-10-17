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
        # GitHub Pages deploys the checked-out Git blobs, whose text files use
        # LF.  Normalize Windows working-tree CRLF before hashing so the
        # version token is identical locally and on the Linux runner.
        content = path.read_bytes().replace(b"\r\n", b"\n")
        assets[relative] = {
            "sha256": hashlib.sha256(content).hexdigest()[:16],
            "bytes": len(content),
        }
    return {"schema_version": "1.0", "assets": assets}
