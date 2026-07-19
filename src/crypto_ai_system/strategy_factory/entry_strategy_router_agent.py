"""Phase S7: EntryStrategyRouterAgent — evaluate the active pool as one gate.

Every PAPER_ACTIVE strategy is evaluated on the *same* FeatureSnapshot (via the
shared S4a evaluator). Active strategies combine with OR: any match produces an
entry candidate. But a match is only an *opportunity* — it is still just a
candidate that the common research permission and PreOrderRiskGate must approve
downstream (directive §2.2). The router submits nothing and mutates nothing.

Two firm rules:

* **One order, not N.** Several strategies matching the same direction still
  yield a single entry candidate — the position is never doubled because two
  strategies agree (§6.9). The agreeing strategies are all recorded on the
  candidate's id chain for attribution (S8).
* **Opposite directions fail closed.** If any matched strategy wants LONG and
  another SHORT, the router blocks with ``BLOCK_STRATEGY_DIRECTION_CONFLICT``
  rather than guessing (§6.10). Regime-priority resolution is a future addition.

Pure over its inputs; no IO, no order submission, no pool mutation.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from crypto_ai_system.strategy_factory.active_strategy_pool import OCCUPYING_STATUSES, POOL_VERSION
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.strategy_factory.strategy_evaluator import evaluate_spec

STATUS_ENTRY_CANDIDATE = "ENTRY_CANDIDATE"
STATUS_NO_ENTRY = "NO_ENTRY"
STATUS_BLOCKED = "BLOCKED"

BLOCK_DIRECTION_CONFLICT = "BLOCK_STRATEGY_DIRECTION_CONFLICT"


def _routable_entries(pool: Mapping[str, Any]) -> list[dict]:
    """Entries allowed to open a new position: those holding a slot
    (PAPER_ACTIVE / WARNING / PROBATION). Suspended and archived strategies are
    excluded — a suspended strategy must not create an OrderIntent (§19), and a
    flagged strategy keeps trading so its rolling window can recover or escalate."""
    return [
        e for e in (pool.get("active_strategies") or [])
        if e.get("status") in OCCUPYING_STATUSES and e.get("strategy_spec")
    ]


def feature_row_key(symbol: str, timeframe: str) -> str:
    """The key ``feature_rows`` is indexed by: one row per (symbol, timeframe)."""
    return f"{symbol}|{timeframe}"


def _spec_symbol(spec: StrategySpec) -> str:
    return str(spec.symbol_scope[0]) if spec.symbol_scope else ""


def route_entries(
    pool: Mapping[str, Any],
    feature_row: Mapping[str, Any],
    *,
    now: str | None = None,
    feature_rows: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate every routable strategy against its feature row and route an entry.

    ``feature_rows`` maps ``feature_row_key(symbol, timeframe)`` to the latest
    feature row built on that pair; a spec whose pair has no (or an empty) row is
    recorded as unevaluable and cannot match — an ETH daily strategy must never be
    judged on a BTC hourly row. Without ``feature_rows`` every spec uses
    ``feature_row`` (single-symbol single-timeframe pools, the original behavior).

    Direction conflicts are per symbol — BTC LONG and ETH SHORT coexist; a LONG
    and a SHORT on the *same* symbol fail closed, and that symbol's matches are
    excluded while the rest of the pool still routes. Still one order per cycle:
    the strongest surviving champion wins.
    """
    entries = _routable_entries(pool)
    evaluations: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []

    for entry in entries:
        spec = StrategySpec.from_dict(entry["strategy_spec"])
        symbol = _spec_symbol(spec)
        if feature_rows is not None:
            row = feature_rows.get(feature_row_key(symbol, spec.timeframe))
        else:
            row = feature_row
        if not row:
            evaluations.append({
                "strategy_id": entry.get("strategy_id"),
                "matched": False,
                "direction": None,
                "unevaluable": f"no feature row for {symbol} {spec.timeframe}",
            })
            continue
        result = evaluate_spec(spec, row)
        evaluations.append({
            "strategy_id": entry.get("strategy_id"),
            "matched": result.matched,
            "direction": result.direction,
            "symbol": symbol,
            "timeframe": spec.timeframe,
        })
        if result.matched:
            matches.append({
                "strategy_id": entry.get("strategy_id"),
                "strategy_rule_hash": entry.get("strategy_rule_hash"),
                "direction": result.direction,
                "symbol": symbol,
                "champion_score": entry.get("champion_score"),
            })

    base = {
        "strategy_pool_version": pool.get("pool_version", POOL_VERSION),
        "strategies_evaluated": len(entries),
        "evaluations": evaluations,
        "matched_strategy_ids": sorted(m["strategy_id"] for m in matches if m["strategy_id"] is not None),
        "matched_strategy_count": len(matches),
        "created_at_utc": now,
        # The router only proposes; nothing here grants execution.
        "order_candidate_count": 0,
        "direction": None,
    }

    if not matches:
        return {**base, "status": STATUS_NO_ENTRY}

    # Conflicts are judged within a symbol; a conflicted symbol's matches are
    # removed rather than blocking every other symbol's honest candidate.
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for m in matches:
        by_symbol.setdefault(m["symbol"], []).append(m)
    conflicted = {
        sym: sorted({m["direction"] for m in group if m["direction"]})
        for sym, group in by_symbol.items()
        if len({m["direction"] for m in group}) > 1
    }
    survivors = [m for m in matches if m["symbol"] not in conflicted]

    if conflicted and not survivors:
        return {
            **base,
            "status": STATUS_BLOCKED,
            "block_reason": BLOCK_DIRECTION_CONFLICT,
            "conflicting_directions": sorted(d for ds in conflicted.values() for d in ds),
            "conflicted_symbols": sorted(conflicted),
        }

    # Ranked candidates: strongest champion score first, id for determinism.
    # The primary is the head; multibook entry (M3) walks the rest, one book
    # each. The router still only proposes — nothing here grants execution.
    # reverse sort on (score, id) so the head is exactly what max() picked
    # before - highest score, then highest id on a tie.
    ranked = sorted(
        survivors,
        key=lambda m: (
            m["champion_score"] if m["champion_score"] is not None else -math.inf,
            m["strategy_id"] or "",
        ),
        reverse=True,
    )
    primary = ranked[0]
    return {
        **base,
        "status": STATUS_ENTRY_CANDIDATE,
        "direction": primary["direction"],
        "symbol": primary["symbol"],
        "order_candidate_count": 1,  # one order per single-book cycle regardless of how many agreed
        "primary_strategy_id": primary["strategy_id"],
        "primary_strategy_rule_hash": primary["strategy_rule_hash"],
        "ranked_candidates": [
            {
                "strategy_id": m["strategy_id"],
                "strategy_rule_hash": m["strategy_rule_hash"],
                "direction": m["direction"],
                "symbol": m["symbol"],
                "champion_score": m["champion_score"],
            }
            for m in ranked
        ],
        "conflicted_symbols": sorted(conflicted) if conflicted else [],
    }
