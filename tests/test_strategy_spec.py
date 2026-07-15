"""Phase S1 contract foundation: StrategySpec, hash, allowed features, registry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.strategy_factory import (
    Direction,
    SpecParseError,
    StrategySpec,
    StrategyStatus,
    compute_strategy_rule_hash,
)
from crypto_ai_system.strategy_factory import allowed_feature_registry as afr
from crypto_ai_system.strategy_factory.strategy_registry import (
    get_strategy_record,
    load_strategy_records,
    persist_strategy_spec,
)


def _valid_spec_dict(**overrides):
    base = {
        "schema_version": "strategy_spec.v1",
        "strategy_id": "S006",
        "strategy_version": "1.0",
        "generation_id": "GEN-002",
        "strategy_family": "trend_pullback",
        "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"],
        "timeframe": "1h",
        "direction": "long_short",
        "entry_rules": {
            "operator": "AND",
            "conditions": [
                {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
                {"feature": "price_distance_ma20", "comparison": "<=", "value": 0.5},
                {"feature": "market_regime", "comparison": "==", "value": "TREND_UP"},
            ],
        },
        "exit_rules": {
            "stop_model": "atr",
            "stop_atr": 1.2,
            "target_atr": 2.4,
            "max_holding_bars": 24,
        },
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
        "created_by": "StrategyGenerationAgent",
    }
    base.update(overrides)
    return base


def _valid_spec_dict_simple(**overrides):
    """A minimal well-formed spec without the tricky categorical condition."""
    d = _valid_spec_dict(**overrides)
    d["entry_rules"] = {
        "operator": "AND",
        "conditions": [
            {"feature": "ma20", "comparison": ">", "value_from": "ma50"},
            {"feature": "rsi", "comparison": "<", "value": 30},
        ],
    }
    return d


# -- parsing / structure ------------------------------------------------------

def test_valid_spec_parses():
    spec = StrategySpec.from_dict(_valid_spec_dict_simple())
    assert spec.strategy_id == "S006"
    assert spec.direction is Direction.LONG_SHORT
    assert spec.status is StrategyStatus.GENERATED
    assert len(spec.entry_rules.conditions) == 2
    assert spec.exit_rules.max_holding_bars == 24


def test_round_trip_to_dict_is_stable():
    spec = StrategySpec.from_dict(_valid_spec_dict_simple())
    again = StrategySpec.from_dict(spec.to_dict())
    assert again.strategy_rule_hash == spec.strategy_rule_hash
    assert again.to_dict() == spec.to_dict()


def test_categorical_string_value_condition_parses_and_round_trips():
    # market_regime == "TREND_UP" — a categorical label value, not a number.
    spec = StrategySpec.from_dict(_valid_spec_dict())
    cond = spec.entry_rules.conditions[-1]
    assert cond.feature == "market_regime"
    assert cond.value == "TREND_UP"
    assert StrategySpec.from_dict(spec.to_dict()).strategy_rule_hash == spec.strategy_rule_hash


def test_boolean_value_rejected():
    d = _valid_spec_dict_simple()
    d["entry_rules"]["conditions"] = [{"feature": "long_liquidation_spike", "comparison": "==", "value": True}]
    with pytest.raises(SpecParseError, match="boolean"):
        StrategySpec.from_dict(d)


def test_missing_required_field_raises():
    d = _valid_spec_dict_simple()
    del d["strategy_id"]
    with pytest.raises(SpecParseError, match="strategy_id"):
        StrategySpec.from_dict(d)


def test_unknown_timeframe_raises():
    with pytest.raises(SpecParseError, match="timeframe"):
        StrategySpec.from_dict(_valid_spec_dict_simple(timeframe="7m"))


def test_bad_direction_raises():
    with pytest.raises(SpecParseError, match="direction"):
        StrategySpec.from_dict(_valid_spec_dict_simple(direction="sideways"))


def test_empty_symbol_scope_raises():
    with pytest.raises(SpecParseError, match="symbol_scope"):
        StrategySpec.from_dict(_valid_spec_dict_simple(symbol_scope=[]))


def test_empty_conditions_raises():
    d = _valid_spec_dict_simple()
    d["entry_rules"] = {"operator": "AND", "conditions": []}
    with pytest.raises(SpecParseError, match="conditions"):
        StrategySpec.from_dict(d)


def test_bad_entry_operator_raises():
    d = _valid_spec_dict_simple()
    d["entry_rules"]["operator"] = "XOR"
    with pytest.raises(SpecParseError, match="operator"):
        StrategySpec.from_dict(d)


def test_condition_with_both_value_and_value_from_raises():
    d = _valid_spec_dict_simple()
    d["entry_rules"]["conditions"] = [
        {"feature": "ma20", "comparison": ">", "value": 1, "value_from": "ma50"}
    ]
    with pytest.raises(SpecParseError, match="both"):
        StrategySpec.from_dict(d)


def test_condition_with_neither_value_raises():
    d = _valid_spec_dict_simple()
    d["entry_rules"]["conditions"] = [{"feature": "ma20", "comparison": ">"}]
    with pytest.raises(SpecParseError, match="neither"):
        StrategySpec.from_dict(d)


def test_missing_stop_loss_raises():
    d = _valid_spec_dict_simple()
    d["exit_rules"] = {"stop_model": "atr", "target_atr": 2.0, "max_holding_bars": 10}
    with pytest.raises(SpecParseError, match="stop_atr"):
        StrategySpec.from_dict(d)


def test_zero_max_holding_raises():
    d = _valid_spec_dict_simple()
    d["exit_rules"]["max_holding_bars"] = 0
    with pytest.raises(SpecParseError, match="max_holding_bars"):
        StrategySpec.from_dict(d)


def test_unknown_stop_model_raises():
    d = _valid_spec_dict_simple()
    d["exit_rules"]["stop_model"] = "trailing"
    with pytest.raises(SpecParseError, match="stop_model"):
        StrategySpec.from_dict(d)


# -- safety invariant ---------------------------------------------------------

def test_cannot_grant_order_authority():
    with pytest.raises(SpecParseError, match="can_submit_orders"):
        StrategySpec.from_dict(_valid_spec_dict_simple(can_submit_orders=True))
    with pytest.raises(SpecParseError, match="can_modify_runtime"):
        StrategySpec.from_dict(_valid_spec_dict_simple(can_modify_runtime=True))


def test_authority_flags_always_false_in_output():
    spec = StrategySpec.from_dict(_valid_spec_dict_simple())
    assert spec.can_submit_orders is False
    assert spec.can_modify_runtime is False
    assert spec.to_dict()["can_submit_orders"] is False
    assert spec.to_dict()["can_modify_runtime"] is False


# -- hash ---------------------------------------------------------------------

def test_hash_is_deterministic():
    a = StrategySpec.from_dict(_valid_spec_dict_simple())
    b = StrategySpec.from_dict(_valid_spec_dict_simple())
    assert a.strategy_rule_hash == b.strategy_rule_hash
    assert a.strategy_rule_hash == compute_strategy_rule_hash(a)


def test_hash_ignores_identity_metadata():
    a = StrategySpec.from_dict(_valid_spec_dict_simple(strategy_id="S001", strategy_version="1.0"))
    b = StrategySpec.from_dict(_valid_spec_dict_simple(strategy_id="S999", strategy_version="3.7",
                                                       generation_id="GEN-050"))
    # Same rules, different identity -> same rule hash (duplicate detection).
    assert a.strategy_rule_hash == b.strategy_rule_hash


def test_hash_changes_with_rules():
    a = StrategySpec.from_dict(_valid_spec_dict_simple())
    d = _valid_spec_dict_simple()
    d["exit_rules"]["target_atr"] = 3.0
    b = StrategySpec.from_dict(d)
    assert a.strategy_rule_hash != b.strategy_rule_hash


def test_status_change_preserves_rule_hash():
    spec = StrategySpec.from_dict(_valid_spec_dict_simple())
    promoted = spec.with_status(StrategyStatus.PAPER_ACTIVE)
    assert promoted.status is StrategyStatus.PAPER_ACTIVE
    assert promoted.strategy_rule_hash == spec.strategy_rule_hash


def test_tampered_hash_rejected():
    d = _valid_spec_dict_simple()
    d["strategy_rule_hash"] = "sha256:deadbeef"
    with pytest.raises(SpecParseError, match="strategy_rule_hash"):
        StrategySpec.from_dict(d)


# -- allowed feature registry -------------------------------------------------

def test_real_feature_keys_allowed():
    for name in ("ma20", "ma50", "rsi", "atr", "adx", "funding_zscore", "oi_change_4h_pct"):
        assert afr.is_allowed_feature(name), name
        assert afr.is_numeric_feature(name)


def test_illustrative_names_not_in_registry():
    # The directive's example names differ from the real feature columns; the
    # registry tracks the real ones so a spec cannot reference a phantom feature.
    for phantom in ("sma20", "volume_ratio", "pullback_distance_pct"):
        assert not afr.is_allowed_feature(phantom), phantom


def test_categorical_feature_values():
    assert afr.is_categorical_feature("market_regime")
    assert "TREND_UP" in afr.allowed_values_for("market_regime")
    assert afr.allowed_comparisons_for("market_regime") == afr.CATEGORICAL_COMPARISONS
    assert afr.allowed_comparisons_for("ma20") == afr.NUMERIC_COMPARISONS
    assert afr.allowed_comparisons_for("nonexistent") == frozenset()


def test_referenced_features_collects_value_from():
    spec = StrategySpec.from_dict(_valid_spec_dict_simple())
    refs = spec.referenced_features()
    assert "ma20" in refs and "ma50" in refs and "rsi" in refs


def test_feature_fingerprint_stable():
    assert afr.feature_registry_fingerprint() == afr.feature_registry_fingerprint()


# -- registry persistence -----------------------------------------------------

def test_persist_and_get_roundtrip(tmp_path):
    registry = tmp_path / "strategy_candidate_registry.jsonl"
    spec = StrategySpec.from_dict(_valid_spec_dict_simple(strategy_id="S042"))
    record = persist_strategy_spec(spec, registry)
    assert record["strategy_id"] == "S042"
    assert record["strategy_rule_hash"] == spec.strategy_rule_hash

    fetched = get_strategy_record("S042", registry)
    assert fetched is not None
    # The stored spec round-trips back into an identical spec.
    restored = StrategySpec.from_dict(fetched["strategy_spec"])
    assert restored.strategy_rule_hash == spec.strategy_rule_hash


def test_registry_is_append_only(tmp_path):
    registry = tmp_path / "strategy_candidate_registry.jsonl"
    persist_strategy_spec(StrategySpec.from_dict(_valid_spec_dict_simple(strategy_id="S001")), registry)
    persist_strategy_spec(StrategySpec.from_dict(_valid_spec_dict_simple(strategy_id="S002")), registry)
    records = load_strategy_records(registry)
    assert [r["strategy_id"] for r in records] == ["S001", "S002"]


def test_get_unknown_returns_none(tmp_path):
    registry = tmp_path / "strategy_candidate_registry.jsonl"
    persist_strategy_spec(StrategySpec.from_dict(_valid_spec_dict_simple()), registry)
    assert get_strategy_record("NOPE", registry) is None
