from __future__ import annotations

import json
from pathlib import Path

from crypto_ai_system.validation.phase7_15_operator_decision_intake_template import (
    persist_phase7_15_operator_decision_intake_template_report,
)
from crypto_ai_system.validation.phase7_16_operator_decision_intake_validator import (
    persist_phase7_16_operator_decision_intake_validator_report,
)
from crypto_ai_system.validation.phase7_17_final_pre_executor_review_packet import (
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_17_final_pre_executor_review_packet_report,
    persist_phase7_17_final_pre_executor_review_packet_report,
)
from tests.agents.test_phase7_15_operator_decision_intake_template import _write_ready_phase7_14_sources


def _write_ready_phase7_16r_sources() -> None:
    _write_ready_phase7_14_sources()
    persist_phase7_15_operator_decision_intake_template_report(run_phase7_14_first=False)
    persist_phase7_16_operator_decision_intake_validator_report(run_phase7_15_first=False)


def test_phase7_17r_reissues_final_packet_after_boundary_hardening() -> None:
    _write_ready_phase7_16r_sources()

    report, packet, guard = build_phase7_17_final_pre_executor_review_packet_report(run_phase7_16_first=False)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["phase7_17_final_packet_reissued"] is True
    assert report["phase7_15_boundary_reconciled"] is True
    assert report["phase7_16_negative_fixtures_passed"] is True
    assert report["phase8_preparation_review_may_continue"] is True
    assert packet["phase7_17_final_packet_reissued"] is True
    assert packet["phase7_15_boundary_reconciled"] is True
    assert packet["phase7_16_negative_fixtures_passed"] is True
    assert guard["guard_passed"] is True
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["actual_order_submission_performed"] is False


def test_phase7_17r_persist_writes_reissued_artifacts_and_disabled_flags() -> None:
    _write_ready_phase7_16r_sources()
    report = persist_phase7_17_final_pre_executor_review_packet_report(run_phase7_16_first=False)
    phase_dir = Path("storage/phase7_17_final_pre_executor_review_packet")

    assert report["phase7_17_final_packet_reissued"] is True
    for rel in [
        "final_pre_executor_review_packet_REISSUED.json",
        "final_pre_executor_review_summary_REISSUED.md",
        "phase_7_completion_guard_report_REVISED.json",
        "still_disabled_execution_flags_REVISED.json",
    ]:
        assert (phase_dir / rel).exists(), rel

    disabled = json.loads((phase_dir / "still_disabled_execution_flags_REVISED.json").read_text())
    assert disabled["ready_for_signed_testnet_execution"] is False
    assert disabled["testnet_order_submission_allowed"] is False
    assert disabled["place_order_enabled"] is False
    assert disabled["cancel_order_enabled"] is False
    assert disabled["signed_order_executor_enabled"] is False
    assert disabled["runtime_settings_mutated"] is False
    assert disabled["score_weights_mutated"] is False
