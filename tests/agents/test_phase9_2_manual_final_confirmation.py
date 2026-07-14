from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_manual_final_confirmation import (
    STATUS_PHASE9_2_MANUAL_FINAL_CONFIRMATION_BLOCKED_STILL_DISABLED,
    STATUS_PHASE9_2_MANUAL_FINAL_CONFIRMATION_VALID_STILL_DISABLED,
    build_manual_final_confirmation_readiness_report,
    build_manual_final_confirmation_template,
    persist_phase9_2_manual_final_confirmation_report,
    validate_manual_final_confirmation_readiness_report,
    validate_manual_final_confirmation_template,
)


def test_phase9_2_manual_final_confirmation_records_still_disabled() -> None:
    report = persist_phase9_2_manual_final_confirmation_report(run_final_approval_first=False)

    assert report["status"] == STATUS_PHASE9_2_MANUAL_FINAL_CONFIRMATION_BLOCKED_STILL_DISABLED
    assert report["phase9_2_manual_final_confirmation_recorded"] is False
    assert report["phase9_2_ready_for_separate_submit_action_review_only"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["negative_fixture_results"]["all_negative_fixtures_blocked_fail_closed"] is True
    assert "PHASE9_2_MANUAL_CONFIRMATION_REQUIRES_SEPARATE_REAL_SUBMIT_ACTION_AFTER_CONFIRMATION" in report["block_reasons"]


def test_phase9_2_manual_final_confirmation_artifacts_persist() -> None:
    persist_phase9_2_manual_final_confirmation_report(run_final_approval_first=False)
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    signed = cfg.root / "storage" / "signed_testnet"

    expected = [
        "phase9_2_manual_final_confirmation_report.json",
        "phase9_2_manual_final_confirmation_TEMPLATE_STILL_DISABLED_REVIEW_ONLY.json",
        "phase9_2_manual_final_confirmation_validation_report.json",
        "phase9_2_manual_final_confirmation_readiness_report.json",
        "phase9_2_manual_final_confirmation_readiness_validation_report.json",
        "phase9_2_manual_final_confirmation_negative_fixture_results.json",
        "PHASE9_2_MANUAL_FINAL_CONFIRMATION_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md",
    ]
    for name in expected:
        assert (latest / name).exists(), name
        assert (signed / name).exists(), name


def test_phase9_2_manual_final_confirmation_blocks_missing_confirmations() -> None:
    template = build_manual_final_confirmation_template({})
    assert validate_manual_final_confirmation_template(template)["manual_final_confirmation_valid"] is True

    unsafe = dict(template)
    unsafe["confirm_kill_switch_ready"] = False
    result = validate_manual_final_confirmation_template(unsafe)
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert any("confirm_kill_switch_ready" in reason for reason in result["block_reasons"])

    unsafe = dict(template)
    unsafe["api_secret"] = "raw-secret-value-should-block"
    result = validate_manual_final_confirmation_template(unsafe)
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert any("SECRET_LIKE_VALUES_PRESENT" in reason for reason in result["block_reasons"])


def test_phase9_2_manual_final_confirmation_readiness_never_authorizes_order() -> None:
    template = build_manual_final_confirmation_template({})
    validation = validate_manual_final_confirmation_template(template)
    readiness = build_manual_final_confirmation_readiness_report(template, validation, {})

    assert readiness["manual_final_confirmation_ready"] is True
    assert readiness["phase9_2_order_submission_authorized"] is False
    assert readiness["actual_order_submission_performed"] is False

    unsafe = dict(readiness)
    unsafe["phase9_2_order_submission_authorized"] = True
    result = validate_manual_final_confirmation_readiness_report(unsafe)
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert any("phase9_2_order_submission_authorized" in reason for reason in result["block_reasons"])


def test_phase9_2_manual_final_confirmation_script_output_is_still_disabled() -> None:
    report = persist_phase9_2_manual_final_confirmation_report(run_final_approval_first=False)
    for field in [
        "testnet_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "actual_order_submission_performed",
    ]:
        assert report[field] is False
