import json

import pytest

from scripts.migrate_rate_natural_key_dimensions import migrate_file


def rate(**updates) -> dict:
    payload = {
        "hotel_id": "hotel",
        "check_in": "2026-10-01",
        "check_out": "2026-10-02",
        "room_type_code": "ROOM",
        "room_type_name": "Room",
        "rate_plan_code": "BAR",
        "rate_plan_name": "BAR",
        "currency": "TWD",
        "queried_at": "2026-09-24T01:00:00Z",
    }
    payload.update(updates)
    return payload


def test_migration_materializes_legacy_natural_key_defaults(tmp_path):
    path = tmp_path / "2026-09-24.jsonl"
    path.write_text(json.dumps(rate()) + "\n", encoding="utf-8")

    count, backfilled = migrate_file(path)

    migrated = json.loads(path.read_text())
    assert count == 1
    assert backfilled == {
        "source_platform": 1,
        "rooms": 1,
        "adults": 1,
        "children": 1,
    }
    assert migrated["source_platform"] == "official"
    assert migrated["rooms"] == 1
    assert migrated["adults"] == 2
    assert migrated["children"] == 0


def test_migration_refuses_to_infer_required_stay_or_currency(tmp_path):
    path = tmp_path / "2026-09-24.jsonl"
    path.write_text(json.dumps(rate(check_out=None)) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing check_out"):
        migrate_file(path)


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "2026-09-24.jsonl"
    path.write_text(
        json.dumps(
            rate(source_platform="official", rooms=1, adults=2, children=0)
        )
        + "\n",
        encoding="utf-8",
    )

    count, backfilled = migrate_file(path)

    assert count == 1
    assert not backfilled
