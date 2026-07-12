from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase7_8_future_executor_approval_packet_template import (
    persist_phase7_8_future_executor_approval_packet_template_report,
)
from crypto_ai_system.validation.phase7_9_future_executor_approval_intake_validator import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_9_future_executor_approval_intake_validator_report,
    persist_phase7_9_future_executor_approval_intake_validator_report,
    validate_future_executor_approval_submission,
)


def test_phase7_9_records_future_executor_approval_intake_validation() -> None:
    report = persist_phase7_9_future_executor_approval_intake_validator_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["review_only"] is True
    assert report["intake_validation_only"] is True
    assert report["phase7_9_intake_validation_ready"] is True
    assert report["future_executor_approval_submission_template_created"] is True
    assert report["future_executor_approval_intake_validation_record_created"] is True
    assert report["intake_guard_passed"] is True
    assert report["valid_future_executor_approval_submission_passed_review_only_validation"] is True
    assert report["invalid_future_executor_approval_submission_fixtures_blocked_fail_closed"] is True
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
    assert Path("storage/latest/phase7_9_future_executor_approval_intake_validator_report.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_approval_intake_validation_record_review_only.json").exists()
    assert Path("storage/latest/future_signed_testnet_executor_approval_intake_guard_report.json").exists()
    assert Path("storage/signed_testnet/future_executor_approval_packet_submission_TEMPLATE_REVIEW_ONLY.json").exists()


def test_phase7_9_submission_template_and_guard_are_safe() -> None:
    persist_phase7_9_future_executor_approval_intake_validator_report()
    template = json.load(open("storage/signed_testnet/future_executor_approval_packet_submission_TEMPLATE_REVIEW_ONLY.json", encoding="utf-8"))
    guard = json.load(open("storage/latest/future_signed_testnet_executor_approval_intake_guard_report.json", encoding="utf-8"))

    assert template["template_type"] == "future_signed_testnet_executor_approval_packet_submission_TEMPLATE_REVIEW_ONLY"
    assert template["review_only"] is True
    assert template["template_only"] is True
    assert template["submission_template_only"] is True
    assert template["not_runtime_authority"] is True
    assert template["actual_executor_approval_created"] is False
    assert template["actual_executor_enablement_performed"] is False
    assert template["actual_order_submission_performed"] is False
    assert template["ready_for_signed_testnet_execution"] is False
    assert template["testnet_order_submission_allowed"] is False
    assert template["place_order_enabled"] is False
    assert template["cancel_order_enabled"] is False
    assert template["signed_order_executor_enabled"] is False
    assert guard["guard_type"] == "future_signed_testnet_executor_approval_intake_guard_review_only"
    assert guard["guard_passed"] is True
    assert guard["actual_executor_approval_created"] is False
    assert guard["actual_executor_enablement_performed"] is False
    assert guard["actual_order_submission_performed"] is False


def test_phase7_9_invalid_fixtures_are_blocked_fail_closed() -> None:
    report = persist_phase7_9_future_executor_approval_intake_validator_report()
    invalid = report["invalid_fixture_validation"]

    assert invalid["missing_metadata_fingerprint"]["submission_blocked_fail_closed"] is True
    assert "MISSING_REQUIRED_FIELDS:metadata_only_key_fingerprint" in invalid["missing_metadata_fingerprint"]["submission_blockers"]
    assert invalid["prerequisite_hash_mismatch"]["submission_blocked_fail_closed"] is True
    assert "PREREQUISITE_PACKET_HASH_MISMATCH" in invalid["prerequisite_hash_mismatch"]["submission_blockers"]
    assert invalid["hard_cap_exceeded"]["submission_blocked_fail_closed"] is True
    assert "MAX_TESTNET_NOTIONAL_EXCEEDS_REVIEW_CAP" in invalid["hard_cap_exceeded"]["submission_blockers"]
    assert invalid["kill_switch_not_rechecked"]["submission_blocked_fail_closed"] is True
    assert any(reason.startswith("REQUIRED_FRESH_RECHECK_FIELDS_NOT_TRUE") for reason in invalid["kill_switch_not_rechecked"]["submission_blockers"])
    assert invalid["unsafe_executor_flag"]["submission_blocked_fail_closed"] is True
    assert any(reason.startswith("UNSAFE_FUTURE_EXECUTOR_APPROVAL_FIELDS_TRUE") for reason in invalid["unsafe_executor_flag"]["submission_blockers"])


def test_phase7_9_blocks_if_phase7_8_not_ready() -> None:
    persist_phase7_8_future_executor_approval_packet_template_report()
    path = Path("storage/latest/phase7_8_future_executor_approval_packet_template_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_8_FUTURE_EXECUTOR_APPROVAL_PACKET_TEMPLATE_BLOCKED_REVIEW_ONLY"
    source["phase7_8_template_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, *_ = build_phase7_9_future_executor_approval_intake_validator_report(cfg=cfg, run_phase7_8_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_8_TEMPLATE_REPORT_NOT_READY" in report["block_reasons"]
    assert "PHASE7_8_TEMPLATE_NOT_READY" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_9_blocks_unsafe_source_flags() -> None:
    persist_phase7_8_future_executor_approval_packet_template_report()
    path = Path("storage/latest/future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY.json")
    source = json.load(open(path, encoding="utf-8"))
    source["place_order_enabled"] = True
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, *_ = build_phase7_9_future_executor_approval_intake_validator_report(cfg=cfg, run_phase7_8_first=False)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert any(reason.startswith("UNSAFE_PHASE7_9_SOURCE_FLAGS:future_executor_approval_template") for reason in report["block_reasons"])
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_9_validate_submission_rejects_placeholder_and_secret_like_metadata() -> None:
    report, submission_template, _record, _guard, fixtures = build_phase7_9_future_executor_approval_intake_validator_report()
    prereq = json.load(open("storage/latest/future_signed_testnet_executor_review_prerequisite_packet_review_only.json", encoding="utf-8"))
    bad = dict(fixtures["valid"])
    bad["operator_id"] = "MANUAL_REQUIRED_OPERATOR_ID"
    bad["metadata_only_key_fingerprint"] = "api_secret_real_value_should_not_be_here"

    result = validate_future_executor_approval_submission(bad, template=submission_template, prerequisite_packet=prereq)

    assert report["secret_value_accessed"] is False
    assert result["submission_valid_review_only"] is False
    assert result["submission_blocked_fail_closed"] is True
    assert any(reason.startswith("PLACEHOLDER_FIELDS_NOT_FILLED") for reason in result["submission_blockers"])
    assert any(reason.startswith("METADATA_ONLY_KEY_FIELD_LOOKS_LIKE_SECRET_VALUE") for reason in result["submission_blockers"])
