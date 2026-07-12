from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_runtime_submit_action_boundary import (
    STATUS_RUNTIME_SUBMIT_ACTION_BOUNDARY_RECORDED_BLOCKED,
    build_runtime_submit_action_boundary_template,
    build_runtime_submit_action_readiness_report,
    persist_phase9_2_runtime_submit_action_boundary_report,
    validate_runtime_submit_action_boundary_template,
    validate_runtime_submit_action_readiness_report,
)


def test_phase9_2_runtime_submit_action_boundary_records_blocked_review_only() -> None:
    report = persist_phase9_2_runtime_submit_action_boundary_report(run_manual_confirmation_first=False)

    assert report["status"] == STATUS_RUNTIME_SUBMIT_ACTION_BOUNDARY_RECORDED_BLOCKED
    assert report["phase9_2_runtime_submit_action_boundary_recorded"] is True
    assert report["runtime_submit_action_ready_for_explicit_submit_approval_review_only"] is True
    assert report["runtime_submit_action_approved"] is False
    assert report["runtime_submit_action_executed"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["negative_fixture_results"]["all_negative_fixtures_blocked_fail_closed"] is True
    assert "PHASE9_2_RUNTIME_SUBMIT_ACTION_REQUIRES_EXPLICIT_RUNTIME_SUBMIT_APPROVAL_TEXT_NOT_PRESENT" in report["block_reasons"]


def test_phase9_2_runtime_submit_action_boundary_artifacts_persist() -> None:
    persist_phase9_2_runtime_submit_action_boundary_report(run_manual_confirmation_first=False)
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    signed = cfg.root / "storage" / "signed_testnet"

    expected = [
        "phase9_2_runtime_submit_action_boundary_report.json",
        "phase9_2_runtime_submit_action_BOUNDARY_BLOCKED_REVIEW_ONLY.json",
        "phase9_2_runtime_submit_action_boundary_validation_report.json",
        "phase9_2_runtime_submit_action_readiness_report.json",
        "phase9_2_runtime_submit_action_readiness_validation_report.json",
        "phase9_2_runtime_submit_action_boundary_negative_fixture_results.json",
        "PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_HANDOFF_BLOCKED_REVIEW_ONLY.md",
    ]
    for name in expected:
        assert (latest / name).exists(), name
        assert (signed / name).exists(), name


def test_phase9_2_runtime_submit_action_boundary_blocks_unsafe_template() -> None:
    template = build_runtime_submit_action_boundary_template({})
    assert validate_runtime_submit_action_boundary_template(template)["runtime_submit_action_boundary_valid"] is True

    unsafe = dict(template)
    unsafe["explicit_runtime_submit_approval_present"] = True
    result = validate_runtime_submit_action_boundary_template(unsafe)
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert any("EXPLICIT_APPROVAL" in reason for reason in result["block_reasons"])

    unsafe = dict(template)
    unsafe["max_order_count"] = 2
    result = validate_runtime_submit_action_boundary_template(unsafe)
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert any("MAX_ORDER_COUNT" in reason for reason in result["block_reasons"])

    unsafe = dict(template)
    unsafe["api_secret"] = "raw-secret-value-should-block"
    result = validate_runtime_submit_action_boundary_template(unsafe)
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert any("SECRET_LIKE_VALUES_PRESENT" in reason for reason in result["block_reasons"])


def test_phase9_2_runtime_submit_action_readiness_never_authorizes_order() -> None:
    template = build_runtime_submit_action_boundary_template({})
    validation = validate_runtime_submit_action_boundary_template(template)
    readiness = build_runtime_submit_action_readiness_report(template, validation, {})

    assert readiness["runtime_submit_action_ready_for_explicit_submit_approval_review_only"] is True
    assert readiness["runtime_submit_action_approved"] is False
    assert readiness["phase9_2_order_submission_authorized"] is False
    assert readiness["actual_order_submission_performed"] is False

    unsafe = dict(readiness)
    unsafe["phase9_2_order_submission_authorized"] = True
    result = validate_runtime_submit_action_readiness_report(unsafe)
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert any("phase9_2_order_submission_authorized" in reason for reason in result["block_reasons"])


def test_phase9_2_runtime_submit_action_script_output_is_still_disabled() -> None:
    report = persist_phase9_2_runtime_submit_action_boundary_report(run_manual_confirmation_first=False)
    for field in [
        "testnet_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
        "runtime_submit_action_approved",
        "runtime_submit_action_executed",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "actual_order_submission_performed",
    ]:
        assert report[field] is False
