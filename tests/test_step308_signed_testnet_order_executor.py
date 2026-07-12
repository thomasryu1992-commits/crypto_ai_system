from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.real_read_only_venue_probe import build_real_read_only_venue_probe
from crypto_ai_system.execution.real_testnet_read_only_adapter import BinanceFuturesTestnetReadOnlyAdapter, build_real_testnet_read_only_adapter_evidence
from crypto_ai_system.execution.signed_testnet_execution_enablement_packet import (
    STATUS_READY_REVIEW_ONLY as ENABLEMENT_STATUS_READY_REVIEW_ONLY,
    build_operator_unlock_request,
    build_signed_testnet_execution_enablement_packet,
)
from crypto_ai_system.execution.signed_testnet_order_executor import (
    BLOCK_ENABLEMENT_PACKET_NOT_VALID,
    BLOCK_MISSING_ENABLEMENT_PACKET,
    BLOCK_MISSING_IDEMPOTENCY_KEY,
    BLOCK_MISSING_PRE_SUBMIT_PAYLOAD,
    BLOCK_PLACE_ORDER_DISABLED,
    BLOCK_SIGNED_ORDER_EXECUTOR_DISABLED,
    BLOCK_TESTNET_ORDER_SUBMISSION_DISABLED,
    STATUS_BLOCKED,
    STEP308_SIGNED_TESTNET_ORDER_EXECUTOR_VERSION,
    SignedTestnetOrderExecutorPolicy,
    build_signed_testnet_order_execution_record,
    persist_signed_testnet_order_execution_record,
    run_signed_testnet_order_executor_latest,
)
from crypto_ai_system.execution.signed_testnet_pre_submit_validator import build_signed_testnet_pre_submit_validation_report
from crypto_ai_system.execution.testnet_secret_metadata_intake_v2 import build_testnet_secret_metadata_intake_v2
from crypto_ai_system.registry.approval_registry import build_approval_registry_record
from crypto_ai_system.utils.audit import sha256_json, sha256_text


def _candidate() -> dict:
    return {
        "candidate_profile_id": "candidate_profile_step308",
        "candidate_profile_created": True,
        "creation_status": "CANDIDATE_PROFILE_DRAFT_CREATED_REVIEW_ONLY",
        "status": "review_only",
        "source_report_id": "performance_report_step308",
        "source_report_hash": "report_hash_step308",
        "feature_matrix_sha256": "feature_matrix_hash_step308",
        "profile_candidate_hash": "profile_candidate_hash_step308",
        "candidate_profile_applied": False,
        "settings_write_preview_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
    }


