"""Phase S3: StrategyValidationAgent gate tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.strategy_factory import strategy_validator_agent as sv
from crypto_ai_system.strategy_factory.strategy_validator_agent import validate_strategy


def _spec(**entry_exit):
    base = {
        "schema_version": "strategy_spec.v1",
        "strategy_id": "S001",
        "strategy_version": "1.0",
        "generation_id": "GEN-001",
        "strategy_family": "trend_pullback",
        "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"],
        "timeframe": "1h",
        "direction": "long",
        "entry_rules": entry_exit.get("entry_rules", {
            "operator": "AND",
            "conditions": [
                {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
                {"feature": "rsi", "comparison": "<=", "value": 55},
            ],
        }),
        "exit_rules": entry_exit.get("exit_rules", {
            "stop_model": "atr", "stop_atr": 1.2, "target_atr": 2.4, "max_holding_bars": 24,
        }),
        "risk_constraints": entry_exit.get("risk_constraints", {"max_risk_per_trade_R": 1.0}),
    }
    return StrategySpec.from_dict(base)


def test_valid_spec_approved():
    verdict = validate_strategy(_spec())
    assert verdict["approved_for_backtest"] is True, verdict["block_reasons"]
    assert verdict["block_reasons"] == []
    assert verdict["strategy_validation_id"]
    assert verdict["feature_registry_fingerprint"]


def test_categorical_condition_approved():
    verdict = validate_strategy(_spec(entry_rules={
        "operator": "AND",
        "conditions": [
            {"feature": "rsi", "comparison": "<=", "value": 30},
            {"feature": "market_regime", "comparison": "==", "value": "RANGE"},
        ],
    }))
    assert verdict["approved_for_backtest"] is True, verdict["block_reasons"]


def test_unknown_feature_blocked():
    verdict = validate_strategy(_spec(entry_rules={
        "operator": "AND",
        "conditions": [{"feature": "volume_ratio", "comparison": ">", "value": 1.2}],
    }))
    assert sv.BLOCK_UNKNOWN_FEATURE in verdict["block_reasons"]
    assert verdict["approved_for_backtest"] is False


def test_invalid_categorical_label_blocked():
    verdict = validate_strategy(_spec(entry_rules={
        "operator": "AND",
        "conditions": [{"feature": "market_regime", "comparison": "==", "value": "MOONSHOT"}],
    }))
    assert sv.BLOCK_INVALID_FEATURE_VALUE in verdict["block_reasons"]


def test_numeric_feature_with_string_value_blocked():
    verdict = validate_strategy(_spec(entry_rules={
        "operator": "AND",
        "conditions": [{"feature": "rsi", "comparison": "<=", "value": "low"}],
    }))
    assert sv.BLOCK_INVALID_FEATURE_VALUE in verdict["block_reasons"]


def test_ordering_comparison_on_categorical_blocked():
    verdict = validate_strategy(_spec(entry_rules={
        "operator": "AND",
        "conditions": [{"feature": "market_regime", "comparison": ">", "value": "RANGE"}],
    }))
    assert sv.BLOCK_INVALID_COMPARISON in verdict["block_reasons"]


def test_value_from_categorical_blocked():
    verdict = validate_strategy(_spec(entry_rules={
        "operator": "AND",
        "conditions": [{"feature": "ma20", "comparison": ">", "value_from": "market_regime"}],
    }))
    assert sv.BLOCK_VALUE_FROM_NOT_NUMERIC in verdict["block_reasons"]


def test_stop_atr_out_of_range_blocked():
    verdict = validate_strategy(_spec(exit_rules={
        "stop_model": "atr", "stop_atr": 9.0, "target_atr": 12.0, "max_holding_bars": 24,
    }))
    assert sv.BLOCK_INVALID_PARAMETER_RANGE in verdict["block_reasons"]


def test_negative_risk_reward_blocked():
    verdict = validate_strategy(_spec(exit_rules={
        "stop_model": "atr", "stop_atr": 2.0, "target_atr": 1.0, "max_holding_bars": 24,
    }))
    assert sv.BLOCK_INVALID_RISK_REWARD in verdict["block_reasons"]


def test_unbounded_holding_blocked():
    verdict = validate_strategy(_spec(exit_rules={
        "stop_model": "atr", "stop_atr": 1.2, "target_atr": 2.4, "max_holding_bars": 5000,
    }))
    assert sv.BLOCK_UNBOUNDED_HOLDING in verdict["block_reasons"]


def test_excess_risk_per_trade_blocked():
    verdict = validate_strategy(_spec(risk_constraints={"max_risk_per_trade_R": 5.0}))
    assert sv.BLOCK_INVALID_PARAMETER_RANGE in verdict["block_reasons"]


def test_too_many_conditions_blocked():
    conditions = [{"feature": "rsi", "comparison": "<=", "value": 50 + i} for i in range(9)]
    verdict = validate_strategy(_spec(entry_rules={"operator": "AND", "conditions": conditions}))
    assert sv.BLOCK_TOO_MANY_CONDITIONS in verdict["block_reasons"]


def test_block_reasons_deduped_and_sorted():
    verdict = validate_strategy(_spec(entry_rules={
        "operator": "AND",
        "conditions": [
            {"feature": "ghost1", "comparison": ">", "value": 1},
            {"feature": "ghost2", "comparison": ">", "value": 2},
        ],
    }))
    # Two unknown features collapse to a single reason, sorted.
    assert verdict["block_reasons"] == sorted(set(verdict["block_reasons"]))
    assert verdict["block_reasons"].count(sv.BLOCK_UNKNOWN_FEATURE) == 1
