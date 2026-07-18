"""Champion-seeded mining: adopted specs re-enter the search as parents.

The contract: a pool champion converts to an evolvable rule set (or None when
not expressible), seeds join the initial population with no other privilege,
and the no-seed path is byte-identical to before.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_ai_system.strategy_factory.rule_miner import (
    mine_rule_sets,
    spec_to_rule_set,
)
from crypto_ai_system.strategy_factory.runtime_feature_adapter import build_backtest_frame


def _champion_spec(direction: str = "LONG") -> dict:
    return {
        "strategy_id": "S271",
        "strategy_family": "breakout",
        "direction": direction,
        "entry_rules": {"operator": "AND", "conditions": [
            {"feature": "close", "comparison": ">", "value_from": "ma20"},
            {"feature": "adx", "comparison": ">=", "value": 25.0},
            {"feature": "rsi", "comparison": "<=", "value": 60.0},
        ]},
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.2, "target_atr": 3.0, "max_holding_bars": 24},
    }


def test_spec_converts_to_rule_set() -> None:
    rule_set = spec_to_rule_set(_champion_spec())
    assert rule_set is not None
    assert rule_set["direction"] == "long"
    assert {c["feature"] for c in rule_set["conditions"]} == {"close", "adx", "rsi"}
    assert rule_set["exit_rules"]["stop_atr"] == 1.2


def test_inexpressible_specs_convert_to_none() -> None:
    no_exits = _champion_spec()
    no_exits["exit_rules"] = {"stop_model": "atr"}
    assert spec_to_rule_set(no_exits) is None

    one_condition = _champion_spec()
    one_condition["entry_rules"]["conditions"] = one_condition["entry_rules"]["conditions"][:1]
    assert spec_to_rule_set(one_condition) is None

    weird_direction = _champion_spec(direction="SIDEWAYS")
    assert spec_to_rule_set(weird_direction) is None


def _frame(n: int = 220):
    ts = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    close = 60000 + np.cumsum(np.sin(np.arange(n)) * 120)
    candles = [
        {"timestamp": str(t), "open": c - 20, "high": c + 80, "low": c - 80, "close": c, "volume": 100.0}
        for t, c in zip(ts, close)
    ]
    return build_backtest_frame(
        candles,
        funding_loader=lambda: pd.DataFrame(),
        liquidation_loader=lambda: pd.DataFrame(),
    )


def test_seeds_join_the_population_and_can_win() -> None:
    """With a fitness that only rewards the seeded family, a survivor must be it."""
    seed_rule_set = spec_to_rule_set(_champion_spec())
    seeded_features = {c["feature"] for c in seed_rule_set["conditions"]}

    def fitness(rule_set) -> float:
        features = {c["feature"] for c in rule_set["conditions"]}
        return 10.0 if features == seeded_features else -1.0

    mined = mine_rule_sets(
        _frame(), fitness=fitness, seed=1, population=8, generations=2,
        seed_population=[seed_rule_set],
    )
    assert mined["seeded"] == 1
    families = [s["family"] for s in mined["survivors"]]
    assert "mined:adx+close+rsi" in families


def test_duplicate_seeds_are_deduped_and_capped() -> None:
    seed_rule_set = spec_to_rule_set(_champion_spec())
    mined = mine_rule_sets(
        _frame(), fitness=lambda rs: 0.0, seed=1, population=4, generations=1,
        seed_population=[seed_rule_set] * 10,
    )
    assert mined["seeded"] == 1


def test_no_seed_population_reports_zero_and_still_mines() -> None:
    mined = mine_rule_sets(_frame(), fitness=lambda rs: 0.0, seed=1, population=6, generations=1)
    assert mined["seeded"] == 0
    assert mined["search_evaluations"] > 0
