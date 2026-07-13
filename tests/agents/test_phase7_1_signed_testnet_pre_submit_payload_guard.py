from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.phase4_outcome_candidate_feedback import persist_phase4_outcome_candidate_feedback_report
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_2_signal_drift_candidate_readiness import persist_phase4_2_signal_drift_candidate_readiness_report
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import persist_phase4_3_research_signal_score_bucket_replay_report
from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import persist_phase4_4_candidate_profile_review_packet_report
from crypto_ai_system.validation.phase5_1_manual_approval_operator_handoff import persist_phase5_1_manual_approval_operator_handoff_report
from crypto_ai_system.validation.phase5_2_manual_approval_submission_fixture_validator import persist_phase5_2_manual_approval_submission_fixture_validator_report
from crypto_ai_system.validation.phase5_manual_approval_intake_validation import persist_phase5_manual_approval_intake_validation_report
from crypto_ai_system.validation.phase6_1_signed_testnet_operator_unlock_request_template import persist_phase6_1_signed_testnet_operator_unlock_request_template_report
from crypto_ai_system.validation.phase6_2_operator_unlock_request_fixture_validator import persist_phase6_2_operator_unlock_request_fixture_validator_report
from crypto_ai_system.validation.phase6_3_signed_testnet_readiness_gate_review import persist_phase6_3_signed_testnet_readiness_gate_review_report
from crypto_ai_system.validation.phase6_4_signed_testnet_readiness_review_packet import persist_phase6_4_signed_testnet_readiness_review_packet_report
from crypto_ai_system.validation.phase6_5_actual_manual_approval_operator_unlock_intake_sandbox import persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report
from crypto_ai_system.validation.phase6_6_actual_intake_validation_bridge import persist_phase6_6_actual_intake_validation_bridge_report
from crypto_ai_system.validation.phase6_signed_testnet_preparation_preview import persist_phase6_signed_testnet_preparation_preview_report
from crypto_ai_system.validation.phase7_signed_testnet_validation_design_guard import persist_phase7_signed_testnet_validation_design_guard_report
from crypto_ai_system.validation.phase7_1_signed_testnet_pre_submit_payload_guard import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    build_phase7_1_signed_testnet_pre_submit_payload_guard_report,
    persist_phase7_1_signed_testnet_pre_submit_payload_guard_report,
)

ACTUAL_APPROVAL = Path("storage/manual_approval/approval_intake_submission.json")
ACTUAL_UNLOCK_LATEST = Path("storage/latest/operator_unlock_request.json")
ACTUAL_UNLOCK_ARCHIVE = Path("storage/signed_testnet/operator_unlock_request.json")


def _remove_actual_files() -> None:
    for path in (ACTUAL_APPROVAL, ACTUAL_UNLOCK_LATEST, ACTUAL_UNLOCK_ARCHIVE):
        if path.exists():
            path.unlink()


def _prepare_base_sources() -> None:
    _remove_actual_files()
    persist_valid_price_lineage_artifacts()
    persist_paper_data_quality_gate_report()
    persist_paper_strategy_validation_report()
    persist_phase4_outcome_candidate_feedback_report()
    persist_phase4_1_paper_outcome_sample_accumulation_report()
    persist_phase4_2_signal_drift_candidate_readiness_report()
    persist_phase4_3_research_signal_score_bucket_replay_report()
    persist_phase4_4_candidate_profile_review_packet_report()
    persist_phase5_1_manual_approval_operator_handoff_report()
    persist_phase5_manual_approval_intake_validation_report()
    persist_phase5_2_manual_approval_submission_fixture_validator_report()
    persist_phase6_signed_testnet_preparation_preview_report()
    persist_phase6_1_signed_testnet_operator_unlock_request_template_report()
    persist_phase6_2_operator_unlock_request_fixture_validator_report()
    persist_phase6_3_signed_testnet_readiness_gate_review_report()
    persist_phase6_4_signed_testnet_readiness_review_packet_report()
    persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report()
    persist_phase6_6_actual_intake_validation_bridge_report()
    persist_phase7_signed_testnet_validation_design_guard_report()


