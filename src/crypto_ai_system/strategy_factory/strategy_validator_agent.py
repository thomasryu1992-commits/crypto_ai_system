"""Phase S3: StrategyValidationAgent — the gate before backtest.

A :class:`StrategySpec` is already structurally well-formed by the time it gets
here (``from_dict`` guarantees types and shape). This agent decides whether it is
*safe and sane enough to backtest*: every referenced feature exists, comparisons
fit the feature type, categorical values are real labels, and the risk/exit
parameters sit in bounded ranges with a positive reward:risk.

Look-ahead bias: the schema has no forward-shift operator, and the allowed
feature registry lists only point-in-time-safe columns from ``feature_store``.
So membership in the registry *is* the look-ahead guarantee — a spec cannot
express a reference to future data. ``BLOCK_UNKNOWN_FEATURE`` is therefore also
the look-ahead guard.

Pure and fail-closed: no IO, and any single failed check denies approval. This
agent never mutates the spec, submits orders, or promotes a stage.
"""

from __future__ import annotations

from typing import Any

from crypto_ai_system.strategy_factory.allowed_feature_registry import (
    allowed_comparisons_for,
    allowed_values_for,
    feature_registry_fingerprint,
    is_allowed_feature,
    is_categorical_feature,
    is_numeric_feature,
)
from crypto_ai_system.strategy_factory.strategy_spec import SCHEMA_VERSION, StrategySpec
from crypto_ai_system.utils.audit import stable_id

# Bounded parameter ranges. A strategy outside these is rejected, not clamped —
# the generator's job is to stay inside them.
STOP_ATR_RANGE = (0.3, 5.0)
TARGET_ATR_RANGE = (0.5, 10.0)
MAX_HOLDING_BARS_RANGE = (1, 500)
MAX_RISK_PER_TRADE_R = 2.0
MIN_REWARD_RISK = 1.0
MAX_ENTRY_CONDITIONS = 8

BLOCK_SCHEMA_VERSION = "BLOCK_SCHEMA_VERSION"
BLOCK_UNKNOWN_FEATURE = "BLOCK_UNKNOWN_FEATURE"
BLOCK_INVALID_COMPARISON = "BLOCK_INVALID_COMPARISON"
BLOCK_INVALID_FEATURE_VALUE = "BLOCK_INVALID_FEATURE_VALUE"
BLOCK_VALUE_FROM_NOT_NUMERIC = "BLOCK_VALUE_FROM_NOT_NUMERIC"
BLOCK_TOO_MANY_CONDITIONS = "BLOCK_TOO_MANY_CONDITIONS"
BLOCK_MISSING_STOP_LOSS = "BLOCK_MISSING_STOP_LOSS"
BLOCK_UNBOUNDED_HOLDING = "BLOCK_UNBOUNDED_HOLDING"
BLOCK_INVALID_PARAMETER_RANGE = "BLOCK_INVALID_PARAMETER_RANGE"
BLOCK_INVALID_RISK_REWARD = "BLOCK_INVALID_RISK_REWARD"


def _in_range(value: float, bounds: tuple[float, float]) -> bool:
    return bounds[0] <= value <= bounds[1]


def _validate_conditions(spec: StrategySpec) -> list[str]:
    reasons: list[str] = []
    conditions = spec.entry_rules.conditions

    if len(conditions) > MAX_ENTRY_CONDITIONS:
        reasons.append(BLOCK_TOO_MANY_CONDITIONS)

    for cond in conditions:
        if not is_allowed_feature(cond.feature):
            reasons.append(BLOCK_UNKNOWN_FEATURE)
            # Without a known feature type the remaining checks are meaningless.
            continue

        if cond.comparison not in allowed_comparisons_for(cond.feature):
            reasons.append(BLOCK_INVALID_COMPARISON)

        if cond.value_from is not None:
            # Comparing a feature to another feature only makes sense numerically.
            if not is_allowed_feature(cond.value_from):
                reasons.append(BLOCK_UNKNOWN_FEATURE)
            elif not (is_numeric_feature(cond.feature) and is_numeric_feature(cond.value_from)):
                reasons.append(BLOCK_VALUE_FROM_NOT_NUMERIC)
        else:
            # Constant value: type must match the feature.
            if is_numeric_feature(cond.feature):
                if not isinstance(cond.value, (int, float)):
                    reasons.append(BLOCK_INVALID_FEATURE_VALUE)
            elif is_categorical_feature(cond.feature):
                labels = allowed_values_for(cond.feature) or frozenset()
                if not isinstance(cond.value, str) or cond.value not in labels:
                    reasons.append(BLOCK_INVALID_FEATURE_VALUE)

    return reasons


def _validate_exit_and_risk(spec: StrategySpec) -> list[str]:
    reasons: list[str] = []
    exit_rules = spec.exit_rules

    if exit_rules.stop_atr <= 0:
        reasons.append(BLOCK_MISSING_STOP_LOSS)
    elif not _in_range(exit_rules.stop_atr, STOP_ATR_RANGE):
        reasons.append(BLOCK_INVALID_PARAMETER_RANGE)

    if not _in_range(exit_rules.target_atr, TARGET_ATR_RANGE):
        reasons.append(BLOCK_INVALID_PARAMETER_RANGE)

    # Positive reward:risk — a target below the stop is a structurally losing edge.
    if exit_rules.stop_atr > 0 and exit_rules.target_atr / exit_rules.stop_atr < MIN_REWARD_RISK:
        reasons.append(BLOCK_INVALID_RISK_REWARD)

    if not _in_range(exit_rules.max_holding_bars, MAX_HOLDING_BARS_RANGE):
        reasons.append(BLOCK_UNBOUNDED_HOLDING)

    risk = spec.risk_constraints.max_risk_per_trade_R
    if risk <= 0 or risk > MAX_RISK_PER_TRADE_R:
        reasons.append(BLOCK_INVALID_PARAMETER_RANGE)

    return reasons


def validate_strategy(spec: StrategySpec) -> dict[str, Any]:
    """Return an approval verdict for ``spec``. Fails closed on any violation."""
    reasons: list[str] = []

    if spec.schema_version != SCHEMA_VERSION:
        reasons.append(BLOCK_SCHEMA_VERSION)

    reasons.extend(_validate_conditions(spec))
    reasons.extend(_validate_exit_and_risk(spec))

    # Stable order, no duplicates, for deterministic evidence.
    block_reasons = sorted(set(reasons))

    verdict: dict[str, Any] = {
        "strategy_id": spec.strategy_id,
        "strategy_rule_hash": spec.strategy_rule_hash,
        "approved_for_backtest": not block_reasons,
        "block_reasons": block_reasons,
        "feature_registry_fingerprint": feature_registry_fingerprint(),
    }
    verdict["strategy_validation_id"] = stable_id("strategy_validation", verdict, 24)
    return verdict
