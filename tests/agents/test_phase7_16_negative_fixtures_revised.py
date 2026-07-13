from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.validation.phase7_16_operator_decision_intake_validator import (
    REQUIRED_PHASE7_15_NEGATIVE_FIXTURES,
    build_phase7_16_operator_decision_intake_validator_report,
    persist_phase7_16_operator_decision_intake_validator_report,
)
from tests.agents.test_phase7_15_boundary_reconciliation import test_phase7_15_persist_writes_revised_boundary_artifacts
from tests.agents.test_phase7_15_operator_decision_intake_template import _write_ready_phase7_14_sources


def _write_ready_phase7_15r_sources() -> None:
    _write_ready_phase7_14_sources()
    # The helper persists all revised Phase 7.15 boundary artifacts and fixtures.
    from crypto_ai_system.validation.phase7_15_operator_decision_intake_template import (
        persist_phase7_15_operator_decision_intake_template_report,
    )

    persist_phase7_15_operator_decision_intake_template_report(run_phase7_14_first=False)


def test_phase7_16r_consumes_required_negative_fixtures_and_blocks_all() -> None:
    _write_ready_phase7_15r_sources()

    report, _submission, validation_report = build_phase7_16_operator_decision_intake_validator_report(
        run_phase7_15_first=False
    )

    assert report["phase7_16_validator_hardened_revised"] is True
    assert report["dedicated_operator_decision_intake_validator"] is True
    assert report["approval_intake_validator_reused"] is False
    assert report["phase7_15_boundary_validation_consumed"] is True
    assert report["phase7_15_negative_fixture_results_consumed"] is True
    assert report["phase7_15_package_boundary_scan_consumed"] is True
    assert report["all_required_negative_fixtures_blocked_fail_closed"] is True
    assert sorted(report["phase7_15_boundary_hardening"]["negative_fixture_revised_check"]["observed_fixture_names"]) == sorted(
        REQUIRED_PHASE7_15_NEGATIVE_FIXTURES
    )
    assert report["phase7_15_boundary_hardening"]["negative_fixture_revised_check"]["approval_intake_misuse_blocked"] is True
    assert report["phase7_15_boundary_hardening"]["negative_fixture_revised_check"]["stale_timestamp_blocked"] is True
    assert validation_report["phase7_15_negative_fixtures_validated_by_7_16"] is True
    assert validation_report["phase7_15_package_boundary_checked_by_7_16"] is True
    assert validation_report["approval_intake_misuse_blocked_by_7_16"] is True
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_16r_persist_writes_hardening_reports() -> None:
    _write_ready_phase7_15r_sources()
    report = persist_phase7_16_operator_decision_intake_validator_report(run_phase7_15_first=False)
    phase_dir = Path("storage/phase7_16_operator_decision_intake_validator")

    assert report["phase7_16_validator_hardened_revised"] is True
    assert (phase_dir / "phase7_16_operator_decision_intake_validator_hardening_report.json").exists()
    assert (phase_dir / "phase7_16_negative_fixture_results_REVISED.json").exists()

    hardening = json.loads((phase_dir / "phase7_16_operator_decision_intake_validator_hardening_report.json").read_text())
    revised = json.loads((phase_dir / "phase7_16_negative_fixture_results_REVISED.json").read_text())
    assert hardening["all_required_negative_fixtures_blocked_fail_closed"] is True
    assert hardening["approval_intake_validator_reused"] is False
    assert revised["all_required_negative_fixtures_blocked_fail_closed"] is True
    assert revised["approval_intake_misuse_blocked"] is True
    assert revised["stale_timestamp_blocked"] is True
