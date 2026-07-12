from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_10_signed_testnet_evidence_intake import (
    EVIDENCE_TEMPLATE_FILES,
    STATUS_PHASE9_10_EVIDENCE_INTAKE_RECORDED_REVIEW_ONLY,
    build_phase9_10_signed_testnet_evidence_intake_report,
    persist_phase9_10_signed_testnet_evidence_intake_report,
    validate_phase9_10_evidence_templates,
)


def _write_ready_sources() -> None:
    latest = Path("storage/latest")
    latest.mkdir(parents=True, exist_ok=True)
    payloads = {
        "phase9_2_runtime_submit_action_boundary_report.json": {
            "status": "PHASE9_2_RUNTIME_SUBMIT_ACTION_BOUNDARY_RECORDED_BLOCKED_REVIEW_ONLY",
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
            "phase9_2_ready_for_manual_final_confirmation": True,
            "phase9_2_order_submission_authorized": False,
        },
        "phase9_2_submit_guard_recheck_after_operator_fixture_report.json": {
            "phase9_2_submit_guard_recheck_ready": True,
            "phase9_2_order_submission_authorized": False,
            "phase9_3_status_polling_may_begin": False,
        },
    }
    import json
    for filename, payload in payloads.items():
        (latest / filename).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_phase9_10_evidence_intake_creates_review_only_templates() -> None:
    _write_ready_sources()
    cfg = load_config()
    report, templates, validation, negative_fixture_results = build_phase9_10_signed_testnet_evidence_intake_report(
        cfg=cfg,
        run_runtime_boundary_first=False,
    )

    assert report["status"] == STATUS_PHASE9_10_EVIDENCE_INTAKE_RECORDED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["phase9_2_execution_evidence_template_ready"] is True
    assert report["phase9_3_status_cancel_evidence_template_ready"] is True
    assert report["phase9_4_reconciliation_evidence_template_ready"] is True
    assert report["phase10_session_validation_evidence_template_ready"] is True
    assert report["phase9_2_actual_submit_performed_by_this_package"] is False
    assert report["phase9_3_status_polling_started_by_this_package"] is False
    assert report["phase9_4_reconciliation_started_by_this_package"] is False
    assert report["phase10_session_validation_started_by_this_package"] is False
    assert "PHASE9_10_EVIDENCE_INTAKE_DOES_NOT_EXECUTE_ORDERS_OR_POLL_ENDPOINTS" in report["block_reasons"]
    assert validation["phase9_10_signed_testnet_evidence_templates_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    assert templates["phase9_2_execution"]["max_order_count"] == 1
    assert templates["phase9_2_execution"]["testnet_only"] is True
    assert templates["phase10_session_validation"]["live_canary_preparation_may_begin"] is False


def test_phase9_10_evidence_intake_validator_blocks_unsafe_flags_and_secrets() -> None:
    _write_ready_sources()
    cfg = load_config()
    _report, templates, _validation, _negative_fixture_results = build_phase9_10_signed_testnet_evidence_intake_report(
        cfg=cfg,
        run_runtime_boundary_first=False,
    )
    templates["phase9_2_execution"]["order_endpoint_called"] = True
    templates["phase9_2_execution"]["secret_value_included"] = True
    templates["phase9_3_status_cancel"]["phase9_3_status_polling_may_begin"] = True
    templates["phase10_session_validation"]["live_canary_preparation_may_begin"] = True

    result = validate_phase9_10_evidence_templates(templates)

    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert any(reason.startswith("PHASE9_10_EVIDENCE_TEMPLATE_UNSAFE_FLAGS:phase9_2_execution") for reason in result["block_reasons"])
    assert "PHASE9_10_EVIDENCE_TEMPLATE_SECRET_INCLUDED:phase9_2_execution" in result["block_reasons"]
    assert "phase9_2_execution" in result["unsafe_template_flags"]


def test_phase9_10_evidence_intake_persists_latest_signed_testnet_and_registry() -> None:
    _write_ready_sources()
    report = persist_phase9_10_signed_testnet_evidence_intake_report(run_runtime_boundary_first=False)

    assert report["status"] == STATUS_PHASE9_10_EVIDENCE_INTAKE_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase9_10_signed_testnet_evidence_intake_report.json").exists()
    assert Path("storage/latest/phase9_10_signed_testnet_evidence_intake_validation_report.json").exists()
    assert Path("storage/latest/phase9_10_signed_testnet_evidence_intake_negative_fixture_results.json").exists()
    for filename in EVIDENCE_TEMPLATE_FILES.values():
        assert Path("storage/latest").joinpath(filename).exists()
        assert Path("storage/signed_testnet").joinpath(filename).exists()
    assert Path("storage/latest/PHASE9_10_SIGNED_TESTNET_EVIDENCE_INTAKE_HANDOFF_REVIEW_ONLY.md").exists()
    assert Path("storage/latest/phase9_10_signed_testnet_evidence_intake_registry_record.json").exists()
