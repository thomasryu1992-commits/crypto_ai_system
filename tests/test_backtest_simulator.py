"""Phase S4c: single-pass execution simulator tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.backtesting.cost_model import CostModel
from crypto_ai_system.backtesting.execution_simulator import simulate_strategy
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec

FREE = CostModel(0.0, 0.0)


def _spec(stop_atr=1.0, target_atr=2.0, max_holding_bars=10, rsi_max=50):
    return StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1",
        "strategy_id": "S001",
        "strategy_version": "1.0",
        "generation_id": "GEN-001",
        "strategy_family": "trend_pullback",
        "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"],
        "timeframe": "1h",
        "direction": "long",
        "entry_rules": {"operator": "AND", "conditions": [
            {"feature": "rsi", "comparison": "<=", "value": rsi_max},
        ]},
        "exit_rules": {"stop_model": "atr", "stop_atr": stop_atr, "target_atr": target_atr,
                       "max_holding_bars": max_holding_bars},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    })


def _frame(rows):
    return pd.DataFrame(rows)


def _bar(rsi=99, atr=2.0, o=100, h=100, l=100, c=100, regime="RANGE", ts=None):
    return {"timestamp": ts, "rsi": rsi, "atr": atr, "open": o, "high": h, "low": l,
            "close": c, "market_regime": regime}


def test_target_hit_is_two_r():
    # Signal bar 0 (rsi 40), enter bar 1 open=100, atr=2 -> stop 98, target 104.
    frame = _frame([
        _bar(rsi=40, atr=2.0, o=100, h=100, l=100, c=100, ts="t0"),
        _bar(rsi=99, atr=2.0, o=100, h=110, l=99, c=108, ts="t1"),  # high 110 >= target 104
        _bar(rsi=99, atr=2.0, ts="t2"),
    ])
    result = simulate_strategy(_spec(), frame, cost=FREE)
    assert result["closed_trades"] == 1
    trade = result["trades"][0]
    assert trade["exit_reason"] == "TARGET"
    assert round(trade["r_multiple"], 6) == 2.0
    assert trade["entry_bar"] == 1


def test_stop_hit_is_minus_one_r():
    frame = _frame([
        _bar(rsi=40, atr=2.0, o=100, h=100, l=100, c=100, ts="t0"),
        _bar(rsi=99, atr=2.0, o=100, h=101, l=97, c=98, ts="t1"),  # low 97 <= stop 98
        _bar(rsi=99, atr=2.0, ts="t2"),
    ])
    result = simulate_strategy(_spec(), frame, cost=FREE)
    trade = result["trades"][0]
    assert trade["exit_reason"] == "STOP"
    assert round(trade["r_multiple"], 6) == -1.0


def test_no_signal_no_trades():
    frame = _frame([_bar(rsi=99) for _ in range(5)])
    result = simulate_strategy(_spec(), frame, cost=FREE)
    assert result["entries"] == 0
    assert result["closed_trades"] == 0


def test_entry_is_next_bar_open_no_lookahead():
    # Signal on bar 0; bar 1 gaps to open 200. Entry must fill near 200, not 100.
    frame = _frame([
        _bar(rsi=40, atr=2.0, o=100, h=100, l=100, c=100, ts="t0"),
        _bar(rsi=99, atr=2.0, o=200, h=205, l=199, c=204, ts="t1"),
        _bar(rsi=99, atr=2.0, o=204, h=204, l=204, c=204, ts="t2"),
    ])
    result = simulate_strategy(_spec(), frame, cost=FREE)
    trade = result["trades"][0]
    assert trade["entry_price"] == 200.0


def test_max_holding_exit():
    # No stop/target hit; exit at close when bars_held reaches the cap.
    frame = _frame([
        _bar(rsi=40, atr=2.0, o=100, h=100, l=100, c=100, ts="t0"),
        _bar(rsi=99, atr=2.0, o=100, h=101, l=99, c=100.5, ts="t1"),  # bars_held 1
        _bar(rsi=99, atr=2.0, o=100, h=101, l=99, c=100.5, ts="t2"),  # bars_held 2 -> exit
        _bar(rsi=99, atr=2.0, ts="t3"),
    ])
    result = simulate_strategy(_spec(max_holding_bars=2), frame, cost=FREE)
    trade = result["trades"][0]
    assert trade["exit_reason"] == "MAX_HOLDING"
    assert trade["bars_held"] == 2


def test_force_close_at_end():
    # Enter on the last bar; nothing hits; force-close at last close.
    frame = _frame([
        _bar(rsi=99, atr=2.0, ts="t0"),
        _bar(rsi=40, atr=2.0, o=100, h=100, l=100, c=100, ts="t1"),  # signal
        _bar(rsi=99, atr=2.0, o=100, h=101, l=99, c=100.7, ts="t2"),  # entry bar = last
    ])
    result = simulate_strategy(_spec(max_holding_bars=50), frame, cost=FREE)
    assert result["closed_trades"] == 1
    assert result["trades"][0]["exit_reason"] == "FORCE_CLOSE"


def test_entry_regime_recorded():
    frame = _frame([
        _bar(rsi=40, atr=2.0, o=100, h=100, l=100, c=100, regime="TREND_UP", ts="t0"),
        _bar(rsi=99, atr=2.0, o=100, h=110, l=99, c=108, ts="t1"),
        _bar(rsi=99, atr=2.0, ts="t2"),
    ])
    result = simulate_strategy(_spec(), frame, cost=FREE)
    assert result["trades"][0]["entry_regime"] == "TREND_UP"


def test_stop_priority_when_both_hit():
    # A bar whose range spans both stop and target -> stop wins (conservative).
    frame = _frame([
        _bar(rsi=40, atr=2.0, o=100, h=100, l=100, c=100, ts="t0"),
        _bar(rsi=99, atr=2.0, o=100, h=110, l=97, c=100, ts="t1"),  # spans stop 98 and target 104
        _bar(rsi=99, atr=2.0, ts="t2"),
    ])
    result = simulate_strategy(_spec(), frame, cost=FREE)
    assert result["trades"][0]["exit_reason"] == "STOP"


def test_costs_make_target_less_than_two_r():
    frame = _frame([
        _bar(rsi=40, atr=2.0, o=100, h=100, l=100, c=100, ts="t0"),
        _bar(rsi=99, atr=2.0, o=100, h=110, l=99, c=108, ts="t1"),
        _bar(rsi=99, atr=2.0, ts="t2"),
    ])
    result = simulate_strategy(_spec(), frame, cost=CostModel(2.5, 3.0))
    trade = result["trades"][0]
    assert trade["r_multiple"] < 2.0
    assert trade["fees"] > 0 and trade["slippage_cost"] > 0


def test_missing_columns_raises():
    frame = pd.DataFrame([{"open": 1, "high": 1, "low": 1, "close": 1}])  # no atr
    with pytest.raises(ValueError, match="atr"):
        simulate_strategy(_spec(), frame)


def test_no_reentry_same_bar_single_position():
    # Continuous signal; still at most one position at a time.
    rows = [_bar(rsi=40, atr=2.0, o=100, h=101, l=99, c=100, ts=f"t{i}") for i in range(6)]
    result = simulate_strategy(_spec(max_holding_bars=1), _frame(rows), cost=FREE)
    # Each trade closes before the next entry; entries never overlap.
    assert result["entries"] == result["closed_trades"]
    assert result["entries"] >= 1
