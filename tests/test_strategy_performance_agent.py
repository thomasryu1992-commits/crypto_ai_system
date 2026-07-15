"""Phase S9: per-strategy rolling performance tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.feedback.strategy_performance_agent import compute_strategy_performance

NOW = "2026-07-16T00:00:00Z"


def _outcomes(r_values, regime="TREND_UP"):
    return [{"r_multiple": r, "entry_regime": regime, "exit_reason": "TARGET" if r > 0 else "STOP"}
            for r in r_values]


def test_empty_history():
    report = compute_strategy_performance("S001", [], now=NOW)
    assert report["trade_count"] == 0
    assert report["lifetime"]["expectancy_r"] is None
    assert report["rolling_20"]["window_full"] is False


def test_lifetime_and_rolling_windows():
    # 60 trades: first 30 winning (+2R), last 30 losing (-1R).
    outcomes = _outcomes([2.0] * 30 + [-1.0] * 30)
    report = compute_strategy_performance("S006", outcomes, now=NOW)
    assert report["trade_count"] == 60
    # Lifetime expectancy = (30*2 + 30*-1)/60 = 0.5
    assert round(report["lifetime"]["expectancy_r"], 6) == 0.5
    # rolling_20 = last 20 (all losers) -> -1.0
    assert round(report["rolling_20"]["expectancy_r"], 6) == -1.0
    assert report["rolling_20"]["window_full"] is True
    # rolling_50 = last 50 (20 winners + 30 losers) -> (20*2 - 30)/50 = 0.2
    assert round(report["rolling_50"]["expectancy_r"], 6) == 0.2


def test_window_full_flag():
    report = compute_strategy_performance("S001", _outcomes([1.0] * 25), now=NOW)
    assert report["rolling_20"]["window_full"] is True    # 25 >= 20
    assert report["rolling_50"]["window_full"] is False   # 25 < 50
    assert report["rolling_100"]["window_full"] is False


def test_live_vs_backtest_win_rate_drop():
    # 10 trades, 4 winners -> live win rate 0.4; backtest was 0.6 -> drop 0.2
    outcomes = _outcomes([1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0])
    report = compute_strategy_performance("S001", outcomes, backtest_win_rate=0.6, now=NOW)
    assert round(report["live_vs_backtest_win_rate_drop"], 6) == 0.2


def test_report_id_is_deterministic():
    outcomes = _outcomes([1.0, -1.0, 2.0])
    a = compute_strategy_performance("S001", outcomes, now=NOW)
    b = compute_strategy_performance("S001", outcomes, now=NOW)
    assert a["strategy_performance_report_id"] == b["strategy_performance_report_id"]


def test_recent_windows_reflect_recency():
    # A strategy that was great then collapsed: rolling window catches the decay
    # the lifetime average still hides.
    outcomes = _outcomes([3.0] * 40 + [-1.0] * 20)
    report = compute_strategy_performance("S006", outcomes, now=NOW)
    assert report["lifetime"]["expectancy_r"] > 0     # still positive overall
    assert report["rolling_20"]["expectancy_r"] < 0   # but recently negative
