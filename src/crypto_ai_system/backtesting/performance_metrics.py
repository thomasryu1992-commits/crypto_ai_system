"""Phase S4d: performance metrics over a trade ledger.

Turns the S4c ledger into the R-based summary the champion selector (S5) scores
on. Everything is in R so strategies of different notional are comparable. Ratio
metrics that are undefined for the given sample (win rate with no trades, profit
factor with no losing trades, Sharpe with <2 trades) return ``None`` rather than
a misleading zero or infinity — the selector decides how to treat an undefined
metric together with sample size.

Pure: a list of trade dicts in, a metrics dict out. Multi-window aggregates
(walk-forward, parameter stability) live in S4e.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

_MIN_FOR_DISPERSION = 2


def _mean(xs: Sequence[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _pstdev(xs: Sequence[float]) -> float | None:
    if len(xs) < _MIN_FOR_DISPERSION:
        return None
    mu = sum(xs) / len(xs)
    var = sum((x - mu) ** 2 for x in xs) / len(xs)
    return math.sqrt(var)


def _max_drawdown_r(r_series: Sequence[float]) -> float:
    """Largest peak-to-trough drop of the cumulative-R curve, as a magnitude."""
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for r in r_series:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return max_dd


def _regime_consistency(trades: Sequence[dict]) -> float | None:
    buckets: dict[str, list[float]] = {}
    for t in trades:
        regime = t.get("entry_regime")
        if regime is None:
            continue
        buckets.setdefault(str(regime), []).append(float(t["r_multiple"]))
    if not buckets:
        return None
    profitable = sum(1 for rs in buckets.values() if (sum(rs) / len(rs)) > 0)
    return profitable / len(buckets)


def compute_backtest_metrics(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Compute R-based performance metrics for one trade ledger."""
    trade_count = len(trades)
    if trade_count == 0:
        return {
            "trade_count": 0,
            "win_rate": None,
            "expectancy_r": None,
            "average_r": None,
            "profit_factor": None,
            "avg_win_r": None,
            "avg_loss_r": None,
            "gross_profit_r": 0.0,
            "gross_loss_r": 0.0,
            "total_net_r": 0.0,
            "max_drawdown_r": 0.0,
            "sharpe_like": None,
            "sortino_like": None,
            "fee_cost_r": 0.0,
            "slippage_cost_r": 0.0,
            "long_expectancy_r": None,
            "short_expectancy_r": None,
            "regime_consistency": None,
        }

    r = [float(t["r_multiple"]) for t in trades]
    wins = [x for x in r if x > 0]
    losses = [x for x in r if x < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    downside = [min(x, 0.0) for x in r]
    downside_dev = math.sqrt(sum(d * d for d in downside) / len(r)) if len(r) >= _MIN_FOR_DISPERSION else None
    stdev = _pstdev(r)
    mean_r = sum(r) / len(r)

    long_r = [float(t["r_multiple"]) for t in trades if t.get("side") == "LONG"]
    short_r = [float(t["r_multiple"]) for t in trades if t.get("side") == "SHORT"]

    return {
        "trade_count": trade_count,
        "win_rate": len(wins) / trade_count,
        "expectancy_r": mean_r,
        "average_r": mean_r,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "avg_win_r": _mean(wins),
        "avg_loss_r": _mean(losses),
        "gross_profit_r": gross_profit,
        "gross_loss_r": gross_loss,
        "total_net_r": sum(r),
        "max_drawdown_r": _max_drawdown_r(r),
        "sharpe_like": (mean_r / stdev) if stdev not in (None, 0.0) else None,
        "sortino_like": (mean_r / downside_dev) if downside_dev not in (None, 0.0) else None,
        "fee_cost_r": sum(float(t.get("fee_cost_r", 0.0)) for t in trades),
        "slippage_cost_r": sum(float(t.get("slippage_cost_r", 0.0)) for t in trades),
        "long_expectancy_r": _mean(long_r),
        "short_expectancy_r": _mean(short_r),
        "regime_consistency": _regime_consistency(trades),
    }
