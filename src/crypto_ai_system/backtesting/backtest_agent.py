"""Phase S4e: the BacktestAgent — evaluate one StrategySpec end to end.

Ties S4a–S4d together into a single evidence record for a strategy: a full-period
simulation, a walk-forward robustness pass, a per-regime breakdown, and an
*absolute* qualification gate. ``qualified`` here answers "is this strategy good
enough on its own merits to be considered?" — the directive's absolute gate. The
*relative* choice of one champion per batch is a separate step (S5); a strategy
that fails the absolute gate is never a champion regardless of its batch rank.

Deterministic: the same spec, frame, and settings yield the same
``backtest_run_id`` and metrics. No IO — persistence is the caller's concern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from crypto_ai_system.backtesting.cost_model import CostModel
from crypto_ai_system.backtesting.execution_simulator import simulate_strategy
from crypto_ai_system.backtesting.performance_metrics import compute_backtest_metrics
from crypto_ai_system.backtesting.regime_evaluator import regime_breakdown
from crypto_ai_system.backtesting.walk_forward import run_walk_forward
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.utils.audit import stable_id, utc_now_canonical


@dataclass(frozen=True)
class AbsoluteGate:
    """Absolute performance thresholds (directive §6.7). A strategy must clear
    all of them to qualify; batch ranking (S5) only chooses among those that do.
    Defaults follow the directive; callers tune them for smaller samples."""

    min_trade_count: int = 100
    min_expectancy_r: float = 0.10
    min_profit_factor: float = 1.15
    min_walk_forward_pass_rate: float = 0.70
    max_drawdown_r: float = 10.0
    min_temporal_stability: float = 0.30


def evaluate_absolute_gate(
    metrics: dict[str, Any], walk_forward: dict[str, Any], gate: AbsoluteGate
) -> list[str]:
    """Return the list of failed gate checks (empty means qualified)."""
    failures: list[str] = []

    if metrics["trade_count"] < gate.min_trade_count:
        failures.append("trade_count_below_min")

    expectancy = metrics["expectancy_r"]
    if expectancy is None or expectancy < gate.min_expectancy_r:
        failures.append("expectancy_below_min")
    # Net R is already fee/slippage-adjusted; a non-positive edge cannot qualify.
    if expectancy is None or expectancy <= 0:
        failures.append("fee_adjusted_expectancy_not_positive")

    profit_factor = metrics["profit_factor"]
    if profit_factor is None or profit_factor < gate.min_profit_factor:
        failures.append("profit_factor_below_min")

    if metrics["max_drawdown_r"] > gate.max_drawdown_r:
        failures.append("drawdown_exceeds_max")

    wf_rate = walk_forward["walk_forward_pass_rate"]
    if wf_rate is None or wf_rate < gate.min_walk_forward_pass_rate:
        failures.append("walk_forward_pass_rate_below_min")

    stability = walk_forward["temporal_stability"]
    if stability is None or stability < gate.min_temporal_stability:
        failures.append("temporal_stability_below_min")

    return sorted(set(failures))


def run_backtest_agent(
    spec: StrategySpec,
    frame: pd.DataFrame,
    *,
    generation_id: str | None = None,
    cost: CostModel | None = None,
    equity: float = 10000.0,
    risk_pct: float = 0.01,
    n_windows: int = 4,
    gate: AbsoluteGate | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Produce the full backtest evidence record for ``spec`` over ``frame``."""
    cost = cost or CostModel()
    gate = gate or AbsoluteGate()

    result = simulate_strategy(spec, frame, cost=cost, equity=equity, risk_pct=risk_pct)
    metrics = compute_backtest_metrics(result["trades"])
    walk_forward = run_walk_forward(
        spec, frame, cost=cost, n_windows=n_windows, equity=equity, risk_pct=risk_pct
    )
    regimes = regime_breakdown(result["trades"])
    gate_failures = evaluate_absolute_gate(metrics, walk_forward, gate)

    record: dict[str, Any] = {
        "strategy_id": spec.strategy_id,
        "strategy_rule_hash": spec.strategy_rule_hash,
        "generation_id": generation_id if generation_id is not None else spec.generation_id,
        "bars": result["bars"],
        "cost_model": {"taker_fee_bps": cost.taker_fee_bps, "slippage_bps": cost.slippage_bps},
        "equity": equity,
        "risk_pct": risk_pct,
        "metrics": metrics,
        "walk_forward": walk_forward,
        "regime_breakdown": regimes,
        "absolute_gate": {
            "min_trade_count": gate.min_trade_count,
            "min_expectancy_r": gate.min_expectancy_r,
            "min_profit_factor": gate.min_profit_factor,
            "min_walk_forward_pass_rate": gate.min_walk_forward_pass_rate,
            "max_drawdown_r": gate.max_drawdown_r,
            "min_temporal_stability": gate.min_temporal_stability,
        },
        "gate_failures": gate_failures,
        "qualified": not gate_failures,
        "created_at_utc": now or utc_now_canonical(),
    }
    # Identity excludes the timestamp so re-running is reproducible.
    identity = {k: v for k, v in record.items() if k != "created_at_utc"}
    record["backtest_run_id"] = stable_id("backtest_run", identity, 24)
    return record
