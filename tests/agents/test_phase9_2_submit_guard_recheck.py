from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_2_submit_guard_recheck import (
    STATUS_RECHECK_READY_REVIEW_ONLY,
    build_phase9_2_submit_guard_recheck_report,
    persist_phase9_2_submit_guard_recheck_report,
)
from tests.agents.test_phase9_1_operator_supplied_approval_fixture import _write_ready_phase9_1_hardened_sources


def _write_valid_operator_fixture() -> None:
    _write_ready_phase9_1_hardened_sources()
    from crypto_ai_system.validation.phase9_1_operator_supplied_approval_fixture import (
        persist_phase9_1_operator_supplied_approval_fixture_report,
    )

    persist_phase9_1_operator_supplied_approval_fixture_report(run_phase9_1_hardening_first=False)


def test_phase9_2_submit_guard_recheck_ready_but_does_not_submit() -> None:
    _write_valid_operator_fixture()
    cfg = load_config()
    report, recheck, negative_fixture_results = build_phase9_2_submit_guard_recheck_report(
        cfg=cfg,
        run_operator_fixture_first=False,
    )

    assert report["status"] == STATUS_RECHECK_READY_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["fixture_only"] is True
    assert report["phase9_2_submit_guard_recheck_ready"] is True
    assert report["phase9_2_pre_submit_conditions_ready_for_review_only"] is True
    assert report["phase9_2_order_submission_authorized"] is False
    assert report["phase9_2_single_testnet_order_submit_may_begin"] is False
    assert report["phase9_3_status_polling_may_begin"] is False
    assert "PHASE9_2_OPERATOR_DECISION_NOT_EXPLICIT_APPROVAL" in report["cleared_previous_phase9_2_blockers_by_fixture"]
    assert "PHASE9_2_ORDER_ENDPOINT_CALLS_DISABLED_BY_DESIGN" in report["remaining_real_submit_blockers"]
    assert recheck["dry_order_payload_preview"]["no_order_endpoint_called"] is True
    assert recheck["dry_order_payload_preview"]["no_signature_created"] is True
    assert recheck["dry_order_payload_preview"]["no_http_request_sent"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    for payload in (report, recheck, negative_fixture_results):
        assert payload["testnet_order_submission_allowed"] is False
        assert payload["place_order_enabled"] is False
        assert payload["cancel_order_enabled"] is False
        assert payload["signed_order_executor_enabled"] is False
        assert payload["actual_order_submission_performed"] is False
        assert payload["order_endpoint_called"] is False
        assert payload["http_request_sent"] is False
        assert payload["signature_created"] is False


def test_phase9_2_submit_guard_recheck_persist_writes_artifacts() -> None:
    _write_valid_operator_fixture()
    report = persist_phase9_2_submit_guard_recheck_report(run_operator_fixture_first=False)

    assert report["status"] == STATUS_RECHECK_READY_REVIEW_ONLY
    assert Path("storage/latest/phase9_2_submit_guard_recheck_after_operator_fixture_report.json").exists()
    assert Path("storage/latest/single_testnet_order_submit_guard_recheck_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_2_submit_guard_recheck_negative_fixture_results.json").exists()
    assert Path("storage/latest/PHASE9_2_SUBMIT_GUARD_RECHECK_AFTER_OPERATOR_FIXTURE_HANDOFF_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/single_testnet_order_submit_guard_recheck_REVIEW_ONLY.json").exists()
