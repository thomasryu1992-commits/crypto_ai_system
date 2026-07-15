"""Phase S10: strategy lifecycle — auto-suspend a decaying strategy.

Reads a strategy's performance report (S9) and its current status, and decides
the next status on the ladder ACTIVE → WARNING → PROBATION → SUSPENDED →
ARCHIVED. The directive's thresholds (§6.16) drive it, and — crucially — a
strategy is never discarded on win rate alone: expectancy and profit factor over
a *full* rolling window carry the decision, with sample size gating escalation.

Auto-degradation (including auto-suspend) is permitted; auto-*reactivation* is
not. SUSPENDED and ARCHIVED are terminal here: recovering them requires a manual
re-backtest → paper re-validate → approval path (§8), so this agent leaves them
untouched. WARNING and PROBATION are reversible — a strategy that recovers its
edge returns toward PAPER_ACTIVE.

The pure decision function takes the running consecutive-failure count and
returns the updated count; the caller persists it. Suspend needs 2 consecutive
failures, archive 3, so a single bad window never suspends outright.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crypto_ai_system.strategy_factory.strategy_spec import StrategyStatus
from crypto_ai_system.utils.audit import stable_id, utc_now_canonical

_RANK = {
    StrategyStatus.PAPER_ACTIVE.value: 0,
    StrategyStatus.WARNING.value: 1,
    StrategyStatus.PROBATION.value: 2,
    StrategyStatus.SUSPENDED.value: 3,
    StrategyStatus.ARCHIVED.value: 4,
}
_TERMINAL = {StrategyStatus.SUSPENDED.value, StrategyStatus.ARCHIVED.value}


@dataclass(frozen=True)
class LifecycleThresholds:
    warn_window: int = 20
    warn_expectancy_r: float = 0.0
    warn_profit_factor: float = 1.0

    probation_window: int = 30
    probation_expectancy_r: float = -0.05
    probation_profit_factor: float = 0.9
    probation_win_rate_drop: float = 0.15

    suspend_window: int = 50
    suspend_expectancy_r: float = 0.0
    suspend_profit_factor: float = 0.9
    suspend_consecutive: int = 2

    archive_min_trades: int = 100
    archive_expectancy_r: float = 0.0
    archive_consecutive: int = 3


def _full_window(performance: Mapping[str, Any], window: int) -> dict | None:
    metrics = performance.get(f"rolling_{window}")
    if not metrics or not metrics.get("window_full"):
        return None
    return metrics


def _lt(value: Any, bound: float) -> bool:
    return value is not None and value < bound


def _le(value: Any, bound: float) -> bool:
    return value is not None and value <= bound


def evaluate_lifecycle(
    current_status: str,
    performance: Mapping[str, Any],
    *,
    consecutive_failures: int = 0,
    thresholds: LifecycleThresholds | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Decide the next lifecycle status. Pure; returns a decision record."""
    t = thresholds or LifecycleThresholds()
    strategy_id = performance.get("strategy_id")
    reasons: list[str] = []

    m_warn = _full_window(performance, t.warn_window)
    warn = m_warn is not None and (
        _lt(m_warn.get("expectancy_r"), t.warn_expectancy_r)
        or _lt(m_warn.get("profit_factor"), t.warn_profit_factor)
    )
    if warn:
        reasons.append(f"rolling_{t.warn_window}_below_warn_thresholds")

    m_prob = _full_window(performance, t.probation_window)
    probation = m_prob is not None and (
        _le(m_prob.get("expectancy_r"), t.probation_expectancy_r)
        or _lt(m_prob.get("profit_factor"), t.probation_profit_factor)
    )
    win_rate_drop = performance.get("live_vs_backtest_win_rate_drop")
    if win_rate_drop is not None and win_rate_drop > t.probation_win_rate_drop:
        probation = True
        reasons.append("live_win_rate_dropped_below_backtest")
    if probation and f"rolling_{t.probation_window}_below_warn_thresholds" not in reasons:
        reasons.append(f"rolling_{t.probation_window}_below_probation_thresholds")

    m_susp = _full_window(performance, t.suspend_window)
    suspend_metrics = m_susp is not None and (
        _lt(m_susp.get("expectancy_r"), t.suspend_expectancy_r)
        and _lt(m_susp.get("profit_factor"), t.suspend_profit_factor)
    )

    lifetime = performance.get("lifetime") or {}
    archive_metrics = (
        lifetime.get("trade_count", 0) >= t.archive_min_trades
        and _lt(lifetime.get("expectancy_r"), t.archive_expectancy_r)
    )

    # A degradation this evaluation extends the consecutive-failure streak.
    failure = bool(warn or probation)
    new_consecutive = consecutive_failures + 1 if failure else 0

    if current_status in _TERMINAL:
        new_status = current_status
        reasons = ["terminal_state_requires_manual_reactivation"]
    elif archive_metrics and new_consecutive >= t.archive_consecutive:
        new_status = StrategyStatus.ARCHIVED.value
        reasons.append("archive_conditions_met")
    elif suspend_metrics and new_consecutive >= t.suspend_consecutive:
        new_status = StrategyStatus.SUSPENDED.value
        reasons.append("suspend_conditions_met")
    elif probation:
        new_status = StrategyStatus.PROBATION.value
    elif warn:
        new_status = StrategyStatus.WARNING.value
    else:
        new_status = StrategyStatus.PAPER_ACTIVE.value
        if current_status in (StrategyStatus.WARNING.value, StrategyStatus.PROBATION.value):
            reasons.append("recovered_to_active")

    prev_rank = _RANK.get(current_status, 0)
    new_rank = _RANK.get(new_status, 0)
    decision: dict[str, Any] = {
        "strategy_id": strategy_id,
        "previous_status": current_status,
        "new_status": new_status,
        "status_changed": new_status != current_status,
        "is_escalation": new_rank > prev_rank,
        "is_recovery": new_rank < prev_rank,
        "consecutive_failures": new_consecutive,
        "new_entry_blocked": new_status in _TERMINAL,
        "requires_manual_reactivation": new_status in _TERMINAL,
        "reasons": reasons,
    }
    decision["strategy_lifecycle_decision_id"] = stable_id("strategy_lifecycle_decision", decision, 24)
    decision["created_at_utc"] = now or utc_now_canonical()
    return decision