def _approval_registry() -> dict:
    candidate = _candidate()
    packet = {
        "approval_packet_id": "approval_packet_step308",
        "candidate_profile_id": candidate["candidate_profile_id"],
        "source_report_hash": candidate["source_report_hash"],
        "feature_matrix_sha256": candidate["feature_matrix_sha256"],
        "profile_candidate_hash": candidate["profile_candidate_hash"],
        "created_at_utc": "2026-06-30T00:00:00Z",
        "approval_file_auto_regenerated": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    packet["approval_packet_hash"] = sha256_json({k: v for k, v in packet.items() if k != "approval_packet_hash"})
    intake = {
        "approval_intake_id": "approval_intake_step308",
        "approval_packet_id": packet["approval_packet_id"],
        "approver_info": "manual_reviewer_thomas",
        "ticket_or_signature": "ticket-or-signature-step308",
        "canonical_utc_timestamp": "2026-06-30T00:01:00Z",
        "profile_candidate_hash": packet["profile_candidate_hash"],
        "approval_decision": "APPROVE_FOR_REVIEW_ONLY_STAGING",
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    intake["approval_intake_hash"] = sha256_json({k: v for k, v in intake.items() if k != "approval_intake_hash"})
    return build_approval_registry_record(candidate, packet, intake)


def _secret_metadata() -> dict:
    return {
        "secret_reference_id": "metadata_ref:testnet/binance_futures/step308_unit",
        "key_fingerprint_sha256": sha256_text("step308-unit-testnet-key-reference"),
        "environment": "testnet",
        "venue": "binance_futures_testnet",
        "scope": ["read_only", "signed_testnet_preparation"],
        "operator_id": "operator_thomas_review_only",
        "base_url": "https://testnet.binancefuture.com",
        "secret_file_loaded": False,
        "secret_file_created": False,
        "secret_bytes_read": False,
        "secret_value_read": False,
        "live_key_detected": False,
    }


def _venue_probe() -> dict:
    adapter_evidence = build_real_testnet_read_only_adapter_evidence(
        adapter=BinanceFuturesTestnetReadOnlyAdapter(),
        order_intent={"order_intent_id": "step308_probe", "symbol": "BTCUSDT", "notional_usdt": 5, "min_notional_usdt": 1},
        symbol="BTCUSDT",
    )
    secret_intake = build_testnet_secret_metadata_intake_v2(_secret_metadata())
    return build_real_read_only_venue_probe(adapter_evidence=adapter_evidence, secret_metadata_intake=secret_intake)


def _order_intent() -> dict:
    return {
        "status": "ORDER_INTENT_CREATED",
        "state": "CREATED",
        "order_intent_created": True,
        "order_intent_id": "order_intent_step308_unit",
        "decision_id": "decision_step308_unit",
        "risk_gate_id": "risk_gate_step308_unit",
        "research_signal_id": "research_signal_step308_unit",
        "profile_id": "profile_step308_unit",
        "execution_stage": "signed_testnet",
        "decision_stage": "signed_testnet",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 0.001,
        "entry_price": 100000.0,
        "notional_usdt": 100.0,
        "pre_order_risk_gate_approved": True,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
    }


def _risk_gate() -> dict:
    return {
        "risk_gate_id": "risk_gate_step308_unit",
        "decision_id": "decision_step308_unit",
        "research_signal_id": "research_signal_step308_unit",
        "profile_id": "profile_step308_unit",
        "status": "PASS_SIGNED_TESTNET",
        "stage": "signed_testnet",
        "approved": True,
        "block_reasons": [],
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
    }


def _pre_submit(probe: dict) -> dict:
    return build_signed_testnet_pre_submit_validation_report(
        order_intent=_order_intent(),
        risk_gate_report=_risk_gate(),
        venue_probe=probe,
    )


def _enablement() -> tuple[dict, dict]:
    probe = _venue_probe()
    pre_submit = _pre_submit(probe)
    request = build_operator_unlock_request(
        operator_id="operator_thomas_review_only",
        ticket_or_signature="ticket-or-signature-step308",
        max_order_notional_usdt=5,
        max_daily_order_count=1,
        max_daily_loss_usdt=10,
    )
    packet = build_signed_testnet_execution_enablement_packet(
        operator_unlock_request=request,
        approval_registry_record=_approval_registry(),
        pre_submit_validation_report=pre_submit,
        venue_probe=probe,
    )
    assert packet["status"] == ENABLEMENT_STATUS_READY_REVIEW_ONLY
    return packet, pre_submit["would_submit_order_payload"]


def test_step308_builds_disabled_executor_record_without_submission() -> None:
    packet, payload = _enablement()
    record = build_signed_testnet_order_execution_record(enablement_packet=packet, would_submit_payload=payload)

    assert record["version"] == STEP308_SIGNED_TESTNET_ORDER_EXECUTOR_VERSION
    assert record["status"] == STATUS_BLOCKED
    assert record["submitted_to_exchange"] is False
    assert record["actual_submission_performed"] is False
    assert record["external_order_submission_performed"] is False
    assert record["adapter_called_for_write"] is False
    assert record["exchange_order_id"] is None
    assert BLOCK_TESTNET_ORDER_SUBMISSION_DISABLED in record["block_reasons"]
    assert BLOCK_PLACE_ORDER_DISABLED in record["block_reasons"]
    assert BLOCK_SIGNED_ORDER_EXECUTOR_DISABLED in record["block_reasons"]
    assert record["idempotency_key"] == payload["idempotency_key"]
    assert record["order_intent_id"] == payload["order_intent_id"]
    assert record["request_hash"]
    assert record["lifecycle_events"]
    assert record["reconciliation_required"] is False


def test_step308_blocks_missing_enablement_and_payload() -> None:
    record = build_signed_testnet_order_execution_record(enablement_packet=None, would_submit_payload=None)
    assert record["status"] == STATUS_BLOCKED
    assert BLOCK_MISSING_ENABLEMENT_PACKET in record["block_reasons"]
    assert BLOCK_MISSING_PRE_SUBMIT_PAYLOAD in record["block_reasons"]
    assert record["submitted_to_exchange"] is False


def test_step308_blocks_invalid_enablement_and_missing_idempotency() -> None:
    packet, payload = _enablement()
    packet["valid"] = False
    payload = dict(payload)
    payload.pop("idempotency_key", None)
    record = build_signed_testnet_order_execution_record(enablement_packet=packet, would_submit_payload=payload)
    assert BLOCK_ENABLEMENT_PACKET_NOT_VALID in record["block_reasons"]
    assert BLOCK_MISSING_IDEMPOTENCY_KEY in record["block_reasons"]
    assert record["external_order_submission_performed"] is False


def test_step308_even_positive_policy_does_not_mark_external_submission_without_exchange_response() -> None:
    packet, payload = _enablement()
    policy = SignedTestnetOrderExecutorPolicy(
        ready_for_signed_testnet_execution=True,
        testnet_order_submission_allowed=True,
        external_order_submission_allowed=True,
        place_order_enabled=True,
        signed_order_executor_enabled=True,
        adapter_write_routing_enabled=True,
    )
    record = build_signed_testnet_order_execution_record(enablement_packet=packet, would_submit_payload=payload, policy=policy)
    assert record["status"] == STATUS_BLOCKED
    assert record["submitted_to_exchange"] is False
    assert record["actual_submission_performed"] is False
    assert record["external_order_submission_performed"] is False
    assert record["adapter_called_for_write"] is False


def test_step308_persists_executor_and_lifecycle_registry(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    packet, payload = _enablement()
    record = build_signed_testnet_order_execution_record(enablement_packet=packet, would_submit_payload=payload)
    persisted = persist_signed_testnet_order_execution_record(cfg, record)
    assert persisted["signed_testnet_order_executor_registry_record_id"]
    assert persisted["signed_testnet_order_lifecycle_record_id"]
    assert (tmp_path / "storage/latest/signed_testnet_order_execution_record.json").exists()
    assert (tmp_path / "storage/latest/signed_testnet_order_lifecycle_events.json").exists()
    assert (tmp_path / "storage/latest/signed_testnet_order_executor_registry_record.json").exists()
    assert (tmp_path / "storage/latest/signed_testnet_order_lifecycle_registry_record.json").exists()
    assert (tmp_path / "storage/registries/signed_testnet_order_executor_registry.jsonl").exists()
    assert (tmp_path / "storage/registries/signed_testnet_order_lifecycle_registry.jsonl").exists()


def test_step308_latest_runner_creates_blocked_evidence(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    result = run_signed_testnet_order_executor_latest(project_root=root)
    assert result["status"] == STATUS_BLOCKED
    assert result["actual_submission_performed"] is False
    assert result["external_order_submission_performed"] is False
    assert result["place_order_enabled"] is False
    assert (root / "storage/latest/signed_testnet_order_execution_record.json").exists()
    assert (root / "storage/latest/signed_testnet_execution_enablement_packet.json").exists()


def test_step308_config_flags_remain_disabled() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    cfg = settings["execution"]["signed_testnet_order_executor"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["ready_for_signed_testnet_execution"] is False
    assert cfg["testnet_order_submission_allowed"] is False
    assert cfg["external_order_submission_allowed"] is False
    assert cfg["external_order_submission_performed"] is False
    assert cfg["place_order_enabled"] is False
    assert cfg["cancel_order_enabled"] is False
    assert cfg["signed_order_executor_enabled"] is False
    assert cfg["api_key_value_access_allowed"] is False
    assert cfg["api_secret_value_access_allowed"] is False
    assert cfg["secret_file_access_allowed"] is False
    assert cfg["secret_file_creation_allowed"] is False
