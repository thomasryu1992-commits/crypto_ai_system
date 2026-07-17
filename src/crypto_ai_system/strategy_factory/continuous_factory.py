"""Phase S11: the continuous strategy factory loop.

One factory *cycle* runs the whole offline pipeline end to end: generate a batch
(S2) → backtest each on shared history (S4) → select at most one champion
(S5) → register it to the paper pool (S6), subject to a diversity guard. Run
cycles on a schedule (weekly at first, §15) and the pool is continuously
replenished with fresh, independently-validated strategies while decayed ones
are retired by the lifecycle agent (S10).

State carried between cycles: a generation counter and a *global* strategy-id
counter, so ids never collide across generations (the pool rejects collisions,
so advancing the counter is how the loop stays clean). The diversity guard caps
how many strategies of one family may hold slots at once, so the pool does not
fill with near-duplicates of a single idea.

This orchestrator is deliberately not exported from the package __init__: it
imports the backtesting package, and keeping the import lazy-at-use avoids a
package-init cycle. It submits no orders and changes no runtime settings.
"""

from __future__ import annotations

from typing import Any, Sequence

from crypto_ai_system.backtesting.backtest_agent import AbsoluteGate, run_backtest_agent
from crypto_ai_system.backtesting.champion_selector_agent import ChampionScoreWeights, select_batch_champion
from crypto_ai_system.backtesting.cost_model import CostModel
from crypto_ai_system.strategy_factory.active_strategy_pool import (
    DEFAULT_PAPER_CAP,
    add_champion,
    empty_pool,
    family_count,
    occupying_entries,
)
from crypto_ai_system.strategy_factory.strategy_generator_agent import generate_batch
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.strategy_factory.strategy_template_library import DEFAULT_TEMPLATE_ORDER

DEFAULT_MAX_PER_FAMILY = 2

ACTION_DIVERSITY_REJECTED = "REJECTED_DIVERSITY"


def initial_state() -> dict[str, Any]:
    return {"generation_seq": 1, "strategy_seq": 1, "pool": empty_pool()}


def run_factory_cycle(
    state: dict[str, Any],
    frame,
    *,
    seed: int,
    cost: CostModel | None = None,
    gate: AbsoluteGate | None = None,
    champion_weights: ChampionScoreWeights | None = None,
    cap: int = DEFAULT_PAPER_CAP,
    max_per_family: int = DEFAULT_MAX_PER_FAMILY,
    templates: Sequence = DEFAULT_TEMPLATE_ORDER,
    symbol: str = "BTCUSDT",
    now: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one generation cycle. Returns ``(new_state, cycle_report)``.

    ``frame`` is the shared historical feature frame every candidate is
    backtested on. ``state`` carries the counters and pool between cycles.
    """
    generation_seq = state.get("generation_seq", 1)
    strategy_seq = state.get("strategy_seq", 1)
    pool = state.get("pool") or empty_pool()
    generation_id = f"GEN-{generation_seq:03d}"

    batch = generate_batch(generation_id, seed=seed, start_index=strategy_seq, templates=templates, symbol=symbol)
    next_strategy_seq = strategy_seq + batch["accepted_count"]

    records = [
        run_backtest_agent(StrategySpec.from_dict(spec), frame, generation_id=generation_id,
                           cost=cost, gate=gate, now=now)
        for spec in batch["specs"]
    ]
    champion = select_batch_champion(records, generation_id=generation_id, weights=champion_weights, now=now)

    new_pool = pool
    pool_decision: dict[str, Any] | None = None
    selected_id = champion.get("selected_strategy_id")

    if selected_id is not None:
        spec = next(s for s in batch["specs"] if s["strategy_id"] == selected_id)
        family = spec["strategy_family"]
        # Diversity is judged within the champion's market: another symbol's
        # strategies of the same family are diversification, not duplication.
        if family_count(pool, family, symbol) >= max_per_family:
            pool_decision = {
                "action": ACTION_DIVERSITY_REJECTED,
                "strategy_id": selected_id,
                "strategy_family": family,
                "symbol": symbol,
                "reason": f"pool already holds {max_per_family} '{family}' strategies on {symbol}",
            }
        else:
            new_pool, pool_decision = add_champion(
                pool, spec, champion.get("champion_score"),
                generation_id=generation_id, cap=cap, now=now,
            )

    new_state = {
        "generation_seq": generation_seq + 1,
        "strategy_seq": next_strategy_seq,
        "pool": new_pool,
    }
    report = {
        "generation_id": generation_id,
        "batch_accepted": batch["accepted_count"],
        "qualified_count": champion.get("qualified_count", 0),
        "selected_strategy_id": selected_id,
        "champion_score": champion.get("champion_score"),
        "pool_decision": pool_decision,
        "active_pool_size": len(occupying_entries(new_pool)),
        # Every generated candidate spec, for the §10 candidate-registry audit. The
        # persisting runner pops this after writing so the returned report stays lean.
        "generated_specs": batch["specs"],
        "created_at_utc": now,
    }
    return new_state, report
