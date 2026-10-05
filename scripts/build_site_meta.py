import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


LATEST_SOURCE = Path("public/data/latest_summary.json")
TARGET = Path("public/data/site_meta.json")


def _latest_data_timestamp(path: Path | None = None) -> str | None:
    path = path or LATEST_SOURCE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    timestamp = payload.get("latest_queried_at")
    return timestamp if isinstance(timestamp, str) and timestamp else None


def build_site_meta(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    taipei_now = now.astimezone(timezone(timedelta(hours=8)))
    commit = (os.getenv("GITHUB_SHA") or "local").strip()
    run_id = (os.getenv("GITHUB_RUN_ID") or "local").strip()
    return {
        "schema_version": "1.0",
        "version": f"v{taipei_now:%Y.%m.%d}",
        "build": commit[:7] if commit != "local" else "local",
        "deployment_run": run_id,
        "published_at": now.isoformat(),
        "data_updated_at": _latest_data_timestamp(),
    }


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(build_site_meta(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote deployment metadata to {TARGET}")


if __name__ == "__main__":
    main()
