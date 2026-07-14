from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.execution.exchange_adapter_contract import DisabledExchangeAdapter
from crypto_ai_system.execution.signed_testnet_dry_run_session_recorder import (
    SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION,
    build_signed_testnet_dry_run_session_recorder,
    validate_signed_testnet_dry_run_session_recorder,
)
from crypto_ai_system.execution.signed_testnet_execution_readiness_packet import (
    build_signed_testnet_execution_readiness_packet,
)
from crypto_ai_system.execution.signed_testnet_gate import build_signed_testnet_gate_artifact
from crypto_ai_system.execution.signed_testnet_preflight_artifact import build_signed_testnet_preflight_artifact
from crypto_ai_system.execution.testnet_secret_intake import build_testnet_key_metadata_intake
from crypto_ai_system.execution.venue_capability_evidence import build_venue_capability_evidence
from crypto_ai_system.utils.audit import sha256_text, utc_now_canonical


def _manual_approval() -> dict:
    return {
        "approval_packet_id": "approval_packet_step277_test",
        "approval_intake_id": "approval_intake_step277_test",
        "approver_id": "operator_thomas_review_only",
        "approver_role": "operator",
        "approval_ticket_id": "TICKET-STEP277-SIGNED-TESTNET-GATE",
        "approval_signature": "signed-testnet-gate-review-only-signature",
        "timestamp_utc": utc_now_canonical(),
    }


def _key_metadata() -> dict:
    return {
        "has_api_key": True,
        "has_api_secret": True,
        "key_scope": "testnet",
        "base_url": "https://testnet.binancefuture.com",
        "api_key_fingerprint_sha256": sha256_text("step277-testnet-key-metadata-only"),
        "secret_reference_id": "secret_ref:testnet/binance_futures/step277_metadata_only",
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
        "order_intent_id": "order_intent_step277_dry_run_session",
        "planned_order_count": 1,
        "per_order_notional_usdt": 5,
        "max_order_notional_usdt": 5,
        "max_daily_order_count": 3,
        "max_daily_loss_usdt": 10,
        "max_consecutive_losses": 2,
        "place_order_enabled": False,
        "testnet_order_submission_allowed": False,
    }


def _order_intent() -> dict:
    return {
        "order_intent_id": "order_intent_step277_dry_run_session",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 0.001,
        "notional_usdt": 5,
        "time_in_force": "GTC",
        "max_order_notional_usdt": 5,
        "place_order_enabled": False,
        "testnet_order_submission_allowed": False,
    }


def _venue_evidence() -> dict:
    adapter = DisabledExchangeAdapter()
    return build_venue_capability_evidence(
        adapter=adapter,
        order_intent={"order_intent_id": "order_intent_step277_dry_run_session", "notional_usdt": 5, "min_notional_usdt": 1},
        symbol="BTCUSDT",
    )


