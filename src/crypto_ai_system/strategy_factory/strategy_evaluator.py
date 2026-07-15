"""Phase S4a: evaluate a StrategySpec's entry rules against a feature row.

This is the one place that turns a declarative spec into a yes/no entry decision,
and it is shared by two callers: the backtest execution simulator (S4c) and the
runtime entry router (S7). Keeping a single evaluator guarantees a strategy
behaves identically in backtest and live — the whole point of a shared feature
source.

It is pure and fail-closed. A condition over a missing or NaN feature is
*indeterminate* (``None``), never a silent match; an ``AND`` block with any
indeterminate or false condition does not match, and an ``OR`` block matches only
on a genuine true. A strategy never enters on data it could not evaluate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crypto_ai_system.strategy_factory.strategy_spec import Direction, RuleCondition, StrategySpec

_EQUALITY_OPS = {"==", "!="}


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    direction: str | None  # "LONG" | "SHORT" when matched, else None
    condition_results: tuple[bool | None, ...]


def _cell(row: Mapping[str, Any], name: str) -> Any:
    """Fetch a feature value, normalising missing/NaN to None.

    Works for dicts and pandas Series alike (both support ``.get``/indexing).
    NaN is detected without importing numpy via the ``x != x`` identity.
    """
    try:
        value = row[name] if name in row else None
    except TypeError:
        value = row.get(name) if hasattr(row, "get") else None
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


def evaluate_condition(cond: RuleCondition, row: Mapping[str, Any]) -> bool | None:
    """Evaluate one condition. Returns None when it cannot be evaluated."""
    left = _cell(row, cond.feature)
    if left is None:
        return None

    if cond.value_from is not None:
        right: Any = _cell(row, cond.value_from)
    else:
        right = cond.value
    if right is None:
        return None

    op = cond.comparison
    if op in _EQUALITY_OPS:
        equal = left == right
        return equal if op == "==" else not equal

    # Ordering comparisons require two numbers; a string operand is indeterminate.
    if isinstance(left, str) or isinstance(right, str):
        return None
    try:
        left_f, right_f = float(left), float(right)
    except (TypeError, ValueError):
        return None
    if op == ">":
        return left_f > right_f
    if op == ">=":
        return left_f >= right_f
    if op == "<":
        return left_f < right_f
    if op == "<=":
        return left_f <= right_f
    return None


def _direction_for(spec: StrategySpec) -> str:
    if spec.direction is Direction.SHORT:
        return "SHORT"
    # LONG, and LONG_SHORT until directional rule sets exist (a single entry
    # block cannot yet express the short leg), both enter long on a match.
    return "LONG"


def evaluate_spec(spec: StrategySpec, row: Mapping[str, Any]) -> MatchResult:
    """Evaluate ``spec``'s entry rules against one feature row."""
    results = tuple(evaluate_condition(c, row) for c in spec.entry_rules.conditions)
    if spec.entry_rules.operator == "OR":
        matched = any(r is True for r in results)
    else:  # AND
        matched = all(r is True for r in results)
    direction = _direction_for(spec) if matched else None
    return MatchResult(matched=matched, direction=direction, condition_results=results)
