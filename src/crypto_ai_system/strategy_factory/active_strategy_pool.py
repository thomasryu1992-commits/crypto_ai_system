"""Phase S6: the Active Strategy Pool.

The pool is the set of strategies currently allowed to trade a stage (paper
first). It replaces the single ``paper_default_v1`` profile with a capped,
multi-strategy registry. A batch champion (S5) may be *added to the paper pool*
automatically — that is the one auto-promotion the directive permits; testnet
and live entry stay manual.

Capacity is bounded (default 5 paper slots, §16). When the pool is full a new
champion only displaces the weakest occupant if it is meaningfully better, and
the displaced strategy is *suspended*, not deleted. Auto-reactivation of a
suspended strategy is never done here.

The functions in the upper half are pure (a pool dict in, a new pool dict out) so
the capacity and status logic is testable without IO. The lower half persists a
pool snapshot and an append-only audit of every decision.
"""

from __future__ import annotations

import math
from typing import Any

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.registry.base_registry import append_registry_record
from crypto_ai_system.strategy_factory.strategy_spec import StrategyStatus
from crypto_ai_system.utils.audit import utc_now_canonical

POOL_VERSION = "active_strategy_pool.v1"
PAPER_STAGE = "paper"
DEFAULT_PAPER_CAP = 5
DEFAULT_MIN_IMPROVEMENT = 0.05

ACTIVE_STRATEGY_REGISTRY_NAME = "active_strategy_registry"

# Statuses that occupy a pool slot (still managed/tradeable). Suspended and
# archived strategies have released their slot.
OCCUPYING_STATUSES = frozenset({
    StrategyStatus.PAPER_ACTIVE.value,
    StrategyStatus.WARNING.value,
    StrategyStatus.PROBATION.value,
})

ACTION_ADDED = "ADDED"
ACTION_REPLACED = "REPLACED"
ACTION_REJECTED_ALREADY_ACTIVE = "REJECTED_ALREADY_ACTIVE"
ACTION_REJECTED_POOL_FULL = "REJECTED_POOL_FULL"


# -- pure pool operations -----------------------------------------------------

def empty_pool(stage: str = PAPER_STAGE) -> dict[str, Any]:
    return {"pool_version": POOL_VERSION, "stage": stage, "active_strategies": []}


def _entries(pool: dict) -> list[dict]:
    return list(pool.get("active_strategies") or [])


def occupying_entries(pool: dict) -> list[dict]:
    """Entries that currently hold a slot (active / warning / probation)."""
    return [e for e in _entries(pool) if e.get("status") in OCCUPYING_STATUSES]


def find_entry(pool: dict, strategy_id: str) -> dict | None:
    for entry in _entries(pool):
        if entry.get("strategy_id") == strategy_id:
            return entry
    return None


def is_rule_hash_active(pool: dict, rule_hash: str) -> bool:
    return any(
        e.get("strategy_rule_hash") == rule_hash and e.get("status") in OCCUPYING_STATUSES
        for e in _entries(pool)
    )


def is_strategy_id_active(pool: dict, strategy_id: str) -> bool:
    return any(
        e.get("strategy_id") == strategy_id and e.get("status") in OCCUPYING_STATUSES
        for e in _entries(pool)
    )


def family_count(pool: dict, family: str, symbol: str | None = None) -> int:
    """How many slot-occupying strategies belong to ``family`` (diversity guard).

    With ``symbol`` the count is per market: two BTC breakouts and two ETH
    breakouts are four distinct bets on the family cap's terms, because the
    diversity the guard protects is *within* a market — across markets the same
    family is exactly the diversification a multi-symbol pool exists for.
    """
    def _matches(e: dict) -> bool:
        spec = e.get("strategy_spec") or {}
        if spec.get("strategy_family") != family:
            return False
        if symbol is None:
            return True
        scope = spec.get("symbol_scope") or []
        return bool(scope) and str(scope[0]) == str(symbol)

    return sum(1 for e in occupying_entries(pool) if _matches(e))


def paper_active_specs(pool: dict) -> list[dict]:
    """Specs of PAPER_ACTIVE strategies — what the S7 router will evaluate."""
    return [
        e["strategy_spec"]
        for e in _entries(pool)
        if e.get("status") == StrategyStatus.PAPER_ACTIVE.value and e.get("strategy_spec")
    ]


def _make_entry(
    spec: dict,
    champion_score: float | None,
    generation_id: str | None,
    now: str,
    robustness: dict | None = None,
) -> dict:
    entry = {
        "strategy_id": spec["strategy_id"],
        "strategy_rule_hash": spec["strategy_rule_hash"],
        "status": StrategyStatus.PAPER_ACTIVE.value,
        "stage": PAPER_STAGE,
        "champion_score": champion_score,
        "generation_id": generation_id if generation_id is not None else spec.get("generation_id"),
        "strategy_spec": spec,
        "added_at_utc": now,
        "updated_at_utc": now,
    }
    # The backtest record is not persisted anywhere, so without this the overfitting
    # verdict would die with the cycle that computed it. An operator reading the
    # pool needs to know which occupants were only ever provisional.
    if robustness is not None:
        entry["robustness_verdict"] = robustness.get("verdict")
        entry["robustness_score"] = robustness.get("robustness_score")
        entry["trades_per_parameter"] = robustness.get("trades_per_parameter")
        entry["robustness_warnings"] = robustness.get("warnings") or []
    return entry


