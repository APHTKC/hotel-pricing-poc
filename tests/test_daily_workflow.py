from pathlib import Path


WORKFLOW = Path(".github/workflows/daily-capella.yml")


def test_daily_workflow_avoids_top_of_hour_schedule() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'cron: "17 22 * * *"' in workflow
    assert 'cron: "0 22 * * *"' not in workflow


def test_daily_workflow_rebases_before_generating_dashboard_shards() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    checkpoint = workflow.index("- name: Checkpoint collected source data")
    pull = workflow.index("git pull --rebase origin main", checkpoint)
    build = workflow.index("- name: Build static dashboard data")
    save = workflow.index("- name: Save new rate history")
    push = workflow.index("git push", save)

    assert checkpoint < pull < build < save < push


def test_daily_workflow_checkpoints_only_authoritative_collector_outputs() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    checkpoint = workflow.split("- name: Checkpoint collected source data", 1)[1].split(
        "- name: Build static dashboard data", 1
    )[0]

    assert "data/rates.jsonl" in checkpoint
    assert "data/adapter_health.json" in checkpoint
    assert "public/data/fx.json" in checkpoint
    assert "git add public/data" not in checkpoint
