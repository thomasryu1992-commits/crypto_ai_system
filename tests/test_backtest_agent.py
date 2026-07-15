"""Phase S4e: walk-forward, regime split, and BacktestAgent tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.backtesting.cost_model import CostModel
from crypto_ai_system.backtesting.walk_forward import split_windows, run_walk_forward
from crypto_ai_system.backtesting.regime_evaluator import regime_breakdown
from crypto_ai_system.backtesting.backtest_agent import AbsoluteGate, run_backtest_agent
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec

FREE = CostModel(0.0, 0.0)
LENIENT = AbsoluteGate(min_trade_count=4, min_expectancy_r=0.1, min_profit_factor=1.15,
                       min_walk_forward_pass_rate=0.7, max_drawdown_r=10.0, min_temporal_stability=0.3)


def _spec(target_atr=2.0, stop_atr=1.0):
    return StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1",
        "strategy_id": "S001", "strategy_version": "1.0", "generation_id": "GEN-001",
        "strategy_family": "trend_pullback", "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"], "timeframe": "1h", "direction": "long",
        "entry_rules": {"operator": "AND", "conditions": [{"feature": "rsi", "comparison": "<=", "value": 50}]},
        "exit_rules": {"stop_model": "atr", "stop_atr": stop_atr, "target_atr": target_atr, "max_holding_bars": 5},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    })


def _winning_frame(cycles=8, regimes=("RANGE", "TREND_UP")):
    """[signal, win] pairs: each pair opens next-bar and hits +2R target."""
    rows = []
    for c in range(cycles):
        regime = regimes[c % len(regimes)]
        rows.append({"rsi": 40, "atr": 2.0, "open": 100, "high": 100, "low": 100,
                     "close": 100, "market_regime": regime, "timestamp": f"t{2*c}"})
        rows.append({"rsi": 99, "atr": 2.0, "open": 100, "high": 110, "low": 99,
                     "close": 108, "market_regime": regime, "timestamp": f"t{2*c+1}"})
    return pd.DataFrame(rows)


def _losing_frame(cycles=8):
    rows = []
    for c in range(cycles):
        rows.append({"rsi": 40, "atr": 2.0, "open": 100, "high": 100, "low": 100,
                     "close": 100, "market_regime": "RANGE", "timestamp": f"t{2*c}"})
        rows.append({"rsi": 99, "atr": 2.0, "open": 100, "high": 101, "low": 97,
                     "close": 98, "market_regime": "RANGE", "timestamp": f"t{2*c+1}"})
    return pd.DataFrame(rows)


def _qualifying_frame(cycles=8, loss_every=4, regimes=("RANGE", "TREND_UP")):
    """Mostly winners with periodic losers, so profit factor is finite and high."""
    rows = []
    for c in range(cycles):
        regime = regimes[c % len(regimes)]
        loss = (c % loss_every) == (loss_every - 1)
        rows.append({"rsi": 40, "atr": 2.0, "open": 100, "high": 100, "low": 100,
                     "close": 100, "market_regime": regime, "timestamp": f"t{2*c}"})
        if loss:  # low pierces stop 98
            rows.append({"rsi": 99, "atr": 2.0, "open": 100, "high": 101, "low": 97,
                         "close": 98, "market_regime": regime, "timestamp": f"t{2*c+1}"})
        else:     # high pierces target 104
            rows.append({"rsi": 99, "atr": 2.0, "open": 100, "high": 110, "low": 99,
                         "close": 108, "market_regime": regime, "timestamp": f"t{2*c+1}"})
    return pd.DataFrame(rows)


# -- window splitting ---------------------------------------------------------

def test_split_windows_contiguous_and_covering():
    windows = split_windows(10, 4)
    assert windows[0][0] == 0 and windows[-1][1] == 10
    for (s1, e1), (s2, e2) in zip(windows, windows[1:]):
        assert e1 == s2  # contiguous, no gaps or overlaps
    assert [e - s for s, e in windows] == [3, 3, 2, 2]


def test_split_windows_more_windows_than_rows():
    assert split_windows(3, 8) == [(0, 1), (1, 2), (2, 3)]
    assert split_windows(0, 4) == []


# -- walk-forward -------------------------------------------------------------

def test_walk_forward_all_windows_pass():
    wf = run_walk_forward(_spec(), _winning_frame(), cost=FREE, n_windows=4)
    assert wf["walk_forward_pass_rate"] == 1.0
    assert wf["temporal_stability"] is not None and wf["temporal_stability"] > 0.9


def test_walk_forward_losing_fails():
    wf = run_walk_forward(_spec(), _losing_frame(), cost=FREE, n_windows=4)
    assert wf["walk_forward_pass_rate"] == 0.0
    assert wf["temporal_stability"] == 0.0


# -- regime breakdown ---------------------------------------------------------

def test_regime_breakdown_splits_by_entry_regime():
    from crypto_ai_system.backtesting.execution_simulator import simulate_strategy
    result = simulate_strategy(_spec(), _winning_frame(regimes=("RANGE", "TREND_UP")), cost=FREE)
    breakdown = regime_breakdown(result["trades"])
    assert set(breakdown["regimes_traded"]) == {"RANGE", "TREND_UP"}
    assert breakdown["profitable_regime_count"] == 2


# -- backtest agent record ----------------------------------------------------

def test_agent_qualifies_a_winning_strategy():
    record = run_backtest_agent(_spec(), _qualifying_frame(), cost=FREE, n_windows=4,
                                gate=LENIENT, now="2026-07-16T00:00:00Z")
    assert record["qualified"] is True, record["gate_failures"]
    assert record["gate_failures"] == []
    assert record["metrics"]["trade_count"] == 8
    assert record["metrics"]["profit_factor"] is not None
    assert record["metrics"]["expectancy_r"] > 0.1
    assert record["backtest_run_id"].startswith("backtest_run_")


def test_agent_rejects_a_losing_strategy():
    record = run_backtest_agent(_spec(), _losing_frame(), cost=FREE, n_windows=4,
                                gate=LENIENT, now="2026-07-16T00:00:00Z")
    assert record["qualified"] is False
    assert "expectancy_below_min" in record["gate_failures"]
    assert "profit_factor_below_min" in record["gate_failures"]


def test_agent_rejects_on_low_sample_with_default_gate():
    # Default gate needs >=100 trades; 8 winning trades still fails on sample size.
    record = run_backtest_agent(_spec(), _winning_frame(), cost=FREE, now="2026-07-16T00:00:00Z")
    assert record["qualified"] is False
    assert "trade_count_below_min" in record["gate_failures"]


def test_agent_is_reproducible():
    a = run_backtest_agent(_spec(), _qualifying_frame(), cost=FREE, gate=LENIENT, now="2026-07-16T00:00:00Z")
    b = run_backtest_agent(_spec(), _qualifying_frame(), cost=FREE, gate=LENIENT, now="2026-07-16T00:00:00Z")
    assert a["backtest_run_id"] == b["backtest_run_id"]


def test_agent_run_id_stable_across_timestamps():
    a = run_backtest_agent(_spec(), _qualifying_frame(), cost=FREE, gate=LENIENT, now="2026-07-16T00:00:00Z")
    b = run_backtest_agent(_spec(), _qualifying_frame(), cost=FREE, gate=LENIENT, now="2027-01-01T00:00:00Z")
    # Identity excludes created_at, so the run id is unchanged by the timestamp.
    assert a["backtest_run_id"] == b["backtest_run_id"]
