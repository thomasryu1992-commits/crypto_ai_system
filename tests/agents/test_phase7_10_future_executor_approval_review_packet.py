from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_9_future_executor_approval_intake_validator import (
    persist_phase7_9_future_executor_approval_intake_validator_report,
)
from crypto_ai_system.validation.phase7_10_future_executor_approval_review_packet import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_10_future_executor_approval_review_packet_report,
    persist_phase7_10_future_executor_approval_review_packet_report,
)


def test_phase7_10_records_future_executor_approval_review_packet() -> None:
    report = persist_phase7_10_future_executor_approval_review_packet_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["review_only"] is True
    assert report["approval_review_packet_only"] is True
    assert report["phase7_10_review_packet_ready"] is True
    assert report["future_executor_approval_review_packet_created"] is True
    assert report["future_executor_approval_review_guard_created"] is True
    assert report["review_guard_passed"] is True
    assert report["phase7_9_intake_validation_ready"] is True
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
    assert Path("storage/latest/phase7_10_future_executor_approval_review_packet_report.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_approval_review_packet_review_only.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_approval_review_guard_report.json").exists()


def test_phase7_10_review_packet_and_guard_are_safe() -> None:
    persist_phase7_10_future_executor_approval_review_packet_report()
    packet = json.load(open("storage/latest/future_signed_testnet_executor_approval_review_packet_review_only.json", encoding="utf-8"))
    guard = json.load(open("storage/latest/future_signed_testnet_executor_approval_review_guard_report.json", encoding="utf-8"))

    assert packet["packet_type"] == "future_signed_testnet_executor_approval_review_packet_review_only"
    assert packet["review_only"] is True
    assert packet["not_runtime_authority"] is True
    assert packet["actual_executor_approval_created"] is False
    assert packet["actual_executor_enablement_performed"] is False
    assert packet["actual_order_submission_performed"] is False
    assert packet["ready_for_signed_testnet_execution"] is False
    assert packet["testnet_order_submission_allowed"] is False
    assert packet["place_order_enabled"] is False
    assert packet["cancel_order_enabled"] is False
    assert packet["signed_order_executor_enabled"] is False
    assert guard["guard_type"] == "future_signed_testnet_executor_approval_review_guard_review_only"
    assert guard["guard_passed"] is True
    assert guard["blocks_executor_enablement"] is True
    assert guard["blocks_order_submission"] is True
    assert guard["actual_executor_approval_created"] is False
    assert guard["actual_executor_enablement_performed"] is False
    assert guard["actual_order_submission_performed"] is False


def test_phase7_10_blocks_if_phase7_9_not_ready() -> None:
    persist_phase7_9_future_executor_approval_intake_validator_report()
    path = Path("storage/latest/phase7_9_future_executor_approval_intake_validator_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_9_FUTURE_EXECUTOR_APPROVAL_INTAKE_VALIDATOR_BLOCKED_REVIEW_ONLY"
    source["phase7_9_intake_validation_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _guard = build_phase7_10_future_executor_approval_review_packet_report(cfg=cfg, run_phase7_9_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_9_INTAKE_VALIDATOR_NOT_READY" in report["block_reasons"]
    assert "PHASE7_9_INTAKE_VALIDATION_NOT_READY" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_10_blocks_unsafe_source_flags() -> None:
    persist_phase7_9_future_executor_approval_intake_validator_report()
    path = Path("storage/latest/future_signed_testnet_executor_approval_intake_validation_record_review_only.json")
    source = json.load(open(path, encoding="utf-8"))
    source["place_order_enabled"] = True
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _guard = build_phase7_10_future_executor_approval_review_packet_report(cfg=cfg, run_phase7_9_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert any(reason.startswith("UNSAFE_PHASE7_10_SOURCE_FLAGS:future_executor_approval_intake_validation_record") for reason in report["block_reasons"])
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False

