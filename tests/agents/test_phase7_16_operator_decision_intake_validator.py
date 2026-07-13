from __future__ import annotations

import json
from pathlib import Path

from core.json_io import atomic_write_json
from crypto_ai_system.config import load_config
from tests.agents.test_phase7_15_operator_decision_intake_template import _write_ready_phase7_14_sources
from crypto_ai_system.validation.phase7_15_operator_decision_intake_template import (
    build_phase7_15_operator_decision_intake_template_report,
)
from crypto_ai_system.validation.phase7_16_operator_decision_intake_validator import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_16_operator_decision_intake_validator_report,
    validate_operator_decision_intake_submission,
)


def _write_ready_phase7_15_sources() -> None:
    _write_ready_phase7_14_sources()
    cfg = load_config()
    report, template, guard = build_phase7_15_operator_decision_intake_template_report(
        cfg=cfg, run_phase7_14_first=False
    )
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    atomic_write_json(latest / "phase7_15_operator_decision_intake_template_report.json", report)
    atomic_write_json(latest / "operator_decision_intake_TEMPLATE_REVIEW_ONLY.json", template)
    atomic_write_json(latest / "operator_decision_intake_template_guard_report.json", guard)


def test_phase7_16_validates_operator_decision_intake_fixture_review_only() -> None:
    _write_ready_phase7_15_sources()
    cfg = load_config()
    report, submission, validation_report = build_phase7_16_operator_decision_intake_validator_report(
        cfg=cfg, run_phase7_15_first=False
    )

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase7_16_intake_validation_ready"] is True
    assert report["operator_decision_intake_validation_passed"] is True
    assert report["validated_fixture_only"] is True
    assert submission["fixture_only"] is True
    assert submission["review_only"] is True
    assert validation_report["submission_validation_passed"] is True
    assert validation_report["blocks_executor_enablement"] is True
    assert validation_report["blocks_order_submission"] is True
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


def test_phase7_16_submission_validator_blocks_unsafe_flags() -> None:
    _write_ready_phase7_15_sources()
    cfg = load_config()
    _report, submission, _validation_report = build_phase7_16_operator_decision_intake_validator_report(
        cfg=cfg, run_phase7_15_first=False
    )
    submission["signed_order_executor_enabled"] = True
    submission["testnet_order_submission_allowed"] = True

    result = validate_operator_decision_intake_submission(submission)

    assert result["submission_validation_passed"] is False
    assert result["submission_blocked_fail_closed"] is True
    assert "signed_order_executor_enabled" in result["unsafe_truthy_fields"]
    assert "testnet_order_submission_allowed" in result["unsafe_truthy_fields"]


def test_phase7_16_blocks_if_phase7_15_not_ready() -> None:
    _write_ready_phase7_15_sources()
    path = Path("storage/latest/phase7_15_operator_decision_intake_template_report.json")
    source = json.load(open(path, encoding="utf-8"))
    source["status"] = "PHASE7_15_OPERATOR_DECISION_INTAKE_TEMPLATE_BLOCKED_REVIEW_ONLY"
    source["phase7_15_intake_template_ready"] = False
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")

    cfg = load_config()
    report, _submission, _validation_report = build_phase7_16_operator_decision_intake_validator_report(
        cfg=cfg, run_phase7_15_first=False
    )

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_15_OPERATOR_DECISION_INTAKE_TEMPLATE_NOT_READY" in report["block_reasons"]
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["signed_order_executor_enabled"] is False
