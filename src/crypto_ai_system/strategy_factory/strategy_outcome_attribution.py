"""Phase S8: attribute every trade outcome to the strategy that drove it.

Per-strategy performance (S9) and lifecycle (S10) are only possible if every
outcome carries an unbroken chain back to the strategy that opened it. This layer
builds that chain: a router entry candidate (S7) becomes a strategy *attribution*
block, and a completed outcome is stamped with that block plus the runtime id
chain (trade plan → risk gate → order intent → execution → reconciliation →
outcome).

One order has one owner. When several strategies agreed on the entry (§6.9), the
*primary* (highest-scored) strategy owns the outcome for performance; the others
are recorded as ``supporting_strategy_ids`` for co-occurrence analysis but are not
separately credited — a single order must not inflate two strategies' records.

Connectivity-test orders (venue plumbing checks) are never attributed to a
strategy, matching the execution layer's ``connectivity_test`` convention.

Pure functions plus a thin append-only persistence helper.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from crypto_ai_system.registry.base_registry import append_registry_record, load_registry_records
from crypto_ai_system.strategy_factory.entry_strategy_router_agent import STATUS_ENTRY_CANDIDATE
from crypto_ai_system.utils.audit import stable_id, utc_now_canonical

# Runtime id chain an attributed outcome must carry (directive §6.14 / §11).
REQUIRED_CHAIN_IDS = (
    "trade_plan_id",
    "risk_gate_id",
    "order_intent_id",
    "execution_id",
    "reconciliation_id",
)

STRATEGY_OUTCOME_REGISTRY_NAME = "strategy_attributed_outcome_registry"

_ATTRIBUTION_FIELDS = (
    "strategy_id",
    "strategy_version",
    "strategy_generation_id",
    "strategy_rule_hash",
    "supporting_strategy_ids",
    "matched_strategy_ids",
    "matched_strategy_count",
    "strategy_pool_version",
    "direction",
    "cycle_id",
    "strategy_entry_evaluation_id",
)


class OutcomeAttributionError(ValueError):
    """Raised when an outcome cannot be attributed to a strategy."""


def build_strategy_attribution(
    router_result: Mapping[str, Any],
    primary_spec: Mapping[str, Any],
    *,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    """Build the attribution block for an entry candidate.

    ``router_result`` must be an ENTRY_CANDIDATE. ``primary_spec`` is the canonical
    spec dict of the router's primary strategy (source of version/generation).
    """
    if router_result.get("status") != STATUS_ENTRY_CANDIDATE:
        raise OutcomeAttributionError(
            f"cannot attribute a non-candidate router result (status={router_result.get('status')!r})"
        )
    primary_id = router_result.get("primary_strategy_id")
    if primary_id is None or primary_spec.get("strategy_id") != primary_id:
        raise OutcomeAttributionError("primary_spec does not match the router's primary strategy")

    matched = list(router_result.get("matched_strategy_ids") or [])
    supporting = [sid for sid in matched if sid != primary_id]

    attribution: dict[str, Any] = {
        "strategy_id": primary_id,
        "strategy_version": primary_spec.get("strategy_version"),
        "strategy_generation_id": primary_spec.get("generation_id"),
        "strategy_rule_hash": router_result.get("primary_strategy_rule_hash") or primary_spec.get("strategy_rule_hash"),
        "supporting_strategy_ids": supporting,
        "matched_strategy_ids": matched,
        "matched_strategy_count": router_result.get("matched_strategy_count", len(matched)),
        "strategy_pool_version": router_result.get("strategy_pool_version"),
        "direction": router_result.get("direction"),
        "cycle_id": cycle_id,
    }
    attribution["strategy_entry_evaluation_id"] = stable_id("strategy_entry_evaluation", attribution, 24)
    return attribution


def chain_missing_ids(record: Mapping[str, Any]) -> list[str]:
    """Required chain ids that are absent/empty on ``record`` (empty => complete)."""
    missing = [cid for cid in REQUIRED_CHAIN_IDS if not record.get(cid)]
    if not record.get("strategy_id"):
        missing.append("strategy_id")
    return missing


def attribute_outcome(
    attribution: Mapping[str, Any],
    outcome: Mapping[str, Any],
    chain: Mapping[str, Any],
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Merge attribution + runtime chain ids + outcome metrics into one record.

    ``chain`` supplies the runtime ids (trade_plan_id … reconciliation_id).
    Raises on a connectivity-test outcome — those are never strategy performance.
    """
    if outcome.get("connectivity_test"):
        raise OutcomeAttributionError("connectivity-test outcomes are not attributed to a strategy")

    record: dict[str, Any] = {field: attribution.get(field) for field in _ATTRIBUTION_FIELDS}
    for cid in REQUIRED_CHAIN_IDS:
        record[cid] = chain.get(cid)
    record.update({
        "r_multiple": outcome.get("r_multiple"),
        "net_pnl": outcome.get("net_pnl"),
        "exit_reason": outcome.get("exit_reason"),
        "entry_regime": outcome.get("entry_regime"),
        "bars_held": outcome.get("bars_held"),
        "connectivity_test": False,
    })
    identity = {k: v for k, v in record.items()}
    record["outcome_id"] = stable_id("strategy_outcome", identity, 24)
    record["chain_complete"] = not chain_missing_ids(record)
    record["created_at_utc"] = now or utc_now_canonical()
    return record


# -- persistence --------------------------------------------------------------

def append_attributed_outcome(registry_file: str, record: Mapping[str, Any]) -> dict[str, Any]:
    return append_registry_record(
        registry_file,
        dict(record),
        registry_name=STRATEGY_OUTCOME_REGISTRY_NAME,
        id_field="strategy_outcome_record_id",
        hash_field="strategy_outcome_record_sha256",
        id_prefix="strategy_outcome",
    )


def load_attributed_outcomes(registry_file: str) -> list[dict[str, Any]]:
    return load_registry_records(registry_file)


def outcomes_for_strategy(records: Sequence[Mapping[str, Any]], strategy_id: str) -> list[dict[str, Any]]:
    """Outcomes a strategy *owns* (is the primary of). Supporting appearances are
    intentionally excluded — performance credit belongs to the primary only."""
    return [dict(r) for r in records if r.get("strategy_id") == strategy_id]
