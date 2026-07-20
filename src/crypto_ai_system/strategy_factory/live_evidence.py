"""Live-evidence scoring: real paper results as graded selection pressure.

Design: ``docs/architecture/design_live_performance_selection_pressure.md``.

The shrunk live-blended score (SLS) blends a strategy's REAL attributed
outcomes into its backtest admission score, weighted by information content:

    w   = n / (n + K)                    # K pseudo-trades, default 20
    SLS = w * live_expectancy + (1 - w) * backtest_score

``n = 0`` reproduces the backtest score exactly, so every consumer is a
mathematical no-op until real data accumulates — the rollout property the
design requires. Influence grows with the sample, never ahead of it.

Pure over injected rows; the one IO helper wraps the S8 registry loader.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: K — how many live trades it takes for live evidence to carry half the
#: weight. Overridable via settings STRATEGY_LIVE_PRESSURE_PSEUDO_TRADES.
DEFAULT_PSEUDO_TRADES = 20


def resolve_pseudo_trades() -> int:
    import config.settings as settings

    value = int(getattr(settings, "STRATEGY_LIVE_PRESSURE_PSEUDO_TRADES", DEFAULT_PSEUDO_TRADES) or 0)
    return value if value > 0 else DEFAULT_PSEUDO_TRADES


def live_stats_by_strategy(
    attributed_rows: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[int, float]]:
    """``strategy_id -> (n, mean r_multiple)`` from S8 attributed outcomes.

    Every appended S8 row IS a closed, strategy-owned outcome (the recorder
    refuses positions without a strategy_id and only fires on close), so the
    only filtering needed is a usable r_multiple. Supporting appearances are
    already excluded at attribution time — credit belongs to the primary.
    """
    sums: dict[str, tuple[int, float]] = {}
    for row in attributed_rows:
        strategy_id = row.get("strategy_id")
        r = row.get("r_multiple")
        if not strategy_id or r is None:
            continue
        try:
            r = float(r)
        except (TypeError, ValueError):
            continue
        n, total = sums.get(str(strategy_id), (0, 0.0))
        sums[str(strategy_id)] = (n + 1, total + r)
    return {sid: (n, total / n) for sid, (n, total) in sums.items() if n > 0}


def shrunk_live_blended_score(
    backtest_score: float | None,
    live_n: int,
    live_expectancy: float | None,
    *,
    pseudo_trades: int = DEFAULT_PSEUDO_TRADES,
) -> float | None:
    """SLS for one strategy. ``None`` backtest score stays ``None`` (the pool
    treats a scoreless entry as weakest/unrankable — semantics unchanged)."""
    if backtest_score is None:
        return None
    if live_n <= 0 or live_expectancy is None:
        return float(backtest_score)
    k = pseudo_trades if pseudo_trades > 0 else DEFAULT_PSEUDO_TRADES
    w = live_n / (live_n + k)
    return w * float(live_expectancy) + (1.0 - w) * float(backtest_score)


def sls_for_entry(
    entry: Mapping[str, Any],
    live_stats: Mapping[str, tuple[int, float]] | None,
    *,
    pseudo_trades: int = DEFAULT_PSEUDO_TRADES,
) -> dict[str, Any]:
    """Comparison-time SLS view of one pool entry (champion_score untouched).

    Returns ``{score, live_n, live_expectancy, pseudo_trades}`` — the audit
    fields every SLS-based decision must record so a displacement is
    explainable from its own row.
    """
    strategy_id = str(entry.get("strategy_id") or "")
    n, live_exp = (live_stats or {}).get(strategy_id, (0, None))
    return {
        "score": shrunk_live_blended_score(
            entry.get("champion_score"), n, live_exp, pseudo_trades=pseudo_trades
        ),
        "live_n": n,
        "live_expectancy": live_exp,
        "pseudo_trades": pseudo_trades,
    }


def load_live_stats(registry_file: str) -> dict[str, tuple[int, float]]:
    """IO wrapper: live stats from the S8 attributed-outcome registry file.

    Best-effort by design: live pressure is an OPTIMIZATION of pool ordering,
    never a gate — an unreadable registry means no pressure (n=0 everywhere),
    not a blocked factory run. (Contrast risk_guard, where unreadable history
    must fail closed; nothing here authorizes trading.)
    """
    try:
        from crypto_ai_system.strategy_factory.strategy_outcome_attribution import (
            load_attributed_outcomes,
        )

        return live_stats_by_strategy(load_attributed_outcomes(registry_file))
    except Exception:  # noqa: BLE001 - pressure is optional; absence is the safe default
        return {}
