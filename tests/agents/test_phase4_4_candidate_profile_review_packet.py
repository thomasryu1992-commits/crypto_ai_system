from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_2_signal_drift_candidate_readiness import persist_phase4_2_signal_drift_candidate_readiness_report
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import persist_phase4_3_research_signal_score_bucket_replay_report
from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import (
    STATUS_RECORDED_REVIEW_ONLY,
    persist_phase4_4_candidate_profile_review_packet_report,
)
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def _prepare_phase4_3() -> None:
    existing = read_json(Path("storage/latest/phase4_3_research_signal_score_bucket_replay_report.json"), default={})
    if existing.get("status") == "PHASE4_3_RESEARCH_SIGNAL_SCORE_BUCKET_REPLAY_RECORDED_REVIEW_ONLY":
        return
    persist_valid_price_lineage_artifacts()
    persist_paper_data_quality_gate_report()
    persist_paper_strategy_validation_report()
    persist_phase4_1_paper_outcome_sample_accumulation_report()
    persist_phase4_2_signal_drift_candidate_readiness_report()
    persist_phase4_3_research_signal_score_bucket_replay_report()


def test_phase4_4_creates_review_packet_and_approval_draft_without_unlock() -> None:
    _prepare_phase4_3()
    report = persist_phase4_4_candidate_profile_review_packet_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["review_only"] is True
    assert report["paper_only"] is True
    assert report["candidate_profile_hash_valid"] is True
    assert report["candidate_review_packet_created"] is True
    assert report["approval_packet_draft_created"] is True
    assert report["approval_packet_created"] is False
    assert report["approval_intake_submitted"] is False
    assert report["approval_intake_status"] == "NOT_SUBMITTED_REVIEW_ONLY"
    assert report["manual_approval_readiness_status"] == "MANUAL_APPROVAL_REVIEW_PACKET_READY_REVIEW_ONLY"
    assert report["runtime_permission_source"] is False
    assert report["signed_testnet_unlock_authority"] is False
    assert report["signed_testnet_unlock_allowed"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["live_execution_unlock_authority"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["candidate_profile_applied"] is False
    assert report["settings_write_preview_applied"] is False
    assert report["external_order_submission_performed"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["block_reasons"] == []


def test_phase4_4_persists_review_packet_approval_draft_and_disabled_preview() -> None:
    _prepare_phase4_3()
    report = persist_phase4_4_candidate_profile_review_packet_report()
    latest = Path("storage/latest")
    review_packet = read_json(latest / "candidate_profile_review_packet.json", default={})
    approval_draft = read_json(latest / "approval_packet_draft_review_only.json", default={})
    registry_record = read_json(latest / "phase4_4_candidate_profile_review_packet_registry_record.json", default={})
    preview = latest / "disabled_candidate_settings_write_preview.diff"

    assert review_packet["status"] == "CANDIDATE_PROFILE_REVIEW_PACKET_DRAFT_REVIEW_ONLY"
    assert review_packet["profile_candidate_hash_valid"] is True
    assert review_packet["approval_packet_draft_created"] is True
    assert review_packet["approval_packet_created"] is False
    assert review_packet["signed_testnet_unlock_allowed"] is False
    assert approval_draft["status"] == "APPROVAL_PACKET_DRAFT_REVIEW_ONLY_NOT_APPROVED"
    assert approval_draft["validation_status"] == "NOT_SUBMITTED_REVIEW_ONLY"
    assert approval_draft["approval_packet_id"] is None
    assert approval_draft["approval_intake_id"] is None
    assert approval_draft["approval_packet_created"] is False
    assert approval_draft["signed_testnet_unlock_allowed"] is False
    assert preview.exists()
    assert "No settings.yaml mutation is performed." in preview.read_text(encoding="utf-8")
    assert registry_record["status"] == report["status"]
    assert registry_record["approval_packet_created"] is False
    assert registry_record["approval_intake_submitted"] is False
