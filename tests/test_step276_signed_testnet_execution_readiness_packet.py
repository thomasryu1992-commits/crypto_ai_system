from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.execution.exchange_adapter_contract import DisabledExchangeAdapter
from crypto_ai_system.execution.signed_testnet_gate import build_signed_testnet_gate_artifact
from crypto_ai_system.execution.signed_testnet_preflight_artifact import build_signed_testnet_preflight_artifact
from crypto_ai_system.execution.signed_testnet_execution_readiness_packet import (
    SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION,
    build_signed_testnet_execution_readiness_packet,
    validate_signed_testnet_execution_readiness_packet,
)
from crypto_ai_system.execution.testnet_secret_intake import build_testnet_key_metadata_intake
from crypto_ai_system.execution.venue_capability_evidence import build_venue_capability_evidence
from crypto_ai_system.utils.audit import sha256_text, utc_now_canonical


def _manual_approval() -> dict:
    return {
        "approval_packet_id": "approval_packet_step276_test",
        "approval_intake_id": "approval_intake_step276_test",
        "approver_id": "operator_thomas_review_only",
        "approver_role": "operator",
        "approval_ticket_id": "TICKET-STEP276-SIGNED-TESTNET-GATE",
        "approval_signature": "signed-testnet-gate-review-only-signature",
        "timestamp_utc": utc_now_canonical(),
    }


def _key_metadata() -> dict:
    return {
        "has_api_key": True,
        "has_api_secret": True,
        "key_scope": "testnet",
        "base_url": "https://testnet.binancefuture.com",
        "api_key_fingerprint_sha256": sha256_text("step276-testnet-key-metadata-only"),
        "secret_reference_id": "secret_ref:testnet/binance_futures/step276_metadata_only",
        "secret_file_loaded": False,
        "secret_file_created": False,
        "secret_bytes_read": False,
        "live_key_detected": False,
    }


def _risk_caps() -> dict:
    return {
        "max_order_notional_usdt": 5,
        "max_daily_order_count": 3,
        "max_daily_loss_usdt": 10,
        "max_consecutive_losses": 2,
        "manual_kill_switch_required": True,
        "manual_kill_switch_active": False,
    }


def _operational_state() -> dict:
    return {
        "trading_mode": "paper",
        "testnet_signed_order_enabled": False,
        "enable_real_orders": False,
        "live_trading_enabled": False,
        "allow_live_trading": False,
        "place_order_enabled": False,
        "signed_order_executor_enabled": False,
        "current_daily_order_count": 0,
        "current_daily_loss_usdt": 0,
        "current_consecutive_losses": 0,
        "manual_kill_switch_required": True,
        "manual_kill_switch_active": False,
    }


def _reconciliation_state() -> dict:
    return {
        "reconciliation_mismatch_present": False,
        "reconciliation_mismatch_rate": 0.0,
        "last_reconciliation_status": "RECONCILIATION_MATCHED",
        "reconciliation_evidence_hash_valid": True,
        "reconciliation_evidence_complete": True,
    }


def _execution_plan() -> dict:
    return {
        "symbol": "BTCUSDT",
        "order_intent_id": "order_intent_step276_execution_readiness",
        "planned_order_count": 1,
        "per_order_notional_usdt": 5,
        "max_order_notional_usdt": 5,
        "max_daily_order_count": 3,
        "max_daily_loss_usdt": 10,
        "max_consecutive_losses": 2,
        "place_order_enabled": False,
        "testnet_order_submission_allowed": False,
    }


def _venue_evidence() -> dict:
    adapter = DisabledExchangeAdapter()
    return build_venue_capability_evidence(
        adapter=adapter,
        order_intent={"order_intent_id": "order_intent_step276_execution_readiness", "notional_usdt": 5, "min_notional_usdt": 1},
        symbol="BTCUSDT",
    )


def _preflight_artifact(evidence: dict | None = None) -> dict:
    adapter = DisabledExchangeAdapter()
    evidence = evidence or _venue_evidence()
    intake = build_testnet_key_metadata_intake(_key_metadata())
    return build_signed_testnet_preflight_artifact(
        adapter_capabilities=adapter.get_capabilities(),
        testnet_key_intake=intake,
        venue_capability_evidence=evidence,
        manual_approval=_manual_approval(),
        risk_limits={"max_order_notional_usdt": 5, "max_daily_order_count": 3, "manual_kill_switch_required": True},
        runtime_flags={
            "trading_mode": "paper",
            "testnet_signed_order_enabled": False,
            "enable_real_orders": False,
            "live_trading_enabled": False,
            "allow_live_trading": False,
        },
    )


def _gate_artifact(evidence: dict | None = None) -> dict:
    return build_signed_testnet_gate_artifact(
        preflight_artifact=_preflight_artifact(evidence),
        manual_approval=_manual_approval(),
        risk_caps=_risk_caps(),
        operational_state={**_operational_state(), **_reconciliation_state()},
    )


def _operator_approval(gate: dict) -> dict:
    return {
        "operator_id": "operator_thomas_step276_review_only",
        "operator_role": "operator",
        "execution_ticket_id": "TICKET-STEP276-EXECUTION-READINESS",
        "operator_signature": "operator-signed-execution-readiness-review-only",
        "timestamp_utc": utc_now_canonical(),
        "signed_testnet_gate_id": gate["signed_testnet_gate_id"],
        "signed_testnet_gate_sha256": gate["signed_testnet_gate_sha256"],
        "operator_confirms_order_submission_enabled": False,
        "operator_confirms_place_order_enabled": False,
    }


