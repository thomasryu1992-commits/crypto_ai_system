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
from crypto_ai_system.validation.phase6_1_signed_testnet_operator_unlock_request_template import persist_phase6_1_signed_testnet_operator_unlock_request_template_report
from crypto_ai_system.validation.phase6_2_operator_unlock_request_fixture_validator import (
    STATUS_RECORDED_REVIEW_ONLY,
    persist_phase6_2_operator_unlock_request_fixture_validator_report,
)
from crypto_ai_system.validation.phase6_signed_testnet_preparation_preview import persist_phase6_signed_testnet_preparation_preview_report
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def _prepare_phase6_2_state() -> None:
    for path in (
        Path("storage/latest/operator_unlock_request.json"),
        Path("storage/signed_testnet/operator_unlock_request.json"),
        Path("storage/manual_approval/approval_intake_submission.json"),
    ):
        if path.exists():
            path.unlink()
    if Path("storage/latest/operator_unlock_request_template_review_only.json").exists() and Path("storage/latest/phase6_1_signed_testnet_operator_unlock_request_template_report.json").exists():
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
    persist_phase6_signed_testnet_preparation_preview_report()
    persist_phase6_1_signed_testnet_operator_unlock_request_template_report()


def test_phase6_2_validates_operator_unlock_request_fixtures_only() -> None:
    _prepare_phase6_2_state()
    report = persist_phase6_2_operator_unlock_request_fixture_validator_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["review_only"] is True
    assert report["fixture_only"] is True
    assert report["valid_operator_unlock_fixture_created"] is True
    assert report["valid_operator_unlock_fixture_passed_review_only_validation"] is True
    assert report["invalid_operator_unlock_fixture_count"] >= 4
    assert report["invalid_operator_unlock_fixtures_blocked_fail_closed"] is True
    assert report["operator_unlock_request_created"] is False
    assert report["actual_operator_unlock_request_path_created"] is False
    assert report["operator_unlock_request_present"] is False
    assert report["operator_unlock_request_validated"] is False
    assert report["approval_intake_validated"] is False
    assert report["signed_testnet_preparation_ready"] is False
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["place_order_enabled"] is False
    assert report["cancel_order_enabled"] is False
    assert report["signed_order_executor_enabled"] is False
    assert report["external_order_submission_performed"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert not Path("storage/latest/operator_unlock_request.json").exists()
    assert not Path("storage/signed_testnet/operator_unlock_request.json").exists()


def test_phase6_2_persists_unlock_fixtures_and_registry_record() -> None:
    _prepare_phase6_2_state()
    report = persist_phase6_2_operator_unlock_request_fixture_validator_report()
    latest = Path("storage/latest")
    persisted = read_json(latest / "phase6_2_operator_unlock_request_fixture_validator_report.json", default={})
    registry_record = read_json(latest / "phase6_2_operator_unlock_request_fixture_validator_registry_record.json", default={})
    valid_fixture = read_json(Path("storage/signed_testnet/fixtures/valid_operator_unlock_request_FIXTURE_REVIEW_ONLY.json"), default={})
    invalid_unsafe = read_json(Path("storage/signed_testnet/fixtures/invalid_unsafe_unlock_flag_operator_unlock_request_FIXTURE_REVIEW_ONLY.json"), default={})

    assert persisted["phase6_2_operator_unlock_request_fixture_validator_id"] == report["phase6_2_operator_unlock_request_fixture_validator_id"]
    assert registry_record["status"] == report["status"]
    assert registry_record["operator_unlock_request_created"] is False
    assert registry_record["operator_unlock_request_validated"] is False
    assert registry_record["ready_for_signed_testnet_execution"] is False
    assert registry_record["testnet_order_submission_allowed"] is False
    assert registry_record["place_order_enabled"] is False
    assert registry_record["signed_order_executor_enabled"] is False
    assert valid_fixture["operator_ticket_or_signature"] == "fixture_operator_ticket_or_signature_review_only"
    assert valid_fixture["kill_switch_rechecked"] is True
    assert valid_fixture["testnet_order_submission_allowed"] is False
    assert invalid_unsafe["testnet_order_submission_allowed"] is True
    assert report["invalid_operator_unlock_fixture_results"]["unsafe_unlock_flag"]["blocked"] is True
    assert any("UNSAFE_OPERATOR_UNLOCK_FIELD_TRUE" in reason for reason in report["invalid_operator_unlock_fixture_results"]["unsafe_unlock_flag"]["block_reasons"])