def _create_actual_files() -> None:
    approval_template = read_json(Path("storage/manual_approval/approval_intake_submission_TEMPLATE_REVIEW_ONLY.json"), default={})
    unlock_template = read_json(Path("storage/signed_testnet/operator_unlock_request_TEMPLATE_REVIEW_ONLY.json"), default={})
    approval = dict(approval_template)
    unlock = dict(unlock_template)
    approval.update(
        {
            "approval_packet_id": "approval_packet_manual_phase7_1_test_001",
            "approval_intake_id": "approval_intake_manual_phase7_1_test_001",
            "approver_info": "Thomas",
            "ticket_or_signature": "MANUAL_APPROVAL_PHASE7_1_TEST_SIGNATURE",
            "canonical_utc_timestamp": "2026-07-02T05:30:00Z",
        }
    )
    unlock.update(
        {
            "operator_id": "Thomas",
            "operator_ticket_or_signature": "OPERATOR_UNLOCK_PHASE7_1_TEST_SIGNATURE",
            "canonical_utc_timestamp": "2026-07-02T05:31:00Z",
            "approval_intake_id": "approval_intake_manual_phase7_1_test_001",
            "approval_packet_id": "approval_packet_manual_phase7_1_test_001",
            "max_testnet_notional_usd": 25.0,
            "max_testnet_order_count": 1,
            "max_testnet_daily_loss_usd": 10.0,
            "kill_switch_rechecked": True,
            "hard_caps_rechecked": True,
            "pre_order_risk_gate_rechecked": True,
        }
    )
    ACTUAL_APPROVAL.parent.mkdir(parents=True, exist_ok=True)
    ACTUAL_UNLOCK_LATEST.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(ACTUAL_APPROVAL, approval)
    atomic_write_json(ACTUAL_UNLOCK_LATEST, unlock)


def _prepare_ready_phase7_sources() -> None:
    _prepare_base_sources()
    _create_actual_files()
    persist_phase5_manual_approval_intake_validation_report()
    persist_phase6_3_signed_testnet_readiness_gate_review_report()
    persist_phase6_4_signed_testnet_readiness_review_packet_report()
    persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report()
    persist_phase6_6_actual_intake_validation_bridge_report()
    persist_phase7_signed_testnet_validation_design_guard_report()


def test_phase7_1_payload_guard_blocks_when_phase7_design_not_ready() -> None:
    _prepare_base_sources()
    report = build_phase7_1_signed_testnet_pre_submit_payload_guard_report()

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "PHASE7_DESIGN_GUARD_NOT_READY" in report["block_reasons"]
    assert report["phase7_1_payload_guard_ready_review_only"] is False
    assert report["phase7_execution_authority"] is False
    assert report["phase7_order_submission_authority"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["signed_order_executor_enabled"] is False


def test_phase7_1_payload_guard_records_fixtures_and_keeps_executor_disabled() -> None:
    _prepare_ready_phase7_sources()
    report = persist_phase7_1_signed_testnet_pre_submit_payload_guard_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["phase7_1_payload_guard_ready_review_only"] is True
    assert report["would_submit_payload_fixture_created"] is True
    assert report["valid_would_submit_payload_passed_review_only_validation"] is True
    assert report["invalid_payload_fixtures_blocked_fail_closed"] is True
    assert report["disabled_executor_guard_passed"] is True
    assert report["phase7_execution_authority"] is False
    assert report["phase7_order_submission_authority"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["external_order_submission_performed"] is False
    assert Path("storage/latest/phase7_1_signed_testnet_pre_submit_payload_guard_report.json").exists()
    assert Path("storage/latest/signed_testnet_would_submit_payload_FIXTURE_REVIEW_ONLY.json").exists()
    assert Path("storage/latest/signed_testnet_disabled_executor_fixture_guard_report.json").exists()
    assert Path("storage/signed_testnet/fixtures/invalid_missing_idempotency_key_would_submit_payload_FIXTURE_REVIEW_ONLY.json").exists()

    _remove_actual_files()
