import json

from scripts import migrate_rate_history_partitions as migration


def row(observation_id: str, queried_at: str) -> dict:
    return {"observation_id": observation_id, "queried_at": queried_at}


def test_migration_splits_monthly_history_by_query_day(monkeypatch, tmp_path):
    source = tmp_path / "rates"
    source.mkdir()
    rows = [
        row("one", "2026-10-01T01:00:00+00:00"),
        row("two", "2026-10-02T01:00:00+00:00"),
        row("three", "2026-10-02T02:00:00+00:00"),
    ]
    (source / "2026-10.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in rows), encoding="utf-8"
    )
    monkeypatch.setattr(migration, "LEGACY_SOURCE", tmp_path / "rates.jsonl")
    monkeypatch.setattr(migration, "SOURCE", source)
    monkeypatch.setattr(migration, "TEMP_TARGET", tmp_path / "rates_daily_tmp")

    migration.main()

    assert not (source / "2026-10.jsonl").exists()
    shards = sorted(source.glob("????-??/????-??-??.jsonl"))
    assert [path.name for path in shards] == [
        "2026-10-01.jsonl",
        "2026-10-02.jsonl",
    ]
    migrated = [json.loads(line) for path in shards for line in path.read_text().splitlines()]
    assert migrated == rows


def test_migration_is_idempotent_after_daily_partitioning(monkeypatch, tmp_path, capsys):
    source = tmp_path / "rates"
    shard = source / "2026-10" / "2026-10-01.jsonl"
    shard.parent.mkdir(parents=True)
    shard.write_text(json.dumps(row("one", "2026-10-01T01:00:00Z")) + "\n")
    monkeypatch.setattr(migration, "LEGACY_SOURCE", tmp_path / "rates.jsonl")
    monkeypatch.setattr(migration, "SOURCE", source)
    monkeypatch.setattr(migration, "TEMP_TARGET", tmp_path / "rates_daily_tmp")

    migration.main()

    assert "already uses 1 bounded daily shards" in capsys.readouterr().out
    assert shard.exists()
