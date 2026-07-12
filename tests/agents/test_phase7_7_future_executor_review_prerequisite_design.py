from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_6_disabled_signed_testnet_session_operator_handoff import (
    persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report,
)
from crypto_ai_system.validation.phase7_7_future_executor_review_prerequisite_design import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_7_future_executor_review_prerequisite_design_report,
    persist_phase7_7_future_executor_review_prerequisite_design_report,
)


def test_phase7_7_records_future_executor_prerequisite_design() -> None:
    report = persist_phase7_7_future_executor_review_prerequisite_design_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["review_only"] is True
    assert report["prerequisite_design_only"] is True
    assert report["phase7_7_prerequisite_design_ready"] is True
    assert report["future_executor_prerequisite_packet_created"] is True
    assert report["future_executor_prerequisite_guard_created"] is True
    assert report["future_executor_prerequisite_guard_passed"] is True
    assert report["future_executor_review_prerequisites_ready_review_only"] is True
    assert report["metadata_only_key_reference_required"] is True
    assert report["fresh_pre_submit_payload_validation_required"] is True
    assert report["fresh_pre_order_risk_gate_recheck_required"] is True
    assert report["manual_kill_switch_confirmation_required"] is True
    assert report["future_executor_review_required_before_any_order"] is True
    assert report["actual_executor_enablement_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["external_order_submission_performed"] is False
    assert report["exchange_endpoint_called"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert Path("storage/latest/phase7_7_future_executor_review_prerequisite_design_report.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_review_prerequisite_packet_review_only.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_review_prerequisite_guard_report.json").exists()
    assert Path("storage/latest/PHASE7_7_FUTURE_EXECUTOR_REVIEW_PREREQUISITE_DESIGN_HANDOFF_REVIEW_ONLY.md").exists()


def test_phase7_7_prerequisite_packet_forbids_executor_enablement() -> None:
    persist_phase7_7_future_executor_review_prerequisite_design_report()
    packet = json.load(open("storage/latest/future_signed_testnet_executor_review_prerequisite_packet_review_only.json", encoding="utf-8"))

    assert packet["packet_type"] == "future_signed_testnet_executor_review_prerequisite_packet_review_only"
    assert packet["review_only"] is True
    assert packet["prerequisite_design_only"] is True
    assert packet["future_executor_review_prerequisites_ready_review_only"] is True
    assert packet["executor_enablement_authority"] is False
    assert packet["signed_testnet_execution_authority"] is False
    assert packet["signed_testnet_order_submission_authority"] is False
    assert "actual_executor_enablement" in packet["forbidden_scope"]
    assert "actual_signed_testnet_order_submission" in packet["forbidden_scope"]
    assert "metadata_only_key_reference_validation_report" in packet["required_future_artifacts_before_any_executor_enablement_review"]
    assert "fresh_pre_order_risk_gate_review_report" in packet["required_future_artifacts_before_any_executor_enablement_review"]
    assert packet["ready_for_signed_testnet_execution"] is False
    assert packet["testnet_order_submission_allowed"] is False
    assert packet["place_order_enabled"] is False
    assert packet["signed_order_executor_enabled"] is False


def test_phase7_7_guard_is_review_only_and_blocks_execution() -> None:
    persist_phase7_7_future_executor_review_prerequisite_design_report()
    guard = json.load(open("storage/latest/future_signed_testnet_executor_review_prerequisite_guard_report.json", encoding="utf-8"))

    assert guard["guard_type"] == "future_signed_testnet_executor_review_prerequisite_guard_review_only"
    assert guard["review_only"] is True
    assert guard["guard_passed"] is True
    assert guard["blocks_executor_enablement"] is True
    assert guard["blocks_order_submission"] is True
    assert guard["ready_for_signed_testnet_execution"] is False
    assert guard["testnet_order_submission_allowed"] is False
    assert guard["place_order_enabled"] is False
    assert guard["cancel_order_enabled"] is False
    assert guard["signed_order_executor_enabled"] is False


def test_phase7_7_blocks_if_phase7_6_not_ready() -> None:
    persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report()
    path = Path("storage/latest/phase7_6_disabled_signed_testnet_session_operator_handoff_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_6_DISABLED_SIGNED_TESTNET_SESSION_OPERATOR_HANDOFF_BLOCKED_REVIEW_ONLY"
    source["phase7_6_operator_handoff_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _guard = build_phase7_7_future_executor_review_prerequisite_design_report(cfg=cfg, run_phase7_6_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_6_OPERATOR_HANDOFF_NOT_READY" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_7_blocks_on_unsafe_source_flags() -> None:
    persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report()
    path = Path("storage/latest/phase7_6_disabled_signed_testnet_session_operator_handoff_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["signed_order_executor_enabled"] = True
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _guard = build_phase7_7_future_executor_review_prerequisite_design_report(cfg=cfg, run_phase7_6_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert any(reason.startswith("UNSAFE_PHASE7_7_SOURCE_FLAGS:phase7_6_operator_handoff") for reason in report["block_reasons"])
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
