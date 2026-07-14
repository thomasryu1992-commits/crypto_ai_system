from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_2_signal_drift_candidate_readiness import persist_phase4_2_signal_drift_candidate_readiness_report
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import persist_phase4_3_research_signal_score_bucket_replay_report
from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import persist_phase4_4_candidate_profile_review_packet_report
from crypto_ai_system.validation.phase5_1_manual_approval_operator_handoff import (
    STATUS_RECORDED_REVIEW_ONLY,
    persist_phase5_1_manual_approval_operator_handoff_report,
)
from crypto_ai_system.validation.phase5_manual_approval_intake_validation import persist_phase5_manual_approval_intake_validation_report
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def _prepare_phase5_blocked_state() -> None:
    manual_dir = Path("storage/manual_approval")
    if manual_dir.exists():
        for path in manual_dir.glob("approval_intake_submission.json"):
            path.unlink()
    latest_submission = Path("storage/latest/manual_approval_intake_submission.json")
    if latest_submission.exists():
        latest_submission.unlink()
    persist_valid_price_lineage_artifacts()
    persist_paper_data_quality_gate_report()
    persist_paper_strategy_validation_report()
    persist_phase4_1_paper_outcome_sample_accumulation_report()
    persist_phase4_2_signal_drift_candidate_readiness_report()
    persist_phase4_3_research_signal_score_bucket_replay_report()
    persist_phase4_4_candidate_profile_review_packet_report()
    persist_phase5_manual_approval_intake_validation_report()


def test_phase5_1_creates_template_without_submission_or_unlock() -> None:
    _prepare_phase5_blocked_state()
    report = persist_phase5_1_manual_approval_operator_handoff_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["fail_closed"] is False
    assert report["manual_approval_submission_template_created"] is True
    assert report["manual_approval_submission_created"] is False
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

    template = read_json(Path("storage/latest/manual_approval_submission_template_review_only.json"), default={})
    assert template["do_not_write_automatically"] is True
    assert template["write_target_when_manually_approved"] == "storage/manual_approval/approval_intake_submission.json"
    assert template["approval_packet_id"] == "MANUAL_REQUIRED_APPROVAL_PACKET_ID"
    assert template["approver_info"] == "MANUAL_REQUIRED_APPROVER_NAME_OR_HANDLE"
    assert template["ticket_or_signature"] == "MANUAL_REQUIRED_TICKET_OR_SIGNATURE"
    assert template["signed_testnet_unlock_allowed"] is False
    assert template["testnet_order_submission_allowed"] is False
    assert not Path("storage/manual_approval/approval_intake_submission.json").exists()


def test_phase5_1_persists_operator_handoff_and_registry() -> None:
    _prepare_phase5_blocked_state()
    report = persist_phase5_1_manual_approval_operator_handoff_report()
    latest = Path("storage/latest")
    registry_record = read_json(latest / "phase5_1_manual_approval_operator_handoff_registry_record.json", default={})
    handoff_md = latest / "MANUAL_APPROVAL_OPERATOR_HANDOFF_REVIEW_ONLY.md"

    assert registry_record["status"] == report["status"]
    assert registry_record["manual_approval_submission_template_created"] is True
    assert registry_record["manual_approval_submission_created"] is False
    assert registry_record["approval_intake_submitted"] is False
    assert registry_record["signed_testnet_unlock_allowed"] is False
    assert registry_record["runtime_settings_mutated"] is False
    assert handoff_md.exists()
    text = handoff_md.read_text(encoding="utf-8")
    assert "does not unlock signed testnet or live execution" in text
    assert "storage/manual_approval/approval_intake_submission.json" in text
