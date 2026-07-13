from __future__ import annotations

from pathlib import Path

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import load_registry_records
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_2_signal_drift_candidate_readiness import (
    STATUS_BLOCKED_REVIEW_ONLY,
    STATUS_RECORDED_REVIEW_ONLY,
    persist_phase4_2_signal_drift_candidate_readiness_report,
)


def _write_min_project(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "settings.yaml").write_text(
        "project:\n  version: step286_researchsignal_feature_lineage_fix\n"
        "storage:\n  registry_dir: storage/registries\n"
        "safety:\n  live_trading_enabled: false\n  testnet_signed_order_enabled: false\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname='tmp-crypto-ai-system'\nversion='0.286.0'\n",
        encoding="utf-8",
    )


def _outcome(index: int, *, result_r: float, drift: float, signal_score: float = -0.8) -> dict:
    return {
        "outcome_id": f"outcome_{index}",
        "outcome_closed": True,
        "status": "OUTCOME_RECORDED",
        "profile_id": "paper_validation_profile_v1",
        "research_signal_id": f"research_signal_{index}",
        "decision_id": f"decision_{index}",
        "risk_gate_id": f"risk_gate_{index}",
        "order_intent_id": f"order_intent_{index}",
        "execution_id": f"execution_{index}",
        "reconciliation_id": f"reconciliation_{index}",
        "feedback_cycle_id": f"feedback_cycle_{index}",
        "regime": "TREND_DOWN",
        "direction": "SHORT",
        "timeframe": "1h",
        "close_reason": "take_profit_hit" if result_r > 0 else "stop_loss_hit",
        "result_R": result_r,
        "pnl": result_r,
        "signal_to_outcome_drift": drift,
        "final_signal_score": signal_score,
        "slippage": 0.0,
        "latency_ms": 25.0,
        "rejection_rate": 0.0,
        "stale_data_rate": 0.0,
        "api_error_rate": 0.0,
        "manual_override_count": 0,
        "reconciliation_mismatch": False,
        "paper_only": True,
        "adapter_called": False,
        "external_order_submission_performed": False,
        "live_order_executed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "outcome_record_sha256": f"hash_{index}",
    }


def test_phase4_2_blocks_current_package_when_signal_drift_is_observed(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    outcomes = [_outcome(i, result_r=(1.0 if i % 2 == 0 else -1.0), drift=(0.6 if i % 2 == 0 else 0.4)) for i in range(50)]
    atomic_write_json(latest / "paper_outcome_sample_accumulation_outcomes.json", {"outcomes": outcomes})
    atomic_write_json(latest / "phase4_1_paper_outcome_sample_accumulation_report.json", {"status": "PHASE4_1_PAPER_OUTCOME_SAMPLE_ACCUMULATION_RECORDED_REVIEW_ONLY", "outcome_count": 50, "closed_count": 50})
    atomic_write_json(latest / "performance_report.json", {"status": "PERFORMANCE_REPORT_RECORDED", "recommendation": "create_candidate_profile_draft"})
    atomic_write_json(latest / "phase4_outcome_candidate_feedback_report.json", {"status": "PHASE4_OUTCOME_CANDIDATE_BLOCKED_REVIEW_ONLY"})

    report = persist_phase4_2_signal_drift_candidate_readiness_report(cfg=cfg)

    assert report["status"] == STATUS_BLOCKED_REVIEW_ONLY
    assert report["blocked"] is True
    assert report["fail_closed"] is True
    assert report["source_outcome_count"] >= 30
    assert report["overall_summary"]["closed_count"] >= 30
    assert report["overall_summary"]["drift_rate"] > report["max_drift_rate"]
    assert "OVERALL_SIGNAL_DRIFT_RATE_ABOVE_LIMIT" in report["readiness_blockers"]
    assert "SIGNAL_TO_OUTCOME_DRIFT_OBSERVED" in report["readiness_blockers"]
    assert "NO_LOW_DRIFT_PRE_TRADE_SUBSET_READY" in report["readiness_blockers"]
    assert report["candidate_profile_created"] is False
    assert report["candidate_profile_applied"] is False
    assert report["approval_packet_created"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["score_weights_mutated"] is False
    assert report["external_order_submission_performed"] is False
    assert report["live_trading_allowed_by_this_module"] is False
    assert report["candidate_filter_policy"]["uses_pre_trade_dimensions_only"] is True

    assert (latest / "phase4_2_signal_drift_candidate_readiness_report.json").exists()
    assert (latest / "phase4_2_signal_drift_candidate_readiness_registry_record.json").exists()


def test_phase4_2_records_readiness_only_when_low_drift_subset_is_available(tmp_path: Path) -> None:
    _write_min_project(tmp_path)
    cfg = load_config(tmp_path)
    latest = tmp_path / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    outcomes = [_outcome(i, result_r=1.0, drift=0.0) for i in range(12)]
    atomic_write_json(latest / "paper_outcome_sample_accumulation_outcomes.json", {"outcomes": outcomes})
    atomic_write_json(latest / "phase4_1_paper_outcome_sample_accumulation_report.json", {"status": "PHASE4_1_PAPER_OUTCOME_SAMPLE_ACCUMULATION_RECORDED_REVIEW_ONLY"})
    atomic_write_json(latest / "performance_report.json", {"status": "PERFORMANCE_REPORT_RECORDED", "recommendation": "create_candidate_profile_draft"})
    atomic_write_json(latest / "phase4_outcome_candidate_feedback_report.json", {"status": "PHASE4_OUTCOME_CANDIDATE_BLOCKED_REVIEW_ONLY"})

    report = persist_phase4_2_signal_drift_candidate_readiness_report(
        cfg=cfg,
        min_closed_sample_size=10,
        min_subset_sample_size=10,
        max_drift_rate=0.25,
        max_drawdown_limit=6.0,
    )

    assert report["status"] == STATUS_RECORDED_REVIEW_ONLY
    assert report["blocked"] is False
    assert report["candidate_readiness_status"] == "CANDIDATE_READINESS_RECORDED_REVIEW_ONLY"
    assert report["readiness_subset_count"] >= 1
    assert report["candidate_profile_created"] is False
    assert report["candidate_profile_applied"] is False
    assert report["approval_packet_ready"] is False
    assert report["runtime_permission_source"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["external_order_submission_performed"] is False


def test_phase4_2_persists_append_only_registry_record() -> None:
    report = persist_phase4_2_signal_drift_candidate_readiness_report()
    cfg = load_config()
    registry = cfg.root / "storage" / "registries" / "phase4_2_signal_drift_candidate_readiness_registry.jsonl"
    assert registry.exists()
    records = load_registry_records(registry)
    assert records[-1]["phase4_2_report_sha256"] == report["phase4_2_report_sha256"]
    assert records[-1]["runtime_settings_mutated"] is False
    assert records[-1]["score_weights_mutated"] is False
    assert records[-1]["external_order_submission_performed"] is False
