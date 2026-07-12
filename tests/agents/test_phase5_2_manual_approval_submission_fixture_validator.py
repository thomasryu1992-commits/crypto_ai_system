from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_2_signal_drift_candidate_readiness import persist_phase4_2_signal_drift_candidate_readiness_report
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import persist_phase4_3_research_signal_score_bucket_replay_report
from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import persist_phase4_4_candidate_profile_review_packet_report
from crypto_ai_system.validation.phase5_1_manual_approval_operator_handoff import persist_phase5_1_manual_approval_operator_handoff_report
from crypto_ai_system.validation.phase5_2_manual_approval_submission_fixture_validator import (
    STATUS_RECORDED_REVIEW_ONLY,
    persist_phase5_2_manual_approval_submission_fixture_validator_report,
)
from crypto_ai_system.validation.phase5_manual_approval_intake_validation import persist_phase5_manual_approval_intake_validation_report
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def _prepare_phase5_1_state() -> None:
    manual_dir = Path("storage/manual_approval")
    if manual_dir.exists():
        for path in manual_dir.glob("approval_intake_submission.json"):
            path.unlink()
    latest_submission = Path("storage/latest/manual_approval_intake_submission.json")
    if latest_submission.exists():
        latest_submission.unlink()
    if Path("storage/latest/phase5_1_manual_approval_operator_handoff_report.json").exists():
        return
    persist_valid_price_lineage_artifacts()
    persist_paper_data_quality_gate_report()
    persist_paper_strategy_validation_report()
    persist_phase4_1_paper_outcome_sample_accumulation_report()
    persist_phase4_2_signal_drift_candidate_readiness_report()
    persist_phase4_3_research_signal_score_bucket_replay_report()
    persist_phase4_4_candidate_profile_review_packet_report()
    persist_phase5_manual_approval_intake_validation_report()
    persist_phase5_1_manual_approval_operator_handoff_report()


def test_phase5_2_validates_fixtures_without_actual_submission_or_unlock() -> None:
    _prepare_phase5_1_state()
    report = persist_phase5_2_manual_approval_submission_fixture_validator_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["fixture_only"] is True
    assert report["valid_fixture_created"] is True
    assert report["valid_fixture_passed_review_only_validation"] is True
    assert report["invalid_fixture_count"] >= 3
    assert report["invalid_fixtures_blocked_fail_closed"] is True
    assert report["manual_approval_submission_created"] is False
    assert report["actual_manual_approval_submission_path_created"] is False
    assert report["approval_intake_submitted"] is False
    assert report["approval_intake_validated"] is False
    assert report["approval_packet_created"] is False
    assert report["runtime_permission_source"] is False
    assert report["signed_testnet_unlock_authority"] is False
    assert report["signed_testnet_unlock_allowed"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["external_order_submission_performed"] is False
    assert report["auto_promotion_allowed"] is False
    assert not Path("storage/manual_approval/approval_intake_submission.json").exists()


def test_phase5_2_persists_valid_and_invalid_fixtures_and_registry() -> None:
    _prepare_phase5_1_state()
    report = persist_phase5_2_manual_approval_submission_fixture_validator_report()
    fixture_dir = Path("storage/manual_approval/fixtures")
    valid_fixture = read_json(fixture_dir / "valid_approval_intake_submission_FIXTURE_REVIEW_ONLY.json", default={})
    invalid_missing_signature = read_json(
        fixture_dir / "invalid_missing_signature_approval_intake_submission_FIXTURE_REVIEW_ONLY.json",
        default={},
    )
    registry_record = read_json(Path("storage/latest/phase5_2_manual_approval_submission_fixture_validator_registry_record.json"), default={})

    assert valid_fixture["review_only_fixture"] is True
    assert valid_fixture["signed_testnet_unlock_allowed"] is False
    assert valid_fixture["testnet_order_submission_allowed"] is False
    assert valid_fixture["runtime_settings_mutated"] is False
    assert "ticket_or_signature" not in invalid_missing_signature
    assert "MANUAL_APPROVAL_FIELD_MISSING:ticket_or_signature" in report["invalid_fixture_results"]["missing_signature"]["block_reasons"]
    assert registry_record["status"] == report["status"]
    assert registry_record["valid_fixture_passed_review_only_validation"] is True
    assert registry_record["invalid_fixtures_blocked_fail_closed"] is True
    assert registry_record["manual_approval_submission_created"] is False
    assert registry_record["signed_testnet_unlock_allowed"] is False
