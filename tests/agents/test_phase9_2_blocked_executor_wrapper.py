from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_blocked_executor_wrapper import (
    STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY,
    build_phase9_2_blocked_executor_wrapper_report,
    persist_phase9_2_blocked_executor_wrapper_report,
    validate_phase9_2_blocked_executor_wrapper,
)
from tests.agents.test_phase9_2_submit_guard_recheck import _write_valid_operator_fixture


def _write_ready_phase9_2_recheck_sources() -> None:
    _write_valid_operator_fixture()
    from crypto_ai_system.validation.phase9_2_submit_guard_recheck import persist_phase9_2_submit_guard_recheck_report

    persist_phase9_2_submit_guard_recheck_report(run_operator_fixture_first=False)


def test_phase9_2_blocked_executor_wrapper_records_no_endpoint_no_signature() -> None:
    _write_ready_phase9_2_recheck_sources()
    cfg = load_config()
    report, wrapper, validation_report, negative_fixture_results = build_phase9_2_blocked_executor_wrapper_report(
        cfg=cfg,
        run_submit_guard_recheck_first=False,
    )

    assert report["status"] == STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY
    assert report["phase9_2_blocked_executor_wrapper_recorded"] is True
    assert report["phase9_2_dry_run_executor_wrapper_ready_review_only"] is True
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["phase9_3_status_polling_may_begin"] is False
    assert report["no_real_order_id_created"] is True
    assert wrapper["executor_wrapper_mode"] == "blocked_dry_run_no_endpoint"
    assert wrapper["blocked_executor_wrapper_recorded"] is True
    assert wrapper["executor_enabled"] is False
    assert wrapper["submit_function_invoked"] is False
    assert wrapper["order_endpoint_called"] is False
    assert wrapper["http_request_sent"] is False
    assert wrapper["signature_created"] is False
    assert wrapper["actual_order_submission_performed"] is False
    assert wrapper["real_order_id"] is None
    assert validation_report["phase9_2_blocked_executor_wrapper_valid"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    for payload in (report, wrapper, validation_report, negative_fixture_results):
        assert payload["testnet_order_submission_allowed"] is False
        assert payload["place_order_enabled"] is False
        assert payload["cancel_order_enabled"] is False
        assert payload["signed_order_executor_enabled"] is False


def test_phase9_2_blocked_executor_wrapper_validator_blocks_unsafe_execution_flags() -> None:
    _write_ready_phase9_2_recheck_sources()
    cfg = load_config()
    _report, wrapper, _validation_report, _negative_fixture_results = build_phase9_2_blocked_executor_wrapper_report(
        cfg=cfg,
        run_submit_guard_recheck_first=False,
    )
    wrapper["order_endpoint_called"] = True
    wrapper["http_request_sent"] = True
    wrapper["signature_created"] = True
    wrapper["phase9_2_order_submission_authorized"] = True
    wrapper["phase9_3_status_polling_may_begin"] = True

    result = validate_phase9_2_blocked_executor_wrapper(wrapper)

    assert result["phase9_2_blocked_executor_wrapper_valid"] is False
    assert result["blocked"] is True
    assert result["fail_closed"] is True
    assert "order_endpoint_called" in result["unsafe_truthy_fields"]
    assert "http_request_sent" in result["unsafe_truthy_fields"]
    assert "signature_created" in result["unsafe_truthy_fields"]
    assert "phase9_2_order_submission_authorized" in result["unsafe_truthy_fields"]
    assert "phase9_3_status_polling_may_begin" in result["unsafe_truthy_fields"]


def test_phase9_2_blocked_executor_wrapper_persist_writes_artifacts() -> None:
    _write_ready_phase9_2_recheck_sources()
    report = persist_phase9_2_blocked_executor_wrapper_report(run_submit_guard_recheck_first=False)

    assert report["status"] == STATUS_BLOCKED_EXECUTOR_WRAPPER_RECORDED_REVIEW_ONLY
    assert Path("storage/latest/phase9_2_blocked_executor_wrapper_report.json").exists()
    assert Path("storage/latest/single_testnet_order_BLOCKED_EXECUTOR_WRAPPER_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_2_blocked_executor_wrapper_validation_report.json").exists()
    assert Path("storage/latest/phase9_2_blocked_executor_wrapper_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_2_BLOCKED_EXECUTOR_WRAPPER_HANDOFF_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/single_testnet_order_BLOCKED_EXECUTOR_WRAPPER_REVIEW_ONLY.json").exists()
