from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_2_signal_drift_candidate_readiness import persist_phase4_2_signal_drift_candidate_readiness_report
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import persist_phase4_3_research_signal_score_bucket_replay_report
from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import persist_phase4_4_candidate_profile_review_packet_report
from crypto_ai_system.validation.phase5_1_manual_approval_operator_handoff import persist_phase5_1_manual_approval_operator_handoff_report
from crypto_ai_system.validation.phase5_2_manual_approval_submission_fixture_validator import persist_phase5_2_manual_approval_submission_fixture_validator_report
from crypto_ai_system.validation.phase5_manual_approval_intake_validation import persist_phase5_manual_approval_intake_validation_report
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.phase6_signed_testnet_preparation_preview import (
    STATUS_RECORDED_REVIEW_ONLY,
    persist_phase6_signed_testnet_preparation_preview_report,
)
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def _prepare_phase5_2_state() -> None:
    submission = Path("storage/manual_approval/approval_intake_submission.json")
    if submission.exists():
        submission.unlink()
    if Path("storage/latest/phase5_2_manual_approval_submission_fixture_validator_report.json").exists():
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
    persist_phase5_2_manual_approval_submission_fixture_validator_report()


def test_phase6_records_signed_testnet_preparation_preview_without_unlock() -> None:
    _prepare_phase5_2_state()
    report = persist_phase6_signed_testnet_preparation_preview_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["review_only"] is True
    assert report["signed_testnet_preparation_preview_only"] is True
    assert report["read_only_venue_probe_recorded"] is True
    assert report["metadata_only_key_reference_recorded"] is True
    assert report["pre_submit_validation_recorded"] is True
    assert report["enablement_packet_recorded"] is True
    assert report["disabled_executor_evidence_recorded"] is True
    assert report["signed_testnet_preparation_ready"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["external_order_submission_performed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["api_key_value_access_allowed"] is False
    assert report["api_secret_value_access_allowed"] is False
    assert report["secret_file_access_allowed"] is False
    assert report["secret_file_creation_allowed"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert not Path("storage/manual_approval/approval_intake_submission.json").exists()


def test_phase6_persists_report_and_registry_record() -> None:
    _prepare_phase5_2_state()
    report = persist_phase6_signed_testnet_preparation_preview_report()
    latest = Path("storage/latest")
    persisted_report = read_json(latest / "phase6_signed_testnet_preparation_preview_report.json", default={})
    registry_record = read_json(latest / "phase6_signed_testnet_preparation_preview_registry_record.json", default={})
    executor = read_json(latest / "signed_testnet_order_execution_record.json", default={})

    assert persisted_report["phase6_signed_testnet_preparation_preview_id"] == report["phase6_signed_testnet_preparation_preview_id"]
    assert registry_record["status"] == report["status"]
    assert registry_record["ready_for_signed_testnet_execution"] is False
    assert registry_record["testnet_order_submission_allowed"] is False
    assert registry_record["external_order_submission_performed"] is False
    assert executor.get("external_order_submission_performed") is False
    assert executor.get("testnet_order_submission_allowed") is False
    assert executor.get("signed_order_executor_enabled") is False
