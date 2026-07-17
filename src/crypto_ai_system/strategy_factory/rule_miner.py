"""Rule miner: discover entry rules from the data instead of a human template.

The template library caps the search at shapes a person already thought of — 480
candidates converged on breakout because breakout was the only shape in the
library that fit the market. This module searches the combination space itself:
conditions are drawn from the allowed-feature registry, thresholds from the
TRAINING slice's own percentiles, and an evolutionary loop breeds rule sets the
library never contained.

A wider search is a stronger overfitting machine, so the honesty rules tighten
rather than relax:

* **Train/holdout split.** Thresholds, fitness, selection, crossover — every
  choice the search makes — see only the first ``train_fraction`` of the frame.
  The final holdout slice is untouched by the search; the runner gates on it.
* **Bounded structure.** 2–4 conditions per rule set, exits from the same
  bounded space as the templates, features only from the runtime-available
  registry. A mined spec is the same declarative data as a template spec — the
  S3 validator, the shared evaluator, and the backtest/live parity contract all
  apply unchanged, and ``can_submit_orders`` stays structurally false.
* **Auditable search size.** Every produced spec records how many candidates the
  search evaluated (``search_evaluations``) — the denominator a reviewer needs to
  discount a survivor's in-sample performance.

Pure over its inputs: no IO, no network, no runtime state. Randomness comes only
from the caller's seed.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from crypto_ai_system.strategy_factory.allowed_feature_registry import (
    CATEGORICAL_FEATURES,
    is_runtime_available_feature,
)
from crypto_ai_system.strategy_factory.strategy_spec import SCHEMA_VERSION, StrategySpec

RULE_MINER_VERSION = "rule_miner.v1"

# Price-scale columns may be compared to EACH OTHER (close > ma20 is structure);
# comparing an oscillator to a price would be dimensional nonsense the validator
# cannot see. Everything else takes a literal threshold from the train slice.
PRICE_SCALE_FEATURES: tuple[str, ...] = (
    "close", "open", "high", "low",
    "ma20", "ma50", "ema20", "ema50",
    "bb_upper", "bb_lower", "mark_price", "index_price",
)

# Oscillator/ratio features that take percentile thresholds. Raw untyped columns
# (volume, atr in absolute terms) are excluded: their scale drifts over years,
# so a fixed literal learned in 2020 means something else in 2026.
THRESHOLD_FEATURES: tuple[str, ...] = (
    "rsi", "adx", "atr_pct_of_price", "atr_percentile",
    "price_distance_ma20", "macd_hist", "bb_percent_b", "bb_width_pct",
    "bb_width_percentile", "roc_4", "roc_12", "volume_zscore",
    "funding_rate", "funding_zscore",
    "htf_4h_ema_gap_pct", "htf_1d_ema_gap_pct", "htf_alignment_score",
    "mark_index_basis_bps", "mark_last_basis_bps",
)

_THRESHOLD_QUANTILES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
_NUMERIC_COMPARISONS = (">", ">=", "<", "<=")

MIN_CONDITIONS = 2
MAX_CONDITIONS = 4

# The same bounded exit space the template library uses; the validator's ranges
# stay the outer bound.
EXIT_SPACE = {
    "stop_atr": (0.8, 2.0),
    "target_atr": (1.6, 8.0),
    "max_holding_bars": (12, 48),
}


def mined_family(conditions: Sequence[Mapping[str, Any]]) -> str:
    """Family name = the feature combination, so the pool's per-family diversity
    cap dedupes near-identical mined rules instead of letting one lucky feature
    pair occupy every slot."""
    features = sorted({str(c["feature"]) for c in conditions})
    return "mined:" + "+".join(features)


def build_condition_pool(train: pd.DataFrame) -> list[dict[str, Any]]:
    """Every condition the miner may draw from, thresholds from ``train`` only.

    A condition over a feature the frame does not carry (or that is all-NaN in
    the train slice) is excluded — the evaluator would only ever score it
    indeterminate, wasting search budget on rules that cannot fire.
    """
    pool: list[dict[str, Any]] = []

    for feature in THRESHOLD_FEATURES:
        if not is_runtime_available_feature(feature) or feature not in train.columns:
            continue
        series = pd.to_numeric(train[feature], errors="coerce").dropna()
        if len(series) < 50:
            continue
        for q in _THRESHOLD_QUANTILES:
            value = float(series.quantile(q))
            for comparison in _NUMERIC_COMPARISONS:
                pool.append({"feature": feature, "comparison": comparison, "value": round(value, 6)})

    available_price = [
        f for f in PRICE_SCALE_FEATURES
        if is_runtime_available_feature(f) and f in train.columns
    ]
    for left in available_price:
        for right in available_price:
            if left == right:
                continue
            for comparison in (">", "<"):
                pool.append({"feature": left, "comparison": comparison, "value_from": right})

    for feature, labels in CATEGORICAL_FEATURES.items():
        if not is_runtime_available_feature(feature) or feature not in train.columns:
            continue
        seen = {str(v) for v in train[feature].dropna().unique()}
        for label in sorted(labels & seen):
            pool.append({"feature": feature, "comparison": "==", "value": label})

    return pool


def _sample_exits(rng: random.Random) -> dict[str, Any]:
    lo, hi = EXIT_SPACE["stop_atr"]
    stop = round(rng.uniform(lo, hi), 4)
    lo, hi = EXIT_SPACE["target_atr"]
    # Reward:risk must clear the validator's floor of 1.0.
    target = round(rng.uniform(max(lo, stop), hi), 4)
    lo, hi = EXIT_SPACE["max_holding_bars"]
    return {
        "stop_model": "atr",
        "stop_atr": stop,
        "target_atr": target,
        "max_holding_bars": rng.randint(int(lo), int(hi)),
    }


def _dedupe_features(conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One condition per feature: 'rsi<30 AND rsi<70' is one fitted number
    pretending to be two."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for cond in conditions:
        if cond["feature"] in seen:
            continue
        seen.add(cond["feature"])
        out.append(cond)
    return out


def random_rule_set(pool: Sequence[Mapping[str, Any]], rng: random.Random) -> dict[str, Any]:
    """One random candidate: direction, 2-4 conditions, bounded exits."""
    n = rng.randint(MIN_CONDITIONS, MAX_CONDITIONS)
    conditions = _dedupe_features([dict(rng.choice(pool)) for _ in range(n)])
    while len(conditions) < MIN_CONDITIONS:
        conditions = _dedupe_features(conditions + [dict(rng.choice(pool))])
    return {
        "direction": rng.choice(("long", "short")),
        "conditions": conditions,
        "exit_rules": _sample_exits(rng),
    }


def crossover(a: Mapping[str, Any], b: Mapping[str, Any], rng: random.Random) -> dict[str, Any]:
    """Child = conditions drawn from both parents, exits from one of them."""
    merged = [dict(c) for c in (*a["conditions"], *b["conditions"])]
    rng.shuffle(merged)
    conditions = _dedupe_features(merged)[: rng.randint(MIN_CONDITIONS, MAX_CONDITIONS)]
    while len(conditions) < MIN_CONDITIONS:
        conditions = _dedupe_features(conditions + [dict(rng.choice(merged))])
    parent = a if rng.random() < 0.5 else b
    return {
        "direction": parent["direction"],
        "conditions": conditions,
        "exit_rules": dict(parent["exit_rules"]),
    }


def mutate(
    rule_set: Mapping[str, Any], pool: Sequence[Mapping[str, Any]], rng: random.Random
) -> dict[str, Any]:
    """Replace one condition, or resample the exits, or flip the direction."""
    out = {
        "direction": rule_set["direction"],
        "conditions": [dict(c) for c in rule_set["conditions"]],
        "exit_rules": dict(rule_set["exit_rules"]),
    }
    roll = rng.random()
    if roll < 0.6 and out["conditions"]:
        out["conditions"][rng.randrange(len(out["conditions"]))] = dict(rng.choice(pool))
        out["conditions"] = _dedupe_features(out["conditions"])
        while len(out["conditions"]) < MIN_CONDITIONS:
            out["conditions"] = _dedupe_features(out["conditions"] + [dict(rng.choice(pool))])
    elif roll < 0.85:
        out["exit_rules"] = _sample_exits(rng)
    else:
        out["direction"] = "short" if out["direction"] == "long" else "long"
    return out


def rule_set_to_spec_dict(
    rule_set: Mapping[str, Any],
    *,
    strategy_id: str,
    generation_id: str,
    symbol: str,
    timeframe: str,
    search_evaluations: int,
) -> dict[str, Any]:
    """The same declarative spec shape the template generator emits."""
    conditions = [dict(c) for c in rule_set["conditions"]]
    spec = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "strategy_version": "1.0",
        "generation_id": generation_id,
        "strategy_family": mined_family(conditions),
        "status": "GENERATED",
        "symbol_scope": [symbol],
        "timeframe": timeframe,
        "direction": rule_set["direction"],
        "entry_rules": {"operator": "AND", "conditions": conditions},
        "exit_rules": dict(rule_set["exit_rules"]),
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
        "created_by": "RuleMinerAgent",
        # The audit denominator: a survivor of 600 evaluations carries more
        # selection bias than a survivor of 6.
        "search_evaluations": int(search_evaluations),
    }
    # from_dict computes (and thereafter enforces) the canonical rule hash.
    spec["strategy_rule_hash"] = StrategySpec.from_dict(spec).strategy_rule_hash
    return spec


def split_train_holdout(frame: pd.DataFrame, train_fraction: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological split. The holdout is the FUTURE relative to the train
    slice — the search must never see it, in thresholds or in fitness."""
    cut = int(len(frame) * train_fraction)
    return frame.iloc[:cut].reset_index(drop=True), frame.iloc[cut:].reset_index(drop=True)


