from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_15_operator_decision_intake_template import (
    ALLOWED_DECISION_OPTIONS,
    OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS,
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_15_operator_decision_intake_template_report,
    persist_phase7_15_operator_decision_intake_template_report,
    validate_operator_decision_intake_template,
)


def _write_json(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_ready_phase7_14_sources() -> None:
    _write_json(
        "storage/latest/phase7_14_future_executor_operator_decision_packet_report.json",
        {
            "phase7_14_future_executor_operator_decision_packet_id": "phase7_14_ready_review",
            "status": "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_DECISION_PACKET_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "fail_closed": False,
            "review_only": True,
            "operator_decision_packet_only": True,
            "phase7_14_operator_decision_packet_ready": True,
            "future_executor_operator_decision_packet_created": True,
            "operator_decision_guard_passed": True,
            "future_operator_decision_required_before_any_order": True,
            "actual_operator_decision_recorded": False,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "signed_testnet_promotion_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "phase7_14_report_sha256": "phase7_14_hash_fixture",
        },
    )
    _write_json(
        "storage/latest/future_signed_testnet_executor_operator_decision_packet_review_only.json",
        {
            "packet_type": "future_signed_testnet_executor_operator_decision_packet_review_only",
            "phase7_14_version": "phase7_14_future_executor_operator_decision_packet_v1",
            "source_phase7_14_report_id": "phase7_14_ready_review",
            "source_phase7_13_report_id": "phase7_13_ready_review",
            "review_only": True,
            "operator_decision_packet_only": True,
            "not_runtime_authority": True,
            "source_phase7_13_report_hash": "phase7_13_hash_fixture",
            "source_enablement_review_packet_hash": "review_packet_hash",
            "source_enablement_review_guard_hash": "review_guard_hash",
            "operator_decision_options": [
                "APPROVE_FUTURE_EXECUTOR_REVIEW_ONLY_NOT_ENABLEMENT",
                "DEFER_FUTURE_EXECUTOR_REVIEW",
                "REJECT_FUTURE_EXECUTOR_REVIEW",
            ],
            "required_before_any_future_executor_enablement": True,
            "metadata_only_key_reference_required": True,
            "fresh_pre_submit_payload_validation_required": True,
            "fresh_pre_order_risk_gate_recheck_required": True,
            "manual_kill_switch_confirmation_required": True,
            "hard_caps_rechecked": True,
            "pre_order_risk_gate_rechecked": True,
            "reconciliation_required_after_any_session": True,
            "session_close_report_required": True,
            "future_operator_decision_required_before_any_order": True,
            "actual_operator_decision_recorded": False,
            "actual_executor_approval_created": False,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
            "external_order_submission_performed": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "signed_testnet_promotion_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "future_executor_operator_decision_packet_sha256": "operator_packet_hash",
        },
    )
    _write_json(
        "storage/latest/future_signed_testnet_executor_operator_decision_guard_report.json",
        {
            "guard_type": "future_signed_testnet_executor_operator_decision_guard_review_only",
            "phase7_14_version": "phase7_14_future_executor_operator_decision_packet_v1",
            "source_phase7_14_report_id": "phase7_14_ready_review",
            "review_only": True,
            "operator_decision_guard_only": True,
            "guard_passed": True,
            "source_phase7_13_review_packet_ready": True,
            "source_enablement_review_guard_passed": True,
            "blocks_executor_enablement": True,
            "blocks_order_submission": True,
            "actual_operator_decision_recorded": False,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
            "external_order_submission_performed": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "signed_testnet_promotion_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "future_executor_operator_decision_guard_report_sha256": "operator_guard_hash",
        },
    )


def test_phase7_15_records_operator_decision_intake_template_from_ready_sources() -> None:
    _write_ready_phase7_14_sources()
    cfg = load_config()
    report, template, guard = build_phase7_15_operator_decision_intake_template_report(cfg=cfg, run_phase7_14_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase7_15_intake_template_ready"] is True
    assert report["operator_decision_intake_template_created"] is True
    assert report["operator_decision_intake_template_guard_passed"] is True
    assert template["template_type"] == "operator_decision_intake_TEMPLATE_REVIEW_ONLY"
    assert template["review_only"] is True
    assert template["template_only"] is True
    assert template["intake_template_only"] is True
    assert template["not_runtime_authority"] is True
    assert template["allowed_decision_options"] == ALLOWED_DECISION_OPTIONS
    assert template["operator_decision_intake_required_fields"] == OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS
    assert guard["guard_passed"] is True
    assert report["actual_operator_decision_recorded"] is False
    assert report["actual_phase8_approval_granted"] is False
    assert report["actual_executor_enablement_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["block_reasons"] == []


def test_phase7_15_persist_writes_artifacts() -> None:
    _write_ready_phase7_14_sources()
    report = persist_phase7_15_operator_decision_intake_template_report(run_phase7_14_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase7_15_operator_decision_intake_template_report.json").exists()
    assert Path("storage/latest/operator_decision_intake_TEMPLATE_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/operator_decision_intake_template_guard_report.json").exists()
    assert Path("storage/signed_testnet/operator_decision_intake_TEMPLATE_REVIEW_ONLY.json").exists()


def test_phase7_15_validator_blocks_unsafe_flags() -> None:
    _write_ready_phase7_14_sources()
    cfg = load_config()
    _report, template, _guard = build_phase7_15_operator_decision_intake_template_report(cfg=cfg, run_phase7_14_first=False)
    template["signed_order_executor_enabled"] = True
    template["testnet_order_submission_allowed"] = True
    result = validate_operator_decision_intake_template(template)

    assert result["template_valid_review_only"] is False
    assert result["template_blocked_fail_closed"] is True
    assert "signed_order_executor_enabled" in result["unsafe_truthy_fields"]
    assert "testnet_order_submission_allowed" in result["unsafe_truthy_fields"]


def test_phase7_15_blocks_if_phase7_14_not_ready() -> None:
    _write_ready_phase7_14_sources()
    path = Path("storage/latest/phase7_14_future_executor_operator_decision_packet_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_DECISION_PACKET_BLOCKED_REVIEW_ONLY"
    source["phase7_14_operator_decision_packet_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _template, _guard = build_phase7_15_operator_decision_intake_template_report(cfg=cfg, run_phase7_14_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_14_OPERATOR_DECISION_PACKET_NOT_READY" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_15_blocks_if_operator_decision_guard_not_passed() -> None:
    _write_ready_phase7_14_sources()
    path = Path("storage/latest/future_signed_testnet_executor_operator_decision_guard_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["guard_passed"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _template, _guard = build_phase7_15_operator_decision_intake_template_report(cfg=cfg, run_phase7_14_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert "FUTURE_EXECUTOR_OPERATOR_DECISION_GUARD_NOT_PASSED" in report["block_reasons"]
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
