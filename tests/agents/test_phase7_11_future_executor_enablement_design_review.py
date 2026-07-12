from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_10_future_executor_approval_review_packet import (
    persist_phase7_10_future_executor_approval_review_packet_report,
)
from crypto_ai_system.validation.phase7_11_future_executor_enablement_design_review import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_11_future_executor_enablement_design_review_report,
    persist_phase7_11_future_executor_enablement_design_review_report,
)


def test_phase7_11_records_enablement_design_review() -> None:
    report = persist_phase7_11_future_executor_enablement_design_review_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["review_only"] is True
    assert report["enablement_design_only"] is True
    assert report["phase7_11_enablement_design_ready"] is True
    assert report["future_executor_enablement_design_packet_created"] is True
    assert report["future_executor_enablement_design_guard_created"] is True
    assert report["enablement_design_guard_passed"] is True
    assert report["actual_executor_approval_created"] is False
    assert report["actual_executor_enablement_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["external_order_submission_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["block_reasons"] == []
    assert Path("storage/latest/phase7_11_future_executor_enablement_design_review_report.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_enablement_design_packet_review_only.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_enablement_design_guard_report.json").exists()


def test_phase7_11_packet_and_guard_are_safe() -> None:
    persist_phase7_11_future_executor_enablement_design_review_report()
    packet = json.load(open("storage/latest/future_signed_testnet_executor_enablement_design_packet_review_only.json", encoding="utf-8"))
    guard = json.load(open("storage/latest/future_signed_testnet_executor_enablement_design_guard_report.json", encoding="utf-8"))

    assert packet["packet_type"] == "future_signed_testnet_executor_enablement_design_packet_review_only"
    assert packet["review_only"] is True
    assert packet["enablement_design_only"] is True
    assert packet["not_runtime_authority"] is True
    assert packet["actual_executor_enablement_performed"] is False
    assert packet["actual_order_submission_performed"] is False
    assert packet["ready_for_signed_testnet_execution"] is False
    assert packet["testnet_order_submission_allowed"] is False
    assert packet["place_order_enabled"] is False
    assert packet["cancel_order_enabled"] is False
    assert packet["signed_order_executor_enabled"] is False
    assert "actual_executor_enablement" in packet["forbidden_scope"]
    assert guard["guard_type"] == "future_signed_testnet_executor_enablement_design_guard_review_only"
    assert guard["guard_passed"] is True
    assert guard["blocks_executor_enablement"] is True
    assert guard["blocks_order_submission"] is True
    assert guard["requires_later_explicit_executor_enablement_review"] is True
    assert guard["actual_executor_enablement_performed"] is False
    assert guard["actual_order_submission_performed"] is False


def test_phase7_11_blocks_if_phase7_10_not_ready() -> None:
    persist_phase7_10_future_executor_approval_review_packet_report()
    path = Path("storage/latest/phase7_10_future_executor_approval_review_packet_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_10_FUTURE_EXECUTOR_APPROVAL_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"
    source["phase7_10_review_packet_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _guard = build_phase7_11_future_executor_enablement_design_review_report(cfg=cfg, run_phase7_10_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_10_APPROVAL_REVIEW_PACKET_NOT_READY" in report["block_reasons"]
    assert "PHASE7_10_APPROVAL_REVIEW_NOT_READY" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_11_blocks_unsafe_source_flags() -> None:
    persist_phase7_10_future_executor_approval_review_packet_report()
    path = Path("storage/latest/future_signed_testnet_executor_approval_review_packet_review_only.json")
    source = json.load(open(path, encoding="utf-8"))
    source["signed_order_executor_enabled"] = True
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _guard = build_phase7_11_future_executor_enablement_design_review_report(cfg=cfg, run_phase7_10_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert any(reason.startswith("UNSAFE_PHASE7_11_SOURCE_FLAGS:future_executor_approval_review_packet") for reason in report["block_reasons"])
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_11_blocks_if_review_guard_not_passed() -> None:
    persist_phase7_10_future_executor_approval_review_packet_report()
    path = Path("storage/latest/future_signed_testnet_executor_approval_review_guard_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["guard_passed"] = False
    source["missing_review_prerequisites"] = ["TEST_MISSING_PREREQ"]
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _guard = build_phase7_11_future_executor_enablement_design_review_report(cfg=cfg, run_phase7_10_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert "FUTURE_EXECUTOR_APPROVAL_REVIEW_GUARD_NOT_PASSED" in report["block_reasons"]
    assert "FUTURE_EXECUTOR_ENABLEMENT_DESIGN_GUARD_NOT_PASSED" in report["block_reasons"]
    assert report["actual_executor_enablement_performed"] is False
    assert report["testnet_order_submission_allowed"] is False
