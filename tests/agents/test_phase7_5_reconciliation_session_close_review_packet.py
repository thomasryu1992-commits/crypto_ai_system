from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_4_disabled_execution_reconciliation_session_close import (
    persist_phase7_4_disabled_execution_reconciliation_session_close_report,
)
from crypto_ai_system.validation.phase7_5_reconciliation_session_close_review_packet import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_5_reconciliation_session_close_review_packet_report,
    persist_phase7_5_reconciliation_session_close_review_packet_report,
)


def test_phase7_5_records_reconciliation_session_close_review_packet() -> None:
    report = persist_phase7_5_reconciliation_session_close_review_packet_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["review_only"] is True
    assert report["phase7_5_review_packet_ready"] is True
    assert report["reconciliation_session_close_review_packet_created"] is True
    assert report["promotion_guard_report_created"] is True
    assert report["promotion_guard_passed"] is True
    assert report["disabled_execution_reconciled_review_only"] is True
    assert report["session_closed_review_only"] is True
    assert report["reconciliation_mismatch"] is False
    assert report["observed_fill_count"] == 0
    assert report["observed_position_delta"] == 0.0
    assert report["observed_balance_delta"] == 0.0
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["external_order_submission_performed"] is False
    assert Path("storage/latest/phase7_5_reconciliation_session_close_review_packet_report.json").exists()
    assert Path("storage/latest/signed_testnet_reconciliation_session_close_review_packet_review_only.json").exists()
    assert Path("storage/latest/signed_testnet_reconciliation_session_close_promotion_guard_report.json").exists()
    assert Path("storage/latest/PHASE7_5_RECONCILIATION_SESSION_CLOSE_REVIEW_PACKET_HANDOFF_REVIEW_ONLY.md").exists()


def test_phase7_5_review_packet_forbids_execution_and_promotion() -> None:
    persist_phase7_5_reconciliation_session_close_review_packet_report()
    packet = json.load(open("storage/latest/signed_testnet_reconciliation_session_close_review_packet_review_only.json", encoding="utf-8"))

    assert packet["packet_type"] == "signed_testnet_reconciliation_session_close_review_packet_review_only"
    assert packet["review_only"] is True
    assert packet["signed_testnet_execution_authority"] is False
    assert packet["signed_testnet_order_submission_authority"] is False
    assert packet["signed_testnet_promotion_authority"] is False
    assert "actual_signed_testnet_order_submission" in packet["forbidden_scope"]
    assert "automatic_promotion_to_signed_testnet_or_live" in packet["forbidden_scope"]
    assert packet["promotion_guard_requirement"]["reconciliation_mismatch_blocks_promotion"] is True
    assert packet["promotion_guard_requirement"]["signed_testnet_promotion_allowed"] is False
    assert packet["ready_for_signed_testnet_execution"] is False
    assert packet["testnet_order_submission_allowed"] is False
    assert packet["place_order_enabled"] is False
    assert packet["signed_order_executor_enabled"] is False


def test_phase7_5_promotion_guard_keeps_promotion_disabled() -> None:
    persist_phase7_5_reconciliation_session_close_review_packet_report()
    guard = json.load(open("storage/latest/signed_testnet_reconciliation_session_close_promotion_guard_report.json", encoding="utf-8"))

    assert guard["guard_type"] == "signed_testnet_reconciliation_session_close_promotion_guard_review_only"
    assert guard["guard_passed"] is True
    assert guard["guard_blocked"] is False
    assert guard["guard_blockers"] == []
    assert guard["reconciliation_mismatch_blocks_promotion"] is True
    assert guard["session_close_blocked_blocks_promotion"] is True
    assert guard["signed_testnet_promotion_allowed"] is False
    assert guard["ready_for_signed_testnet_execution"] is False
    assert guard["testnet_order_submission_allowed"] is False
    assert guard["place_order_enabled"] is False
    assert guard["cancel_order_enabled"] is False
    assert guard["signed_order_executor_enabled"] is False


def test_phase7_5_blocks_if_phase7_4_source_not_ready() -> None:
    persist_phase7_4_disabled_execution_reconciliation_session_close_report()
    path = Path("storage/latest/phase7_4_disabled_execution_reconciliation_session_close_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_4_DISABLED_EXECUTION_RECONCILIATION_SESSION_CLOSE_BLOCKED_REVIEW_ONLY"
    source["phase7_4_reconciliation_session_close_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, guard = build_phase7_5_reconciliation_session_close_review_packet_report(cfg=cfg, run_phase7_4_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_4_RECONCILIATION_SESSION_CLOSE_NOT_READY" in report["block_reasons"]
    assert guard["guard_passed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_5_blocks_on_reconciliation_mismatch() -> None:
    persist_phase7_4_disabled_execution_reconciliation_session_close_report()
    path = Path("storage/latest/disabled_execution_reconciliation_report_review_only.json")
    reconciliation = json.load(open(path, encoding="utf-8"))
    reconciliation["execution_reconciled_review_only"] = False
    reconciliation["reconciliation_mismatch"] = True
    reconciliation["reconciliation_mismatch_reasons"] = ["TEST_MISMATCH"]
    path.write_text(json.dumps(reconciliation, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, packet, guard = build_phase7_5_reconciliation_session_close_review_packet_report(cfg=cfg, run_phase7_4_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["reconciliation_mismatch"] is True
    assert "RECONCILIATION_MISMATCH_PRESENT" in report["block_reasons"]
    assert "DISABLED_EXECUTION_NOT_RECONCILED" in guard["guard_blockers"]
    assert "RECONCILIATION_MISMATCH_PRESENT" in guard["guard_blockers"]
    assert packet["promotion_guard_requirement"]["signed_testnet_promotion_allowed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
