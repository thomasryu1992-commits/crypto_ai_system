"""Phase S4e: walk-forward evaluation of a fixed-parameter strategy.

A generated strategy carries fixed parameters (there is no in-sample fitting to
optimise), so walk-forward here means: does the same strategy hold up across
consecutive slices of time? The series is cut into contiguous windows, the
strategy is simulated independently on each, and two robustness signals are
derived — how often a window is profitable (``walk_forward_pass_rate``) and how
consistent the per-window edge is (``temporal_stability``). A strategy that only
works in one stretch of history is exposed here.

``temporal_stability`` is a first-pass heuristic (dispersion of per-window
expectancy). Parameter-perturbation stability is a heavier future addition.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from crypto_ai_system.backtesting.cost_model import CostModel
from crypto_ai_system.backtesting.execution_simulator import simulate_strategy
from crypto_ai_system.backtesting.performance_metrics import compute_backtest_metrics
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec

_MIN_BARS_PER_WINDOW = 2


def split_windows(n: int, k: int) -> list[tuple[int, int]]:
    """Cut ``n`` rows into up to ``k`` contiguous, non-overlapping [start, end) slices."""
    if n <= 0 or k <= 0:
        return []
    k = min(k, n)
    base, rem = divmod(n, k)
    windows: list[tuple[int, int]] = []
    start = 0
    for w in range(k):
        size = base + (1 if w < rem else 0)
        windows.append((start, start + size))
        start += size
    return windows


def _temporal_stability(expectancies: list[float]) -> float | None:
    """0..1 consistency score from per-window expectancy dispersion.

    High when windows agree and the mean edge is positive; 0 when the mean edge
    is non-positive. None when fewer than two windows actually traded.
    """
    if len(expectancies) < 2:
        return None
    mean_e = sum(expectancies) / len(expectancies)
    if mean_e <= 0:
        return 0.0
    var = sum((x - mean_e) ** 2 for x in expectancies) / len(expectancies)
    cv = math.sqrt(var) / abs(mean_e)
    return 1.0 / (1.0 + cv)


def run_walk_forward(
    spec: StrategySpec,
    frame: pd.DataFrame,
    *,
    cost: CostModel | None = None,
    n_windows: int = 4,
    equity: float = 10000.0,
    risk_pct: float = 0.01,
    min_trades_per_window: int = 1,
) -> dict[str, Any]:
    """Simulate ``spec`` on each contiguous window and summarise robustness."""
    cost = cost or CostModel()
    n = len(frame)
    windows: list[dict[str, Any]] = []
    traded_expectancies: list[float] = []
    passes = 0
    windows_with_trades = 0

    for idx, (start, end) in enumerate(split_windows(n, n_windows)):
        window_frame = frame.iloc[start:end]
        if len(window_frame) < _MIN_BARS_PER_WINDOW:
            windows.append({"index": idx, "start": start, "end": end, "trade_count": 0,
                            "expectancy_r": None, "total_net_r": 0.0})
            continue
        result = simulate_strategy(spec, window_frame, cost=cost, equity=equity, risk_pct=risk_pct)
        metrics = compute_backtest_metrics(result["trades"])
        windows.append({
            "index": idx, "start": start, "end": end,
            "trade_count": metrics["trade_count"],
            "expectancy_r": metrics["expectancy_r"],
            "total_net_r": metrics["total_net_r"],
        })
        if metrics["trade_count"] >= min_trades_per_window and metrics["expectancy_r"] is not None:
            windows_with_trades += 1
            traded_expectancies.append(metrics["expectancy_r"])
            if metrics["expectancy_r"] > 0:
                passes += 1

    return {
        "n_windows_requested": n_windows,
        "windows": windows,
        "windows_with_trades": windows_with_trades,
        "walk_forward_pass_rate": (passes / windows_with_trades) if windows_with_trades else None,
        "temporal_stability": _temporal_stability(traded_expectancies),
    }
