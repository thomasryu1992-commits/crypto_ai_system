from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.signed_testnet_reconciliation import (
    PROMOTION_BLOCKER_EXECUTION_NOT_SUBMITTED,
    PROMOTION_BLOCKER_NONE,
    STATUS_BLOCKED_NO_SUBMISSION,
    STATUS_RECONCILED,
)
from crypto_ai_system.execution.signed_testnet_session_close_report import (
    BLOCK_EXECUTION_NOT_SUBMITTED,
    BLOCK_RECONCILIATION_PROMOTION_BLOCKED,
    BLOCK_UNSAFE_SIDE_EFFECT,
    RECOMMEND_BLOCK_SIGNED_TESTNET_PROMOTION,
    RECOMMEND_EXPAND_TESTNET_VALIDATION,
    STATUS_BLOCKED,
    STATUS_BLOCKED_EVIDENCE_MISSING,
    STATUS_BLOCKED_UNSAFE_SIDE_EFFECT,
    STATUS_RECORDED_REVIEW_ONLY,
    STEP310_SIGNED_TESTNET_SESSION_CLOSE_REPORT_VERSION,
    SignedTestnetSessionClosePolicy,
    build_signed_testnet_session_close_report,
    persist_signed_testnet_session_close_report,
    run_signed_testnet_session_close_report_latest,
)
from crypto_ai_system.execution.signed_testnet_order_executor import STATUS_BLOCKED as EXECUTOR_BLOCKED, STATUS_SUBMITTED
from crypto_ai_system.utils.audit import sha256_json


def _execution(submitted: bool = True) -> dict:
    payload = {
        "order_intent_id": "order_intent_step310_unit",
        "decision_id": "decision_step310_unit",
        "risk_gate_id": "risk_gate_step310_unit",
        "research_signal_id": "research_signal_step310_unit",
        "profile_id": "profile_step310_unit",
        "idempotency_key": "idem_step310_unit",
        "environment": "testnet",
        "symbol": "BTCUSDT",
        "would_submit_only": True,
    }
    payload["would_submit_order_payload_sha256"] = sha256_json(payload)
    return {
        "signed_testnet_execution_id": "execution_step310_unit",
        "execution_id": "execution_step310_unit",
        "status": STATUS_SUBMITTED if submitted else EXECUTOR_BLOCKED,
        "state": "SIGNED_TESTNET_SUBMITTED" if submitted else "SIGNED_TESTNET_SUBMISSION_BLOCKED_DISABLED",
        "submitted_to_exchange": submitted,
        "actual_submission_performed": False,
        "external_order_submission_performed": False,
        "adapter_called_for_write": False,
        "exchange_order_id": "testnet_exchange_order_step310" if submitted else None,
        "exchange_response_hash": sha256_json({"exchange_order_id": "testnet_exchange_order_step310", "status": "FILLED"}) if submitted else None,
        "request_hash": sha256_json(payload),
        "idempotency_key": payload["idempotency_key"],
        "order_intent_id": payload["order_intent_id"],
        "decision_id": payload["decision_id"],
        "risk_gate_id": payload["risk_gate_id"],
        "research_signal_id": payload["research_signal_id"],
        "profile_id": payload["profile_id"],
        "would_submit_order_payload": payload,
        "latency_ms": 42,
        "slippage_bps": 1.5,
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
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
    }


