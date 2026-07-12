from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_scaled_readiness_gate import (
    BLOCK_CANARY_OUTCOME_HAS_BLOCKERS,
    BLOCK_CANARY_OUTCOME_NOT_READY,
    BLOCK_LIVE_SCALED_PROMOTION_ATTEMPT,
    BLOCK_MISSING_OPERATOR_LIVE_SCALED_REVIEW_REQUEST,
    BLOCK_NO_LIVE_CANARY_SUBMISSION,
    BLOCK_UNSAFE_SIDE_EFFECT,
    DECISION_BLOCK,
    DECISION_REVIEW_READY,
    LIVE_SCALED_READINESS_GATE_REGISTRY_NAME,
    STATUS_BLOCKED,
    STATUS_BLOCKED_UNSAFE_SIDE_EFFECT,
    STATUS_READY_REVIEW_ONLY,
    LiveScaledReadinessGatePolicy,
    build_live_scaled_readiness_gate,
    persist_live_scaled_readiness_gate,
    run_live_scaled_readiness_gate_latest,
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


def _ready_canary() -> dict:
    return {
        "canary_outcome_report_id": "canary_report_1",
        "status": "CANARY_OUTCOME_REPORT_REVIEW_ONLY_RECORDED",
        "live_scaled_readiness_recommendation": "create_live_scaled_readiness_gate_candidate_review_only",
        "blocked_reasons": [],
        "orders_submitted_count": 1,
        "orders_reconciled_count": 1,
        "reconciliation_mismatch_count": 0,
        "monitoring_critical_alert_count": 0,
        "live_scaled_deployment_ready": True,
        "paper_live_gap": 0.0,
        "slippage": 0.0,
        "latency_ms": 0.0,
        "api_error_count": 0,
        "manual_override_count": 0,
    }


def _operator_request() -> dict:
    return {
        "operator_live_scaled_review_request_id": "op_live_scaled_1",
        "target_stage": "live_scaled_readiness",
        "operator_id": "operator_1",
        "ticket_or_signature": "TICKET-319",
        "canonical_utc_timestamp": "2026-07-01T00:00:00Z",
        "acknowledge_review_only_gate": True,
        "request_live_scaled_promotion_allowed": False,
        "request_live_scaled_execution_enabled": False,
        "request_live_order_submission_allowed": False,
        "request_place_order_enabled": False,
    }


def test_step319_ready_gate_is_review_only_and_does_not_promote() -> None:
    gate = build_live_scaled_readiness_gate(
        canary_outcome_report=_ready_canary(),
        operator_live_scaled_review_request=_operator_request(),
    )

    assert gate["status"] == STATUS_READY_REVIEW_ONLY
    assert gate["gate_decision"] == DECISION_REVIEW_READY
    assert gate["readiness_passed_review_only"] is True
    assert gate["live_scaled_readiness_candidate_created"] is False
    assert gate["live_scaled_promotion_allowed_by_this_module"] is False
    assert gate["live_scaled_execution_enabled_by_this_module"] is False
    assert gate["live_trading_allowed_by_this_module"] is False
    assert gate["runtime_settings_mutated"] is False


def test_step319_blocks_current_no_submission_canary_outcome() -> None:
    blocked_canary = {
        **_ready_canary(),
        "status": "CANARY_OUTCOME_REPORT_BLOCKED",
        "live_scaled_readiness_recommendation": "block_live_scaled_readiness",
        "blocked_reasons": ["STEP318_BLOCK_NO_LIVE_CANARY_SUBMISSION"],
        "orders_submitted_count": 0,
        "orders_reconciled_count": 0,
        "live_scaled_deployment_ready": False,
    }
    gate = build_live_scaled_readiness_gate(
        canary_outcome_report=blocked_canary,
        operator_live_scaled_review_request={},
    )

    assert gate["status"] == STATUS_BLOCKED
    assert gate["gate_decision"] == DECISION_BLOCK
    assert BLOCK_CANARY_OUTCOME_NOT_READY in gate["blocked_reasons"]
    assert BLOCK_CANARY_OUTCOME_HAS_BLOCKERS in gate["blocked_reasons"]
    assert BLOCK_NO_LIVE_CANARY_SUBMISSION in gate["blocked_reasons"]
    assert BLOCK_MISSING_OPERATOR_LIVE_SCALED_REVIEW_REQUEST in gate["blocked_reasons"]
    assert gate["live_scaled_promotion_allowed"] is False


def test_step319_blocks_live_scaled_promotion_attempt() -> None:
    gate = build_live_scaled_readiness_gate(
        canary_outcome_report={**_ready_canary(), "live_scaled_promotion_allowed_by_this_module": True},
        operator_live_scaled_review_request=_operator_request(),
    )

    assert gate["status"] == STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert BLOCK_UNSAFE_SIDE_EFFECT in gate["blocked_reasons"]
    assert BLOCK_LIVE_SCALED_PROMOTION_ATTEMPT in gate["blocked_reasons"]
    assert gate["live_scaled_promotion_allowed_by_this_module"] is False


def test_step319_policy_never_enables_live_execution() -> None:
    gate = build_live_scaled_readiness_gate(
        canary_outcome_report=_ready_canary(),
        operator_live_scaled_review_request=_operator_request(),
        policy=LiveScaledReadinessGatePolicy(live_scaled_execution_enabled=True),
    )

    assert gate["status"] == STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert BLOCK_UNSAFE_SIDE_EFFECT in gate["blocked_reasons"]
    assert gate["live_scaled_execution_enabled_by_this_module"] is False
    assert gate["live_order_submission_allowed"] is False
    assert gate["api_key_value_access_allowed"] is False


def test_step319_persists_gate_and_registry(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    cfg = load_config(root)
    gate = build_live_scaled_readiness_gate(
        canary_outcome_report=_ready_canary(),
        operator_live_scaled_review_request=_operator_request(),
    )
    persisted = persist_live_scaled_readiness_gate(cfg, gate)

    assert persisted["live_scaled_readiness_gate_registry_record_id"]
    assert (root / "storage/latest/live_scaled_readiness_gate.json").exists()
    assert (root / "storage/latest/live_scaled_readiness_gate_registry_record.json").exists()
    assert (root / "storage/live_scaled_readiness_gate/live_scaled_readiness_gate.json").exists()
    records = load_registry_records(root / "storage/registries" / f"{LIVE_SCALED_READINESS_GATE_REGISTRY_NAME}.jsonl")
    assert len(records) == 1
    assert records[0]["live_scaled_readiness_gate_registry_record_sha256"]


def test_step319_run_latest_reads_canary_and_operator_evidence(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    latest = root / "storage/latest"
    latest.mkdir(parents=True)
    atomic_write_json(latest / "canary_outcome_report.json", _ready_canary())
    atomic_write_json(latest / "operator_live_scaled_review_request.json", _operator_request())

    gate = run_live_scaled_readiness_gate_latest(project_root=root)

    assert gate["status"] == STATUS_READY_REVIEW_ONLY
    assert gate["canary_outcome_report_id"] == "canary_report_1"
    assert gate["operator_live_scaled_review_request_id"] == "op_live_scaled_1"
    assert gate["live_scaled_promotion_allowed_by_this_module"] is False
