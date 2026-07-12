from __future__ import annotations

from pathlib import Path

from crypto_ai_system.execution.deployment_runbook import (
    BLOCK_DEPLOYMENT_EXECUTION_ATTEMPT,
    BLOCK_SECRET_VALUE_ACCESS,
    DEPLOYMENT_RUNBOOK_REGISTRY_NAME,
    REQUIRED_SECTION_IDS,
    STATUS_BLOCKED_UNSAFE_SIDE_EFFECT,
    STATUS_RECORDED_REVIEW_ONLY,
    DeploymentRunbookPolicy,
    build_deployment_runbook,
    persist_deployment_runbook,
    run_deployment_runbook_latest,
)
from crypto_ai_system.registry.base_registry import load_registry_records
from crypto_ai_system.config import load_config


def _minimal_project(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "config").mkdir()
    (root / "config/settings.yaml").write_text("project:\n  version: step286_researchsignal_feature_lineage_fix\nstorage:\n  registry_dir: storage/registries\n", encoding="utf-8")
    return root


def test_step317_builds_review_only_runbook_with_required_sections() -> None:
    runbook = build_deployment_runbook(monitoring_alerting={"monitoring_alerting_report_id": "mon_1", "status": "MONITORING_ALERTING_REVIEW_ONLY_RECORDED", "alert_count": 3})

    assert runbook["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert runbook["deployment_ready"] is False
    assert runbook["live_canary_deployment_ready"] is False
    assert runbook["live_scaled_deployment_ready"] is False
    assert runbook["missing_required_section_ids"] == []
    assert {section["section_id"] for section in runbook["sections"]} == set(REQUIRED_SECTION_IDS)
    assert "Environment setup" in runbook["deployment_runbook_markdown"]
    assert runbook["safety_flags"]["server_deployment_performed"] is False
    assert runbook["safety_flags"]["api_key_value_access_allowed"] is False


def test_step317_blocks_deployment_and_secret_side_effects() -> None:
    runbook = build_deployment_runbook(policy=DeploymentRunbookPolicy(deployment_execution_enabled=True, api_secret_value_access_allowed=True))

    assert runbook["status"] == STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert BLOCK_DEPLOYMENT_EXECUTION_ATTEMPT in runbook["blocked_reasons"]
    assert BLOCK_SECRET_VALUE_ACCESS in runbook["blocked_reasons"]
    assert runbook["deployment_ready"] is False
    assert runbook["safety_flags"]["live_order_submission_allowed"] is False


def test_step317_persists_runbook_manifest_markdown_and_registry(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    cfg = load_config(root)
    runbook = build_deployment_runbook(monitoring_alerting={"monitoring_alerting_report_id": "mon_2", "status": "MONITORING_ALERTING_REVIEW_ONLY_RECORDED"})
    persisted = persist_deployment_runbook(cfg, runbook)

    assert persisted["deployment_runbook_registry_record_id"]
    assert (root / "storage/latest/deployment_runbook_manifest.json").exists()
    assert (root / "storage/latest/deployment_runbook_registry_record.json").exists()
    assert (root / "storage/deployment_runbook/DEPLOYMENT_RUNBOOK_STEP317.md").exists()
    assert (root / "docs/DEPLOYMENT_RUNBOOK_STEP317.md").exists()
    records = load_registry_records(root / "storage/registries" / f"{DEPLOYMENT_RUNBOOK_REGISTRY_NAME}.jsonl")
    assert len(records) == 1
    assert records[0]["deployment_runbook_registry_record_sha256"]


def test_step317_run_latest_reads_monitoring_evidence(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    latest = root / "storage/latest"
    latest.mkdir(parents=True)
    from core.json_io import atomic_write_json
    atomic_write_json(latest / "monitoring_alerting_report.json", {"monitoring_alerting_report_id": "mon_latest", "status": "MONITORING_ALERTING_REVIEW_ONLY_RECORDED", "alert_count": 7})

    result = run_deployment_runbook_latest(project_root=root)

    assert result["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert result["monitoring_alerting_report_id"] == "mon_latest"
    assert result["monitoring_alerting_alert_count"] == 7
    assert result["server_deployment_performed"] is False
    assert result["live_order_submission_allowed"] is False
