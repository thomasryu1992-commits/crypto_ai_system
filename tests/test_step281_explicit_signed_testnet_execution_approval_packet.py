from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent))

import yaml

from crypto_ai_system.execution.signed_testnet_execution_approval_packet import (
    SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION,
    build_explicit_signed_testnet_execution_approval_packet,
    validate_explicit_signed_testnet_execution_approval_packet,
)
from crypto_ai_system.execution.signed_testnet_probe_result_validator import build_read_only_venue_probe_result_summary
from crypto_ai_system.utils.audit import utc_now_canonical
from test_step279_read_only_venue_probe_result_validator import _step278_session  # type: ignore


def _probe_result_summary() -> dict:
    return build_read_only_venue_probe_result_summary(read_only_probe_session=_step278_session())


def _full_regression_report() -> dict:
    report_path = Path("data/reports/step280_full_regression_runtime_hygiene_report.json")
    if not report_path.exists():
        report_path = Path("tests/fixtures/step280_full_regression_runtime_hygiene_report.json")
    return json.loads(report_path.read_text(encoding="utf-8"))


def _operator_approval(summary: dict, report: dict) -> dict:
    from crypto_ai_system.utils.audit import sha256_json

    return {
        "operator_id": "operator_thomas_step281_review_only",
        "operator_role": "operator",
        "execution_ticket_id": "TICKET-STEP281-EXPLICIT-SIGNED-TESTNET-APPROVAL",
        "operator_signature": "operator-signed-explicit-testnet-approval-review-only",
        "timestamp_utc": utc_now_canonical(),
        "read_only_venue_probe_result_summary_id": summary["read_only_venue_probe_result_summary_id"],
        "probe_result_summary_sha256": summary["probe_result_summary_sha256"],
        "full_regression_report_sha256": sha256_json(report),
        "operator_acknowledges_execution_still_disabled": True,
        "operator_acknowledges_no_external_submission": True,
        "operator_acknowledges_place_order_disabled": True,
        "operator_acknowledges_cancel_order_disabled": True,
        "operator_confirms_order_submission_enabled": False,
        "operator_confirms_place_order_enabled": False,
    }


def _risk_acceptance() -> dict:
    return {
        "risk_acceptance_id": "risk_acceptance_step281_review_only",
        "risk_approver_id": "risk_approver_thomas_step281",
        "risk_approver_role": "risk_reviewer",
        "risk_acceptance_ticket_id": "RISK-STEP281-REVIEW-ONLY",
        "risk_acceptance_signature": "risk-accepted-review-only-no-order-submission",
        "timestamp_utc": utc_now_canonical(),
        "max_order_notional_usdt": 5,
        "max_daily_order_count": 3,
        "max_daily_loss_usdt": 10,
        "max_consecutive_losses": 2,
        "manual_kill_switch_required": True,
        "manual_kill_switch_active": False,
        "acknowledges_review_only_no_order_submission": True,
        "acknowledges_testnet_scope_only": True,
    }


def _scope(summary: dict) -> dict:
    return {
        "venue": "binance_futures_testnet",
        "environment": "testnet",
        "key_scope": "testnet",
        "base_url": "https://testnet.binancefuture.com",
        "symbol": "BTCUSDT",
        "allowed_order_types": ["MARKET"],
        "testnet_execution_session_id": summary["testnet_execution_session_id"],
        "max_order_notional_usdt": 5,
        "max_daily_order_count": 3,
        "max_daily_loss_usdt": 10,
        "max_consecutive_losses": 2,
        "live_trading_enabled": False,
        "allow_live_trading": False,
        "place_order_enabled": False,
        "testnet_order_submission_allowed": False,
    }


def _packet() -> dict:
    summary = _probe_result_summary()
    report = _full_regression_report()
    return build_explicit_signed_testnet_execution_approval_packet(
        probe_result_summary=summary,
        full_regression_report=report,
        operator_execution_approval=_operator_approval(summary, report),
        manual_risk_acceptance=_risk_acceptance(),
        testnet_execution_scope=_scope(summary),
    )


