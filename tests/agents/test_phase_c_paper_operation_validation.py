from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import persist_phase4_3_research_signal_score_bucket_replay_report
from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import persist_phase4_4_candidate_profile_review_packet_report
from crypto_ai_system.validation.phase_c_paper_operation_validation import (
    STATUS_PHASE_C_BLOCKED_REVIEW_ONLY,
    STATUS_PHASE_C_RECORDED_REVIEW_ONLY,
    persist_phase_c_paper_operation_validation_report,
)
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts


def _write_min_project(root: Path) -> None:
    (root / "storage" / "latest").mkdir(parents=True, exist_ok=True)
    (root / "storage" / "registries").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  name: tmp-crypto-ai-system\n  version: test\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text("[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n", encoding="utf-8")


def test_phase_c_records_closed_paper_loop_and_review_candidate_gate() -> None:
    persist_valid_price_lineage_artifacts()
    persist_paper_data_quality_gate_report()
    persist_paper_strategy_validation_report()
    persist_phase4_1_paper_outcome_sample_accumulation_report(sample_size=50, horizon_bars=12, min_closed_sample_size=30)
    persist_phase4_3_research_signal_score_bucket_replay_report()
    persist_phase4_4_candidate_profile_review_packet_report()

    report = persist_phase_c_paper_operation_validation_report(min_closed_sample_size=30, run_upstream=False)

    assert report["status"] == STATUS_PHASE_C_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["paper_operation_loop_validated"] is True
    assert report["research_signal_v2_generated"] is True
    assert report["signal_qa_passed_for_paper"] is True
    assert report["pre_order_risk_gate_paper_passed"] is True
    assert report["paper_order_intent_created_after_risk_gate"] is True
    assert report["paper_execution_simulated_fill_created"] is True
    assert report["paper_reconciliation_clean"] is True
    assert report["outcome_analytics_recorded"] is True
    assert report["closed_paper_outcome_sample_count"] >= 30
    assert report["performance_report_recorded"] is True
    assert report["performance_metrics"]["reconciliation_mismatch_count"] == 0
    assert report["performance_metrics"]["score_bucket_alignment_drift_rate"] == 0.0
    assert report["drift_controlled_candidate_profile_draft_created"] is True
    assert report["candidate_profile_review_packet_created"] is True
    assert report["approval_packet_draft_created_review_only"] is True
    assert report["approval_packet_created"] is False
    assert report["approval_intake_submitted"] is False
    assert report["candidate_profile_runtime_applied"] is False
    assert report["candidate_profile_ready_for_manual_review"] is True
    assert report["paper_stage_chain_complete"] is True
    assert report["full_canonical_id_chain_complete"] is False
    assert set(report["missing_full_canonical_id_chain_fields"]) == {"approval_packet_id", "approval_intake_id"}
    assert report["runtime_permission_source"] is False
    assert report["signed_testnet_unlock_authority"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["live_execution_unlock_authority"] is False
    assert report["live_trading_allowed_by_this_module"] is False
    assert report["external_order_submission_performed"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["block_reasons"] == []

    latest = Path("storage/latest")
    assert (latest / "phase_c_paper_operation_validation_report.json").exists()
    assert (latest / "phase_c_paper_operation_validation_registry_record.json").exists()
    registry_record = read_json(latest / "phase_c_paper_operation_validation_registry_record.json", default={})
    assert registry_record["status"] == report["status"]
    assert registry_record["paper_operation_loop_validated"] is True
    assert registry_record["testnet_order_submission_allowed"] is False


def test_phase_c_blocks_when_reconciliation_is_missing(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    latest = tmp_path / "storage" / "latest"
    atomic_write_json(latest / "paper_data_quality_gate_report.json", {"status": "PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY"})
    atomic_write_json(latest / "paper_strategy_validation_report.json", {"status": "PAPER_STRATEGY_VALIDATION_RECORDED_REVIEW_ONLY"})
    atomic_write_json(latest / "research_signal.json", {"research_signal_id": "rs1", "signal_version": "research_signal_v2_test", "data_snapshot_id": "ds1", "feature_snapshot_id": "fs1", "profile_id": "p1"})
    atomic_write_json(latest / "signal_qa_report.json", {"signal_qa_result": "PASS", "allowed_for_paper": True, "allowed_for_live": False, "allowed_for_signed_testnet": False})
    atomic_write_json(latest / "legacy_signal_fallback_blocker_report.json", {"allowed_for_live": False})
    atomic_write_json(latest / "paper_trade_decision.json", {"decision_id": "d1", "research_signal_id": "rs1", "profile_id": "p1", "signal_permission_authoritative": True, "external_order_submission_performed": False})
    atomic_write_json(latest / "pre_order_risk_gate_report.json", {"status": "PASS_PAPER", "approved": True, "risk_gate_id": "rg1"})
    atomic_write_json(latest / "paper_order_intent.json", {"status": "ORDER_INTENT_CREATED", "paper_only": True, "risk_gate_id": "rg1", "order_intent_id": "oi1"})
    atomic_write_json(latest / "paper_execution_record.json", {"execution_id": "ex1", "order_intent_id": "oi1", "paper_order_submitted": True, "external_order_submission_performed": False, "adapter_called": False})
    atomic_write_json(latest / "outcome_analytics_record.json", {"status": "OUTCOME_RECORDED", "outcome_closed": True, "outcome_id": "o1", "feedback_cycle_id": "fb1"})
    atomic_write_json(latest / "phase4_1_paper_outcome_sample_accumulation_report.json", {"status": "PHASE4_1_PAPER_OUTCOME_SAMPLE_ACCUMULATION_RECORDED_REVIEW_ONLY", "closed_count": 30})
    atomic_write_json(latest / "paper_outcome_sample_accumulation_outcomes.json", {"outcomes": []})
    atomic_write_json(latest / "performance_report.json", {"status": "PERFORMANCE_REPORT_RECORDED", "expectancy": 0.1, "max_drawdown": 0.0, "average_slippage": 0.0, "average_latency_ms": 1.0, "rejection_rate": 0.0, "stale_data_rate": 0.0, "api_error_rate": 0.0, "reconciliation_mismatch_count": 0})
    atomic_write_json(latest / "phase4_3_research_signal_score_bucket_replay_report.json", {"status": "PHASE4_3_RESEARCH_SIGNAL_SCORE_BUCKET_REPLAY_RECORDED_REVIEW_ONLY", "candidate_profile_draft_created": True, "overall_summary": {"alignment_drift_rate": 0.0, "missing_signal_score_count": 0}})
    atomic_write_json(latest / "drift_reduced_candidate_profile_draft.json", {"status": "review_only_draft", "candidate_profile_applied": False})
    atomic_write_json(latest / "phase4_4_candidate_profile_review_packet_report.json", {"status": "PHASE4_4_CANDIDATE_PROFILE_REVIEW_PACKET_RECORDED_REVIEW_ONLY", "candidate_review_packet_created": True, "approval_packet_draft_created": True, "approval_packet_created": False, "approval_intake_submitted": False})

    report = persist_phase_c_paper_operation_validation_report(cfg=cfg, min_closed_sample_size=30)

    assert report["status"] == STATUS_PHASE_C_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert "MISSING_REQUIRED_PHASE_C_ARTIFACT:paper_reconciliation_record.json" in report["block_reasons"]
    assert "PAPER_RECONCILIATION_NOT_CLEAN" in report["block_reasons"]
    assert "PAPER_STAGE_CANONICAL_CHAIN_INCOMPLETE" in report["block_reasons"]
    assert report["paper_operation_loop_validated"] is False
    assert report["testnet_order_submission_allowed"] is False
    assert report["live_trading_allowed_by_this_module"] is False
