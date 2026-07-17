"""The gate calibration report turns "is this gate too strict?" into a number:
the average R of the trades each block reason turned away."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.feedback import gate_calibration_report as report_mod
from crypto_ai_system.feedback.counterfactual_tracker import classify_counterfactual
from crypto_ai_system.feedback.gate_calibration_report import build_gate_calibration_report


def _outcome(block_reason: str, result_r: float, **overrides):
    row = {
        "outcome_closed": True,
        "block_stage": "pre_order_risk_gate",
        "block_reason": block_reason,
        "regime": "TREND_UP",
        "direction": "LONG",
        "result_R": result_r,
        "classification": classify_counterfactual(result_r),
    }
    row.update(overrides)
    return row


def _summary(report, reason):
    return report["summary_by_block_reason"][reason]


def test_gate_that_blocks_winners_is_costly():
    rows = [_outcome("BLOCK_DAILY_LOSS_LIMIT", 2.0) for _ in range(5)]
    summary = _summary(build_gate_calibration_report(rows, min_sample_size=5), "BLOCK_DAILY_LOSS_LIMIT")
    assert summary["verdict"] == report_mod.COSTLY_GATE
    assert summary["expectancy_R"] == 2.0
    assert summary["total_R"] == 10.0
    assert summary["missed_opportunity_count"] == 5
    assert summary["missed_rate"] == 1.0


def test_gate_that_blocks_losers_is_protective():
    rows = [_outcome("BLOCK_STALE_DATA", -1.0) for _ in range(5)]
    summary = _summary(build_gate_calibration_report(rows, min_sample_size=5), "BLOCK_STALE_DATA")
    assert summary["verdict"] == report_mod.PROTECTIVE_GATE
    assert summary["expectancy_R"] == -1.0
    assert summary["avoided_loss_count"] == 5


def test_small_edge_is_not_a_verdict():
    rows = [_outcome("BLOCK_SPREAD_SLIPPAGE", 0.05) for _ in range(5)]
    summary = _summary(build_gate_calibration_report(rows, min_sample_size=5), "BLOCK_SPREAD_SLIPPAGE")
    assert summary["verdict"] == report_mod.NEUTRAL_GATE


def test_thin_evidence_yields_no_verdict():
    rows = [_outcome("BLOCK_POSITION_LIMIT", 3.0) for _ in range(2)]
    report = build_gate_calibration_report(rows, min_sample_size=5)
    assert _summary(report, "BLOCK_POSITION_LIMIT")["verdict"] == report_mod.INSUFFICIENT_SAMPLE
    # An under-sampled gate must not be recommended for loosening.
    assert report["costly_gates_ranked"] == []


def test_costly_gates_ranked_by_forgone_r():
    rows = (
        [_outcome("BLOCK_POSITION_LIMIT", 1.0) for _ in range(5)]      # total 5R
        + [_outcome("BLOCK_DAILY_LOSS_LIMIT", 2.0) for _ in range(5)]  # total 10R
        + [_outcome("BLOCK_STALE_DATA", -1.0) for _ in range(5)]       # protective
    )
    ranked = build_gate_calibration_report(rows, min_sample_size=5)["costly_gates_ranked"]
    assert [item["block_reason"] for item in ranked] == [
        "BLOCK_DAILY_LOSS_LIMIT",
        "BLOCK_POSITION_LIMIT",
    ]


def test_mixed_results_average_out():
    rows = [
        _outcome("BLOCK_X", 2.0),
        _outcome("BLOCK_X", -1.0),
        _outcome("BLOCK_X", -1.0),
        _outcome("BLOCK_X", 2.0),
        _outcome("BLOCK_X", 0.0),
    ]
    summary = _summary(build_gate_calibration_report(rows, min_sample_size=5), "BLOCK_X")
    assert summary["expectancy_R"] == 0.4
    assert summary["missed_opportunity_count"] == 2
    assert summary["avoided_loss_count"] == 2
    assert summary["neutral_count"] == 1
    assert summary["best_R"] == 2.0
    assert summary["worst_R"] == -1.0
    assert summary["verdict"] == report_mod.COSTLY_GATE


def test_groups_by_stage_regime_and_direction():
    rows = [
        _outcome("BLOCK_X", 1.0, block_stage="trading_decision", regime="RANGE", direction="SHORT"),
        _outcome("BLOCK_Y", 1.0),
    ]
    report = build_gate_calibration_report(rows)
    assert set(report["summary_by_block_stage"]) == {"trading_decision", "pre_order_risk_gate"}
    assert set(report["summary_by_regime"]) == {"RANGE", "TREND_UP"}
    assert set(report["summary_by_direction"]) == {"SHORT", "LONG"}


def test_unsettled_rows_are_excluded():
    rows = [_outcome("BLOCK_X", 2.0), {"outcome_closed": False, "block_reason": "BLOCK_X", "result_R": 99.0}]
    report = build_gate_calibration_report(rows)
    assert report["overall"]["count"] == 1
    assert report["overall"]["total_R"] == 2.0


def test_empty_registry_reports_nothing_rather_than_failing():
    report = build_gate_calibration_report([])
    assert report["overall"]["count"] == 0
    assert report["overall"]["verdict"] == report_mod.INSUFFICIENT_SAMPLE
    assert report["summary_by_block_reason"] == {}


def test_report_is_review_only():
    report = build_gate_calibration_report([_outcome("BLOCK_X", 2.0)])
    assert report["review_only"] is True
    assert report["gate_thresholds_mutated"] is False
    assert report["runtime_settings_mutated"] is False
    assert report["live_trading_allowed_by_this_module"] is False