def test_step281_packet_links_probe_summary_full_regression_and_remains_disabled(tmp_path: Path) -> None:
    summary = _probe_result_summary()
    report = _full_regression_report()
    packet = build_explicit_signed_testnet_execution_approval_packet(
        probe_result_summary=summary,
        full_regression_report=report,
        operator_execution_approval=_operator_approval(summary, report),
        manual_risk_acceptance=_risk_acceptance(),
        testnet_execution_scope=_scope(summary),
        output_path=tmp_path / "step281_explicit_approval_packet.json",
    )
    assert packet["version"] == SIGNED_TESTNET_EXECUTION_APPROVAL_PACKET_VERSION
    assert packet["packet_review_ready"] is True
    assert packet["read_only_venue_probe_result_summary_id"] == summary["read_only_venue_probe_result_summary_id"]
    assert packet["probe_result_summary_sha256"] == summary["probe_result_summary_sha256"]
    assert packet["step280_full_regression_report_validation"]["valid"] is True
    assert packet["operator_execution_approval_validation"]["valid"] is True
    assert packet["manual_risk_acceptance_validation"]["valid"] is True
    assert packet["testnet_execution_scope_validation"]["valid"] is True
    assert packet["ready_for_signed_testnet_execution"] is False
    assert packet["testnet_order_submission_allowed"] is False
    assert packet["external_order_submission_performed"] is False
    assert packet["place_order_enabled"] is False
    assert packet["cancel_order_enabled"] is False
    assert packet["signed_order_executor_enabled"] is False
    assert Path(packet["approval_packet_path"]).exists()
    assert validate_explicit_signed_testnet_execution_approval_packet(packet)["valid"] is True


def test_step281_blocks_tampered_probe_summary_hash() -> None:
    summary = _probe_result_summary()
    report = _full_regression_report()
    summary["probe_result_summary_sha256"] = "bad-hash"
    packet = build_explicit_signed_testnet_execution_approval_packet(
        probe_result_summary=summary,
        full_regression_report=report,
        operator_execution_approval=_operator_approval(summary, report),
        manual_risk_acceptance=_risk_acceptance(),
        testnet_execution_scope=_scope(summary),
    )
    assert packet["packet_review_ready"] is False
    assert "STEP281_PROBE_RESULT_SUMMARY_INVALID" in packet["block_reasons"]


def test_step281_blocks_full_regression_failure_report() -> None:
    summary = _probe_result_summary()
    report = _full_regression_report()
    report["status"] = "failed"
    packet = build_explicit_signed_testnet_execution_approval_packet(
        probe_result_summary=summary,
        full_regression_report=report,
        operator_execution_approval=_operator_approval(summary, report),
        manual_risk_acceptance=_risk_acceptance(),
        testnet_execution_scope=_scope(summary),
    )
    assert packet["packet_review_ready"] is False
    assert "STEP281_FULL_REGRESSION_REPORT_INVALID" in packet["block_reasons"]
    assert "STEP281_FULL_REGRESSION_REPORT_STATUS_NOT_PASSED" in packet["block_reasons"]


def test_step281_blocks_operator_hash_mismatch() -> None:
    summary = _probe_result_summary()
    report = _full_regression_report()
    operator = _operator_approval(summary, report)
    operator["probe_result_summary_sha256"] = "bad-hash"
    packet = build_explicit_signed_testnet_execution_approval_packet(
        probe_result_summary=summary,
        full_regression_report=report,
        operator_execution_approval=operator,
        manual_risk_acceptance=_risk_acceptance(),
        testnet_execution_scope=_scope(summary),
    )
    assert packet["packet_review_ready"] is False
    assert "STEP281_OPERATOR_PROBE_SUMMARY_HASH_MISMATCH" in packet["block_reasons"]


