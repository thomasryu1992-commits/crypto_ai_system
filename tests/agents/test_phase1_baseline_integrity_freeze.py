from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.baseline_integrity_freeze import (
    STATUS_BASELINE_INTEGRITY_FROZEN_REVIEW_ONLY,
    build_baseline_integrity_freeze_report,
    persist_baseline_integrity_freeze_report,
)
from crypto_ai_system.registry.base_registry import load_registry_records


def test_phase1_baseline_integrity_freeze_report_passes_review_only() -> None:
    root = Path.cwd()
    report = build_baseline_integrity_freeze_report(project_root=root)

    assert report["status"] == STATUS_BASELINE_INTEGRITY_FROZEN_REVIEW_ONLY
    assert report["passed"] is True
    assert report["blocked"] is False
    assert report["review_only"] is True
    assert report["runtime_permission_source"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["order_submission_performed"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["signed_testnet_unlock_authority"] is False
    assert report["live_execution_unlock_authority"] is False
    assert report["checks"]["agent_count_at_least_21"] is True
    assert report["checks"]["review_packet_agent_library_evidence_included"] is True
    assert report["checks"]["live_scaled_readiness_blocked"] is True
    assert report["missing_latest_evidence_files"] == []
    assert report["missing_source_files"] == []
    assert report["unsafe_runtime_flags"] == []


def test_phase1_baseline_integrity_freeze_persists_latest_and_registry() -> None:
    root = Path.cwd()
    cfg = load_config(root)
    report = persist_baseline_integrity_freeze_report(cfg=cfg, project_root=root)

    latest_report = root / "storage" / "latest" / "baseline_integrity_freeze_report.json"
    latest_registry_record = root / "storage" / "latest" / "baseline_integrity_freeze_registry_record.json"
    registry = root / "storage" / "registries" / "baseline_integrity_freeze_registry.jsonl"

    assert report["passed"] is True
    assert latest_report.exists()
    assert latest_registry_record.exists()
    assert registry.exists()
    records = load_registry_records(registry)
    assert records
    assert records[-1]["baseline_integrity_freeze_sha256"] == report["baseline_integrity_freeze_sha256"]
