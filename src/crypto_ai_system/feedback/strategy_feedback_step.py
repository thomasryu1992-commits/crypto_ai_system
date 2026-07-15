"""Increment 3: close the factory loop on real paper trades.

Two halves:

* ``record_strategy_outcome`` — when a *strategy-driven* paper position closes,
  turn it into an S8-attributed outcome (strategy id + chain + result R) and
  append it to the attributed-outcome registry. Research-driven closes carry no
  strategy id and are skipped.
* ``run_strategy_lifecycle_feedback`` — recompute each active strategy's rolling
  performance (S9) from those attributed outcomes and apply the lifecycle
  decision (S10) to the pool: a decayed strategy is moved WARNING → PROBATION →
  SUSPENDED, at which point the router stops routing it. This is the one loop the
  directive lets run automatically; testnet/live promotion and reactivation stay
  manual.

Pure-ish orchestration over registries and the pool file; no orders, no runtime
settings mutated.
"""

from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.feedback.strategy_lifecycle_agent import evaluate_lifecycle
from crypto_ai_system.feedback.strategy_performance_agent import compute_strategy_performance
from crypto_ai_system.registry.base_registry import append_registry_record
from crypto_ai_system.strategy_factory.active_strategy_pool import OCCUPYING_STATUSES, load_pool, save_pool
from crypto_ai_system.strategy_factory.strategy_outcome_attribution import (
    append_attributed_outcome,
    attribute_outcome,
    load_attributed_outcomes,
    outcomes_for_strategy,
)

STRATEGY_LIFECYCLE_REGISTRY_NAME = "strategy_lifecycle_registry"


def record_strategy_outcome(
    position: Mapping[str, Any],
    settlement: Mapping[str, Any],
    *,
    registry_file: str,
    now: str | None = None,
) -> dict[str, Any] | None:
    """Append an attributed outcome for a closed strategy-driven position.

    Returns the record, or None when the position was not strategy-driven.
    """
    strategy_id = position.get("strategy_id")
    if not strategy_id:
        return None

    attribution = {
        "strategy_id": strategy_id,
        "strategy_version": position.get("strategy_version"),
        "strategy_generation_id": position.get("strategy_generation_id"),
        "strategy_rule_hash": position.get("strategy_rule_hash"),
        "supporting_strategy_ids": position.get("supporting_strategy_ids") or [],
        "matched_strategy_ids": position.get("matched_strategy_ids") or [strategy_id],
        "strategy_pool_version": position.get("strategy_pool_version"),
        "cycle_id": position.get("cycle_id"),
        "strategy_entry_evaluation_id": position.get("strategy_entry_evaluation_id"),
    }
    chain = {
        "trade_plan_id": position.get("trade_plan_id") or position.get("decision_id"),
        "risk_gate_id": position.get("risk_gate_id"),
        "order_intent_id": position.get("order_intent_id"),
        "execution_id": position.get("execution_id"),
        "reconciliation_id": position.get("reconciliation_id"),
    }
    outcome = {
        "r_multiple": settlement.get("result_R"),
        "exit_reason": settlement.get("close_reason"),
        "entry_regime": position.get("entry_regime"),
        "bars_held": position.get("holding_candles"),
    }
    record = attribute_outcome(attribution, outcome, chain, now=now)
    return append_attributed_outcome(registry_file, record)


def run_strategy_lifecycle_feedback(
    *,
    pool_file: str,
    outcome_registry_file: str,
    lifecycle_registry_file: str,
    now: str | None = None,
) -> dict[str, Any]:
    """Recompute S9 performance + S10 lifecycle for every active strategy.

    Updates each occupying entry's status and running failure count in place,
    persists the pool, and logs each status change. Returns a summary.
    """
    pool = load_pool(pool_file)
    all_outcomes = load_attributed_outcomes(outcome_registry_file)

    decisions: list[dict[str, Any]] = []
    changed = False
    for entry in pool.get("active_strategies", []):
        if entry.get("status") not in OCCUPYING_STATUSES:
            continue
        strategy_id = entry.get("strategy_id")
        outcomes = outcomes_for_strategy(all_outcomes, strategy_id)
        performance = compute_strategy_performance(
            strategy_id, outcomes, backtest_win_rate=entry.get("backtest_win_rate"), now=now
        )
        decision = evaluate_lifecycle(
            entry.get("status"), performance,
            consecutive_failures=int(entry.get("consecutive_failures", 0) or 0), now=now,
        )
        entry["consecutive_failures"] = decision["consecutive_failures"]
        if decision["status_changed"]:
            entry["status"] = decision["new_status"]
            entry["updated_at_utc"] = now
            changed = True
            append_registry_record(
                lifecycle_registry_file, decision,
                registry_name=STRATEGY_LIFECYCLE_REGISTRY_NAME,
                id_field="strategy_lifecycle_record_id",
                hash_field="strategy_lifecycle_record_sha256",
                id_prefix="strategy_lifecycle",
            )
        decisions.append({
            "strategy_id": strategy_id,
            "previous_status": decision["previous_status"],
            "new_status": decision["new_status"],
            "status_changed": decision["status_changed"],
            "trade_count": performance["trade_count"],
        })

    if changed:
        save_pool(pool_file, pool)

    return {
        "evaluated": len(decisions),
        "status_changes": sum(1 for d in decisions if d["status_changed"]),
        "decisions": decisions,
    }