def test_step281_blocks_manual_kill_switch_and_risk_cap_violation() -> None:
    summary = _probe_result_summary()
    report = _full_regression_report()
    risk = _risk_acceptance()
    risk["manual_kill_switch_active"] = True
    risk["max_order_notional_usdt"] = 50
    packet = build_explicit_signed_testnet_execution_approval_packet(
        probe_result_summary=summary,
        full_regression_report=report,
        operator_execution_approval=_operator_approval(summary, report),
        manual_risk_acceptance=risk,
        testnet_execution_scope=_scope(summary),
    )
    assert packet["packet_review_ready"] is False
    assert "STEP281_RISK_MANUAL_KILL_SWITCH_ACTIVE_BLOCKED" in packet["block_reasons"]
    assert "STEP281_RISK_MAX_ORDER_NOTIONAL_OUT_OF_BOUNDS" in packet["block_reasons"]


def test_step281_blocks_live_or_mainnet_scope() -> None:
    summary = _probe_result_summary()
    report = _full_regression_report()
    scope = _scope(summary)
    scope["environment"] = "live"
    scope["key_scope"] = "live"
    scope["base_url"] = "https://fapi.binance.com"
    scope["live_trading_enabled"] = True
    packet = build_explicit_signed_testnet_execution_approval_packet(
        probe_result_summary=summary,
        full_regression_report=report,
        operator_execution_approval=_operator_approval(summary, report),
        manual_risk_acceptance=_risk_acceptance(),
        testnet_execution_scope=scope,
    )
    assert packet["packet_review_ready"] is False
    assert "STEP281_SCOPE_ENVIRONMENT_NOT_TESTNET" in packet["block_reasons"]
    assert "STEP281_SCOPE_KEY_SCOPE_NOT_TESTNET" in packet["block_reasons"]
    assert "STEP281_SCOPE_BASE_URL_NOT_TESTNET" in packet["block_reasons"]
    assert "STEP281_SCOPE_LIVE_TRADING_ENABLED_BLOCKED" in packet["block_reasons"]


def test_step281_detects_packet_hash_and_invariant_tampering() -> None:
    packet = _packet()
    assert validate_explicit_signed_testnet_execution_approval_packet(packet)["valid"] is True
    packet["testnet_order_submission_allowed"] = True
    validation = validate_explicit_signed_testnet_execution_approval_packet(packet)
    assert validation["valid"] is False
    assert "STEP281_APPROVAL_PACKET_TESTNET_ORDER_SUBMISSION_ALLOWED_INVARIANT_FAILED" in validation["block_reasons"]
    assert "STEP281_APPROVAL_PACKET_HASH_INVALID" in validation["block_reasons"]


def test_step281_config_version_and_safety_flags() -> None:
    settings = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    assert settings["project"]["version"] == "step286_researchsignal_feature_lineage_fix"
    cfg = settings["execution"]["explicit_signed_testnet_execution_approval_packet"]
    assert cfg["enabled"] is False
    assert cfg["review_only"] is True
    assert cfg["require_step279_probe_result_summary"] is True
    assert cfg["require_step280_full_regression_report"] is True
    assert cfg["require_operator_signed_execution_approval"] is True
    assert cfg["require_manual_risk_acceptance"] is True
    assert cfg["require_testnet_execution_scope"] is True
    assert cfg["ready_for_signed_testnet_execution"] is False
    assert cfg["testnet_order_submission_allowed"] is False
    assert cfg["external_order_submission_allowed"] is False
    assert cfg["external_order_submission_performed"] is False
    assert cfg["place_order_enabled"] is False
    assert cfg["cancel_order_enabled"] is False
    assert cfg["signed_order_executor_enabled"] is False
    assert settings["safety"]["live_trading_enabled"] is False
    assert settings["safety"]["testnet_signed_order_enabled"] is False
