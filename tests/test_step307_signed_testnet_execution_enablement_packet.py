from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.real_read_only_venue_probe import build_real_read_only_venue_probe
from crypto_ai_system.execution.real_testnet_read_only_adapter import BinanceFuturesTestnetReadOnlyAdapter, build_real_testnet_read_only_adapter_evidence
from crypto_ai_system.execution.signed_testnet_execution_enablement_packet import (
    BLOCK_HARD_CAP_INVALID,
    BLOCK_MISSING_OPERATOR_UNLOCK_REQUEST,
    BLOCK_OPERATOR_REQUESTS_ORDER_SUBMISSION_ENABLED,
    BLOCK_PRE_SUBMIT_NOT_VALIDATED,
    BLOCK_UNSAFE_RUNTIME_FLAG,
    STATUS_BLOCKED,
    STATUS_READY_REVIEW_ONLY,
    STEP307_SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_VERSION,
    build_operator_unlock_request,
    build_signed_testnet_execution_enablement_packet,
    persist_signed_testnet_execution_enablement_packet,
    run_signed_testnet_execution_enablement_packet_latest,
)
from crypto_ai_system.execution.signed_testnet_pre_submit_validator import build_signed_testnet_pre_submit_validation_report
from crypto_ai_system.execution.testnet_secret_metadata_intake_v2 import build_testnet_secret_metadata_intake_v2
from crypto_ai_system.registry.approval_registry import build_approval_registry_record
from crypto_ai_system.registry.base_registry import registry_path
from crypto_ai_system.utils.audit import sha256_json, sha256_text


def _candidate() -> dict:
    return {
        "candidate_profile_id": "candidate_profile_step307",
        "candidate_profile_created": True,
        "creation_status": "CANDIDATE_PROFILE_DRAFT_CREATED_REVIEW_ONLY",
        "status": "review_only",
        "source_report_id": "performance_report_step307",
        "source_report_hash": "report_hash_step307",
        "feature_matrix_sha256": "feature_matrix_hash_step307",
        "profile_candidate_hash": "profile_candidate_hash_step307",
        "candidate_profile_applied": False,
        "settings_write_preview_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "live_trading_allowed_by_this_module": False,
    }


