from pathlib import Path


WORKFLOW = Path(".github/workflows/daily-capella.yml")
PUBLISH_WORKFLOW = Path(".github/workflows/publish-dashboard.yml")


def test_daily_workflow_avoids_top_of_hour_schedule() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'cron: "17 22 * * *"' in workflow
    assert 'cron: "0 22 * * *"' not in workflow


def test_daily_workflow_allows_release_validation_to_finish() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "timeout-minutes: 45" in workflow
    assert "timeout-minutes: 30" not in workflow
    assert "enough room to save" in workflow


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

    assert "git add data/rates " in checkpoint
    assert "data/adapter_health.json" in checkpoint
    assert "public/data/fx.json" in checkpoint
    assert "git add public/data" not in checkpoint


def test_daily_workflow_tests_before_each_commit_and_before_pages_upload() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    source_test = workflow.index("- name: Validate collected source data")
    checkpoint = workflow.index("- name: Checkpoint collected source data")
    release_test = workflow.index("- name: Validate release artifacts")
    save = workflow.index("- name: Save new rate history")
    upload = workflow.index("- name: Upload dashboard")

    assert source_test < checkpoint
    assert release_test < save < upload
    assert workflow.count("run: python -m pytest -q") == 2


def test_daily_workflow_builds_and_commits_verified_parquet_mirror() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    deduplicate = workflow.index("python -m scripts.deduplicate_rate_history")
    warehouse = workflow.index("python -m scripts.build_rate_warehouse")
    static = workflow.index("python -m scripts.build_static_data")
    release_test = workflow.index("- name: Validate release artifacts")
    save = workflow.index("- name: Save new rate history")

    assert deduplicate < warehouse < static < release_test < save
    assert "git add data/rates data/warehouse data/adapter_health.json public/data" in workflow


def test_daily_workflow_finalizes_catalog_before_content_hash_manifest() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    catalog = workflow.index("python -m scripts.build_hotel_catalog")
    static = workflow.index("python -m scripts.build_static_data")
    release_test = workflow.index("- name: Validate release artifacts")

    assert catalog < static < release_test


def test_dashboard_publish_is_blocked_by_full_test_suite() -> None:
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    install = workflow.index("- name: Install project")
    test = workflow.index("- name: Validate dashboard release")
    metadata = workflow.index("- name: Generate deployment metadata")
    upload = workflow.index("uses: actions/upload-pages-artifact@v3")

    assert install < test < metadata < upload
    assert "run: python -m pytest -q" in workflow
