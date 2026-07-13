from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_3_9_4_blocked_design_hardening import (
    RECONCILIATION_CHECKS_REQUIRED,
    STATUS_PHASE9_3_9_4_HARDENING_RECORDED_BLOCKED_REVIEW_ONLY,
    STATUS_STATES_REQUIRED,
    build_phase9_3_9_4_blocked_design_hardening_report,
    persist_phase9_3_9_4_blocked_design_hardening_report,
    validate_phase9_3_status_cancel_hardened_design,
    validate_phase9_4_testnet_reconciliation_design,
)
from tests.agents.test_phase9_3_status_polling_cancel_handling import _write_ready_phase9_2_blocked_wrapper_sources


def _write_ready_phase9_3_sources() -> None:
    _write_ready_phase9_2_blocked_wrapper_sources()
    from crypto_ai_system.validation.phase9_3_status_polling_cancel_handling import persist_phase9_3_status_polling_cancel_handling_report

    persist_phase9_3_status_polling_cancel_handling_report(run_phase9_2_blocked_wrapper_first=False)


def test_phase9_3_9_4_blocked_design_hardening_records_hardened_artifacts() -> None:
    _write_ready_phase9_3_sources()
    cfg = load_config()
    report, phase9_3_design, phase9_3_validation, phase9_4_design, phase9_4_validation, negative_fixture_results = build_phase9_3_9_4_blocked_design_hardening_report(
        cfg=cfg,
        run_phase9_3_first=False,
    )

    assert report["status"] == STATUS_PHASE9_3_9_4_HARDENING_RECORDED_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["phase9_3_status_cancel_hardening_recorded"] is True
    assert report["phase9_4_testnet_reconciliation_design_recorded"] is True
    assert report["phase9_3_status_polling_may_begin"] is False
    assert report["phase9_4_testnet_reconciliation_may_begin"] is False
    assert report["phase10_signed_testnet_session_validation_may_begin"] is False
    assert report["real_order_id"] is None
    assert "PHASE9_4_RECONCILIATION_BLOCKED_UNTIL_REAL_PHASE9_2_ORDER_AND_FINAL_STATUS_EXIST" in report["block_reasons"]
    assert phase9_3_validation["phase9_3_status_cancel_hardened_design_valid"] is True
    assert phase9_4_validation["phase9_4_testnet_reconciliation_design_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    for state in STATUS_STATES_REQUIRED:
        assert state in phase9_3_design["status_state_machine"]["states"]
    for check in RECONCILIATION_CHECKS_REQUIRED:
        assert check in phase9_4_design["reconciliation_checks_required"]
        assert check in phase9_4_design["reconciliation_plan"]


def test_phase9_3_hardened_validator_blocks_endpoint_or_cancel_activation() -> None:
    _write_ready_phase9_3_sources()
    cfg = load_config()
    _report, phase9_3_design, _phase9_3_validation, _phase9_4_design, _phase9_4_validation, _negative_fixture_results = build_phase9_3_9_4_blocked_design_hardening_report(
        cfg=cfg,
        run_phase9_3_first=False,
    )
    phase9_3_design["real_order_id"] = "fake-order-id"
    phase9_3_design["no_real_order_id_available"] = False
    phase9_3_design["status_polling_started"] = True
    phase9_3_design["order_status_endpoint_called"] = True
    phase9_3_design["cancel_endpoint_called"] = True
    phase9_3_design["cancel_request_sent"] = True

    result = validate_phase9_3_status_cancel_hardened_design(phase9_3_design)

    assert result["phase9_3_status_cancel_hardened_design_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "PHASE9_3_HARDENED_STATUS_CANCEL_REAL_ORDER_ID_PRESENT" in result["block_reasons"]
    assert "order_status_endpoint_called" in result["unsafe_truthy_fields"]
    assert "cancel_endpoint_called" in result["unsafe_truthy_fields"]


def test_phase9_4_reconciliation_validator_blocks_reconciliation_without_real_exchange_evidence() -> None:
    _write_ready_phase9_3_sources()
    cfg = load_config()
    _report, _phase9_3_design, _phase9_3_validation, phase9_4_design, _phase9_4_validation, _negative_fixture_results = build_phase9_3_9_4_blocked_design_hardening_report(
        cfg=cfg,
        run_phase9_3_first=False,
    )
    phase9_4_design["real_order_id"] = "fake-order-id"
    phase9_4_design["no_real_order_id_available"] = False
    phase9_4_design["reconciliation_started"] = True
    phase9_4_design["exchange_execution_record_present"] = True
    phase9_4_design["phase9_4_testnet_reconciliation_may_begin"] = True

    result = validate_phase9_4_testnet_reconciliation_design(phase9_4_design)

    assert result["phase9_4_testnet_reconciliation_design_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "PHASE9_4_RECONCILIATION_REAL_ORDER_ID_PRESENT" in result["block_reasons"]
    assert "PHASE9_4_RECONCILIATION_MAY_BEGIN_WITHOUT_REAL_ORDER" in result["block_reasons"]
    assert "reconciliation_started" in result["unsafe_truthy_fields"]


def test_phase9_3_9_4_persist_writes_latest_signed_testnet_and_registry_artifacts() -> None:
    _write_ready_phase9_3_sources()
    report = persist_phase9_3_9_4_blocked_design_hardening_report(run_phase9_3_first=False)

    assert report["status"] == STATUS_PHASE9_3_9_4_HARDENING_RECORDED_BLOCKED_REVIEW_ONLY
    assert Path("storage/latest/phase9_3_9_4_blocked_design_hardening_report.json").exists()
    assert Path("storage/latest/phase9_3_status_cancel_HARDENED_BLOCKED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_4_testnet_reconciliation_DESIGN_BLOCKED_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_4_testnet_reconciliation_validation_report.json").exists()
    assert Path("storage/latest/phase9_3_9_4_blocked_design_hardening_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_3_9_4_BLOCKED_DESIGN_HARDENING_HANDOFF_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/phase9_4_testnet_reconciliation_DESIGN_BLOCKED_REVIEW_ONLY.json").exists()