def test_step276_execution_readiness_packet_links_gate_session_and_remains_disabled(tmp_path: Path) -> None:
    evidence = _venue_evidence()
    gate = _gate_artifact(evidence)
    packet = build_signed_testnet_execution_readiness_packet(
        signed_testnet_gate_artifact=gate,
        operator_approval=_operator_approval(gate),
        execution_plan=_execution_plan(),
        operational_state=_operational_state(),
        venue_capability_evidence=evidence,
        reconciliation_state=_reconciliation_state(),
        output_path=tmp_path / "step276_execution_readiness_packet.json",
    )
    assert packet["version"] == SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION
    assert packet["packet_review_ready"] is True
    assert packet["signed_testnet_gate_id"] == gate["signed_testnet_gate_id"]
    assert packet["testnet_execution_session_id"].startswith("testnet_execution_session_")
    assert packet["ready_for_signed_testnet_execution"] is False
    assert packet["testnet_order_submission_allowed"] is False
    assert packet["external_order_submission_performed"] is False
    assert packet["place_order_enabled"] is False
    assert packet["signed_order_executor_enabled"] is False
    assert packet["order_submission_remains_disabled"] is True
    assert Path(packet["execution_readiness_packet_path"]).exists()
    assert validate_signed_testnet_execution_readiness_packet(packet)["valid"] is True


def test_step276_blocks_operator_gate_hash_mismatch() -> None:
    evidence = _venue_evidence()
    gate = _gate_artifact(evidence)
    operator = _operator_approval(gate)
    operator["signed_testnet_gate_sha256"] = "0" * 64
    packet = build_signed_testnet_execution_readiness_packet(
        signed_testnet_gate_artifact=gate,
        operator_approval=operator,
        execution_plan=_execution_plan(),
        operational_state=_operational_state(),
        venue_capability_evidence=evidence,
        reconciliation_state=_reconciliation_state(),
    )
    assert packet["packet_review_ready"] is False
    assert "STEP276_OPERATOR_GATE_HASH_MISMATCH" in packet["block_reasons"]
    assert packet["ready_for_signed_testnet_execution"] is False


def test_step276_blocks_cap_violation_and_kill_switch() -> None:
    evidence = _venue_evidence()
    gate = _gate_artifact(evidence)
    plan = _execution_plan()
    plan["per_order_notional_usdt"] = 6
    ops = _operational_state()
    ops["manual_kill_switch_active"] = True
    packet = build_signed_testnet_execution_readiness_packet(
        signed_testnet_gate_artifact=gate,
        operator_approval=_operator_approval(gate),
        execution_plan=plan,
        operational_state=ops,
        venue_capability_evidence=evidence,
        reconciliation_state=_reconciliation_state(),
    )
    assert packet["packet_review_ready"] is False
    assert "STEP276_PER_ORDER_NOTIONAL_EXCEEDS_MAX_ORDER_CAP" in packet["block_reasons"]
    assert "STEP276_MANUAL_KILL_SWITCH_ACTIVE_BLOCKED" in packet["block_reasons"]
    assert packet["testnet_order_submission_allowed"] is False


def test_step276_blocks_stale_venue_evidence_and_reconciliation_mismatch() -> None:
    evidence = _venue_evidence()
    evidence["created_at_utc"] = "2026-01-01T00:00:00Z"
    gate = _gate_artifact(evidence)
    reconciliation = _reconciliation_state()
    reconciliation["reconciliation_mismatch_present"] = True
    reconciliation["reconciliation_mismatch_rate"] = 0.1
    packet = build_signed_testnet_execution_readiness_packet(
        signed_testnet_gate_artifact=gate,
        operator_approval=_operator_approval(gate),
        execution_plan=_execution_plan(),
        operational_state=_operational_state(),
        venue_capability_evidence=evidence,
        reconciliation_state=reconciliation,
        venue_evidence_max_age_sec=1,
    )
    assert packet["packet_review_ready"] is False
    assert "STEP276_VENUE_EVIDENCE_STALE_BLOCKED" in packet["block_reasons"]
    assert "STEP276_RECONCILIATION_MISMATCH_PRESENT_BLOCKED" in packet["block_reasons"]
    assert "STEP276_RECONCILIATION_MISMATCH_RATE_NOT_ZERO_BLOCKED" in packet["block_reasons"]


def test_step276_packet_hash_validation_fails_when_tampered() -> None:
    evidence = _venue_evidence()
    gate = _gate_artifact(evidence)
    packet = build_signed_testnet_execution_readiness_packet(
        signed_testnet_gate_artifact=gate,
        operator_approval=_operator_approval(gate),
        execution_plan=_execution_plan(),
        operational_state=_operational_state(),
        venue_capability_evidence=evidence,
        reconciliation_state=_reconciliation_state(),
    )
    packet["testnet_execution_session_id"] = "tampered_session"
    validation = validate_signed_testnet_execution_readiness_packet(packet)
    assert validation["valid"] is False
    assert "STEP276_EXECUTION_READINESS_PACKET_HASH_INVALID" in validation["block_reasons"]


def test_step276_version_and_config_safety_flags() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.286.0"' in pyproject

    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    assert settings["project"]["version"] == "step286_researchsignal_feature_lineage_fix"
    readiness = settings["execution"]["signed_testnet_execution_readiness_packet"]
    assert readiness["enabled"] is False
    assert readiness["review_only"] is True
    assert readiness["require_step275_signed_testnet_gate_artifact"] is True
    assert readiness["require_operator_signed_execution_readiness"] is True
    assert readiness["require_venue_evidence_freshness"] is True
    assert readiness["ready_for_signed_testnet_execution"] is False
    assert readiness["testnet_order_submission_allowed"] is False
    assert readiness["place_order_enabled"] is False
    assert readiness["signed_order_executor_enabled"] is False
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False
