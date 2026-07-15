"""Phase S9: per-strategy rolling performance.

Aggregates a strategy's *attributed* outcomes (S8) into rolling and lifetime
metrics, so the lifecycle agent (S10) can tell a decaying strategy from a healthy
one. It reuses the same R-based metric function as the backtest (S4d), so a live
rolling window and a backtest window are measured identically.

Windows are trade-count based (rolling 20/30/50/100) plus lifetime. A rolling-N
window is only *full* once the strategy has N outcomes; the lifecycle agent
requires a full window before it will escalate, so a young strategy is never
degraded on thin data.

Pure: a strategy's outcome list in, a performance report out.
"""

from __future__ import annotations

from typing import Any, Sequence

from crypto_ai_system.backtesting.performance_metrics import compute_backtest_metrics
from crypto_ai_system.utils.audit import stable_id, utc_now_canonical

DEFAULT_WINDOWS = (20, 30, 50, 100)


def compute_strategy_performance(
    strategy_id: str,
    outcomes: Sequence[dict[str, Any]],
    *,
    windows: Sequence[int] = DEFAULT_WINDOWS,
    backtest_win_rate: float | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Build the performance report for one strategy.

    ``outcomes`` are the strategy's attributed outcomes in chronological order
    (oldest first) — typically ``outcomes_for_strategy(...)`` from S8.
    """
    ordered = list(outcomes)
    lifetime = compute_backtest_metrics(ordered)

    report: dict[str, Any] = {
        "strategy_id": strategy_id,
        "trade_count": len(ordered),
        "lifetime": lifetime,
    }
    for w in windows:
        window_trades = ordered[-w:]
        metrics = compute_backtest_metrics(window_trades)
        metrics["window_full"] = len(window_trades) >= w
        report[f"rolling_{w}"] = metrics

    report["backtest_win_rate"] = backtest_win_rate
    live_win_rate = lifetime.get("win_rate")
    if backtest_win_rate is not None and live_win_rate is not None:
        report["live_vs_backtest_win_rate_drop"] = round(backtest_win_rate - live_win_rate, 6)
    else:
        report["live_vs_backtest_win_rate_drop"] = None

    identity = {k: v for k, v in report.items()}
    report["strategy_performance_report_id"] = stable_id("strategy_performance", identity, 24)
    report["created_at_utc"] = now or utc_now_canonical()
    return report
