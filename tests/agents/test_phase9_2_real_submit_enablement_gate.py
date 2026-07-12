from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_real_submit_enablement_gate import (
    REMAINING_REAL_SUBMIT_BLOCKERS,
    STATUS_PHASE9_2_REAL_SUBMIT_GATE_RECORDED_BLOCKED_REVIEW_ONLY,
    build_phase9_2_real_submit_enablement_gate_report,
    persist_phase9_2_real_submit_enablement_gate_report,
    validate_phase9_2_real_submit_enablement_gate,
)
from tests.agents.test_phase9_3_status_polling_cancel_handling import _write_ready_phase9_2_blocked_wrapper_sources


def _write_ready_phase9_3_sources() -> None:
    _write_ready_phase9_2_blocked_wrapper_sources()
    from crypto_ai_system.validation.phase9_3_status_polling_cancel_handling import persist_phase9_3_status_polling_cancel_handling_report

    persist_phase9_3_status_polling_cancel_handling_report(run_phase9_2_blocked_wrapper_first=False)


def test_phase9_2_real_submit_gate_records_blocked_final_gate_after_phase9_3_design() -> None:
    _write_ready_phase9_3_sources()
    cfg = load_config()
    report, gate, validation_report, negative_fixture_results = build_phase9_2_real_submit_enablement_gate_report(
        cfg=cfg,
        run_phase9_3_design_first=False,
    )

    assert report["status"] == STATUS_PHASE9_2_REAL_SUBMIT_GATE_RECORDED_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["phase9_2_real_submit_enablement_gate_recorded"] is True
    assert report["phase9_2_real_submit_preconditions_ready_for_manual_runtime_review"] is True
    assert report["phase9_2_real_submit_authorized"] is False
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["phase9_3_status_polling_may_begin"] is False
    assert report["phase9_4_testnet_reconciliation_may_begin"] is False
    assert report["real_order_id_created"] is False
    for blocker in REMAINING_REAL_SUBMIT_BLOCKERS:
        assert blocker in report["block_reasons"]
    assert gate["artifact_type"] == "phase9_2_real_submit_enablement_gate_review_only"
    assert gate["blocked_final_runtime_gate"] is True
    assert gate["real_order_id"] is None
    assert gate["order_endpoint_called"] is False
    assert gate["http_request_sent"] is False
    assert gate["signature_created"] is False
    assert validation_report["phase9_2_real_submit_enablement_gate_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True


def test_phase9_2_real_submit_gate_validator_blocks_unsafe_runtime_opening() -> None:
    _write_ready_phase9_3_sources()
    cfg = load_config()
    _report, gate, _validation_report, _negative_fixture_results = build_phase9_2_real_submit_enablement_gate_report(
        cfg=cfg,
        run_phase9_3_design_first=False,
    )
    gate.update(
        {
            "phase9_2_real_submit_authorized": True,
            "phase9_2_order_submission_authorized": True,
            "real_order_id": "fake-real-order-id",
            "real_order_id_created": True,
            "order_endpoint_called": True,
            "http_request_sent": True,
            "signature_created": True,
            "phase9_3_status_polling_may_begin": True,
        }
    )

    result = validate_phase9_2_real_submit_enablement_gate(gate)

    assert result["phase9_2_real_submit_enablement_gate_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "phase9_2_real_submit_authorized" in result["unsafe_truthy_fields"]
    assert "phase9_2_order_submission_authorized" in result["unsafe_truthy_fields"]
    assert "order_endpoint_called" in result["unsafe_truthy_fields"]
    assert "signature_created" in result["unsafe_truthy_fields"]
    assert "PHASE9_2_REAL_SUBMIT_AUTHORIZED_UNEXPECTED" in result["block_reasons"]
    assert "PHASE9_2_REAL_ORDER_ID_PRESENT_UNEXPECTED" in result["block_reasons"]


def test_phase9_2_real_submit_gate_persist_writes_review_only_artifacts() -> None:
    _write_ready_phase9_3_sources()
    report = persist_phase9_2_real_submit_enablement_gate_report(run_phase9_3_design_first=False)

    assert report["status"] == STATUS_PHASE9_2_REAL_SUBMIT_GATE_RECORDED_BLOCKED_REVIEW_ONLY
    assert Path("storage/latest/phase9_2_real_submit_enablement_gate_report.json").exists()
    assert Path("storage/latest/real_submit_enablement_gate_BLOCKED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_2_real_submit_enablement_gate_validation_report.json").exists()
    assert Path("storage/latest/phase9_2_real_submit_enablement_gate_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_2_REAL_SUBMIT_ENABLEMENT_GATE_HANDOFF_BLOCKED_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/real_submit_enablement_gate_BLOCKED_REVIEW_ONLY.json").exists()