def mine_rule_sets(
    train: pd.DataFrame,
    *,
    fitness: Callable[[Mapping[str, Any]], float],
    seed: int,
    population: int = 40,
    generations: int = 12,
    elite_fraction: float = 0.25,
    top_n: int = 5,
) -> dict[str, Any]:
    """Evolve rule sets against ``fitness`` (which must only see ``train``).

    Returns the ``top_n`` distinct-by-family survivors and the total number of
    fitness evaluations performed (the selection-bias denominator).
    """
    rng = random.Random(seed)
    pool = build_condition_pool(train)
    if not pool:
        return {"survivors": [], "search_evaluations": 0, "condition_pool_size": 0}

    scored: dict[str, tuple[float, dict[str, Any]]] = {}
    evaluations = 0

    def _key(rs: Mapping[str, Any]) -> str:
        conds = sorted(
            (c["feature"], c["comparison"], str(c.get("value", c.get("value_from"))))
            for c in rs["conditions"]
        )
        return f"{rs['direction']}|{conds}|{sorted(rs['exit_rules'].items())}"

    def _evaluate(rs: dict[str, Any]) -> float:
        nonlocal evaluations
        key = _key(rs)
        if key in scored:
            return scored[key][0]
        evaluations += 1
        score = float(fitness(rs))
        scored[key] = (score, rs)
        return score

    current = [random_rule_set(pool, rng) for _ in range(population)]
    for _ in range(max(1, generations)):
        ranked = sorted(current, key=_evaluate, reverse=True)
        elite = ranked[: max(2, int(population * elite_fraction))]
        next_gen = list(elite)
        while len(next_gen) < population:
            if rng.random() < 0.7:
                child = crossover(rng.choice(elite), rng.choice(elite), rng)
            else:
                child = random_rule_set(pool, rng)
            if rng.random() < 0.5:
                child = mutate(child, pool, rng)
            next_gen.append(child)
        current = next_gen

    # Final ranking over everything ever scored; one survivor per family so the
    # top-N are N different ideas, not N jitters of the best one.
    final = sorted(scored.values(), key=lambda item: item[0], reverse=True)
    survivors: list[dict[str, Any]] = []
    families: set[str] = set()
    for score, rs in final:
        family = mined_family(rs["conditions"])
        if family in families:
            continue
        families.add(family)
        survivors.append({"rule_set": rs, "train_fitness": round(score, 6), "family": family})
        if len(survivors) >= top_n:
            break

    return {
        "rule_miner_version": RULE_MINER_VERSION,
        "survivors": survivors,
        "search_evaluations": evaluations,
        "condition_pool_size": len(pool),
    }
