"""Tests for the scheduler dashboard aggregation and warnings."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.scheduler.dashboard import build_dashboard, build_warnings


def _cycle(ok=True, trade=False, synthetic=False, ts="2026-07-15T00:00:00+00:00"):
    return {"ts": ts, "ok": ok, "trade_executed": trade, "data_is_synthetic": synthetic}


def _report(**kw):
    base = {
        "status": "PERFORMANCE_REPORT_RECORDED",
        "sample_size": 10,
        "closed_count": 10,
        "expectancy": 0.2,
        "win_loss_ratio": 1.5,
        "average_R": 0.3,
        "max_drawdown": -1.0,
        "stale_data_rate": 0.0,
        "signal_to_outcome_drift": 0.0,
        "reconciliation_mismatch_count": 0,
        "live_candidate_eligible": True,
    }
    base.update(kw)
    return base


def test_dashboard_counts_and_rates():
    records = [
        _cycle(ok=True, trade=True),
        _cycle(ok=True, trade=False),
        _cycle(ok=False),
    ]
    board = build_dashboard(records, _report())
    assert board["cycles"] == 3
    assert board["ok_cycles"] == 2
    assert board["error_cycles"] == 1
    assert board["ok_rate"] == round(2 / 3, 4)
    assert board["trades_placed"] == 1
    assert board["performance"]["expectancy"] == 0.2


def test_no_warnings_on_healthy_report():
    records = [_cycle(ok=True) for _ in range(5)]
    assert build_warnings(records, _report()) == []


def test_negative_expectancy_warns_only_with_enough_samples():
    records = [_cycle() for _ in range(3)]
    assert "negative_expectancy" in build_warnings(records, _report(expectancy=-0.1, closed_count=10))
    # Too few samples -> no expectancy warning.
    assert "negative_expectancy" not in build_warnings(records, _report(expectancy=-0.1, closed_count=1))


def test_data_and_error_warnings():
    records = [_cycle(ok=True), _cycle(ok=False), _cycle(ok=True, synthetic=True)]
    warns = build_warnings(records, _report())
    assert "recent_cycle_errors" in warns
    assert "running_on_synthetic_data" in warns


def test_stale_and_drift_and_mismatch_warnings():
    warns = build_warnings(
        [_cycle()],
        _report(stale_data_rate=0.3, signal_to_outcome_drift=0.9, reconciliation_mismatch_count=2),
    )
    assert "elevated_stale_data_rate" in warns
    assert "signal_to_outcome_drift" in warns
    assert "reconciliation_mismatch" in warns


def test_empty_records():
    board = build_dashboard([], _report())
    assert board["cycles"] == 0
    assert board["ok_rate"] is None
    assert board["first_cycle_at"] is None
