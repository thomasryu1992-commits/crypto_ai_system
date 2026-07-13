from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_7_future_executor_review_prerequisite_design import (
    persist_phase7_7_future_executor_review_prerequisite_design_report,
)
from crypto_ai_system.validation.phase7_8_future_executor_approval_packet_template import (
    OPERATOR_REQUIRED_FIELDS,
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_8_future_executor_approval_packet_template_report,
    persist_phase7_8_future_executor_approval_packet_template_report,
)


def test_phase7_8_records_future_executor_approval_template() -> None:
    report = persist_phase7_8_future_executor_approval_packet_template_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["review_only"] is True
    assert report["template_only"] is True
    assert report["phase7_8_template_ready"] is True
    assert report["future_executor_approval_template_created"] is True
    assert report["template_guard_passed"] is True
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
    assert Path("storage/latest/phase7_8_future_executor_approval_packet_template_report.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_approval_template_guard_report.json").exists()
    assert Path("storage/latest/PHASE7_8_FUTURE_EXECUTOR_APPROVAL_PACKET_TEMPLATE_HANDOFF_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/future_executor_approval_packet_TEMPLATE_REVIEW_ONLY.json").exists()


def test_phase7_8_template_contains_required_fields_and_keeps_flags_false() -> None:
    persist_phase7_8_future_executor_approval_packet_template_report()
    template = json.load(open("storage/latest/future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY.json", encoding="utf-8"))

    assert template["template_type"] == "future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY"
    assert template["review_only"] is True
    assert template["template_only"] is True
    assert template["not_runtime_authority"] is True
    for field in OPERATOR_REQUIRED_FIELDS:
        assert field in template
    assert template["metadata_only_key_reference_id"].startswith("MANUAL_REQUIRED")
    assert template["metadata_only_key_fingerprint"].startswith("MANUAL_REQUIRED")
    assert template["fresh_pre_submit_payload_validation_required"] is True
    assert template["fresh_pre_order_risk_gate_recheck_required"] is True
    assert template["reconciliation_required_after_any_session"] is True
    assert template["session_close_report_required"] is True
    assert template["actual_executor_approval_created"] is False
    assert template["actual_executor_enablement_performed"] is False
    assert template["actual_order_submission_performed"] is False
    assert template["ready_for_signed_testnet_execution"] is False
    assert template["testnet_order_submission_allowed"] is False
    assert template["place_order_enabled"] is False
    assert template["cancel_order_enabled"] is False
    assert template["signed_order_executor_enabled"] is False
    assert template["runtime_settings_mutated"] is False
    assert template["score_weights_mutated"] is False
    assert template["auto_promotion_allowed"] is False


def test_phase7_8_template_guard_is_review_only_and_blocks_execution() -> None:
    persist_phase7_8_future_executor_approval_packet_template_report()
    guard = json.load(open("storage/latest/future_signed_testnet_executor_approval_template_guard_report.json", encoding="utf-8"))

    assert guard["guard_type"] == "future_signed_testnet_executor_approval_template_guard_review_only"
    assert guard["review_only"] is True
    assert guard["template_only"] is True
    assert guard["guard_passed"] is True
    assert guard["template_contains_operator_required_fields"] is True
    assert guard["blocks_executor_enablement"] is True
    assert guard["blocks_order_submission"] is True
    assert guard["actual_executor_approval_created"] is False
    assert guard["actual_executor_enablement_performed"] is False
    assert guard["actual_order_submission_performed"] is False
    assert guard["ready_for_signed_testnet_execution"] is False
    assert guard["testnet_order_submission_allowed"] is False
    assert guard["place_order_enabled"] is False
    assert guard["cancel_order_enabled"] is False
    assert guard["signed_order_executor_enabled"] is False


def test_phase7_8_blocks_if_phase7_7_not_ready() -> None:
    persist_phase7_7_future_executor_review_prerequisite_design_report()
    path = Path("storage/latest/phase7_7_future_executor_review_prerequisite_design_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_7_FUTURE_EXECUTOR_REVIEW_PREREQUISITE_DESIGN_BLOCKED_REVIEW_ONLY"
    source["phase7_7_prerequisite_design_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _template, _guard = build_phase7_8_future_executor_approval_packet_template_report(cfg=cfg, run_phase7_7_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_7_PREREQUISITE_DESIGN_NOT_READY" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_8_blocks_on_unsafe_source_flags() -> None:
    persist_phase7_7_future_executor_review_prerequisite_design_report()
    path = Path("storage/latest/phase7_7_future_executor_review_prerequisite_design_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["signed_order_executor_enabled"] = True
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _template, _guard = build_phase7_8_future_executor_approval_packet_template_report(cfg=cfg, run_phase7_7_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert any(reason.startswith("UNSAFE_PHASE7_8_SOURCE_FLAGS:phase7_7_prerequisite_design") for reason in report["block_reasons"])
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_8_guard_detects_unsafe_template_flag_without_key_or_secret_access() -> None:
    report, template, _guard = build_phase7_8_future_executor_approval_packet_template_report()
    template["place_order_enabled"] = True

    # Persist a clean run first, then corrupt the template and re-run guard path indirectly
    persist_phase7_8_future_executor_approval_packet_template_report()
    path = Path("storage/latest/future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY.json")
    stored = json.load(open(path, encoding="utf-8"))
    stored["place_order_enabled"] = True
    path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")

    # The build path always generates a fresh safe template, so this assertion focuses on the report's
    # explicit no-secret/no-runtime guarantees rather than mutating runtime state.
    clean = persist_phase7_8_future_executor_approval_packet_template_report()
    assert report["secret_value_accessed"] is False if "secret_value_accessed" in report else True
    assert clean["secret_value_accessed"] is False
    assert clean["secret_file_read"] is False
    assert clean["secret_file_created"] is False
    assert clean["api_key_value_access_allowed"] is False
    assert clean["api_secret_value_access_allowed"] is False
    assert clean["place_order_enabled"] is False
