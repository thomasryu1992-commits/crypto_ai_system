from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.signed_testnet_order_executor import STATUS_BLOCKED, STATUS_SUBMITTED
from crypto_ai_system.execution.signed_testnet_reconciliation import (
    PROMOTION_BLOCKER_EVIDENCE_MISSING,
    PROMOTION_BLOCKER_EXECUTION_NOT_SUBMITTED,
    PROMOTION_BLOCKER_MISMATCH,
    PROMOTION_BLOCKER_NONE,
    PROMOTION_BLOCKER_UNSAFE_SIDE_EFFECT,
    STATUS_BLOCKED_EVIDENCE_MISSING,
    STATUS_BLOCKED_NO_SUBMISSION,
    STATUS_BLOCKED_UNSAFE_SIDE_EFFECT,
    STATUS_MISMATCH,
    STATUS_RECONCILED,
    STEP309_SIGNED_TESTNET_RECONCILIATION_VERSION,
    SignedTestnetReconciliationPolicy,
    build_signed_testnet_reconciliation_record,
    persist_signed_testnet_reconciliation_record,
    run_signed_testnet_reconciliation_latest,
)
from crypto_ai_system.utils.audit import sha256_json


def _payload() -> dict:
    payload = {
        "order_intent_id": "order_intent_step309_unit",
        "decision_id": "decision_step309_unit",
        "risk_gate_id": "risk_gate_step309_unit",
        "research_signal_id": "research_signal_step309_unit",
        "profile_id": "profile_step309_unit",
        "venue": "binance_futures_testnet",
        "environment": "testnet",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quantity": 0.001,
        "idempotency_key": "idem_step309_unit",
        "would_submit_only": True,
    }
    payload["would_submit_order_payload_sha256"] = sha256_json(payload)
    return payload


