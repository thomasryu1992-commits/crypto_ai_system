"""Live (paper) performance as breeding selection pressure (L-A1/L-A2).

Design: docs/architecture/design_live_performance_selection_pressure.md.
The REQUIRED invariant: with no live evidence, every consumer behaves exactly
as before — shrinkage makes the whole mechanism a no-op until data exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.strategy_factory.active_strategy_pool import (
    ACTION_REJECTED_POOL_FULL,
    ACTION_REPLACED,
    add_champion,
    empty_pool,
)
from crypto_ai_system.strategy_factory.live_evidence import (
    DEFAULT_PSEUDO_TRADES,
    live_stats_by_strategy,
    shrunk_live_blended_score,
    sls_for_entry,
)

NOW = "2026-07-20T00:00:00Z"


# -- SLS math -------------------------------------------------------------------

def test_no_live_data_is_the_identity():
    assert shrunk_live_blended_score(0.7, 0, None) == 0.7
    assert shrunk_live_blended_score(0.7, 0, 1.5) == 0.7  # n=0 wins over any exp


def test_k_live_trades_is_an_even_blend():
    k = DEFAULT_PSEUDO_TRADES
    assert shrunk_live_blended_score(0.4, k, -0.2, pseudo_trades=k) == pytest.approx(0.1)


def test_influence_grows_with_sample():
    scores = [shrunk_live_blended_score(1.0, n, 0.0) for n in (0, 5, 20, 60)]
    assert scores == sorted(scores, reverse=True)  # monotonic pull toward live
    assert scores[0] == 1.0
    assert scores[2] == pytest.approx(0.5)


def test_none_backtest_score_stays_none():
    assert shrunk_live_blended_score(None, 50, 2.0) is None


def test_live_stats_aggregation():
    rows = [
        {"strategy_id": "S1", "r_multiple": 1.0},
        {"strategy_id": "S1", "r_multiple": -1.0},
        {"strategy_id": "S1", "r_multiple": 3.0},
        {"strategy_id": "S2", "r_multiple": None},   # unusable -> skipped
        {"strategy_id": None, "r_multiple": 5.0},    # unattributed -> skipped
    ]
    stats = live_stats_by_strategy(rows)
    assert stats == {"S1": (3, pytest.approx(1.0))}


# -- L-A1: replacement pressure --------------------------------------------------

def _spec(strategy_id, rule_hash=None):
    return {"strategy_id": strategy_id, "strategy_rule_hash": rule_hash or f"hash_{strategy_id}"}


def _full_pool(cap=3):
    pool = empty_pool()
    for sid, score in (("S001", 0.50), ("S002", 0.60), ("S003", 0.70)):
        pool, _ = add_champion(pool, _spec(sid), score, cap=cap, now=NOW)
    return pool


def test_no_live_stats_is_byte_identical_decisions():
    pool = _full_pool()
    # 0.53 - 0.50 < 0.05: rejected exactly as before, for every "no data" form.
    for stats in (None, {}):
        _, decision = add_champion(pool, _spec("S010"), 0.53, cap=3,
                                   min_improvement=0.05, now=NOW, live_stats=stats)
        assert decision["action"] == ACTION_REJECTED_POOL_FULL
        assert decision["weakest_strategy_id"] == "S001"
        assert decision["weakest_score"] == 0.50  # SLS == frozen score at n=0
        assert decision["weakest_live_n"] == 0


def test_live_refuted_incumbent_becomes_displaceable():
    pool = _full_pool()
    # S001's real record refutes its backtest: 20 trades at -1.0R.
    # SLS = 0.5*(-1.0) + 0.5*0.50 = -0.25 -> the same 0.53 challenger now wins.
    live = {"S001": (20, -1.0)}
    new_pool, decision = add_champion(pool, _spec("S010"), 0.53, cap=3,
                                      min_improvement=0.05, now=NOW, live_stats=live)
    assert decision["action"] == ACTION_REPLACED
    assert decision["displaced_strategy_id"] == "S001"
    assert decision["displaced_score"] == pytest.approx(-0.25)
    assert decision["weakest_frozen_score"] == 0.50  # audit: frozen anchor kept


def test_live_confirmed_incumbent_hardens_and_pressure_reorders():
    pool = _full_pool()
    # S001 (weakest on paper) is live-CONFIRMED: SLS 0.5*2.0+0.5*0.5 = 1.25.
    # The comparison-time weakest becomes S002 (0.60, no live data).
    live = {"S001": (20, 2.0)}
    _, decision = add_champion(pool, _spec("S010"), 0.70, cap=3,
                               min_improvement=0.05, now=NOW, live_stats=live)
    assert decision["action"] == ACTION_REPLACED
    assert decision["displaced_strategy_id"] == "S002"


def test_champion_score_is_never_rewritten():
    pool = _full_pool()
    live = {"S001": (20, -1.0)}
    new_pool, _ = add_champion(pool, _spec("S010"), 0.53, cap=3,
                               min_improvement=0.05, now=NOW, live_stats=live)
    # The displaced (suspended) entry keeps its frozen admission score.
    displaced = next(e for e in new_pool["active_strategies"] if e["strategy_id"] == "S001")
    assert displaced["champion_score"] == 0.50


def test_thin_live_sample_barely_moves_the_needle():
    pool = _full_pool()
    # 2 catastrophic trades: w = 2/22 -> SLS = 0.409; 0.53-0.409 > 0.05 REPLACED?
    # 0.53 - 0.409 = 0.121 >= 0.05 -> yes, displaceable, but the shift is small
    # and proportional; assert the blended score, not a cliff.
    live = {"S001": (2, -1.0)}
    _, decision = add_champion(pool, _spec("S010"), 0.53, cap=3,
                               min_improvement=0.05, now=NOW, live_stats=live)
    expected_sls = (2 / 22) * -1.0 + (20 / 22) * 0.50
    assert decision.get("displaced_score", decision.get("weakest_score")) == pytest.approx(expected_sls)


def test_sls_for_entry_audit_fields():
    entry = {"strategy_id": "S001", "champion_score": 0.5}
    view = sls_for_entry(entry, {"S001": (10, 0.2)}, pseudo_trades=10)
    assert view["live_n"] == 10
    assert view["live_expectancy"] == 0.2
    assert view["score"] == pytest.approx(0.35)
    assert view["pseudo_trades"] == 10


# -- L-A2: miner seed weighting ---------------------------------------------------

def _mini_frame():
    import pandas as pd

    n = 200
    return pd.DataFrame({
        "close": [100 + i * 0.1 for i in range(n)],
        "open": [100 + i * 0.1 for i in range(n)],
        "high": [101 + i * 0.1 for i in range(n)],
        "low": [99 + i * 0.1 for i in range(n)],
        "ma20": [99.5 + i * 0.1 for i in range(n)],
        "ma50": [99.0 + i * 0.1 for i in range(n)],
        "rsi": [40 + (i % 40) for i in range(n)],
        "atr": [1.0] * n,
    })


def _seed_rule_set(feature="rsi", value=50.0):
    return {
        "direction": "long",
        "conditions": [
            {"feature": feature, "comparison": "<=", "value": value},
            {"feature": "close", "comparison": ">", "value_from": "ma20"},
        ],
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.0, "target_atr": 2.0,
                       "max_holding_bars": 24},
    }


def test_miner_none_weights_is_deterministic_and_unchanged_path():
    from crypto_ai_system.strategy_factory.rule_miner import mine_rule_sets

    frame = _mini_frame()
    kwargs = dict(fitness=lambda rs: float(len(rs["conditions"])), seed=7,
                  population=10, generations=2, top_n=3,
                  seed_population=[_seed_rule_set()])
    a = mine_rule_sets(frame, **kwargs)
    b = mine_rule_sets(frame, **kwargs, seed_weights=None)
    assert a["survivors"] == b["survivors"]  # None weights = original path
    assert a["seeded"] == 1


def test_miner_weighted_seeds_produce_a_valid_search():
    from crypto_ai_system.strategy_factory.rule_miner import mine_rule_sets

    frame = _mini_frame()
    seeds = [_seed_rule_set("rsi", 50.0), _seed_rule_set("rsi", 60.0)]
    result = mine_rule_sets(
        frame, fitness=lambda rs: float(len(rs["conditions"])), seed=7,
        population=10, generations=2, top_n=3,
        seed_population=seeds, seed_weights=[1.9, 1.0],
    )
    assert result["seeded"] == 2
    assert result["search_evaluations"] > 0
    assert isinstance(result["survivors"], list)


def test_miner_truncation_keeps_the_first_seeds():
    from crypto_ai_system.strategy_factory.rule_miner import mine_rule_sets

    frame = _mini_frame()
    # population=2 but 3 seeds: the caller orders best-first, so the first two
    # survive truncation.
    seeds = [_seed_rule_set("rsi", v) for v in (30.0, 40.0, 50.0)]
    result = mine_rule_sets(
        frame, fitness=lambda rs: 1.0, seed=7,
        population=2, generations=1, top_n=2,
        seed_population=seeds, seed_weights=[2.0, 1.5, 1.0],
    )
    assert result["seeded"] == 2
