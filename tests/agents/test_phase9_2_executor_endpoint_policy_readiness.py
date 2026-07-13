from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_executor_endpoint_policy_and_readiness import (
    STATUS_PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_RECORDED_STILL_DISABLED,
    build_endpoint_policy_application_design,
    build_executor_policy_application_design,
    build_real_submit_readiness_packet,
    persist_phase9_2_executor_endpoint_policy_readiness_report,
    validate_endpoint_policy_application_design,
    validate_executor_policy_application_design,
    validate_real_submit_readiness_packet,
)


def test_phase9_2_executor_endpoint_policy_readiness_records_still_disabled() -> None:
    report = persist_phase9_2_executor_endpoint_policy_readiness_report()

    assert report["status"] == STATUS_PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_RECORDED_STILL_DISABLED
    assert report["phase9_2_executor_endpoint_policy_readiness_recorded"] is True
    assert report["executor_policy_application_design_ready"] is True
    assert report["endpoint_policy_application_design_ready"] is True
    assert report["real_submit_readiness_packet_ready_for_manual_review"] is True
    assert report["runtime_authority_granted"] is False
    assert report["executor_policy_application_performed"] is False
    assert report["endpoint_policy_application_performed"] is False
    assert report["endpoint_policy_changed"] is False
    assert report["secret_manager_runtime_binding_performed"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["phase9_3_status_polling_may_begin"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["negative_fixture_results"]["all_negative_fixtures_blocked_fail_closed"] is True
    assert "PHASE9_2_READINESS_REQUIRES_SEPARATE_REAL_OPERATOR_APPROVAL_RECORD_NOT_FIXTURE" in report["block_reasons"]


def test_phase9_2_executor_endpoint_policy_artifacts_persist_to_latest_and_signed_testnet() -> None:
    persist_phase9_2_executor_endpoint_policy_readiness_report()
    cfg = load_config(Path.cwd())
    latest = Path(cfg.get("storage.latest_dir", "storage/latest"))
    if not latest.is_absolute():
        latest = cfg.root / latest
    signed = cfg.root / "storage" / "signed_testnet"

    expected = [
        "phase9_2_executor_endpoint_policy_readiness_report.json",
        "executor_policy_application_DESIGN_STILL_DISABLED_REVIEW_ONLY.json",
        "endpoint_policy_application_DESIGN_STILL_DISABLED_REVIEW_ONLY.json",
        "real_submit_readiness_PACKET_STILL_DISABLED_REVIEW_ONLY.json",
        "phase9_2_executor_policy_application_validation_report.json",
        "phase9_2_endpoint_policy_application_validation_report.json",
        "phase9_2_real_submit_readiness_packet_validation_report.json",
        "phase9_2_executor_endpoint_policy_readiness_negative_fixture_results.json",
        "PHASE9_2_EXECUTOR_ENDPOINT_POLICY_READINESS_HANDOFF_STILL_DISABLED_REVIEW_ONLY.md",
    ]
    for name in expected:
        assert (latest / name).exists(), name
        assert (signed / name).exists(), name


def test_phase9_2_executor_policy_negative_flags_fail_closed() -> None:
    design = build_executor_policy_application_design({})
    assert validate_executor_policy_application_design(design)["executor_policy_application_design_valid"] is True

    for field in ["executor_policy_application_performed", "signed_order_executor_enabled", "place_order_enabled", "cancel_order_enabled", "testnet_order_submission_allowed", "phase9_2_order_submission_authorized"]:
        unsafe = dict(design)
        unsafe[field] = True
        validation = validate_executor_policy_application_design(unsafe)
        assert validation["blocked"] is True
        assert validation["fail_closed"] is True
        assert any(field in reason for reason in validation["block_reasons"])


def test_phase9_2_endpoint_policy_negative_flags_fail_closed() -> None:
    executor_design = build_executor_policy_application_design({})
    design = build_endpoint_policy_application_design(executor_design, {})
    assert validate_endpoint_policy_application_design(design)["endpoint_policy_application_design_valid"] is True

    for field in ["endpoint_policy_application_performed", "endpoint_policy_changed", "order_endpoint_call_allowed", "order_status_endpoint_call_allowed", "cancel_endpoint_call_allowed", "http_request_allowed", "phase9_2_order_submission_authorized"]:
        unsafe = dict(design)
        unsafe[field] = True
        validation = validate_endpoint_policy_application_design(unsafe)
        assert validation["blocked"] is True
        assert validation["fail_closed"] is True
        assert any(field in reason for reason in validation["block_reasons"])


def test_phase9_2_real_submit_readiness_packet_never_authorizes_order() -> None:
    executor_design = build_executor_policy_application_design({})
    endpoint_design = build_endpoint_policy_application_design(executor_design, {})
    packet = build_real_submit_readiness_packet(executor_design, endpoint_design, {})

    assert packet["real_submit_readiness_packet_complete"] is True
    assert packet["ready_for_separate_real_runtime_approval_review"] is True
    assert packet["phase9_2_order_submission_authorized"] is False
    assert packet["actual_order_submission_performed"] is False

    unsafe = dict(packet)
    unsafe["phase9_2_order_submission_authorized"] = True
    validation = validate_real_submit_readiness_packet(unsafe)
    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert any("phase9_2_order_submission_authorized" in reason for reason in validation["block_reasons"])


def test_phase9_2_real_submit_readiness_blocks_secret_like_values() -> None:
    executor_design = build_executor_policy_application_design({})
    endpoint_design = build_endpoint_policy_application_design(executor_design, {})
    packet = build_real_submit_readiness_packet(executor_design, endpoint_design, {})
    packet["api_secret"] = "raw-secret-value-should-block"

    validation = validate_real_submit_readiness_packet(packet)
    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert any("SECRET_LIKE_VALUES_PRESENT" in reason for reason in validation["block_reasons"])