def _packet(candidate: dict) -> dict:
    payload = {
        "approval_packet_id": "approval_packet_step307",
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
    payload["approval_packet_hash"] = sha256_json({k: v for k, v in payload.items() if k != "approval_packet_hash"})
    return payload


def _intake(packet: dict) -> dict:
    payload = {
        "approval_intake_id": "approval_intake_step307",
        "approval_packet_id": packet["approval_packet_id"],
        "approver_info": "manual_reviewer_thomas",
        "ticket_or_signature": "ticket-or-signature-step307",
        "canonical_utc_timestamp": "2026-06-30T00:01:00Z",
        "profile_candidate_hash": packet["profile_candidate_hash"],
        "approval_decision": "APPROVE_FOR_REVIEW_ONLY_STAGING",
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    payload["approval_intake_hash"] = sha256_json({k: v for k, v in payload.items() if k != "approval_intake_hash"})
    return payload


def _approval_registry() -> dict:
    candidate = _candidate()
    packet = _packet(candidate)
    intake = _intake(packet)
    return build_approval_registry_record(candidate, packet, intake)


def _secret_metadata() -> dict:
    return {
        "secret_reference_id": "metadata_ref:testnet/binance_futures/step307_unit",
        "key_fingerprint_sha256": sha256_text("step307-unit-testnet-key-reference"),
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
        order_intent={"order_intent_id": "step307_probe", "symbol": "BTCUSDT", "notional_usdt": 5, "min_notional_usdt": 1},
        symbol="BTCUSDT",
    )
    secret_intake = build_testnet_secret_metadata_intake_v2(_secret_metadata())
    return build_real_read_only_venue_probe(adapter_evidence=adapter_evidence, secret_metadata_intake=secret_intake)


def _order_intent() -> dict:
    return {
        "status": "ORDER_INTENT_CREATED",
        "state": "CREATED",
        "order_intent_created": True,
        "order_intent_id": "order_intent_step307_unit",
        "decision_id": "decision_step307_unit",
        "risk_gate_id": "risk_gate_step307_unit",
        "research_signal_id": "research_signal_step307_unit",
        "profile_id": "profile_step307_unit",
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
        "risk_gate_id": "risk_gate_step307_unit",
        "decision_id": "decision_step307_unit",
        "research_signal_id": "research_signal_step307_unit",
        "profile_id": "profile_step307_unit",
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


def _pre_submit(venue_probe: dict) -> dict:
    return build_signed_testnet_pre_submit_validation_report(
        order_intent=_order_intent(),
        risk_gate_report=_risk_gate(),
        venue_probe=venue_probe,
    )


def test_step307_builds_ready_review_only_packet_without_enabling_execution() -> None:
    probe = _venue_probe()
    request = build_operator_unlock_request(
        operator_id="operator_thomas_review_only",
        ticket_or_signature="signed-testnet-enable-preview-ticket-step307",
        max_order_notional_usdt=5,
        max_daily_order_count=1,
        max_daily_loss_usdt=10,
    )
    packet = build_signed_testnet_execution_enablement_packet(
        operator_unlock_request=request,
        approval_registry_record=_approval_registry(),
        pre_submit_validation_report=_pre_submit(probe),
        venue_probe=probe,
    )

    assert packet["version"] == STEP307_SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_VERSION
    assert packet["status"] == STATUS_READY_REVIEW_ONLY
    assert packet["valid"] is True
    assert packet["review_only"] is True
    assert packet["enablement_packet_may_unlock_execution"] is False
    assert packet["ready_for_signed_testnet_execution"] is False
    assert packet["testnet_order_submission_allowed"] is False
    assert packet["external_order_submission_performed"] is False
    assert packet["place_order_enabled"] is False
    assert packet["signed_order_executor_enabled"] is False
    assert packet["api_key_value_access_allowed"] is False
    assert packet["secret_file_access_allowed"] is False
    assert packet["canonical_id_chain"]["order_intent_id"] == "order_intent_step307_unit"
    assert packet["idempotency_key"]


def test_step307_blocks_missing_operator_and_invalid_pre_submit() -> None:
    probe = _venue_probe()
    pre_submit = _pre_submit(probe)
    pre_submit["valid"] = False
    pre_submit["status"] = "SIGNED_TESTNET_PRE_SUBMIT_BLOCKED"
    packet = build_signed_testnet_execution_enablement_packet(
        operator_unlock_request=None,
        approval_registry_record=_approval_registry(),
        pre_submit_validation_report=pre_submit,
        venue_probe=probe,
    )

    assert packet["status"] == STATUS_BLOCKED
    assert BLOCK_MISSING_OPERATOR_UNLOCK_REQUEST in packet["block_reasons"]
    assert BLOCK_PRE_SUBMIT_NOT_VALIDATED in packet["block_reasons"]
    assert packet["testnet_order_submission_allowed"] is False


def test_step307_blocks_operator_requests_to_enable_submission() -> None:
    probe = _venue_probe()
    request = build_operator_unlock_request(
        operator_id="operator_thomas_review_only",
        ticket_or_signature="ticket-step307",
        testnet_order_submission_allowed=True,
    )
    packet = build_signed_testnet_execution_enablement_packet(
        operator_unlock_request=request,
        approval_registry_record=_approval_registry(),
        pre_submit_validation_report=_pre_submit(probe),
        venue_probe=probe,
    )

    assert packet["status"] == STATUS_BLOCKED
    assert BLOCK_OPERATOR_REQUESTS_ORDER_SUBMISSION_ENABLED in packet["block_reasons"]
    assert BLOCK_UNSAFE_RUNTIME_FLAG in packet["block_reasons"]
    assert packet["place_order_enabled"] is False


def test_step307_blocks_hard_cap_above_policy_limits() -> None:
    probe = _venue_probe()
    request = build_operator_unlock_request(
        operator_id="operator_thomas_review_only",
        ticket_or_signature="ticket-step307",
        max_order_notional_usdt=50,
        max_daily_order_count=10,
        max_daily_loss_usdt=100,
    )
    packet = build_signed_testnet_execution_enablement_packet(
        operator_unlock_request=request,
        approval_registry_record=_approval_registry(),
        pre_submit_validation_report=_pre_submit(probe),
        venue_probe=probe,
    )

    assert packet["status"] == STATUS_BLOCKED
    assert BLOCK_HARD_CAP_INVALID in packet["block_reasons"]
    assert packet["hard_cap_validation"]["valid"] is False


def test_step307_persists_packet_registry_and_latest(tmp_path: Path) -> None:
    cfg = load_config(Path.cwd())
    object.__setattr__(cfg, "root", tmp_path)
    probe = _venue_probe()
    request = build_operator_unlock_request(
        operator_id="operator_thomas_review_only",
        ticket_or_signature="ticket-step307",
    )
    packet = build_signed_testnet_execution_enablement_packet(
        operator_unlock_request=request,
        approval_registry_record=_approval_registry(),
        pre_submit_validation_report=_pre_submit(probe),
        venue_probe=probe,
    )
    persisted = persist_signed_testnet_execution_enablement_packet(cfg, packet)
    registry = registry_path(cfg, "signed_testnet_execution_enablement_packet_registry")
    rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]

    assert persisted["signed_testnet_execution_enablement_registry_record_id"]
    assert len(rows) == 1
    assert rows[0]["testnet_order_submission_allowed"] is False
    assert (tmp_path / "storage/latest/signed_testnet_execution_enablement_packet.json").exists()
    assert (tmp_path / "storage/signed_testnet_execution_enablement/signed_testnet_execution_enablement_packet.json").exists()


def test_step307_latest_runner_fails_closed_without_operator_request(tmp_path: Path) -> None:
    root = tmp_path
    (root / "config").mkdir(parents=True)
    (root / "config/settings.yaml").write_text(Path("config/settings.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_signed_testnet_execution_enablement_packet_latest(project_root=root)

    assert result["status"] == STATUS_BLOCKED
    assert BLOCK_MISSING_OPERATOR_UNLOCK_REQUEST in result["block_reasons"]
    assert result["ready_for_signed_testnet_execution"] is False
    assert result["testnet_order_submission_allowed"] is False
    assert (root / "storage/latest/signed_testnet_execution_enablement_packet.json").exists()