def _reconciliation(submitted: bool = True) -> dict:
    return {
        "signed_testnet_reconciliation_id": "reconciliation_step310_unit",
        "reconciliation_id": "reconciliation_step310_unit",
        "status": STATUS_RECONCILED if submitted else STATUS_BLOCKED_NO_SUBMISSION,
        "reconciliation_status": STATUS_RECONCILED if submitted else STATUS_BLOCKED_NO_SUBMISSION,
        "promotion_blocked": not submitted,
        "promotion_blocker": PROMOTION_BLOCKER_NONE if submitted else PROMOTION_BLOCKER_EXECUTION_NOT_SUBMITTED,
        "execution_id": "execution_step310_unit",
        "order_intent_id": "order_intent_step310_unit",
        "decision_id": "decision_step310_unit",
        "risk_gate_id": "risk_gate_step310_unit",
        "research_signal_id": "research_signal_step310_unit",
        "profile_id": "profile_step310_unit",
        "idempotency_key": "idem_step310_unit",
        "submitted_to_exchange": submitted,
        "failed_check_names": [] if submitted else ["EXECUTION_NOT_SUBMITTED"],
        "testnet_promotion_allowed_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }


def test_step310_records_submitted_session_review_only() -> None:
    report = build_signed_testnet_session_close_report(
        execution_record=_execution(submitted=True),
        reconciliation_record=_reconciliation(submitted=True),
    )

    assert report["version"] == STEP310_SIGNED_TESTNET_SESSION_CLOSE_REPORT_VERSION
    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["orders_submitted_count"] == 1
    assert report["orders_filled_count"] == 1
    assert report["reconciliation_mismatch_count"] == 0
    assert report["promotion_recommendation"] == RECOMMEND_EXPAND_TESTNET_VALIDATION
    assert report["signed_testnet_promotion_allowed_by_this_module"] is False
    assert report["testnet_order_submission_allowed_by_this_module"] is False
    assert report["live_trading_allowed_by_this_module"] is False


def test_step310_blocks_no_submission_session() -> None:
    report = build_signed_testnet_session_close_report(
        execution_record=_execution(submitted=False),
        reconciliation_record=_reconciliation(submitted=False),
    )

    assert report["status"] == STATUS_BLOCKED
    assert report["promotion_recommendation"] == RECOMMEND_BLOCK_SIGNED_TESTNET_PROMOTION
    assert report["orders_submitted_count"] == 0
    assert report["orders_not_submitted_count"] == 1
    assert BLOCK_EXECUTION_NOT_SUBMITTED in report["block_reasons"]
    assert BLOCK_RECONCILIATION_PROMOTION_BLOCKED in report["block_reasons"]


def test_step310_blocks_missing_evidence() -> None:
    report = build_signed_testnet_session_close_report(execution_record=None, reconciliation_record=None)
    assert report["status"] == STATUS_BLOCKED_EVIDENCE_MISSING
    assert report["promotion_recommendation"] == RECOMMEND_BLOCK_SIGNED_TESTNET_PROMOTION
    assert report["orders_submitted_count"] == 0


def test_step310_blocks_unsafe_side_effect_policy() -> None:
    report = build_signed_testnet_session_close_report(
        execution_record=_execution(submitted=True),
        reconciliation_record=_reconciliation(submitted=True),
        policy=SignedTestnetSessionClosePolicy(api_key_value_access_allowed=True),
    )
    assert report["status"] == STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
    assert BLOCK_UNSAFE_SIDE_EFFECT in report["block_reasons"]
    assert report["api_key_value_access_allowed"] is False


def test_step310_persists_registry_and_latest(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    report = build_signed_testnet_session_close_report(
        execution_record=_execution(submitted=False),
        reconciliation_record=_reconciliation(submitted=False),
    )
    persisted = persist_signed_testnet_session_close_report(cfg, report)

    assert persisted["signed_testnet_session_close_registry_record_id"]
    assert (tmp_path / "storage/latest/signed_testnet_session_close_report.json").exists()
    assert (tmp_path / "storage/latest/signed_testnet_session_close_registry_record.json").exists()
    assert (tmp_path / "storage/registries/signed_testnet_session_close_report_registry.jsonl").exists()


def test_step310_latest_runner_creates_blocked_evidence(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    result = run_signed_testnet_session_close_report_latest(project_root=root)
    assert result["status"] == STATUS_BLOCKED_EVIDENCE_MISSING
    assert result["promotion_recommendation"] == RECOMMEND_BLOCK_SIGNED_TESTNET_PROMOTION
    assert (root / "storage/latest/signed_testnet_session_close_report.json").exists()
