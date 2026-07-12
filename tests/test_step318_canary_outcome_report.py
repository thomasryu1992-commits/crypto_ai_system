from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.canary_outcome_report import (
    BLOCK_LIVE_CANARY_RECONCILIATION_PROMOTION_BLOCKER,
    BLOCK_LIVE_SCALED_PROMOTION_ATTEMPT,
    BLOCK_NO_LIVE_CANARY_SUBMISSION,
    BLOCK_UNSAFE_SIDE_EFFECT,
    CANARY_OUTCOME_REPORT_REGISTRY_NAME,
    RECOMMENDATION_BLOCK_LIVE_SCALED,
    RECOMMENDATION_CREATE_READINESS_CANDIDATE,
    STATUS_BLOCKED,
    STATUS_BLOCKED_UNSAFE_SIDE_EFFECT,
    STATUS_RECORDED_REVIEW_ONLY,
    CanaryOutcomeReportPolicy,
    build_canary_outcome_report,
    persist_canary_outcome_report,
    run_canary_outcome_report_latest,
)
from crypto_ai_system.registry.base_registry import load_registry_records


def _minimal_project(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "config").mkdir()
    (root / "config/settings.yaml").write_text(
        "project:\n  version: step286_researchsignal_feature_lineage_fix\nstorage:\n  registry_dir: storage/registries\n",
        encoding="utf-8",
    )
    return root


def _reconciled() -> dict:
    return {
        "live_canary_reconciliation_id": "live_rec_1",
        "status": "LIVE_CANARY_RECONCILED_REVIEW_ONLY",
        "promotion_blocker": "NO_LIVE_CANARY_PROMOTION_BLOCKER",
        "submitted_to_exchange": True,
        "exchange_order_id": "live_order_1",
        "exchange_response_hash": "hash_response",
        "paper_live_gap": 0.0,
        "slippage": 0.1,
        "latency_ms": 120,
    }


def _monitoring(critical: int = 0) -> dict:
    return {
        "monitoring_alerting_report_id": "mon_1",
        "status": "MONITORING_ALERTING_REVIEW_ONLY_RECORDED",
        "alert_count": 2,
        "critical_alert_count": critical,
        "api_error_count": 0,
    }


def _runbook() -> dict:
    return {
        "deployment_runbook_id": "runbook_1",
        "status": "DEPLOYMENT_RUNBOOK_REVIEW_ONLY_RECORDED",
        "deployment_ready": False,
        "live_canary_deployment_ready": False,
        "live_scaled_deployment_ready": False,
    }


def test_step318_records_review_only_canary_outcome_without_live_scaled_promotion() -> None:
    report = build_canary_outcome_report(
        live_canary_reconciliation=_reconciled(),
        monitoring_alerting=_monitoring(),
        deployment_runbook=_runbook(),
    )

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["live_scaled_readiness_recommendation"] == RECOMMENDATION_CREATE_READINESS_CANDIDATE
    assert report["orders_submitted_count"] == 1
    assert report["orders_reconciled_count"] == 1
    assert report["live_scaled_promotion_allowed_by_this_module"] is False
    assert report["live_trading_allowed_by_this_module"] is False
    assert report["runtime_settings_mutated"] is False


def test_step318_blocks_no_submission_and_reconciliation_promotion_blocker() -> None:
    rec = {
        "live_canary_reconciliation_id": "live_rec_blocked",
        "status": "LIVE_CANARY_RECONCILIATION_BLOCKED_NO_SUBMISSION",
        "promotion_blocker": "BLOCK_LIVE_CANARY_PROMOTION_EXECUTION_NOT_SUBMITTED",
        "submitted_to_exchange": False,
    }
    report = build_canary_outcome_report(
        live_canary_reconciliation=rec,
        monitoring_alerting=_monitoring(),
        deployment_runbook=_runbook(),
    )

    assert report["status"] == STATUS_BLOCKED
    assert BLOCK_NO_LIVE_CANARY_SUBMISSION in report["blocked_reasons"]
    assert BLOCK_LIVE_CANARY_RECONCILIATION_PROMOTION_BLOCKER in report["blocked_reasons"]
    assert report["live_scaled_readiness_recommendation"] == RECOMMENDATION_BLOCK_LIVE_SCALED
    assert report["live_scaled_promotion_allowed"] is False


def test_step318_blocks_critical_monitoring_alerts() -> None:
    report = build_canary_outcome_report(
        live_canary_reconciliation=_reconciled(),
        monitoring_alerting=_monitoring(critical=1),
        deployment_runbook=_runbook(),
    )

    assert report["status"] == STATUS_BLOCKED
    assert "STEP318_BLOCK_MONITORING_CRITICAL_ALERTS" in report["blocked_reasons"]
    assert report["monitoring_critical_alert_count"] == 1


def test_step318_blocks_live_scaled_promotion_attempts() -> None:
    report = build_canary_outcome_report(
        live_canary_reconciliation={**_reconciled(), "live_scaled_promotion_allowed_by_this_module": True},
        monitoring_alerting=_monitoring(),
        deployment_runbook=_runbook(),
    )

    assert report["status"] == STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert BLOCK_UNSAFE_SIDE_EFFECT in report["blocked_reasons"]
    assert BLOCK_LIVE_SCALED_PROMOTION_ATTEMPT in report["blocked_reasons"]
    assert report["live_scaled_promotion_allowed_by_this_module"] is False


def test_step318_persists_report_and_registry(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    cfg = load_config(root)
    report = build_canary_outcome_report(
        live_canary_reconciliation=_reconciled(),
        monitoring_alerting=_monitoring(),
        deployment_runbook=_runbook(),
    )
    persisted = persist_canary_outcome_report(cfg, report)

    assert persisted["canary_outcome_report_registry_record_id"]
    assert (root / "storage/latest/canary_outcome_report.json").exists()
    assert (root / "storage/latest/canary_outcome_report_registry_record.json").exists()
    assert (root / "storage/canary_outcome_report/canary_outcome_report.json").exists()
    records = load_registry_records(root / "storage/registries" / f"{CANARY_OUTCOME_REPORT_REGISTRY_NAME}.jsonl")
    assert len(records) == 1
    assert records[0]["canary_outcome_report_registry_record_sha256"]


def test_step318_run_latest_reads_live_canary_monitoring_and_runbook_evidence(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    latest = root / "storage/latest"
    latest.mkdir(parents=True)
    atomic_write_json(latest / "live_canary_reconciliation_record.json", _reconciled())
    atomic_write_json(latest / "monitoring_alerting_report.json", _monitoring())
    atomic_write_json(latest / "deployment_runbook_manifest.json", _runbook())

    result = run_canary_outcome_report_latest(project_root=root)

    assert result["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert result["live_canary_reconciliation_id"] == "live_rec_1"
    assert result["monitoring_alerting_report_id"] == "mon_1"
    assert result["deployment_runbook_id"] == "runbook_1"
    assert result["live_scaled_readiness_candidate_created"] is False


def test_step318_policy_never_enables_runtime_side_effects() -> None:
    report = build_canary_outcome_report(
        live_canary_reconciliation=_reconciled(),
        monitoring_alerting=_monitoring(),
        deployment_runbook=_runbook(),
        policy=CanaryOutcomeReportPolicy(live_scaled_promotion_allowed=True),
    )

    assert report["status"] == STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert report["live_scaled_promotion_allowed_by_this_module"] is False
    assert report["live_trading_allowed_by_this_module"] is False
    assert report["api_key_value_access_allowed"] is False
    assert report["secret_file_access_allowed"] is False
