from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_5_reconciliation_session_close_review_packet import (
    persist_phase7_5_reconciliation_session_close_review_packet_report,
)
from crypto_ai_system.validation.phase7_6_disabled_signed_testnet_session_operator_handoff import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_6_disabled_signed_testnet_session_operator_handoff_report,
    persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report,
)


def test_phase7_6_records_operator_handoff_and_checklist() -> None:
    report = persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["review_only"] is True
    assert report["operator_handoff_only"] is True
    assert report["phase7_6_operator_handoff_ready"] is True
    assert report["operator_handoff_packet_created"] is True
    assert report["executor_approval_checklist_created"] is True
    assert report["executor_approval_checklist_ready_review_only"] is True
    assert report["promotion_guard_passed"] is True
    assert report["future_executor_approval_required_before_any_order"] is True
    assert report["actual_executor_enablement_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["external_order_submission_performed"] is False
    assert report["exchange_endpoint_called"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert Path("storage/latest/phase7_6_disabled_signed_testnet_session_operator_handoff_report.json").exists()
    assert Path("storage/latest/disabled_signed_testnet_session_operator_handoff_packet_review_only.json").exists()
    assert Path("storage/latest/signed_testnet_executor_approval_checklist_review_only.json").exists()
    assert Path("storage/latest/PHASE7_6_DISABLED_SIGNED_TESTNET_SESSION_OPERATOR_HANDOFF_REVIEW_ONLY.md").exists()


def test_phase7_6_handoff_packet_forbids_execution_enablement() -> None:
    persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report()
    packet = json.load(open("storage/latest/disabled_signed_testnet_session_operator_handoff_packet_review_only.json", encoding="utf-8"))

    assert packet["packet_type"] == "disabled_signed_testnet_session_operator_handoff_review_only"
    assert packet["review_only"] is True
    assert packet["operator_handoff_only"] is True
    assert packet["actual_executor_enablement_authority"] is False
    assert packet["signed_testnet_execution_authority"] is False
    assert packet["signed_testnet_order_submission_authority"] is False
    assert "actual_executor_enablement" in packet["forbidden_scope"]
    assert "actual_signed_testnet_order_submission" in packet["forbidden_scope"]
    assert packet["operator_next_decision"]["future_executor_approval_required_before_any_order"] is True
    assert packet["operator_next_decision"]["current_packet_grants_runtime_permission"] is False
    assert packet["ready_for_signed_testnet_execution"] is False
    assert packet["testnet_order_submission_allowed"] is False
    assert packet["place_order_enabled"] is False
    assert packet["signed_order_executor_enabled"] is False


def test_phase7_6_executor_approval_checklist_is_review_only() -> None:
    persist_phase7_6_disabled_signed_testnet_session_operator_handoff_report()
    checklist = json.load(open("storage/latest/signed_testnet_executor_approval_checklist_review_only.json", encoding="utf-8"))

    assert checklist["checklist_type"] == "signed_testnet_executor_approval_checklist_review_only"
    assert checklist["review_only"] is True
    assert checklist["checklist_ready_review_only"] is True
    assert checklist["all_required_items_observed"] is True
    assert checklist["executor_approval_authority"] is False
    assert checklist["executor_enablement_authority"] is False
    assert checklist["signed_testnet_execution_authority"] is False
    assert checklist["signed_testnet_order_submission_authority"] is False
    assert any(item["item"] == "separate_future_executor_approval_required" for item in checklist["checklist_items"])
    assert checklist["ready_for_signed_testnet_execution"] is False
    assert checklist["testnet_order_submission_allowed"] is False
    assert checklist["place_order_enabled"] is False
    assert checklist["cancel_order_enabled"] is False
    assert checklist["signed_order_executor_enabled"] is False


def test_phase7_6_blocks_if_phase7_5_not_ready() -> None:
    persist_phase7_5_reconciliation_session_close_review_packet_report()
    path = Path("storage/latest/phase7_5_reconciliation_session_close_review_packet_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_5_RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"
    source["phase7_5_review_packet_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, checklist = build_phase7_6_disabled_signed_testnet_session_operator_handoff_report(cfg=cfg, run_phase7_5_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_5_RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_NOT_READY" in report["block_reasons"]
    assert checklist["checklist_ready_review_only"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_6_blocks_on_unsafe_source_flags() -> None:
    persist_phase7_5_reconciliation_session_close_review_packet_report()
    path = Path("storage/latest/phase7_5_reconciliation_session_close_review_packet_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["place_order_enabled"] = True
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _checklist = build_phase7_6_disabled_signed_testnet_session_operator_handoff_report(cfg=cfg, run_phase7_5_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert any(reason.startswith("UNSAFE_PHASE7_6_SOURCE_FLAGS:phase7_5_reconciliation_session_close_review_packet") for reason in report["block_reasons"])
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
