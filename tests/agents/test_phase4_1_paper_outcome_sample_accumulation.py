from __future__ import annotations

from pathlib import Path

from core.json_io import read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import (
    STATUS_RECORDED_REVIEW_ONLY,
    persist_phase4_1_paper_outcome_sample_accumulation_report,
)


def test_phase4_1_accumulates_closed_paper_outcomes_review_only() -> None:
    if not Path("storage/latest/paper_strategy_validation_report.json").exists():
        persist_valid_price_lineage_artifacts()
        gate = persist_paper_data_quality_gate_report()
        assert gate["status"] == "PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY"
        persist_paper_strategy_validation_report()

    report = persist_phase4_1_paper_outcome_sample_accumulation_report(sample_size=50, horizon_bars=12, min_closed_sample_size=10)

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["paper_sample_accumulated"] is True
    assert report["outcome_count"] >= 10
    assert report["closed_count"] >= 10
    assert report["performance_report_status"] in {"PERFORMANCE_REPORT_RECORDED", "PERFORMANCE_REPORT_REVIEW_ONLY_INSUFFICIENT_SAMPLE"}
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["candidate_profile_applied"] is False
    assert report["settings_write_preview_applied"] is False
    assert report["approval_packet_created"] is False
    assert report["auto_promotion_allowed"] is False
    assert report["external_order_submission_performed"] is False

    latest = load_config().root / "storage" / "latest"
    outcomes = read_json(latest / "paper_outcome_sample_accumulation_outcomes.json", default={})
    assert len(outcomes["outcomes"]) == report["outcome_count"]
    assert all(item["outcome_closed"] is True for item in outcomes["outcomes"])
    assert all(item["paper_only"] is True for item in outcomes["outcomes"])
    assert all(item["external_order_submission_performed"] is False for item in outcomes["outcomes"])


def test_phase4_1_writes_review_only_registry_record() -> None:
    report = persist_phase4_1_paper_outcome_sample_accumulation_report(sample_size=50, horizon_bars=12, min_closed_sample_size=10)
    latest = load_config().root / "storage" / "latest"
    record = read_json(latest / "phase4_1_paper_outcome_sample_accumulation_registry_record.json", default={})
    assert record["phase4_1_paper_outcome_sample_accumulation_id"] == report["phase4_1_paper_outcome_sample_accumulation_id"]
    assert record["runtime_settings_mutated"] is False
    assert record["score_weights_mutated"] is False
    assert record["live_trading_allowed_by_this_module"] is False
