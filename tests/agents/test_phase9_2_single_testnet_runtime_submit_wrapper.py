from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.phase9_2_single_testnet_runtime_submit_wrapper import (
    APPROVAL_TEXT_KO,
    STATUS_PHASE9_2_RUNTIME_SUBMIT_WRAPPER_BLOCKED,
    STATUS_PHASE9_2_RUNTIME_SUBMIT_WRAPPER_MOCK_SUBMITTED,
    RuntimeSubmitIntent,
    build_negative_fixture_results,
    build_runtime_submit_wrapper_template,
    persist_phase9_2_single_testnet_runtime_submit_wrapper,
    run_phase9_2_single_testnet_runtime_submit_wrapper,
    validate_runtime_submit_wrapper_payload,
)


def _write_sources() -> None:
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    payloads = {
        "phase9_2_runtime_submit_action_boundary_report.json": {
            "runtime_submit_action_ready_for_explicit_submit_approval_review_only": True,
            "runtime_submit_action_approved": False,
            "runtime_submit_action_executed": False,
            "actual_order_submission_performed": False,
        },
        "phase9_2_manual_final_confirmation_report.json": {
            "manual_final_confirmation_valid": True,
            "phase9_2_order_submission_authorized": False,
            "actual_order_submission_performed": False,
        },
        "phase9_2_final_approval_package_report.json": {
            "final_approval_packet_valid": True,
            "phase9_2_order_submission_authorized": False,
        },
        "phase9_10_signed_testnet_evidence_intake_report.json": {
            "phase9_2_execution_evidence_template_ready": True,
            "phase9_10_evidence_templates_valid": True,
            "actual_order_submission_performed": False,
        },
    }
    for filename, payload in payloads.items():
        (latest / filename).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_runtime_submit_wrapper_default_is_blocked_and_does_not_call_endpoint() -> None:
    _write_sources()
    cfg = load_config()
    report, template = run_phase9_2_single_testnet_runtime_submit_wrapper(cfg=cfg)

    assert template["mocked_by_default"] is True
    assert template["real_endpoint_call_default_allowed"] is False
    assert report["status"] == STATUS_PHASE9_2_RUNTIME_SUBMIT_WRAPPER_BLOCKED
    assert report["blocked"] is True
    assert report["mock_order_submission_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False


def test_runtime_submit_wrapper_can_mock_submit_only_with_all_runtime_controls() -> None:
    _write_sources()
    cfg = load_config()
    intent = RuntimeSubmitIntent(
        approval_text=f"{APPROVAL_TEXT_KO} 범위는 testnet 단일 주문 1개로 제한합니다. live/mainnet 주문은 승인하지 않습니다.",
        key_fingerprint_sha256="a" * 64,
        confirm_real_testnet_submit=True,
        fresh_endpoint_time_risk_refresh_passed=True,
        kill_switch_confirmed=True,
    )
    report, _template = run_phase9_2_single_testnet_runtime_submit_wrapper(cfg=cfg, intent=intent)

    assert report["status"] == STATUS_PHASE9_2_RUNTIME_SUBMIT_WRAPPER_MOCK_SUBMITTED
    assert report["blocked"] is False
    assert report["mock_order_submission_performed"] is True
    assert report["real_exchange_endpoint_call_performed"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False
    assert report["signed_order_executor_enabled_after_action"] is False
    assert report["mock_exchange_response_redacted"]["mock_response"] is True
    assert report["mock_exchange_response_redacted"]["api_secret_value_logged"] is False


def test_runtime_submit_wrapper_validator_blocks_unsafe_flags_and_secret_values() -> None:
    _write_sources()
    template = build_runtime_submit_wrapper_template()
    template["actual_order_submission_performed"] = True
    template["order_endpoint_called"] = True
    template["api_secret"] = "SHOULD_NOT_BE_HERE"
    validation = validate_runtime_submit_wrapper_payload(template)

    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert "actual_order_submission_performed" in validation["unsafe_true_fields"]
    assert validation["secret_like_values_detected"] is True


def test_runtime_submit_wrapper_persists_reports_and_negative_fixtures() -> None:
    _write_sources()
    report = persist_phase9_2_single_testnet_runtime_submit_wrapper()
    negative = build_negative_fixture_results()

    assert report["actual_order_submission_performed"] is False
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert Path("storage/latest/phase9_2_single_testnet_runtime_submit_wrapper_report.json").exists()
    assert Path("storage/latest/phase9_2_single_testnet_runtime_submit_WRAPPER_MOCK_DEFAULT_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/PHASE9_2_SINGLE_TESTNET_RUNTIME_SUBMIT_WRAPPER_HANDOFF_MOCK_DEFAULT_REVIEW_ONLY.md").exists()
    assert Path("storage/latest/phase9_2_single_testnet_runtime_submit_wrapper_registry_record.json").exists()
