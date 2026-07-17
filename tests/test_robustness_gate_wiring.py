"""The scorer only matters if the backtest record carries it and the gate can act
on it. Both are checked here against a real simulated backtest."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.backtesting import robustness_scorer as rs
from crypto_ai_system.backtesting.backtest_agent import AbsoluteGate, run_backtest_agent
from crypto_ai_system.backtesting.cost_model import CostModel
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec

FREE = CostModel(0.0, 0.0)
# Lenient enough that the classic gate passes, so a failure can only come from
# the robustness thresholds under test.
LENIENT = AbsoluteGate(min_trade_count=4, min_expectancy_r=0.1, min_profit_factor=1.15,
                       min_walk_forward_pass_rate=0.5, max_drawdown_r=10.0,
                       min_temporal_stability=0.2)


def _spec():
    return StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1",
        "strategy_id": "S001", "strategy_version": "1.0", "generation_id": "GEN-001",
        "strategy_family": "trend_pullback", "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"], "timeframe": "1h", "direction": "long",
        "entry_rules": {"operator": "AND", "conditions": [{"feature": "rsi", "comparison": "<=", "value": 50}]},
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.0, "target_atr": 2.0, "max_holding_bars": 5},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    })


def _mixed_frame(cycles=8, losing_cycles=(0,), regimes=("RANGE", "TREND_UP")):
    """[signal, outcome] pairs. A winner hits the +2R target, a loser the stop.

    At least one loser is needed or profit_factor is None (no gross loss to
    divide by) and the classic gate fails for a reason unrelated to robustness."""
    rows = []
    for c in range(cycles):
        regime = regimes[c % len(regimes)]
        rows.append({"rsi": 40, "atr": 2.0, "open": 100, "high": 100, "low": 100,
                     "close": 100, "market_regime": regime, "timestamp": f"t{2*c}"})
        if c in losing_cycles:  # low 97 <= stop 98
            outcome = {"high": 101, "low": 97, "close": 98}
        else:  # high 110 >= target 104
            outcome = {"high": 110, "low": 99, "close": 108}
        rows.append({"rsi": 99, "atr": 2.0, "open": 100, **outcome,
                     "market_regime": regime, "timestamp": f"t{2*c+1}"})
    return pd.DataFrame(rows)


def _run(gate=LENIENT):
    return run_backtest_agent(_spec(), _mixed_frame(), cost=FREE, gate=gate, now="2026-07-17T00:00:00Z")


def test_record_carries_a_robustness_verdict():
    record = _run()
    robustness = record["robustness"]
    assert robustness["verdict"] in {rs.ROBUST, rs.PROVISIONAL, rs.FRAGILE}
    # 1 entry literal + 3 exit numbers.
    assert robustness["free_parameters"] == 4
    assert robustness["trade_count"] == record["metrics"]["trade_count"]


def test_robustness_does_not_gate_by_default():
    """A thin-sample champion still qualifies unless the operator opted in —
    turning this on with short history would reject everything, not improve it."""
    record = _run()
    assert record["robustness"]["verdict"] == rs.FRAGILE
    assert record["qualified"] is True
    assert "trades_per_parameter_below_min" not in record["gate_failures"]
    assert "robustness_score_below_min" not in record["gate_failures"]


def test_trades_per_parameter_gate_disqualifies_when_enabled():
    from dataclasses import replace

    record = _run(replace(LENIENT, min_trades_per_parameter=10.0))
    assert "trades_per_parameter_below_min" in record["gate_failures"]
    assert record["qualified"] is False


def test_robustness_score_gate_disqualifies_when_enabled():
    from dataclasses import replace

    record = _run(replace(LENIENT, min_robustness_score=0.9))
    assert "robustness_score_below_min" in record["gate_failures"]
    assert record["qualified"] is False


def test_enabled_gate_still_passes_a_strategy_that_clears_it():
    from dataclasses import replace

    record = _run(replace(LENIENT, min_trades_per_parameter=1.0, min_robustness_score=0.1))
    assert "trades_per_parameter_below_min" not in record["gate_failures"]
    assert "robustness_score_below_min" not in record["gate_failures"]


def test_thresholds_are_recorded_for_audit():
    from dataclasses import replace

    record = _run(replace(LENIENT, min_trades_per_parameter=10.0, min_robustness_score=0.5))
    assert record["absolute_gate"]["min_trades_per_parameter"] == 10.0
    assert record["absolute_gate"]["min_robustness_score"] == 0.5


def test_pool_entry_keeps_the_verdict():
    """The backtest record is never persisted, so the pool entry is the only
    place an operator can later see that an occupant was fitted."""
    from crypto_ai_system.strategy_factory.active_strategy_pool import add_champion, empty_pool

    record = _run()
    spec = _spec().to_dict()
    pool, decision = add_champion(
        empty_pool(), spec, 0.8, generation_id="GEN-001",
        now="2026-07-17T00:00:00Z", robustness=record["robustness"],
    )
    entry = pool["active_strategies"][0]
    assert decision["action"] == "ADDED"
    assert entry["robustness_verdict"] == rs.FRAGILE
    assert entry["trades_per_parameter"] == record["robustness"]["trades_per_parameter"]
    assert "trades_per_parameter_below_critical" in entry["robustness_warnings"]


def test_pool_entry_without_robustness_is_unchanged():
    """Existing callers that pass no robustness must produce the old entry shape."""
    from crypto_ai_system.strategy_factory.active_strategy_pool import add_champion, empty_pool

    pool, _ = add_champion(empty_pool(), _spec().to_dict(), 0.8, now="2026-07-17T00:00:00Z")
    assert "robustness_verdict" not in pool["active_strategies"][0]
