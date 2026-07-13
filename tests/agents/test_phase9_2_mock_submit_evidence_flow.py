from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.execution.phase9_2_single_testnet_runtime_submit_wrapper import (
    APPROVAL_TEXT_KO,
    RuntimeSubmitIntent,
    run_phase9_2_single_testnet_runtime_submit_wrapper,
)
from crypto_ai_system.validation.phase9_2_mock_submit_evidence_flow import (
    STATUS_MOCK_SUBMIT_EVIDENCE_FLOW_RECORDED,
    build_negative_fixture_results,
    build_phase9_2_mock_submit_evidence_flow_report,
    persist_phase9_2_mock_submit_evidence_flow,
    validate_mock_submit_evidence_flow_payload,
)


def _write_wrapper_sources() -> None:
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


def _write_mock_submit_wrapper_report() -> None:
    _write_wrapper_sources()
    cfg = load_config()
    intent = RuntimeSubmitIntent(
        approval_text=f"{APPROVAL_TEXT_KO} 범위는 testnet 단일 주문 1개로 제한합니다. live/mainnet 주문은 승인하지 않습니다.",
        key_fingerprint_sha256="b" * 64,
        confirm_real_testnet_submit=True,
        fresh_endpoint_time_risk_refresh_passed=True,
        kill_switch_confirmed=True,
    )
    report, _template = run_phase9_2_single_testnet_runtime_submit_wrapper(cfg=cfg, intent=intent)
    Path("storage/latest/phase9_2_single_testnet_runtime_submit_wrapper_report.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def test_mock_submit_evidence_flow_builds_phase9_3_9_4_inputs_without_real_unlocks() -> None:
    _write_mock_submit_wrapper_report()
    cfg = load_config()
    report, mock_execution, mock_status, mock_reconciliation = build_phase9_2_mock_submit_evidence_flow_report(cfg=cfg)

    assert report["status"] == STATUS_MOCK_SUBMIT_EVIDENCE_FLOW_RECORDED
    assert report["blocked"] is False
    assert report["mock_flow_ready_for_review_only_evidence_intake"] is True
    assert mock_execution["mock_evidence_only"] is True
    assert mock_execution["usable_for_real_phase9_3_polling"] is False
    assert mock_status["real_status_polling_allowed"] is False
    assert mock_status["phase9_3_status_polling_may_begin"] is False
    assert mock_reconciliation["real_reconciliation_allowed"] is False
    assert mock_reconciliation["phase9_4_testnet_reconciliation_may_begin"] is False
    assert report["actual_order_submission_performed"] is False
    assert report["order_endpoint_called"] is False
    assert report["http_request_sent"] is False
    assert report["signature_created"] is False


def test_mock_submit_evidence_flow_blocks_when_wrapper_source_is_dry_run() -> None:
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    (latest / "phase9_2_single_testnet_runtime_submit_wrapper_report.json").write_text(json.dumps({
        "mock_order_submission_performed": False,
        "actual_order_submission_performed": False,
        "real_exchange_endpoint_call_performed": False,
    }), encoding="utf-8")
    cfg = load_config()
    report, mock_execution, mock_status, mock_reconciliation = build_phase9_2_mock_submit_evidence_flow_report(cfg=cfg)

    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert mock_execution == {}
    assert mock_status == {}
    assert mock_reconciliation == {}
    assert "PHASE9_2_MOCK_EVIDENCE_FLOW_REQUIRES_MOCK_SUBMIT_PERFORMED_TRUE" in report["block_reasons"]


def test_mock_submit_evidence_flow_validator_blocks_real_or_secret_flags() -> None:
    payload = {
        "review_only": True,
        "mock_evidence_only": True,
        "actual_order_submission_performed": True,
        "real_exchange_endpoint_call_performed": True,
        "phase9_3_status_polling_may_begin": True,
        "api_secret": "SHOULD_NOT_BE_HERE",
    }
    validation = validate_mock_submit_evidence_flow_payload(payload)

    assert validation["blocked"] is True
    assert validation["fail_closed"] is True
    assert "actual_order_submission_performed" in validation["unsafe_true_fields"]
    assert validation["secret_like_values_detected"] is True


def test_mock_submit_evidence_flow_persists_reports_and_negative_fixtures() -> None:
    _write_mock_submit_wrapper_report()
    report = persist_phase9_2_mock_submit_evidence_flow()
    negative = build_negative_fixture_results()

    assert report["mock_flow_ready_for_review_only_evidence_intake"] is True
    assert negative["all_negative_fixtures_blocked_fail_closed"] is True
    assert Path("storage/latest/phase9_2_mock_submit_evidence_flow_report.json").exists()
    assert Path("storage/latest/phase9_2_mock_execution_EVIDENCE_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_3_mock_status_input_FROM_PHASE9_2_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_4_mock_reconciliation_input_FROM_PHASE9_2_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/PHASE9_2_MOCK_SUBMIT_EVIDENCE_FLOW_HANDOFF_REVIEW_ONLY.md").exists()
    assert Path("storage/latest/phase9_2_mock_submit_evidence_flow_registry_record.json").exists()
