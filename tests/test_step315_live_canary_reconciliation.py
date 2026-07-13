from __future__ import annotations

from pathlib import Path
import shutil

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.live_canary_reconciliation import (
    PROMOTION_BLOCKER_EXECUTION_NOT_SUBMITTED,
    PROMOTION_BLOCKER_MISMATCH,
    PROMOTION_BLOCKER_NONE,
    PROMOTION_BLOCKER_UNSAFE_SIDE_EFFECT,
    STATUS_BLOCKED_EVIDENCE_MISSING,
    STATUS_BLOCKED_NO_SUBMISSION,
    STATUS_BLOCKED_UNSAFE_SIDE_EFFECT,
    STATUS_MISMATCH,
    STATUS_RECONCILED,
    STEP315_LIVE_CANARY_RECONCILIATION_VERSION,
    LiveCanaryReconciliationPolicy,
    build_live_canary_reconciliation_record,
    persist_live_canary_reconciliation_record,
    run_live_canary_reconciliation_latest,
)
from crypto_ai_system.utils.audit import sha256_json, sha256_text
from core.json_io import atomic_write_json


def _payload() -> dict:
    payload = {
        "data_snapshot_id": "data_snapshot_step315",
        "feature_snapshot_id": "feature_snapshot_step315",
        "research_signal_id": "research_signal_step315",
        "profile_id": "profile_step315",
        "approval_packet_id": "approval_packet_step315",
        "approval_intake_id": "approval_intake_step315",
        "decision_id": "decision_step315",
        "risk_gate_id": "risk_gate_step315",
        "order_intent_id": "order_intent_step315",
        "execution_id": "execution_step315",
        "reconciliation_id": "reconciliation_step315",
        "venue": "binance_futures_live",
        "environment": "live_canary",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quantity": 0.0001,
        "notional_usdt": 5.0,
        "idempotency_key": "live-canary-idempotency-step315",
        "review_only": True,
        "would_submit_only": True,
        "actual_submission_performed": False,
        "external_order_submission_performed": False,
    }
    payload["live_canary_order_payload_sha256"] = sha256_json(payload)
    return payload


def _approval_packet() -> dict:
    return {
        "live_canary_approval_packet_id": "live_canary_approval_packet_step315",
        "live_canary_approval_packet_sha256": sha256_text("live_canary_approval_packet_step315"),
        "status": "LIVE_CANARY_APPROVAL_PACKET_READY_REVIEW_ONLY",
        "valid": True,
    }


def _execution(*, submitted: bool = False) -> dict:
    payload = _payload()
    status = "LIVE_CANARY_ORDER_SUBMITTED" if submitted else "NO_LIVE_CANARY_ORDER_SUBMITTED"
    execution = {
        "version": "step314_live_canary_executor_v1",
        "live_canary_execution_id": "live_canary_execution_step315",
        "execution_id": payload["execution_id"],
        "status": status,
        "state": "LIVE_CANARY_RECONCILIATION_REQUIRED" if submitted else "LIVE_CANARY_SUBMISSION_BLOCKED_DISABLED",
        "submitted_to_exchange": submitted,
        "actual_submission_performed": submitted,
        "external_order_submission_performed": submitted,
        "adapter_called_for_write": submitted,
        "exchange_order_id": "live_exchange_order_step315" if submitted else None,
        "exchange_response_hash": sha256_text("live_exchange_response_step315") if submitted else None,
        "request_hash": sha256_json(payload),
        "live_canary_approval_packet_id": _approval_packet()["live_canary_approval_packet_id"],
        "live_canary_approval_packet_sha256": _approval_packet()["live_canary_approval_packet_sha256"],
        "idempotency_key": payload["idempotency_key"],
        "order_intent_id": payload["order_intent_id"],
        "decision_id": payload["decision_id"],
        "risk_gate_id": payload["risk_gate_id"],
        "research_signal_id": payload["research_signal_id"],
        "profile_id": payload["profile_id"],
        "canonical_id_chain": {k: payload.get(k) for k in ["data_snapshot_id", "feature_snapshot_id", "research_signal_id", "profile_id", "approval_packet_id", "approval_intake_id", "decision_id", "risk_gate_id", "order_intent_id", "execution_id", "reconciliation_id"]},
        "missing_canonical_id_fields": [],
        "live_canary_order_payload": payload,
        "lifecycle_events": [
            {"state": "LIVE_CANARY_APPROVAL_PACKET_RECEIVED", "status": "VALID"},
            {"state": "LIVE_CANARY_ORDER_PAYLOAD_VALIDATED", "status": "VALID"},
            {"state": "LIVE_CANARY_RECONCILIATION_REQUIRED", "status": "REQUIRED"},
        ],
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_enabled": False,
    }
    execution["live_canary_order_executor_record_sha256"] = sha256_json(execution)
    return execution


