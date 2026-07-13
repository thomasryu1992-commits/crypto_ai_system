from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_2_signal_drift_candidate_readiness import persist_phase4_2_signal_drift_candidate_readiness_report
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import persist_phase4_3_research_signal_score_bucket_replay_report
from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import persist_phase4_4_candidate_profile_review_packet_report
from crypto_ai_system.validation.phase5_manual_approval_intake_validation import (
    STATUS_BLOCKED_REVIEW_ONLY,
    persist_phase5_manual_approval_intake_validation_report,
)
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def _prepare_phase4_4() -> None:
    # Ensure no developer-local manual submission leaks into the fail-closed test.
    manual_dir = Path("storage/manual_approval")
    if manual_dir.exists():
        for path in manual_dir.glob("approval_intake_submission.json"):
            path.unlink()
    latest_submission = Path("storage/latest/manual_approval_intake_submission.json")
    if latest_submission.exists():
        latest_submission.unlink()
    if Path("storage/latest/phase4_4_candidate_profile_review_packet_report.json").exists():
        return
    persist_valid_price_lineage_artifacts()
    persist_paper_data_quality_gate_report()
    persist_paper_strategy_validation_report()
    persist_phase4_1_paper_outcome_sample_accumulation_report()
    persist_phase4_2_signal_drift_candidate_readiness_report()
    persist_phase4_3_research_signal_score_bucket_replay_report()
    persist_phase4_4_candidate_profile_review_packet_report()


def test_phase5_blocks_missing_manual_approval_submission_without_unlock() -> None:
    _prepare_phase4_4()
    report = persist_phase5_manual_approval_intake_validation_report()

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["manual_approval_submission_present"] is False
    assert report["approval_intake_submitted"] is False
    assert report["approval_intake_validated"] is False
    assert report["approval_intake_status"] == "BLOCKED_FAIL_CLOSED"
    assert "MANUAL_APPROVAL_SUBMISSION_MISSING" in report["block_reasons"]
    assert report["approval_packet_created"] is False
    assert report["runtime_permission_source"] is False
    assert report["signed_testnet_unlock_authority"] is False
    assert report["signed_testnet_unlock_allowed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["candidate_profile_applied"] is False
    assert report["external_order_submission_performed"] is False
    assert report["auto_promotion_allowed"] is False


def test_phase5_persists_intake_validation_record_and_registry() -> None:
    _prepare_phase4_4()
    report = persist_phase5_manual_approval_intake_validation_report()
    latest = Path("storage/latest")
    validation_record = read_json(latest / "approval_intake_validation_record_review_only.json", default={})
    registry_record = read_json(latest / "phase5_manual_approval_intake_validation_registry_record.json", default={})

    assert validation_record["approval_intake_validation_record_id"] == report["approval_intake_validation_record_id"]
    assert validation_record["status"] == "BLOCKED_FAIL_CLOSED"
    assert validation_record["approval_intake_validated"] is False
    assert validation_record["approval_packet_created"] is False
    assert validation_record["signed_testnet_unlock_allowed"] is False
    assert validation_record["testnet_order_submission_allowed"] is False
    assert validation_record["runtime_settings_mutated"] is False
    assert validation_record["score_weights_mutated"] is False
    assert registry_record["status"] == report["status"]
    assert registry_record["blocked"] is True
    assert registry_record["approval_intake_validated"] is False
    assert registry_record["approval_packet_created"] is False
    assert registry_record["signed_testnet_unlock_allowed"] is False
