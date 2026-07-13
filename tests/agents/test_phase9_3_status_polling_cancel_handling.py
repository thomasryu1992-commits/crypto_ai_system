from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_3_status_polling_cancel_handling import (
    STATUS_PHASE9_3_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY,
    STATUS_TRANSITION_MODEL,
    build_phase9_3_status_polling_cancel_handling_report,
    persist_phase9_3_status_polling_cancel_handling_report,
    validate_phase9_3_status_polling_cancel_handling_design,
)
from tests.agents.test_phase9_2_blocked_executor_wrapper import _write_ready_phase9_2_recheck_sources


def _write_ready_phase9_2_blocked_wrapper_sources() -> None:
    _write_ready_phase9_2_recheck_sources()
    from crypto_ai_system.validation.phase9_2_blocked_executor_wrapper import persist_phase9_2_blocked_executor_wrapper_report

    persist_phase9_2_blocked_executor_wrapper_report(run_submit_guard_recheck_first=False)


def test_phase9_3_status_polling_cancel_handling_records_blocked_design_without_real_order_id() -> None:
    _write_ready_phase9_2_blocked_wrapper_sources()
    cfg = load_config()
    report, design, validation_report, negative_fixture_results = build_phase9_3_status_polling_cancel_handling_report(
        cfg=cfg,
        run_phase9_2_blocked_wrapper_first=False,
    )

    assert report["status"] == STATUS_PHASE9_3_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["phase9_3_design_recorded"] is True
    assert report["phase9_3_status_polling_may_begin"] is False
    assert report["phase9_4_testnet_reconciliation_may_begin"] is False
    assert report["no_real_order_id_available"] is True
    assert "PHASE9_3_NO_REAL_ORDER_ID_AVAILABLE_STATUS_POLLING_BLOCKED_BY_DESIGN" in report["block_reasons"]
    assert design["real_order_id"] is None
    assert design["status_polling_started"] is False
    assert design["order_status_endpoint_called"] is False
    assert design["cancel_endpoint_called"] is False
    assert design["cancel_request_sent"] is False
    assert design["http_request_sent"] is False
    assert design["signature_created"] is False
    for status in STATUS_TRANSITION_MODEL:
        assert status in design["status_transition_model"]
    assert validation_report["phase9_3_status_polling_cancel_handling_design_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True


def test_phase9_3_validator_blocks_polling_cancel_or_reconciliation_without_order_id() -> None:
    _write_ready_phase9_2_blocked_wrapper_sources()
    cfg = load_config()
    _report, design, _validation_report, _negative_fixture_results = build_phase9_3_status_polling_cancel_handling_report(
        cfg=cfg,
        run_phase9_2_blocked_wrapper_first=False,
    )
    design["real_order_id"] = "fake-order-id"
    design["no_real_order_id_available"] = False
    design["status_polling_started"] = True
    design["order_status_endpoint_called"] = True
    design["cancel_endpoint_called"] = True
    design["cancel_request_sent"] = True
    design["phase9_4_testnet_reconciliation_may_begin"] = True

    result = validate_phase9_3_status_polling_cancel_handling_design(design)

    assert result["phase9_3_status_polling_cancel_handling_design_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "status_polling_started" in result["unsafe_truthy_fields"]
    assert "order_status_endpoint_called" in result["unsafe_truthy_fields"]
    assert "cancel_endpoint_called" in result["unsafe_truthy_fields"]
    assert "cancel_request_sent" in result["unsafe_truthy_fields"]
    assert "PHASE9_3_STATUS_CANCEL_REAL_ORDER_ID_PRESENT_UNEXPECTED" in result["block_reasons"]
    assert "PHASE9_3_OPENED_RECONCILIATION_WITHOUT_FINAL_STATUS" in result["block_reasons"]


def test_phase9_3_persist_writes_blocked_design_artifacts() -> None:
    _write_ready_phase9_2_blocked_wrapper_sources()
    report = persist_phase9_3_status_polling_cancel_handling_report(run_phase9_2_blocked_wrapper_first=False)

    assert report["status"] == STATUS_PHASE9_3_DESIGN_RECORDED_BLOCKED_REVIEW_ONLY
    assert Path("storage/latest/phase9_3_status_polling_cancel_handling_report.json").exists()
    assert Path("storage/latest/status_polling_cancel_handling_DESIGN_BLOCKED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_3_status_polling_cancel_handling_validation_report.json").exists()
    assert Path("storage/latest/phase9_3_status_polling_cancel_handling_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_3_STATUS_POLLING_CANCEL_HANDLING_HANDOFF_BLOCKED_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/status_polling_cancel_handling_DESIGN_BLOCKED_REVIEW_ONLY.json").exists()
