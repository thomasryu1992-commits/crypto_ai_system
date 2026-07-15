"""Phase S10: strategy lifecycle agent tests (directive §6.16 / §18 / §19)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.feedback.strategy_lifecycle_agent import evaluate_lifecycle
from crypto_ai_system.feedback.strategy_performance_agent import compute_strategy_performance
from crypto_ai_system.strategy_factory.strategy_spec import StrategyStatus

NOW = "2026-07-16T00:00:00Z"
ACTIVE = StrategyStatus.PAPER_ACTIVE.value
WARNING = StrategyStatus.WARNING.value
PROBATION = StrategyStatus.PROBATION.value
SUSPENDED = StrategyStatus.SUSPENDED.value
ARCHIVED = StrategyStatus.ARCHIVED.value


def _perf(r_values, *, backtest_win_rate=None):
    outcomes = [{"r_multiple": r, "entry_regime": "TREND_UP", "exit_reason": "TARGET" if r > 0 else "STOP"}
                for r in r_values]
    return compute_strategy_performance("S006", outcomes, backtest_win_rate=backtest_win_rate, now=NOW)


# -- healthy / insufficient data ----------------------------------------------

def test_healthy_strategy_stays_active():
    perf = _perf([2.0, -1.0] * 30)  # expectancy +0.5, pf 2.0
    decision = evaluate_lifecycle(ACTIVE, perf, now=NOW)
    assert decision["new_status"] == ACTIVE
    assert decision["status_changed"] is False


def test_young_strategy_not_degraded_on_thin_data():
    # Only 10 losing trades: rolling_20 not full -> cannot warn yet.
    perf = _perf([-1.0] * 10)
    decision = evaluate_lifecycle(ACTIVE, perf, now=NOW)
    assert decision["new_status"] == ACTIVE
    assert decision["consecutive_failures"] == 0


# -- warning ------------------------------------------------------------------

def test_negative_rolling_20_warns():
    # 20 trades, expectancy negative -> WARNING.
    perf = _perf([1.0, -1.0, -1.0, -1.0] * 5)  # win rate 0.25, expectancy -0.5
    decision = evaluate_lifecycle(ACTIVE, perf, now=NOW)
    assert decision["new_status"] == WARNING
    assert decision["is_escalation"] is True
    assert decision["consecutive_failures"] == 1


# -- probation ----------------------------------------------------------------

def test_probation_on_worse_rolling_30():
    perf = _perf([-1.0] * 30)  # deeply negative over 30
    decision = evaluate_lifecycle(WARNING, perf, now=NOW)
    assert decision["new_status"] == PROBATION


def test_probation_on_win_rate_drop_vs_backtest():
    # Expectancy fine but live win rate collapsed vs backtest -> probation.
    perf = _perf([1.0] * 12 + [-1.0] * 18, backtest_win_rate=0.9)  # live wr 0.4, drop 0.5
    decision = evaluate_lifecycle(ACTIVE, perf, now=NOW)
    assert decision["new_status"] == PROBATION
    assert "live_win_rate_dropped_below_backtest" in decision["reasons"]


# -- suspend (needs 2 consecutive) --------------------------------------------

def test_suspend_needs_two_consecutive_failures():
    perf = _perf([-1.0] * 50)  # 50 negative -> suspend metrics true
    # First failing evaluation: not yet 2 consecutive -> probation, not suspended.
    first = evaluate_lifecycle(WARNING, perf, consecutive_failures=0, now=NOW)
    assert first["new_status"] == PROBATION
    assert first["consecutive_failures"] == 1
    # Second consecutive failing evaluation -> SUSPENDED.
    second = evaluate_lifecycle(first["new_status"], perf, consecutive_failures=first["consecutive_failures"], now=NOW)
    assert second["new_status"] == SUSPENDED
    assert second["new_entry_blocked"] is True


# -- archive (needs 100 trades + 3 consecutive) -------------------------------

def test_archive_conditions():
    perf = _perf([-1.0] * 120)  # 120 trades, negative lifetime
    decision = evaluate_lifecycle(PROBATION, perf, consecutive_failures=2, now=NOW)
    assert decision["new_status"] == ARCHIVED
    assert decision["new_entry_blocked"] is True


def test_not_archived_below_100_trades():
    perf = _perf([-1.0] * 60)  # negative but <100 lifetime trades
    decision = evaluate_lifecycle(PROBATION, perf, consecutive_failures=5, now=NOW)
    assert decision["new_status"] == SUSPENDED  # suspend, not archive


# -- terminal states are sticky (no auto-reactivation) ------------------------

def test_suspended_is_terminal_no_auto_recovery():
    perf = _perf([2.0, -1.0] * 30)  # now healthy again
    decision = evaluate_lifecycle(SUSPENDED, perf, now=NOW)
    assert decision["new_status"] == SUSPENDED
    assert decision["requires_manual_reactivation"] is True


def test_archived_is_terminal():
    perf = _perf([3.0] * 40)
    decision = evaluate_lifecycle(ARCHIVED, perf, now=NOW)
    assert decision["new_status"] == ARCHIVED


# -- recovery from reversible states ------------------------------------------

def test_warning_recovers_to_active_when_healthy():
    perf = _perf([2.0, -1.0] * 30)  # healthy
    decision = evaluate_lifecycle(WARNING, perf, consecutive_failures=1, now=NOW)
    assert decision["new_status"] == ACTIVE
    assert decision["is_recovery"] is True
    assert decision["consecutive_failures"] == 0


# -- §18 full degradation path ------------------------------------------------

def test_full_degradation_path_active_to_suspended():
    bad = _perf([-1.0] * 50)
    s1 = evaluate_lifecycle(ACTIVE, bad, consecutive_failures=0, now=NOW)
    assert s1["new_status"] == PROBATION and s1["consecutive_failures"] == 1
    s2 = evaluate_lifecycle(s1["new_status"], bad, consecutive_failures=s1["consecutive_failures"], now=NOW)
    assert s2["new_status"] == SUSPENDED
    # §19: a suspended strategy is blocked from new entries.
    assert s2["new_entry_blocked"] is True


# -- win rate alone must not discard ------------------------------------------

def test_low_win_rate_but_positive_expectancy_not_warned():
    # 20 trades: 5 big winners (+5R), 15 small losers (-1R). Win rate 0.25 but
    # expectancy = (5*5 - 15)/20 = +0.5 and profit factor 25/15 > 1 -> healthy.
    perf = _perf([5.0] * 5 + [-1.0] * 15)
    decision = evaluate_lifecycle(ACTIVE, perf, now=NOW)
    assert decision["new_status"] == ACTIVE
