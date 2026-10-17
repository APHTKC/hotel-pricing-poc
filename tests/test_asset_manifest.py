import hashlib
import json
from pathlib import Path

from services.asset_manifest import build_asset_manifest


def test_asset_manifest_matches_published_json_content():
    published = json.loads(Path("public/data/asset_manifest.json").read_text(encoding="utf-8"))
    assert published == build_asset_manifest(Path("public"))
    assert "data/latest_details/index.json" in published["assets"]
    assert "data/latest_details.json" not in published["assets"]
    assert "data/rates/index.json" in published["assets"]
    assert "data/asset_manifest.json" not in published["assets"]
    assert "data/site_meta.json" not in published["assets"]

    details = Path("public/data/latest_details/index.json").read_bytes()
    assert published["assets"]["data/latest_details/index.json"] == {
        "sha256": hashlib.sha256(details).hexdigest()[:16],
        "bytes": len(details),
    }


def test_asset_manifest_hash_is_independent_of_windows_line_endings(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.json").write_bytes(b'{\r\n  "ok": true\r\n}\r\n')
    normalized = b'{\n  "ok": true\n}\n'

    manifest = build_asset_manifest(tmp_path)

    assert manifest["assets"]["data/sample.json"] == {
        "sha256": hashlib.sha256(normalized).hexdigest()[:16],
        "bytes": len(normalized),
    }


def test_dashboard_uses_content_versioned_shared_loader():
    loader = Path("public/assets/js/data-loader.js").read_text(encoding="utf-8")
    assert "asset_manifest.json" in loader
    assert "force-cache" in loader
    assert "Date.now()" not in loader
    assert "no-store" not in loader

    for page in ("index.html", "history.html", "hotels.html", "map.html"):
        html = Path("public", page).read_text(encoding="utf-8")
        assert './assets/js/data-loader.js' in html
        assert "window.HotelDataLoader.loadJson" in html
