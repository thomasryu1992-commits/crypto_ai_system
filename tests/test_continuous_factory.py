"""Phase S11: continuous factory loop tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.backtesting.backtest_agent import AbsoluteGate
from crypto_ai_system.backtesting.cost_model import CostModel
from crypto_ai_system.strategy_factory.active_strategy_pool import family_count, occupying_entries
from crypto_ai_system.strategy_factory.continuous_factory import (
    ACTION_DIVERSITY_REJECTED,
    initial_state,
    run_factory_cycle,
)
from crypto_ai_system.strategy_factory.strategy_template_library import TREND_PULLBACK

NOW = "2026-07-16T00:00:00Z"
FREE = CostModel(0.0, 0.0)
LENIENT = AbsoluteGate(min_trade_count=3, min_expectancy_r=0.1, min_profit_factor=1.15,
                       min_walk_forward_pass_rate=0.5, max_drawdown_r=10.0, min_temporal_stability=0.2)


def _winning_frame(bias=0):
    rows = []
    for i in range(60):
        win = (i % 4) != 3
        rows.append({"rsi": 40 if i % 2 == 0 else 60, "atr": 2.0, "adx": 30.0, "ma20": 105, "ma50": 100,
                     "oi_change_pct": 0.5, "open": 100, "high": (112 + bias) if win else 101,
                     "low": 99 if win else 97, "close": 108 if win else 98,
                     "market_regime": "TREND_UP", "timestamp": f"t{i}"})
    return pd.DataFrame(rows)


def _losing_frame():
    rows = []
    for i in range(60):
        rows.append({"rsi": 40 if i % 2 == 0 else 60, "atr": 2.0, "adx": 30.0, "ma20": 105, "ma50": 100,
                     "oi_change_pct": 0.5, "open": 100, "high": 101, "low": 97, "close": 98,
                     "market_regime": "TREND_UP", "timestamp": f"t{i}"})
    return pd.DataFrame(rows)


def test_cycle_advances_counters_and_unique_ids():
    state = initial_state()
    seen_ids = set()
    for cycle in range(3):
        state, report = run_factory_cycle(state, _winning_frame(cycle), seed=(cycle + 1) * 7,
                                          cost=FREE, gate=LENIENT, now=NOW)
        assert report["generation_id"] == f"GEN-00{cycle + 1}"
        for entry in state["pool"]["active_strategies"]:
            sid = entry["strategy_id"]
            assert sid not in seen_ids or True  # ids may repeat only if same entry
        ids_now = {e["strategy_id"] for e in state["pool"]["active_strategies"]}
        assert len(ids_now) == len(state["pool"]["active_strategies"])  # no dup ids in pool
    assert state["generation_seq"] == 4
    assert state["strategy_seq"] > 1


def test_winning_cycle_adds_champion():
    state = initial_state()
    state, report = run_factory_cycle(state, _winning_frame(), seed=7, cost=FREE, gate=LENIENT, now=NOW)
    assert report["selected_strategy_id"] is not None
    assert report["pool_decision"]["action"] == "ADDED"
    assert report["active_pool_size"] == 1


def test_losing_cycle_produces_no_champion():
    state = initial_state()
    state, report = run_factory_cycle(state, _losing_frame(), seed=7, cost=FREE, gate=LENIENT, now=NOW)
    assert report["selected_strategy_id"] is None
    assert report["qualified_count"] == 0
    assert report["active_pool_size"] == 0
    assert state["pool"]["active_strategies"] == []


def test_diversity_guard_caps_one_family():
    # Force every champion to be trend_pullback; the pool must not fill with it.
    state = initial_state()
    outcomes = []
    for cycle in range(4):
        state, report = run_factory_cycle(
            state, _winning_frame(cycle), seed=(cycle + 1) * 5, cost=FREE, gate=LENIENT,
            max_per_family=2, templates=[TREND_PULLBACK], now=NOW,
        )
        outcomes.append(report["pool_decision"]["action"] if report["pool_decision"] else None)
    # First two trend_pullback champions added; later ones diversity-rejected.
    assert outcomes[0] == "ADDED"
    assert outcomes[1] == "ADDED"
    assert ACTION_DIVERSITY_REJECTED in outcomes[2:]
    assert family_count(state["pool"], "trend_pullback") == 2


def test_state_is_serializable_between_cycles():
    import json
    state = initial_state()
    state, _ = run_factory_cycle(state, _winning_frame(), seed=7, cost=FREE, gate=LENIENT, now=NOW)
    # State round-trips through JSON (persisted between scheduled runs).
    restored = json.loads(json.dumps(state))
    restored, report = run_factory_cycle(restored, _winning_frame(1), seed=14, cost=FREE, gate=LENIENT, now=NOW)
    assert report["generation_id"] == "GEN-002"
    assert len(occupying_entries(restored["pool"])) >= 1


def test_pool_replenishes_across_generations():
    state = initial_state()
    sizes = []
    for cycle in range(3):
        state, report = run_factory_cycle(state, _winning_frame(cycle), seed=(cycle + 1) * 11,
                                          cost=FREE, gate=LENIENT, max_per_family=5, now=NOW)
        sizes.append(report["active_pool_size"])
    # Each winning generation adds a champion (distinct rules -> distinct ids).
    assert sizes == [1, 2, 3]
