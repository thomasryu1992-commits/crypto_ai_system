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


def route_entries(
    pool: Mapping[str, Any],
    feature_row: Mapping[str, Any],
    *,
    now: str | None = None,
    feature_rows: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate every routable strategy against its feature row and route an entry.

    ``feature_rows`` maps a spec timeframe to the latest feature row built on that
    timeframe; a spec whose timeframe has no (or an empty) row is recorded as
    unevaluable and cannot match — a 1d strategy must never be judged on a 1h row.
    Without ``feature_rows`` every spec uses ``feature_row`` (single-timeframe
    pools, the original behavior).

    Returns a router result carrying the strategy id chain. ``order_candidate_count``
    is 0 (no match or conflict) or 1 (a single entry candidate, however many
    strategies agreed).
    """
    entries = _routable_entries(pool)
    evaluations: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []

    for entry in entries:
        spec = StrategySpec.from_dict(entry["strategy_spec"])
        row = feature_rows.get(spec.timeframe) if feature_rows is not None else feature_row
        if not row:
            evaluations.append({
                "strategy_id": entry.get("strategy_id"),
                "matched": False,
                "direction": None,
                "unevaluable": f"no feature row for timeframe {spec.timeframe}",
            })
            continue
        result = evaluate_spec(spec, row)
        evaluations.append({
            "strategy_id": entry.get("strategy_id"),
            "matched": result.matched,
            "direction": result.direction,
            "timeframe": spec.timeframe,
        })
        if result.matched:
            matches.append({
                "strategy_id": entry.get("strategy_id"),
                "strategy_rule_hash": entry.get("strategy_rule_hash"),
                "direction": result.direction,
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

    directions = {m["direction"] for m in matches}
    if len(directions) > 1:
        return {
            **base,
            "status": STATUS_BLOCKED,
            "block_reason": BLOCK_DIRECTION_CONFLICT,
            "conflicting_directions": sorted(d for d in directions if d),
        }

    direction = directions.pop()
    # Primary strategy: strongest champion score, then id for determinism.
    primary = max(
        matches,
        key=lambda m: (m["champion_score"] if m["champion_score"] is not None else -math.inf, m["strategy_id"] or ""),
    )
    return {
        **base,
        "status": STATUS_ENTRY_CANDIDATE,
        "direction": direction,
        "order_candidate_count": 1,  # one order regardless of how many agreed
        "primary_strategy_id": primary["strategy_id"],
        "primary_strategy_rule_hash": primary["strategy_rule_hash"],
    }
