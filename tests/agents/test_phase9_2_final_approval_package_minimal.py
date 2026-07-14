from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_final_approval_package_minimal import (
    STATUS_PHASE9_2_FINAL_APPROVAL_PACKAGE_BLOCKED_STILL_DISABLED,
    STATUS_PHASE9_2_FINAL_APPROVAL_PACKAGE_VALID_STILL_DISABLED,
    build_final_approval_packet_template,
    build_final_submit_readiness_report,
    persist_phase9_2_final_approval_package_report,
    validate_final_approval_packet,
    validate_final_submit_readiness_report,
)


def test_phase9_2_final_approval_package_records_still_disabled() -> None:
    report = persist_phase9_2_final_approval_package_report(run_readiness_first=False)

    assert report["status"] == STATUS_PHASE9_2_FINAL_APPROVAL_PACKAGE_BLOCKED_STILL_DISABLED
    assert report["phase9_2_final_approval_package_recorded"] is False
    assert report["phase9_2_ready_for_manual_final_confirmation"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["negative_fixture_results"]["all_negative_fixtures_blocked_fail_closed"] is True
    assert "PHASE9_2_FINAL_APPROVAL_REQUIRES_REAL_OPERATOR_APPROVAL_RECORD_NOT_FIXTURE_BEFORE_RUNTIME_SUBMIT" in report["block_reasons"]


def test_phase9_2_final_approval_package_artifacts_persist() -> None:
    persist_phase9_2_final_approval_package_report(run_readiness_first=False)
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    signed = cfg.root / "storage" / "signed_testnet"

    expected = [
        "phase9_2_final_approval_package_report.json",
        "phase9_2_final_approval_packet_TEMPLATE_STILL_DISABLED_REVIEW_ONLY.json",
        "phase9_2_final_approval_validation_report.json",
        "phase9_2_final_submit_readiness_report.json",
        "phase9_2_final_submit_readiness_validation_report.json",
        "phase9_2_final_approval_package_negative_fixture_results.json",
        "PHASE9_2_FINAL_APPROVAL_PACKAGE_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md",
    ]
    for name in expected:
        assert (latest / name).exists(), name
        assert (signed / name).exists(), name


def test_phase9_2_final_approval_packet_blocks_unsafe_values() -> None:
    packet = build_final_approval_packet_template({})
    assert validate_final_approval_packet(packet)["final_approval_packet_valid"] is True

    for field in ["phase9_2_order_submission_authorized", "actual_order_submission_performed", "order_endpoint_called", "http_request_sent", "signature_created", "signed_order_executor_enabled"]:
        unsafe = dict(packet)
        unsafe[field] = True
        validation = validate_final_approval_packet(unsafe)
        assert validation["blocked"] is True
        assert validation["fail_closed"] is True
        assert any(field in reason for reason in validation["block_reasons"])


def test_phase9_2_final_approval_packet_blocks_scope_and_secret_violations() -> None:
    packet = build_final_approval_packet_template({})
    packet["max_order_count"] = 2
    validation = validate_final_approval_packet(packet)
    assert validation["blocked"] is True
    assert any("MAX_ORDER_COUNT_NOT_ONE" in reason for reason in validation["block_reasons"])

    packet = build_final_approval_packet_template({})
    packet["api_secret"] = "raw-secret-value-should-block"
    validation = validate_final_approval_packet(packet)
    assert validation["blocked"] is True
    assert any("SECRET_LIKE_VALUES_PRESENT" in reason for reason in validation["block_reasons"])


def test_phase9_2_final_submit_readiness_never_authorizes_order() -> None:
    packet = build_final_approval_packet_template({})
    validation = validate_final_approval_packet(packet)
    readiness = build_final_submit_readiness_report(packet, validation, {})

    assert readiness["phase9_2_ready_for_manual_final_confirmation"] is True
    assert readiness["phase9_2_order_submission_authorized"] is False
    assert readiness["actual_order_submission_performed"] is False

    unsafe = dict(readiness)
    unsafe["phase9_2_order_submission_authorized"] = True
    result = validate_final_submit_readiness_report(unsafe)
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert any("phase9_2_order_submission_authorized" in reason for reason in result["block_reasons"])
