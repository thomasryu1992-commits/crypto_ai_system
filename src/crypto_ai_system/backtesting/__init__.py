"""Strategy Factory backtesting (Phase S4).

A self-contained engine that evaluates a :class:`StrategySpec` on historical
data under a fixed cost model and reports R-based performance. Distinct from the
legacy ``crypto_ai_system.backtest`` package: strategies here define their own
single-stop / single-target / max-holding exit, evaluated bar-by-bar via the
shared spec evaluator, so backtest and live share one signal source.
"""

from crypto_ai_system.backtesting.cost_model import CostModel
from crypto_ai_system.backtesting.execution_simulator import simulate_strategy
from crypto_ai_system.backtesting.performance_metrics import compute_backtest_metrics
from crypto_ai_system.backtesting.walk_forward import run_walk_forward
from crypto_ai_system.backtesting.regime_evaluator import regime_breakdown
from crypto_ai_system.backtesting.backtest_agent import (
    AbsoluteGate,
    evaluate_absolute_gate,
    run_backtest_agent,
)
from crypto_ai_system.backtesting.champion_selector_agent import (
    ChampionScoreWeights,
    select_batch_champion,
)

__all__ = [
    "CostModel",
    "simulate_strategy",
    "compute_backtest_metrics",
    "run_walk_forward",
    "regime_breakdown",
    "AbsoluteGate",
    "evaluate_absolute_gate",
    "run_backtest_agent",
    "ChampionScoreWeights",
    "select_batch_champion",
]
