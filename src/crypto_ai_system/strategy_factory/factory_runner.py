"""The factory runner: the entry point that actually populates the pool.

Everything at runtime (routing, drive, lifecycle) reads the active pool, but only
this runner *fills* it. One run turns a batch of freshly generated strategies
into (at most) one new paper-pool champion, backtested on real historical
candles. Run it on a schedule (weekly at first, §15) and the pool is continuously
replenished while the lifecycle agent retires decayed strategies.

The pool is the single shared source of truth: this runner loads the current pool
(which the feedback lifecycle may have edited), adds its champion, and saves it
back. Only the generation/strategy counters live in a separate state file, so ids
stay globally unique across runs.

Registers no order, changes no runtime setting: it produces candidate strategies
and, at most, adds one to the *paper* pool — testnet/live entry stays manual.
"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.backtesting.backtest_agent import AbsoluteGate
from crypto_ai_system.backtesting.champion_selector_agent import ChampionScoreWeights
from crypto_ai_system.backtesting.cost_model import CostModel
from crypto_ai_system.registry.base_registry import append_registry_record
from crypto_ai_system.strategy_factory.active_strategy_pool import (
    ACTIVE_STRATEGY_REGISTRY_NAME,
    DEFAULT_PAPER_CAP,
    load_pool,
    occupying_entries,
    save_pool,
)
from crypto_ai_system.strategy_factory.continuous_factory import (
    DEFAULT_MAX_PER_FAMILY,
    run_factory_cycle,
)
from crypto_ai_system.strategy_factory.runtime_feature_adapter import build_backtest_frame

DEFAULT_BASE_SEED = 1000


def load_counters(state_file: str) -> dict[str, int]:
    data = read_json(state_file, {}) or {}
    return {
        "generation_seq": int(data.get("generation_seq", 1) or 1),
        "strategy_seq": int(data.get("strategy_seq", 1) or 1),
    }


def save_counters(state_file: str, *, generation_seq: int, strategy_seq: int, now: str | None) -> None:
    atomic_write_json(state_file, {
        "generation_seq": generation_seq,
        "strategy_seq": strategy_seq,
        "updated_at_utc": now,
    })


def run_generation(
    frame: pd.DataFrame,
    *,
    pool_file: str,
    state_file: str,
    cost: CostModel | None = None,
    gate: AbsoluteGate | None = None,
    champion_weights: ChampionScoreWeights | None = None,
    cap: int = DEFAULT_PAPER_CAP,
    max_per_family: int = DEFAULT_MAX_PER_FAMILY,
    base_seed: int = DEFAULT_BASE_SEED,
    registry_file: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Run one generation cycle, persisting the pool and counters.

    When ``registry_file`` is given, every pool decision (add / replace / reject,
    including diversity rejections) is appended to the append-only active-strategy
    registry — the §10 audit trail for how the pool changed over time. The pure
    ``run_factory_cycle`` stays I/O-free; the audit is written here at the boundary.
    """
    counters = load_counters(state_file)
    pool = load_pool(pool_file)
    state = {"generation_seq": counters["generation_seq"], "strategy_seq": counters["strategy_seq"], "pool": pool}
    seed = base_seed + counters["generation_seq"]

    new_state, report = run_factory_cycle(
        state, frame, seed=seed, cost=cost, gate=gate, champion_weights=champion_weights,
        cap=cap, max_per_family=max_per_family, now=now,
    )

    save_pool(pool_file, new_state["pool"])
    save_counters(state_file, generation_seq=new_state["generation_seq"],
                  strategy_seq=new_state["strategy_seq"], now=now)

    decision = report.get("pool_decision")
    if registry_file and decision:
        append_registry_record(
            registry_file,
            {"decision": decision, "generation_id": report.get("generation_id"),
             "strategy_id": decision.get("strategy_id")},
            registry_name=ACTIVE_STRATEGY_REGISTRY_NAME,
            id_field="active_strategy_registry_record_id",
            hash_field="active_strategy_registry_record_sha256",
            id_prefix="active_strategy",
        )

    report["seed"] = seed
    return report


def run_factory(
    candles: Sequence[dict[str, Any]],
    *,
    pool_file: str,
    state_file: str,
    cycles: int = 1,
    cost: CostModel | None = None,
    gate: AbsoluteGate | None = None,
    champion_weights: ChampionScoreWeights | None = None,
    cap: int = DEFAULT_PAPER_CAP,
    max_per_family: int = DEFAULT_MAX_PER_FAMILY,
    base_seed: int = DEFAULT_BASE_SEED,
    registry_file: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Build the backtest frame from real candles and run ``cycles`` generations."""
    frame = build_backtest_frame(candles)
    if frame.empty:
        return {"error": "insufficient_candles_for_backtest_frame", "candles": len(candles or []),
                "reports": [], "active_pool_size": len(occupying_entries(load_pool(pool_file)))}

    reports: list[dict[str, Any]] = []
    for _ in range(max(1, cycles)):
        reports.append(run_generation(
            frame, pool_file=pool_file, state_file=state_file, cost=cost, gate=gate,
            champion_weights=champion_weights, cap=cap, max_per_family=max_per_family,
            base_seed=base_seed, registry_file=registry_file, now=now,
        ))

    final_pool = load_pool(pool_file)
    return {
        "bars": int(len(frame)),
        "cycles_run": len(reports),
        "reports": reports,
        "active_pool_size": len(occupying_entries(final_pool)),
        "active_strategies": [
            {"strategy_id": e.get("strategy_id"), "strategy_family": (e.get("strategy_spec") or {}).get("strategy_family"),
             "status": e.get("status"), "generation_id": e.get("generation_id")}
            for e in final_pool.get("active_strategies", [])
        ],
    }
