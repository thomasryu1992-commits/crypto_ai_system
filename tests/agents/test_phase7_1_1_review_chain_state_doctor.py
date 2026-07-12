from __future__ import annotations

from pathlib import Path

from crypto_ai_system.validation.review_chain_state_doctor import (
    STATUS_RECORDED_REVIEW_ONLY,
    _diagnose_root_cause,
    persist_phase7_1_review_chain_state_doctor_report,
)

ACTUAL_APPROVAL = Path("storage/manual_approval/approval_intake_submission.json")
ACTUAL_UNLOCK_LATEST = Path("storage/latest/operator_unlock_request.json")


def _remove_actual_files() -> None:
    for path in (ACTUAL_APPROVAL, ACTUAL_UNLOCK_LATEST):
        if path.exists():
            path.unlink()


def test_phase7_1_1_review_chain_runner_records_ready_review_only_and_keeps_execution_disabled() -> None:
    _remove_actual_files()
    report = persist_phase7_1_review_chain_state_doctor_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase7_1_chain_ready_review_only"] is True
    assert report["doctor_summary"]["review_only_actual_fixtures_synced"] is True
    assert (report["root_cause_diagnosis"] or {}).get("first_blocked_step") is None
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["external_order_submission_performed"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert Path("storage/latest/review_chain_state_doctor_report.json").exists()
    assert Path("storage/latest/PHASE7_1_1_REVIEW_CHAIN_OPERATOR_HANDOFF.md").exists()
    assert ACTUAL_APPROVAL.exists()
    assert ACTUAL_UNLOCK_LATEST.exists()
    _remove_actual_files()


def test_phase7_1_1_root_cause_ignores_nonfatal_blocked_steps_when_critical_chain_is_ready() -> None:
    summaries = {
        "phase4_2_signal_drift_candidate_readiness": {
            "status": "PHASE4_2_SIGNAL_DRIFT_CANDIDATE_READINESS_BLOCKED_REVIEW_ONLY",
            "blocked": True,
            "block_reasons": ["OVERALL_SIGNAL_DRIFT_RATE_ABOVE_LIMIT"],
        },
        "phase4_3_research_signal_score_bucket_replay": {
            "status": "PHASE4_3_RESEARCH_SIGNAL_SCORE_BUCKET_REPLAY_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "block_reasons": [],
        },
        "phase4_4_candidate_profile_review_packet": {
            "status": "PHASE4_4_CANDIDATE_PROFILE_REVIEW_PACKET_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "block_reasons": [],
        },
        "phase5_manual_approval_intake_validation": {
            "status": "PHASE5_MANUAL_APPROVAL_INTAKE_VALIDATION_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "block_reasons": [],
        },
        "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox": {
            "status": "PHASE6_5_ACTUAL_APPROVAL_OPERATOR_UNLOCK_INTAKE_SANDBOX_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "block_reasons": [],
        },
        "phase6_6_actual_intake_validation_bridge": {
            "status": "PHASE6_6_ACTUAL_INTAKE_VALIDATION_BRIDGE_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "block_reasons": [],
        },
        "phase7_signed_testnet_validation_design_guard": {
            "status": "PHASE7_SIGNED_TESTNET_VALIDATION_DESIGN_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "block_reasons": [],
        },
        "phase7_1_signed_testnet_pre_submit_payload_guard": {
            "status": "PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_RECORDED_REVIEW_ONLY",
            "blocked": False,
            "block_reasons": [],
        },
    }
    diagnosis = _diagnose_root_cause(summaries)

    assert diagnosis["first_blocked_step"] is None
    assert "phase4_2_signal_drift_candidate_readiness" in diagnosis["diagnostic_blocked_steps"]
    assert "NON_FATAL_REVIEW_ONLY_BLOCKED_STEPS_PRESENT_BUT_PHASE7_1_CHAIN_READY" in diagnosis["diagnosis"]
