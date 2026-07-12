from __future__ import annotations

from pathlib import Path

import yaml

from crypto_ai_system.execution.exchange_adapter_contract import DisabledExchangeAdapter
from crypto_ai_system.execution.signed_testnet_gate import (
    SIGNED_TESTNET_GATE_VERSION,
    build_signed_testnet_gate_artifact,
    validate_signed_testnet_gate_artifact,
)
from crypto_ai_system.execution.signed_testnet_preflight_artifact import build_signed_testnet_preflight_artifact
from crypto_ai_system.execution.testnet_secret_intake import build_testnet_key_metadata_intake
from crypto_ai_system.execution.venue_capability_evidence import build_venue_capability_evidence
from crypto_ai_system.utils.audit import sha256_text, utc_now_canonical


def _valid_approval() -> dict:
    return {
        "approval_packet_id": "approval_packet_step275_test",
        "approval_intake_id": "approval_intake_step275_test",
        "approver_id": "operator_thomas_review_only",
        "approver_role": "operator",
        "approval_ticket_id": "TICKET-STEP275-SIGNED-TESTNET-GATE",
        "approval_signature": "signed-testnet-gate-review-only-signature",
        "timestamp_utc": utc_now_canonical(),
    }


def _valid_key_metadata() -> dict:
    return {
        "has_api_key": True,
        "has_api_secret": True,
        "key_scope": "testnet",
        "base_url": "https://testnet.binancefuture.com",
        "api_key_fingerprint_sha256": sha256_text("step275-testnet-key-metadata-only"),
        "secret_reference_id": "secret_ref:testnet/binance_futures/step275_metadata_only",
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
        "current_daily_order_count": 0,
        "current_daily_loss_usdt": 0,
        "current_consecutive_losses": 0,
        "reconciliation_mismatch_present": False,
        "reconciliation_mismatch_rate": 0.0,
        "last_reconciliation_status": "RECONCILIATION_MATCHED",
    }


def _preflight_artifact() -> dict:
    adapter = DisabledExchangeAdapter()
    intake = build_testnet_key_metadata_intake(_valid_key_metadata())
    evidence = build_venue_capability_evidence(
        adapter=adapter,
        order_intent={"order_intent_id": "order_intent_step275_preflight", "notional_usdt": 5, "min_notional_usdt": 1},
        symbol="BTCUSDT",
    )
    return build_signed_testnet_preflight_artifact(
        adapter_capabilities=adapter.get_capabilities(),
        testnet_key_intake=intake,
        venue_capability_evidence=evidence,
        manual_approval=_valid_approval(),
        risk_limits={"max_order_notional_usdt": 5, "max_daily_order_count": 3, "manual_kill_switch_required": True},
        runtime_flags={
            "trading_mode": "paper",
            "testnet_signed_order_enabled": False,
            "enable_real_orders": False,
            "live_trading_enabled": False,
            "allow_live_trading": False,
        },
    )


def test_step275_gate_links_preflight_approval_risk_and_remains_execution_disabled(tmp_path: Path) -> None:
    preflight = _preflight_artifact()
    gate = build_signed_testnet_gate_artifact(
        preflight_artifact=preflight,
        manual_approval=_valid_approval(),
        risk_caps=_risk_caps(),
        operational_state=_operational_state(),
        output_path=tmp_path / "step275_signed_testnet_gate.json",
    )
    assert gate["version"] == SIGNED_TESTNET_GATE_VERSION
    assert gate["gate_review_ready"] is True
    assert gate["preflight_artifact_id"] == preflight["signed_testnet_preflight_artifact_id"]
    assert gate["preflight_artifact_sha256"] == preflight["preflight_artifact_sha256"]
    assert gate["ready_for_signed_testnet_execution"] is False
    assert gate["testnet_order_submission_allowed"] is False
    assert gate["external_order_submission_performed"] is False
    assert gate["place_order_enabled"] is False
    assert gate["signed_order_executor_enabled"] is False
    assert Path(gate["gate_artifact_path"]).exists()
    assert validate_signed_testnet_gate_artifact(gate)["valid"] is True