def test_step315_blocks_no_live_canary_submission() -> None:
    record = build_live_canary_reconciliation_record(execution_record=_execution(submitted=False), approval_packet=_approval_packet())
    assert record["version"] == STEP315_LIVE_CANARY_RECONCILIATION_VERSION
    assert record["status"] == STATUS_BLOCKED_NO_SUBMISSION
    assert record["promotion_blocked"] is True
    assert record["promotion_blocker"] == PROMOTION_BLOCKER_EXECUTION_NOT_SUBMITTED
    assert record["submitted_to_exchange"] is False
    assert record["live_canary_promotion_allowed_by_this_module"] is False
    assert record["live_trading_allowed_by_this_module"] is False


def test_step315_reconciles_submitted_live_canary_review_only_evidence() -> None:
    record = build_live_canary_reconciliation_record(execution_record=_execution(submitted=True), approval_packet=_approval_packet())
    assert record["status"] == STATUS_RECONCILED
    assert record["promotion_blocked"] is False
    assert record["promotion_blocker"] == PROMOTION_BLOCKER_NONE
    assert record["exchange_order_id"] == "live_exchange_order_step315"
    assert record["live_canary_promotion_allowed_by_this_module"] is False


def test_step315_detects_payload_mismatch() -> None:
    payload = _payload()
    payload["idempotency_key"] = "different-idempotency"
    record = build_live_canary_reconciliation_record(execution_record=_execution(submitted=True), live_canary_order_payload=payload, approval_packet=_approval_packet())
    assert record["status"] == STATUS_MISMATCH
    assert record["promotion_blocker"] == PROMOTION_BLOCKER_MISMATCH
    assert "IDEMPOTENCY_KEY_MATCH" in record["failed_check_names"]


def test_step315_blocks_missing_evidence() -> None:
    record = build_live_canary_reconciliation_record(execution_record=None, live_canary_order_payload=None, approval_packet=None)
    assert record["status"] == STATUS_BLOCKED_EVIDENCE_MISSING
    assert record["promotion_blocked"] is True


def test_step315_blocks_unsafe_side_effect_flags() -> None:
    execution = _execution(submitted=True)
    execution["api_key_value_access_allowed"] = True
    record = build_live_canary_reconciliation_record(execution_record=execution, approval_packet=_approval_packet())
    assert record["status"] == STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert record["promotion_blocker"] == PROMOTION_BLOCKER_UNSAFE_SIDE_EFFECT
    assert record["unsafe_side_effect_evidence"]["api_key_value_access_allowed"] is True


def test_step315_policy_blocks_external_sync_side_effect() -> None:
    record = build_live_canary_reconciliation_record(
        execution_record=_execution(submitted=True),
        approval_packet=_approval_packet(),
        policy=LiveCanaryReconciliationPolicy(external_position_sync_performed=True),
    )
    assert record["status"] == STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert record["unsafe_side_effect_evidence"]["external_position_sync_performed_by_this_module"] is True


def test_step315_persists_reconciliation_registry(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    record = build_live_canary_reconciliation_record(execution_record=_execution(submitted=False), approval_packet=_approval_packet())
    persisted = persist_live_canary_reconciliation_record(cfg, record)
    assert persisted["live_canary_reconciliation_registry_record_id"]
    assert (tmp_path / "storage/latest/live_canary_reconciliation_record.json").exists()
    assert (tmp_path / "storage/latest/live_canary_reconciliation_registry_record.json").exists()
    assert (tmp_path / "storage/registries/live_canary_reconciliation_registry.jsonl").exists()


def test_step315_run_latest_reads_live_canary_executor_evidence(tmp_path: Path) -> None:
    shutil.copytree(Path("config"), tmp_path / "config")
    latest = tmp_path / "storage/latest"
    latest.mkdir(parents=True)
    atomic_write_json(latest / "live_canary_order_execution_record.json", _execution(submitted=False))
    atomic_write_json(latest / "live_canary_approval_packet.json", _approval_packet())
    record = run_live_canary_reconciliation_latest(project_root=tmp_path)
    assert record["status"] == STATUS_BLOCKED_NO_SUBMISSION
    assert (tmp_path / "storage/latest/live_canary_reconciliation_record.json").exists()