def set_status(pool: dict, strategy_id: str, new_status: StrategyStatus | str, *, now: str | None = None) -> tuple[dict, bool]:
    """Return a copy of the pool with ``strategy_id`` at a new status."""
    now = now or utc_now_canonical()
    status_value = new_status.value if isinstance(new_status, StrategyStatus) else str(new_status)
    changed = False
    new_entries = []
    for entry in _entries(pool):
        if entry.get("strategy_id") == strategy_id and entry.get("status") != status_value:
            entry = {**entry, "status": status_value, "updated_at_utc": now}
            changed = True
        new_entries.append(entry)
    return {**pool, "active_strategies": new_entries}, changed


def add_champion(
    pool: dict,
    spec: dict,
    champion_score: float | None,
    *,
    generation_id: str | None = None,
    cap: int = DEFAULT_PAPER_CAP,
    min_improvement: float = DEFAULT_MIN_IMPROVEMENT,
    now: str | None = None,
    robustness: dict | None = None,
) -> tuple[dict, dict]:
    """Try to add a champion spec to the paper pool.

    Returns ``(new_pool, decision)``. The pool is unchanged when the champion is
    rejected (already active, or the pool is full and the champion is not clearly
    better than the weakest occupant).
    """
    now = now or utc_now_canonical()
    strategy_id = spec["strategy_id"]
    rule_hash = spec["strategy_rule_hash"]

    if is_rule_hash_active(pool, rule_hash):
        return pool, {"action": ACTION_REJECTED_ALREADY_ACTIVE, "strategy_id": strategy_id,
                      "reason": "an identical rule set is already active"}
    # strategy_id must be globally unique among active entries; a collision means
    # the generator was not advancing ids across generations (caller/S11 bug).
    if is_strategy_id_active(pool, strategy_id):
        return pool, {"action": ACTION_REJECTED_ALREADY_ACTIVE, "strategy_id": strategy_id,
                      "reason": "strategy_id already active (ids must be globally unique)"}

    occupying = occupying_entries(pool)
    if len(occupying) < cap:
        new_pool = {**pool, "active_strategies": _entries(pool) + [_make_entry(spec, champion_score, generation_id, now, robustness)]}
        return new_pool, {"action": ACTION_ADDED, "strategy_id": strategy_id,
                          "occupied_after": len(occupying) + 1, "cap": cap}

    # Pool full: only displace the weakest occupant if clearly beaten.
    weakest = min(occupying, key=lambda e: e["champion_score"] if e.get("champion_score") is not None else -math.inf)
    weakest_score = weakest.get("champion_score")
    if champion_score is None or weakest_score is None or (champion_score - weakest_score) < min_improvement:
        return pool, {"action": ACTION_REJECTED_POOL_FULL, "strategy_id": strategy_id,
                      "weakest_strategy_id": weakest.get("strategy_id"),
                      "weakest_score": weakest_score, "champion_score": champion_score,
                      "min_improvement": min_improvement,
                      "reason": "pool full and champion not sufficiently better than the weakest occupant"}

    displaced_pool, _ = set_status(pool, weakest["strategy_id"], StrategyStatus.SUSPENDED, now=now)
    new_pool = {**displaced_pool, "active_strategies": _entries(displaced_pool) + [_make_entry(spec, champion_score, generation_id, now, robustness)]}
    return new_pool, {"action": ACTION_REPLACED, "strategy_id": strategy_id,
                      "displaced_strategy_id": weakest["strategy_id"],
                      "displaced_score": weakest_score, "champion_score": champion_score, "cap": cap}


# -- persistence --------------------------------------------------------------

def load_pool(pool_file: str, *, stage: str = PAPER_STAGE) -> dict:
    data = read_json(pool_file, default=None)
    if not isinstance(data, dict) or "active_strategies" not in data:
        return empty_pool(stage)
    return data


def save_pool(pool_file: str, pool: dict) -> None:
    atomic_write_json(pool_file, pool)


def register_champion(
    pool_file: str,
    registry_file: str,
    spec: dict,
    champion_score: float | None,
    *,
    generation_id: str | None = None,
    cap: int = DEFAULT_PAPER_CAP,
    min_improvement: float = DEFAULT_MIN_IMPROVEMENT,
    now: str | None = None,
) -> dict:
    """Load the pool, attempt to add ``spec``, persist, and audit the decision.

    Returns the decision. The pool snapshot is only rewritten when it changed;
    the append-only registry records every decision (including rejections).
    """
    pool = load_pool(pool_file)
    new_pool, decision = add_champion(
        pool, spec, champion_score, generation_id=generation_id,
        cap=cap, min_improvement=min_improvement, now=now,
    )
    if decision["action"] in (ACTION_ADDED, ACTION_REPLACED):
        save_pool(pool_file, new_pool)
    append_registry_record(
        registry_file,
        {"decision": decision, "strategy_id": spec.get("strategy_id"),
         "strategy_rule_hash": spec.get("strategy_rule_hash")},
        registry_name=ACTIVE_STRATEGY_REGISTRY_NAME,
        id_field="active_strategy_registry_record_id",
        hash_field="active_strategy_registry_record_sha256",
        id_prefix="active_strategy",
    )
    return decision