def _gate_artifact(evidence: dict) -> dict:
    adapter = DisabledExchangeAdapter()
    intake = build_testnet_key_metadata_intake(_key_metadata())
    preflight = build_signed_testnet_preflight_artifact(
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
    return build_signed_testnet_gate_artifact(
        preflight_artifact=preflight,
        manual_approval=_manual_approval(),
        risk_caps=_risk_caps(),
        operational_state={**_operational_state(), **_reconciliation_state()},
    )


def _operator_approval(gate: dict) -> dict:
    return {
        "operator_id": "operator_thomas_step277_review_only",
        "operator_role": "operator",
        "execution_ticket_id": "TICKET-STEP277-EXECUTION-READINESS",
        "operator_signature": "operator-signed-execution-readiness-review-only",
        "timestamp_utc": utc_now_canonical(),
        "signed_testnet_gate_id": gate["signed_testnet_gate_id"],
        "signed_testnet_gate_sha256": gate["signed_testnet_gate_sha256"],
        "operator_confirms_order_submission_enabled": False,
        "operator_confirms_place_order_enabled": False,
    }


def _readiness_packet(evidence: dict | None = None) -> dict:
    evidence = evidence or _venue_evidence()
    gate = _gate_artifact(evidence)
    return build_signed_testnet_execution_readiness_packet(
        signed_testnet_gate_artifact=gate,
        operator_approval=_operator_approval(gate),
        execution_plan=_execution_plan(),
        operational_state=_operational_state(),
        venue_capability_evidence=evidence,
        reconciliation_state=_reconciliation_state(),
    )


def _operator_ack(packet: dict) -> dict:
    return {
        "operator_id": "operator_thomas_step277_review_only",
        "operator_role": "operator",
        "execution_ticket_id": "TICKET-STEP277-DRY-RUN-SESSION",
        "operator_signature": "operator-acknowledged-dry-run-session-review-only",
        "timestamp_utc": utc_now_canonical(),
        "signed_testnet_execution_readiness_packet_id": packet["signed_testnet_execution_readiness_packet_id"],
        "execution_readiness_packet_sha256": packet["execution_readiness_packet_sha256"],
        "testnet_execution_session_id": packet["testnet_execution_session_id"],
        "operator_acknowledges_dry_run_only": True,
        "operator_acknowledges_no_external_submission": True,
        "operator_acknowledges_place_order_disabled": True,
        "operator_confirms_order_submission_enabled": False,
        "operator_confirms_place_order_enabled": False,
    }


def test_step277_dry_run_session_recorder_links_packet_payload_events_and_remains_disabled(tmp_path: Path) -> None:
    packet = _readiness_packet()
    recorder = build_signed_testnet_dry_run_session_recorder(
        execution_readiness_packet=packet,
        operator_acknowledgement=_operator_ack(packet),
        order_intent=_order_intent(),
        output_path=tmp_path / "step277_dry_run_session.json",
    )
    assert recorder["version"] == SIGNED_TESTNET_DRY_RUN_SESSION_RECORDER_VERSION
    assert recorder["session_review_ready"] is True
    assert recorder["testnet_execution_session_id"] == packet["testnet_execution_session_id"]
    assert recorder["would_submit_order_payload"]["dry_run_only"] is True
    assert recorder["pre_submit_checklist"]["valid"] is True
    assert len(recorder["session_event_log"]) >= 7
    assert recorder["session_close_report"]["valid"] is True
    assert recorder["ready_for_signed_testnet_execution"] is False
    assert recorder["testnet_order_submission_allowed"] is False
    assert recorder["external_order_submission_performed"] is False
    assert recorder["place_order_enabled"] is False
    assert recorder["signed_order_executor_enabled"] is False
    assert recorder["adapter_place_order_called"] is False
    assert Path(recorder["session_recorder_path"]).exists()
    assert validate_signed_testnet_dry_run_session_recorder(recorder)["valid"] is True


def test_step277_blocks_operator_ack_packet_hash_mismatch() -> None:
    packet = _readiness_packet()
    ack = _operator_ack(packet)
    ack["execution_readiness_packet_sha256"] = "0" * 64
    recorder = build_signed_testnet_dry_run_session_recorder(
        execution_readiness_packet=packet,
        operator_acknowledgement=ack,
        order_intent=_order_intent(),
    )
    assert recorder["session_review_ready"] is False
    assert "STEP277_OPERATOR_ACK_PACKET_HASH_MISMATCH" in recorder["block_reasons"]
    assert recorder["testnet_order_submission_allowed"] is False


def test_step277_blocks_place_order_or_submission_enabled_flags() -> None:
    packet = _readiness_packet()
    ack = _operator_ack(packet)
    ack["operator_confirms_place_order_enabled"] = True
    order_intent = _order_intent()
    order_intent["place_order_enabled"] = True
    order_intent["testnet_order_submission_allowed"] = True
    recorder = build_signed_testnet_dry_run_session_recorder(
        execution_readiness_packet=packet,
        operator_acknowledgement=ack,
        order_intent=order_intent,
    )
    assert recorder["session_review_ready"] is False
    assert "STEP277_OPERATOR_CONFIRMS_PLACE_ORDER_ENABLED_BLOCKED" in recorder["block_reasons"]
    assert "STEP277_ORDER_INTENT_PLACE_ORDER_ENABLED_BLOCKED" in recorder["block_reasons"]
    assert "STEP277_ORDER_INTENT_SUBMISSION_ALLOWED_BLOCKED" in recorder["block_reasons"]
    assert recorder["adapter_place_order_called"] is False


def test_step277_blocks_invalid_order_intent_cap() -> None:
    packet = _readiness_packet()
    order_intent = _order_intent()
    order_intent["notional_usdt"] = 6
    recorder = build_signed_testnet_dry_run_session_recorder(
        execution_readiness_packet=packet,
        operator_acknowledgement=_operator_ack(packet),
        order_intent=order_intent,
    )
    assert recorder["session_review_ready"] is False
    assert "STEP277_ORDER_NOTIONAL_EXCEEDS_CAP" in recorder["block_reasons"]
    assert recorder["would_submit_order_payload"]["external_order_submission_performed"] is False


def test_step277_session_event_hash_tampering_is_detected() -> None:
    packet = _readiness_packet()
    recorder = build_signed_testnet_dry_run_session_recorder(
        execution_readiness_packet=packet,
        operator_acknowledgement=_operator_ack(packet),
        order_intent=_order_intent(),
    )
    recorder["session_event_log"][0]["event_type"] = "TAMPERED"
    validation = validate_signed_testnet_dry_run_session_recorder(recorder)
    assert validation["valid"] is False
    assert "STEP277_SESSION_EVENT_HASH_INVALID" in validation["block_reasons"]
    assert "STEP277_SESSION_EVENT_LOG_HASH_INVALID" in validation["block_reasons"]
    assert "STEP277_DRY_RUN_SESSION_HASH_INVALID" in validation["block_reasons"]


def test_step277_recorder_hash_tampering_is_detected() -> None:
    packet = _readiness_packet()
    recorder = build_signed_testnet_dry_run_session_recorder(
        execution_readiness_packet=packet,
        operator_acknowledgement=_operator_ack(packet),
        order_intent=_order_intent(),
    )
    recorder["testnet_execution_session_id"] = "tampered_session"
    validation = validate_signed_testnet_dry_run_session_recorder(recorder)
    assert validation["valid"] is False
    assert "STEP277_DRY_RUN_SESSION_HASH_INVALID" in validation["block_reasons"]


def test_step277_version_and_config_safety_flags() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.286.2"' in pyproject

    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    assert settings["project"]["version"] == "p70_venue_neutral_execution_contract"
    cfg = settings["execution"]["signed_testnet_dry_run_session_recorder"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["require_step276_execution_readiness_packet"] is True
    assert cfg["require_would_submit_order_payload"] is True
    assert cfg["require_session_event_log"] is True
    assert cfg["adapter_place_order_call_allowed"] is False
    assert cfg["place_order_enabled"] is False
    assert cfg["testnet_order_submission_allowed"] is False
    assert cfg["external_order_submission_performed"] is False
