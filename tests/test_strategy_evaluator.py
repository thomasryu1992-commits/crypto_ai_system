"""Phase S4a: StrategySpec entry-rule evaluator tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.strategy_factory.strategy_evaluator import evaluate_spec, evaluate_condition


def _spec(conditions, *, operator="AND", direction="long"):
    return StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1",
        "strategy_id": "S001",
        "strategy_version": "1.0",
        "generation_id": "GEN-001",
        "strategy_family": "trend_pullback",
        "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"],
        "timeframe": "1h",
        "direction": direction,
        "entry_rules": {"operator": operator, "conditions": conditions},
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.2, "target_atr": 2.4, "max_holding_bars": 24},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    })


# -- single conditions --------------------------------------------------------

def test_numeric_constant_comparison():
    spec = _spec([{"feature": "rsi", "comparison": "<=", "value": 30}])
    assert evaluate_spec(spec, {"rsi": 25}).matched is True
    assert evaluate_spec(spec, {"rsi": 35}).matched is False


def test_feature_to_feature_comparison():
    spec = _spec([{"feature": "ma20", "comparison": ">", "value_from": "ma50"}])
    assert evaluate_spec(spec, {"ma20": 101, "ma50": 100}).matched is True
    assert evaluate_spec(spec, {"ma20": 99, "ma50": 100}).matched is False


def test_categorical_equality():
    spec = _spec([{"feature": "market_regime", "comparison": "==", "value": "RANGE"}])
    assert evaluate_spec(spec, {"market_regime": "RANGE"}).matched is True
    assert evaluate_spec(spec, {"market_regime": "TREND_UP"}).matched is False


def test_categorical_inequality():
    spec = _spec([{"feature": "market_regime", "comparison": "!=", "value": "RANGE"}])
    assert evaluate_spec(spec, {"market_regime": "TREND_UP"}).matched is True
    assert evaluate_spec(spec, {"market_regime": "RANGE"}).matched is False


# -- fail-closed on missing / NaN --------------------------------------------

def test_missing_feature_is_indeterminate():
    spec = _spec([{"feature": "rsi", "comparison": "<=", "value": 30}])
    assert evaluate_condition(spec.entry_rules.conditions[0], {}) is None
    assert evaluate_spec(spec, {}).matched is False


def test_nan_feature_is_indeterminate():
    spec = _spec([{"feature": "rsi", "comparison": "<=", "value": 30}])
    assert evaluate_spec(spec, {"rsi": float("nan")}).matched is False


def test_missing_value_from_is_indeterminate():
    spec = _spec([{"feature": "ma20", "comparison": ">", "value_from": "ma50"}])
    assert evaluate_spec(spec, {"ma20": 100}).matched is False


# -- AND / OR combination -----------------------------------------------------

def test_and_requires_all_true():
    spec = _spec([
        {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
        {"feature": "rsi", "comparison": "<=", "value": 55},
    ], operator="AND")
    assert evaluate_spec(spec, {"ma20": 101, "ma50": 100, "rsi": 50}).matched is True
    assert evaluate_spec(spec, {"ma20": 101, "ma50": 100, "rsi": 60}).matched is False


def test_or_requires_any_true():
    spec = _spec([
        {"feature": "rsi", "comparison": "<=", "value": 20},
        {"feature": "adx", "comparison": ">=", "value": 30},
    ], operator="OR")
    assert evaluate_spec(spec, {"rsi": 50, "adx": 35}).matched is True
    assert evaluate_spec(spec, {"rsi": 50, "adx": 10}).matched is False


def test_and_with_one_indeterminate_does_not_match():
    spec = _spec([
        {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
        {"feature": "rsi", "comparison": "<=", "value": 55},
    ], operator="AND")
    # rsi missing -> indeterminate -> AND fails closed even though ma condition holds.
    assert evaluate_spec(spec, {"ma20": 101, "ma50": 100}).matched is False


def test_or_ignores_indeterminate():
    spec = _spec([
        {"feature": "rsi", "comparison": "<=", "value": 20},   # true
        {"feature": "adx", "comparison": ">=", "value": 30},   # missing -> None
    ], operator="OR")
    assert evaluate_spec(spec, {"rsi": 15}).matched is True


# -- direction ----------------------------------------------------------------

def test_direction_long_on_match():
    spec = _spec([{"feature": "rsi", "comparison": "<=", "value": 30}], direction="long")
    result = evaluate_spec(spec, {"rsi": 25})
    assert result.matched is True and result.direction == "LONG"


def test_direction_short_on_match():
    spec = _spec([{"feature": "rsi", "comparison": ">=", "value": 70}], direction="short")
    result = evaluate_spec(spec, {"rsi": 75})
    assert result.matched is True and result.direction == "SHORT"


def test_no_direction_when_not_matched():
    spec = _spec([{"feature": "rsi", "comparison": "<=", "value": 30}])
    assert evaluate_spec(spec, {"rsi": 90}).direction is None


# -- integration with a generated spec + feature snapshot shape ---------------

def test_evaluates_over_pandas_series_row():
    import pandas as pd

    spec = _spec([
        {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
        {"feature": "market_regime", "comparison": "==", "value": "TREND_UP"},
    ])
    frame = pd.DataFrame([
        {"ma20": 105, "ma50": 100, "market_regime": "TREND_UP"},
        {"ma20": 98, "ma50": 100, "market_regime": "TREND_UP"},
    ])
    assert evaluate_spec(spec, frame.iloc[0]).matched is True
    assert evaluate_spec(spec, frame.iloc[1]).matched is False