def test_step275_gate_blocks_tampered_preflight_hash() -> None:
    preflight = _preflight_artifact()
    preflight["venue_capability_evidence_hash"] = "0" * 64
    gate = build_signed_testnet_gate_artifact(
        preflight_artifact=preflight,
        manual_approval=_valid_approval(),
        risk_caps=_risk_caps(),
        operational_state=_operational_state(),
    )
    assert gate["gate_review_ready"] is False
    assert "SIGNED_TESTNET_PREFLIGHT_ARTIFACT_HASH_INVALID" in gate["block_reasons"]
    assert gate["ready_for_signed_testnet_execution"] is False


def test_step275_gate_blocks_missing_manual_approval_and_active_kill_switch() -> None:
    risk_caps = _risk_caps()
    risk_caps["manual_kill_switch_active"] = True
    gate = build_signed_testnet_gate_artifact(
        preflight_artifact=_preflight_artifact(),
        manual_approval={"approval_packet_id": "packet_only"},
        risk_caps=risk_caps,
        operational_state=_operational_state(),
    )
    assert gate["gate_review_ready"] is False
    assert "SIGNED_TESTNET_APPROVAL_APPROVAL_SIGNATURE_MISSING" in gate["block_reasons"]
    assert "SIGNED_TESTNET_MANUAL_KILL_SWITCH_ACTIVE_BLOCKED" in gate["block_reasons"]
    assert gate["testnet_order_submission_allowed"] is False


def test_step275_gate_blocks_risk_cap_and_reconciliation_mismatch() -> None:
    risk_caps = _risk_caps()
    risk_caps["max_order_notional_usdt"] = 50
    ops = _operational_state()
    ops["reconciliation_mismatch_present"] = True
    ops["reconciliation_mismatch_rate"] = 0.01
    gate = build_signed_testnet_gate_artifact(
        preflight_artifact=_preflight_artifact(),
        manual_approval=_valid_approval(),
        risk_caps=risk_caps,
        operational_state=ops,
    )
    assert gate["gate_review_ready"] is False
    assert "SIGNED_TESTNET_MAX_ORDER_NOTIONAL_EXCEEDS_STEP275_CAP" in gate["block_reasons"]
    assert "SIGNED_TESTNET_RECONCILIATION_MISMATCH_PRESENT_BLOCKED" in gate["block_reasons"]
    assert "SIGNED_TESTNET_RECONCILIATION_MISMATCH_RATE_NOT_ZERO_BLOCKED" in gate["block_reasons"]


def test_step275_gate_hash_validation_fails_when_tampered() -> None:
    gate = build_signed_testnet_gate_artifact(
        preflight_artifact=_preflight_artifact(),
        manual_approval=_valid_approval(),
        risk_caps=_risk_caps(),
        operational_state=_operational_state(),
    )
    gate["preflight_artifact_sha256"] = "0" * 64
    validation = validate_signed_testnet_gate_artifact(gate)
    assert validation["valid"] is False
    assert "SIGNED_TESTNET_GATE_HASH_INVALID" in validation["block_reasons"]


def test_step275_version_and_config_safety_flags() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.286.0"' in pyproject

    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    assert settings["project"]["version"] == "step286_researchsignal_feature_lineage_fix"
    gate = settings["execution"]["signed_testnet_gate"]
    assert gate["enabled"] is False
    assert gate["review_only"] is True
    assert gate["ready_for_signed_testnet_execution"] is False
    assert gate["testnet_order_submission_allowed"] is False
    assert gate["place_order_enabled"] is False
    assert gate["require_preflight_artifact_hash"] is True
    assert gate["require_manual_signed_approval"] is True
    assert gate["manual_kill_switch_required"] is True
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False