def _submitted_execution(payload: dict | None = None) -> dict:
    payload = dict(payload or _payload())
    execution = {
        "version": "step308_first_signed_testnet_order_executor_v1",
        "signed_testnet_execution_id": "execution_step309_unit",
        "execution_id": "execution_step309_unit",
        "status": STATUS_SUBMITTED,
        "state": "SIGNED_TESTNET_SUBMITTED",
        "submitted_to_exchange": True,
        "actual_submission_performed": False,
        "external_order_submission_performed": False,
        "adapter_called_for_write": False,
        "exchange_order_id": "testnet_exchange_order_step309",
        "exchange_response_hash": sha256_json({"exchange_order_id": "testnet_exchange_order_step309", "status": "FILLED"}),
        "request_hash": sha256_json(payload),
        "idempotency_key": payload["idempotency_key"],
        "order_intent_id": payload["order_intent_id"],
        "decision_id": payload["decision_id"],
        "risk_gate_id": payload["risk_gate_id"],
        "research_signal_id": payload["research_signal_id"],
        "profile_id": payload["profile_id"],
        "would_submit_order_payload_sha256": payload["would_submit_order_payload_sha256"],
        "would_submit_order_payload": payload,
        "signed_testnet_order_executor_record_sha256": "executor_record_hash_step309",
        "signed_testnet_order_lifecycle_record_id": "lifecycle_record_step309",
        "signed_testnet_order_lifecycle_record_sha256": "lifecycle_record_hash_step309",
        "lifecycle_events": [
            {"state": "SIGNED_TESTNET_ORDER_INTENT_RECEIVED"},
            {"state": "SIGNED_TESTNET_PRE_SUBMIT_VALIDATED"},
            {"state": "SIGNED_TESTNET_ENABLEMENT_CHECKED"},
            {"state": "SIGNED_TESTNET_FETCHED_STATUS"},
            {"state": "SIGNED_TESTNET_RECONCILIATION_REQUIRED"},
        ],
        "canonical_id_chain": {
            "order_intent_id": payload["order_intent_id"],
            "decision_id": payload["decision_id"],
            "risk_gate_id": payload["risk_gate_id"],
            "research_signal_id": payload["research_signal_id"],
            "profile_id": payload["profile_id"],
        },
        "missing_canonical_id_fields": [],
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    return execution


def test_step309_reconciles_submitted_testnet_execution_review_only() -> None:
    payload = _payload()
    execution = _submitted_execution(payload)
    record = build_signed_testnet_reconciliation_record(execution_record=execution, would_submit_payload=payload)

    assert record["version"] == STEP309_SIGNED_TESTNET_RECONCILIATION_VERSION
    assert record["status"] == STATUS_RECONCILED
    assert record["promotion_blocked"] is False
    assert record["promotion_blocker"] == PROMOTION_BLOCKER_NONE
    assert record["submitted_to_exchange"] is True
    assert record["exchange_order_id"] == "testnet_exchange_order_step309"
    assert record["testnet_promotion_allowed_by_this_module"] is False
    assert record["live_trading_allowed_by_this_module"] is False


def test_step309_blocks_disabled_no_submission_execution() -> None:
    payload = _payload()
    execution = _submitted_execution(payload)
    execution.update({
        "status": STATUS_BLOCKED,
        "state": "SIGNED_TESTNET_SUBMISSION_BLOCKED_DISABLED",
        "submitted_to_exchange": False,
        "exchange_order_id": None,
        "exchange_response_hash": None,
        "lifecycle_events": [{"state": "SIGNED_TESTNET_SUBMISSION_BLOCKED_DISABLED"}],
    })
    record = build_signed_testnet_reconciliation_record(execution_record=execution, would_submit_payload=payload)

    assert record["status"] == STATUS_BLOCKED_NO_SUBMISSION
    assert record["promotion_blocked"] is True
    assert record["promotion_blocker"] == PROMOTION_BLOCKER_EXECUTION_NOT_SUBMITTED
    assert record["external_execution_sync_performed"] is False
    assert record["external_order_submission_performed_by_this_module"] is False


def test_step309_blocks_missing_execution_evidence() -> None:
    record = build_signed_testnet_reconciliation_record(execution_record=None, would_submit_payload=None)
    assert record["status"] == STATUS_BLOCKED_EVIDENCE_MISSING
    assert record["promotion_blocker"] == PROMOTION_BLOCKER_EVIDENCE_MISSING
    assert record["promotion_blocked"] is True


def test_step309_detects_idempotency_and_request_hash_mismatch() -> None:
    payload = _payload()
    execution = _submitted_execution(payload)
    payload["idempotency_key"] = "different-idempotency-key"
    record = build_signed_testnet_reconciliation_record(execution_record=execution, would_submit_payload=payload)

    assert record["status"] == STATUS_MISMATCH
    assert record["promotion_blocker"] == PROMOTION_BLOCKER_MISMATCH
    assert "IDEMPOTENCY_KEY_MATCH" in record["failed_check_names"]
    assert "REQUEST_HASH_MATCH" in record["failed_check_names"]


def test_step309_detects_unsafe_side_effect_flags() -> None:
    payload = _payload()
    execution = _submitted_execution(payload)
    policy = SignedTestnetReconciliationPolicy(api_key_value_access_allowed=True)
    record = build_signed_testnet_reconciliation_record(execution_record=execution, would_submit_payload=payload, policy=policy)

    assert record["status"] == STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert record["promotion_blocker"] == PROMOTION_BLOCKER_UNSAFE_SIDE_EFFECT
    assert record["promotion_blocked"] is True


def test_step309_persists_registry_and_latest(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    payload = _payload()
    record = build_signed_testnet_reconciliation_record(execution_record=_submitted_execution(payload), would_submit_payload=payload)
    persisted = persist_signed_testnet_reconciliation_record(cfg, record)

    assert persisted["signed_testnet_reconciliation_registry_record_id"]
    assert (tmp_path / "storage/latest/signed_testnet_reconciliation_record.json").exists()
    assert (tmp_path / "storage/latest/signed_testnet_reconciliation_registry_record.json").exists()
    assert (tmp_path / "storage/registries/signed_testnet_reconciliation_registry.jsonl").exists()


def test_step309_latest_runner_creates_blocked_evidence(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    result = run_signed_testnet_reconciliation_latest(project_root=root)
    assert result["status"] == STATUS_BLOCKED_EVIDENCE_MISSING
    assert result["promotion_blocked"] is True
    assert (root / "storage/latest/signed_testnet_reconciliation_record.json").exists()
