from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_14_future_executor_operator_decision_packet import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_14_future_executor_operator_decision_packet_report,
    persist_phase7_14_future_executor_operator_decision_packet_report,
    validate_operator_decision_packet,
)


def _write_json(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_ready_phase7_13_sources() -> None:
    _write_json(
        "storage/latest/phase7_13_future_executor_enablement_review_packet_report.json",
        {
            "phase7_13_future_executor_enablement_review_packet_id": "phase7_13_ready_review",
            "status": "PHASE7_13_FUTURE_EXECUTOR_ENABLEMENT_REVIEW_PACKET_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "fail_closed": False,
            "review_only": True,
            "phase7_13_review_packet_ready": True,
            "future_executor_enablement_review_packet_created": True,
            "enablement_review_guard_passed": True,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "phase7_13_report_sha256": "phase7_13_hash_fixture",
        },
    )
    _write_json(
        "storage/latest/future_signed_testnet_executor_enablement_review_packet_review_only.json",
        {
            "packet_type": "future_signed_testnet_executor_enablement_review_packet_review_only",
            "review_only": True,
            "enablement_review_only": True,
            "not_runtime_authority": True,
            "source_phase7_13_report_id": "phase7_13_ready_review",
            "metadata_only_key_reference_required": True,
            "fresh_pre_submit_payload_validation_required": True,
            "fresh_pre_order_risk_gate_recheck_required": True,
            "manual_kill_switch_confirmation_required": True,
            "hard_caps_rechecked": True,
            "pre_order_risk_gate_rechecked": True,
            "reconciliation_required_after_any_session": True,
            "session_close_report_required": True,
            "future_executor_enablement_review_required_before_any_order": True,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "future_executor_enablement_review_packet_sha256": "review_packet_hash",
        },
    )
    _write_json(
        "storage/latest/future_signed_testnet_executor_enablement_review_guard_report.json",
        {
            "guard_type": "future_signed_testnet_executor_enablement_review_guard_review_only",
            "review_only": True,
            "guard_passed": True,
            "review_packet_validation": {"packet_valid_review_only": True},
            "blocks_executor_enablement": True,
            "blocks_order_submission": True,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "future_executor_enablement_review_guard_report_sha256": "review_guard_hash",
        },
    )


def test_phase7_14_records_operator_decision_packet_from_ready_sources() -> None:
    _write_ready_phase7_13_sources()
    cfg = load_config()
    report, packet, guard = build_phase7_14_future_executor_operator_decision_packet_report(cfg=cfg, run_phase7_13_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase7_14_operator_decision_packet_ready"] is True
    assert report["future_executor_operator_decision_packet_created"] is True
    assert report["operator_decision_guard_passed"] is True
    assert packet["packet_type"] == "future_signed_testnet_executor_operator_decision_packet_review_only"
    assert packet["not_runtime_authority"] is True
    assert guard["guard_passed"] is True
    assert report["actual_operator_decision_recorded"] is False
    assert report["actual_executor_enablement_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["block_reasons"] == []


def test_phase7_14_persist_writes_artifacts() -> None:
    _write_ready_phase7_13_sources()
    report = persist_phase7_14_future_executor_operator_decision_packet_report(run_phase7_13_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase7_14_future_executor_operator_decision_packet_report.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_operator_decision_packet_review_only.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_operator_decision_guard_report.json").exists()


def test_phase7_14_validator_blocks_unsafe_flags() -> None:
    _write_ready_phase7_13_sources()
    cfg = load_config()
    _report, packet, _guard = build_phase7_14_future_executor_operator_decision_packet_report(cfg=cfg, run_phase7_13_first=False)
    packet["signed_order_executor_enabled"] = True
    packet["testnet_order_submission_allowed"] = True
    result = validate_operator_decision_packet(packet)

    assert result["packet_valid_review_only"] is False
    assert result["packet_blocked_fail_closed"] is True
    assert "signed_order_executor_enabled" in result["unsafe_truthy_fields"]
    assert "testnet_order_submission_allowed" in result["unsafe_truthy_fields"]


def test_phase7_14_blocks_if_phase7_13_not_ready() -> None:
    _write_ready_phase7_13_sources()
    path = Path("storage/latest/phase7_13_future_executor_enablement_review_packet_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_13_FUTURE_EXECUTOR_ENABLEMENT_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"
    source["phase7_13_review_packet_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _guard = build_phase7_14_future_executor_operator_decision_packet_report(cfg=cfg, run_phase7_13_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_13_ENABLEMENT_REVIEW_PACKET_NOT_READY" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_14_blocks_if_review_guard_not_passed() -> None:
    _write_ready_phase7_13_sources()
    path = Path("storage/latest/future_signed_testnet_executor_enablement_review_guard_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["guard_passed"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _packet, _guard = build_phase7_14_future_executor_operator_decision_packet_report(cfg=cfg, run_phase7_13_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert "FUTURE_EXECUTOR_ENABLEMENT_REVIEW_GUARD_NOT_PASSED" in report["block_reasons"]
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
