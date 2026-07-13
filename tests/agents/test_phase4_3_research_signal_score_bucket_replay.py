from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_2_signal_drift_candidate_readiness import persist_phase4_2_signal_drift_candidate_readiness_report
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import (
    STATUS_RECORDED_REVIEW_ONLY,
    persist_phase4_3_research_signal_score_bucket_replay_report,
)
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def test_phase4_3_research_signal_score_bucket_replay_creates_review_only_candidate_draft() -> None:
    existing = read_json(Path("storage/latest/phase4_3_research_signal_score_bucket_replay_report.json"), default={})
    phase4_1 = read_json(Path("storage/latest/phase4_1_paper_outcome_sample_accumulation_report.json"), default={})
    if existing.get("status") != STATUS_RECORDED_REVIEW_ONLY or int(phase4_1.get("closed_count", 0) or 0) < 30:
        persist_valid_price_lineage_artifacts()
        persist_paper_data_quality_gate_report()
        persist_paper_strategy_validation_report()
        persist_phase4_1_paper_outcome_sample_accumulation_report(sample_size=50, horizon_bars=12, min_closed_sample_size=10)
        persist_phase4_2_signal_drift_candidate_readiness_report()

    report = persist_phase4_3_research_signal_score_bucket_replay_report()

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["review_only"] is True
    assert report["paper_only"] is True
    assert report["score_bucket_metadata_attached"] is True
    assert report["source_outcome_count"] >= 30
    assert report["drift_reduced_subset_count"] >= 1
    assert report["candidate_profile_draft_created"] is True
    assert report["candidate_profile_applied"] is False
    assert report["approval_packet_created"] is False
    assert report["runtime_permission_source"] is False
    assert report["signed_testnet_unlock_authority"] is False
    assert report["live_execution_unlock_authority"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["external_order_submission_performed"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["block_reasons"] == []
    assert report["overall_summary"]["missing_signal_score_count"] == 0
    assert report["overall_summary"]["alignment_drift_rate"] == 0.0


def test_phase4_3_persists_enriched_outcomes_and_candidate_draft() -> None:
    report = persist_phase4_3_research_signal_score_bucket_replay_report()
    latest = Path("storage/latest")
    enriched = read_json(latest / "paper_outcome_score_bucket_enriched_outcomes.json", default={})
    draft = read_json(latest / "drift_reduced_candidate_profile_draft.json", default={})
    registry_record = read_json(latest / "phase4_3_research_signal_score_bucket_replay_registry_record.json", default={})

    rows = enriched.get("outcomes") or []
    assert rows
    assert all(row.get("research_signal_score_metadata_attached") is True for row in rows)
    assert all(row.get("signal_score_bucket") != "missing_signal_score" for row in rows)
    assert draft["status"] == "review_only_draft"
    assert draft["candidate_profile_applied"] is False
    assert draft["approval_packet_created"] is False
    assert draft["live_candidate_eligible"] is False
    assert registry_record["status"] == report["status"]
    assert registry_record["candidate_profile_draft_created"] is True
