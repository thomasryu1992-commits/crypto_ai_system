"""Phase S4e: per-regime performance breakdown.

A strategy's edge often lives in one market regime and bleeds in another. This
splits a trade ledger by the entry-time ``market_regime`` and computes full
metrics for each bucket, so the champion selector can see *where* an edge comes
from rather than trusting a blended average.
"""

from __future__ import annotations

from typing import Any, Sequence

from crypto_ai_system.backtesting.performance_metrics import compute_backtest_metrics


def regime_breakdown(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Metrics per entry regime plus a summary of profitable regimes."""
    buckets: dict[str, list[dict]] = {}
    for trade in trades:
        regime = trade.get("entry_regime")
        buckets.setdefault(str(regime) if regime is not None else "UNKNOWN", []).append(trade)

    by_regime = {regime: compute_backtest_metrics(rows) for regime, rows in buckets.items()}
    profitable = [
        regime for regime, m in by_regime.items()
        if m["expectancy_r"] is not None and m["expectancy_r"] > 0
    ]
    return {
        "by_regime": by_regime,
        "regimes_traded": sorted(by_regime.keys()),
        "profitable_regimes": sorted(profitable),
        "profitable_regime_count": len(profitable),
    }
