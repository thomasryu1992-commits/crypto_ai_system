"""Rule miner contract: bounded search, train-only knowledge, honest specs.

The miner widens the search space far beyond the template library, so the thing
these tests protect is the honesty envelope around it: thresholds and fitness
must see only the train slice, produced specs must be the same declarative data
the whole pipeline already trusts, and the search must stay bounded and
deterministic.
"""

from __future__ import annotations

import random

import numpy as np
import pandas as pd
import pytest

from crypto_ai_system.strategy_factory.rule_miner import (
    MAX_CONDITIONS,
    MIN_CONDITIONS,
    build_condition_pool,
    crossover,
    mine_rule_sets,
    mined_family,
    mutate,
    random_rule_set,
    rule_set_to_spec_dict,
    split_train_holdout,
)
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.strategy_factory.strategy_validator_agent import validate_strategy


def _frame(n: int = 400, close_shift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    ts = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    close = 60000 + np.cumsum(rng.normal(0, 200, n)) + close_shift
    return pd.DataFrame({
        "timestamp": [str(t) for t in ts],
        "open": close - 20, "high": close + 60, "low": close - 60, "close": close,
        "volume": rng.uniform(50, 150, n),
        "ma20": close * 0.99, "ma50": close * 0.98, "ema20": close * 0.995, "ema50": close * 0.985,
        "rsi": rng.uniform(20, 80, n), "adx": rng.uniform(10, 40, n),
        "atr": rng.uniform(300, 700, n), "atr_pct_of_price": rng.uniform(0.005, 0.02, n),
        "atr_percentile": rng.uniform(0, 1, n),
        "price_distance_ma20": rng.normal(0, 0.01, n),
        "macd_hist": rng.normal(0, 50, n),
        "bb_percent_b": rng.uniform(-0.2, 1.2, n), "bb_width_pct": rng.uniform(0.01, 0.1, n),
        "bb_width_percentile": rng.uniform(0, 1, n),
        "bb_upper": close * 1.02, "bb_lower": close * 0.98,
        "roc_4": rng.normal(0, 0.02, n), "roc_12": rng.normal(0, 0.04, n),
        "volume_zscore": rng.normal(0, 1, n),
        "funding_rate": rng.normal(0.0001, 0.0002, n), "funding_zscore": rng.normal(0, 1, n),
        "htf_4h_ema_gap_pct": rng.normal(0, 0.005, n), "htf_1d_ema_gap_pct": rng.normal(0, 0.01, n),
        "htf_alignment_score": rng.choice([-1.0, 0.0, 1.0], n),
        "mark_price": close, "index_price": close,
        "mark_index_basis_bps": rng.normal(0, 5, n), "mark_last_basis_bps": rng.normal(0, 5, n),
        "market_regime": rng.choice(["TREND_UP", "TREND_DOWN", "RANGE"], n),
        "htf_4h_trend": rng.choice(["UP", "DOWN", "FLAT"], n),
        "htf_1d_trend": rng.choice(["UP", "DOWN", "FLAT"], n),
    })


def test_split_is_chronological() -> None:
    frame = _frame(400)
    train, holdout = split_train_holdout(frame, 0.7)
    assert len(train) == 280 and len(holdout) == 120
    assert pd.to_datetime(train["timestamp"].iloc[-1]) < pd.to_datetime(holdout["timestamp"].iloc[0])


def test_condition_pool_thresholds_come_from_the_train_slice_only() -> None:
    """Changing the FUTURE must not change the conditions the miner can draw."""
    base = _frame(400)
    train, _ = split_train_holdout(base, 0.7)
    shifted = base.copy()
    shifted.iloc[280:, shifted.columns.get_loc("rsi")] = 99.0  # corrupt the holdout
    train_after, _ = split_train_holdout(shifted, 0.7)

    assert build_condition_pool(train) == build_condition_pool(train_after)


def test_condition_pool_excludes_absent_and_unavailable_features() -> None:
    frame = _frame(400).drop(columns=["funding_zscore"])
    pool = build_condition_pool(frame)
    features = {c["feature"] for c in pool}
    assert "funding_zscore" not in features
    assert "open_interest" not in features, "runtime-unavailable features must never be drawn"


def test_price_features_compare_to_prices_and_oscillators_to_literals() -> None:
    pool = build_condition_pool(_frame(400))
    for cond in pool:
        if "value_from" in cond:
            assert cond["feature"] != "rsi", "an oscillator must never compare to a price column"


def test_random_rule_set_is_bounded_and_deduped() -> None:
    pool = build_condition_pool(_frame(400))
    rng = random.Random(3)
    for _ in range(50):
        rs = random_rule_set(pool, rng)
        assert MIN_CONDITIONS <= len(rs["conditions"]) <= MAX_CONDITIONS
        features = [c["feature"] for c in rs["conditions"]]
        assert len(features) == len(set(features)), "one condition per feature"
        assert rs["exit_rules"]["target_atr"] >= rs["exit_rules"]["stop_atr"], "reward:risk >= 1"


def test_crossover_and_mutate_stay_bounded() -> None:
    pool = build_condition_pool(_frame(400))
    rng = random.Random(5)
    a, b = random_rule_set(pool, rng), random_rule_set(pool, rng)
    for _ in range(50):
        child = mutate(crossover(a, b, rng), pool, rng)
        assert MIN_CONDITIONS <= len(child["conditions"]) <= MAX_CONDITIONS
        features = [c["feature"] for c in child["conditions"]]
        assert len(features) == len(set(features))


def test_mined_spec_parses_validates_and_carries_the_audit_denominator() -> None:
    pool = build_condition_pool(_frame(400))
    rs = random_rule_set(pool, random.Random(9))
    spec_dict = rule_set_to_spec_dict(
        rs, strategy_id="S900", generation_id="MINE-001",
        symbol="ETHUSDT", timeframe="1d", search_evaluations=921,
    )
    spec = StrategySpec.from_dict(spec_dict)
    assert spec.symbol_scope == ("ETHUSDT",)
    assert spec_dict["search_evaluations"] == 921
    assert spec_dict["strategy_family"].startswith("mined:")
    verdict = validate_strategy(spec)
    assert verdict["approved_for_backtest"], verdict["block_reasons"]


def test_mined_spec_cannot_grant_itself_execution() -> None:
    pool = build_condition_pool(_frame(400))
    rs = random_rule_set(pool, random.Random(9))
    spec_dict = rule_set_to_spec_dict(
        rs, strategy_id="S901", generation_id="MINE-001",
        symbol="BTCUSDT", timeframe="1d", search_evaluations=1,
    )
    spec_dict["can_submit_orders"] = True
    with pytest.raises(Exception):
        StrategySpec.from_dict(spec_dict)


def test_family_is_the_feature_combination() -> None:
    conds = [
        {"feature": "rsi", "comparison": "<=", "value": 30.0},
        {"feature": "close", "comparison": ">", "value_from": "ma20"},
    ]
    assert mined_family(conds) == "mined:close+rsi"


def test_mining_is_deterministic_by_seed_and_counts_evaluations() -> None:
    train, _ = split_train_holdout(_frame(400), 0.7)

    def fitness(rs) -> float:
        return float(len(rs["conditions"]))

    a = mine_rule_sets(train, fitness=fitness, seed=42, population=10, generations=3, top_n=3)
    b = mine_rule_sets(train, fitness=fitness, seed=42, population=10, generations=3, top_n=3)
    c = mine_rule_sets(train, fitness=fitness, seed=43, population=10, generations=3, top_n=3)

    assert a["survivors"] == b["survivors"], "same seed must reproduce the same search"
    assert a["search_evaluations"] == b["search_evaluations"] > 0
    assert a != c or a["survivors"] != c["survivors"]


def test_survivors_are_distinct_families() -> None:
    train, _ = split_train_holdout(_frame(400), 0.7)
    result = mine_rule_sets(
        train, fitness=lambda rs: random.Random(str(rs)).random(),
        seed=1, population=20, generations=4, top_n=5,
    )
    families = [s["family"] for s in result["survivors"]]
    assert len(families) == len(set(families))


def test_empty_condition_pool_yields_no_survivors() -> None:
    empty = pd.DataFrame({"timestamp": [], "close": []})
    result = mine_rule_sets(empty, fitness=lambda rs: 0.0, seed=1)
    assert result["survivors"] == [] and result["search_evaluations"] == 0
