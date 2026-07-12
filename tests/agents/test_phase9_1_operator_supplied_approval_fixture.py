from __future__ import annotations

from pathlib import Path

from crypto_ai_system.config import load_config
from crypto_ai_system.validation.phase9_1_operator_supplied_approval_fixture import (
    STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY,
    build_phase9_1_operator_supplied_approval_fixture_report,
    persist_phase9_1_operator_supplied_approval_fixture_report,
)
from tests.agents.test_phase9_1_actual_operator_approval_intake_hardening import _write_ready_phase9_1_sources


def _write_ready_phase9_1_hardened_sources() -> None:
    _write_ready_phase9_1_sources()
    from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import (
        persist_phase9_1_actual_operator_approval_intake_hardening_report,
    )

    persist_phase9_1_actual_operator_approval_intake_hardening_report(run_phase9_1_first=False)


def test_phase9_1_operator_supplied_approval_fixture_validates_review_only() -> None:
    _write_ready_phase9_1_hardened_sources()
    cfg = load_config()
    report, fixture, validation_report, negative_fixture_results = build_phase9_1_operator_supplied_approval_fixture_report(
        cfg=cfg,
        run_phase9_1_hardening_first=False,
    )

    assert report["status"] == STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["fixture_only"] is True
    assert report["fixture_not_actual_runtime_approval"] is True
    assert report["phase9_1_operator_supplied_approval_fixture_validated"] is True
    assert report["phase9_1_actual_approval_complete_for_fixture_only"] is True
    assert report["phase9_2_submit_guard_recheck_may_begin"] is True
    assert report["phase9_2_order_submission_authorized"] is False
    assert fixture["operator_decision"] == "approve_single_signed_testnet_order"
    assert fixture["actual_operator_approval_recorded"] is True
    assert fixture["operator_supplied_fixture_only"] is True
    assert fixture["fixture_not_actual_runtime_approval"] is True
    assert validation_report["fixture_valid_review_only"] is True
    assert validation_report["fixture_values_complete_review_only"] is True
    assert negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] is True
    for payload in (report, fixture, validation_report, negative_fixture_results):
        assert payload["testnet_order_submission_allowed"] is False
        assert payload["place_order_enabled"] is False
        assert payload["cancel_order_enabled"] is False
        assert payload["signed_order_executor_enabled"] is False
        assert payload["actual_order_submission_performed"] is False
        assert payload["order_endpoint_called"] is False
        assert payload["http_request_sent"] is False
        assert payload["signature_created"] is False


def test_phase9_1_operator_supplied_approval_fixture_persist_writes_artifacts() -> None:
    _write_ready_phase9_1_hardened_sources()
    report = persist_phase9_1_operator_supplied_approval_fixture_report(run_phase9_1_hardening_first=False)

    assert report["status"] == STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY
    assert Path("storage/latest/phase9_1_operator_supplied_approval_fixture_report.json").exists()
    assert Path("storage/latest/phase9_1_operator_supplied_approval_FIXTURE_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/phase9_1_operator_supplied_approval_fixture_validation_report.json").exists()
    assert Path("storage/latest/phase9_1_operator_supplied_approval_fixture_negative_results.json").exists()
    assert Path("storage/latest/PHASE9_1_OPERATOR_SUPPLIED_APPROVAL_FIXTURE_HANDOFF_REVIEW_ONLY.md").exists()
    assert Path("storage/signed_testnet/phase9_1_operator_supplied_approval_FIXTURE_REVIEW_ONLY.json").exists()
