"""Phase S2: StrategyGenerationAgent — produce a batch of candidate specs.

Generates a fixed-size *generation batch* (default 4) by picking templates in
rotation, mutating their parameters within the allowed space, and keeping only
specs that both parse and pass the S3 validator. Duplicates (same rule hash) are
skipped so a batch is genuinely diverse. Generation is seeded, so the same seed
reproduces the same batch — essential for reproducible backtests.

The agent can only create candidate specs. It cannot activate a strategy, change
risk limits, or submit orders — every produced spec carries ``can_submit_orders
= false`` (enforced by :class:`StrategySpec`).
"""

from __future__ import annotations

import random
from typing import Any, Sequence

from crypto_ai_system.strategy_factory.strategy_spec import SCHEMA_VERSION, SpecParseError, StrategySpec
from crypto_ai_system.strategy_factory.strategy_template_library import (
    DEFAULT_TEMPLATE_ORDER,
    ParamSpec,
    StrategyTemplate,
)
from crypto_ai_system.strategy_factory.strategy_validator_agent import validate_strategy

DEFAULT_BATCH_SIZE = 4
_MUTATION_SCALE = 0.35
_MAX_ATTEMPTS_PER_SPEC = 12


def mutate_params(
    base_params: dict[str, float],
    param_space: dict[str, ParamSpec],
    rng: random.Random,
    *,
    scale: float = _MUTATION_SCALE,
) -> dict[str, float]:
    """Perturb each parameter within a fraction of its range, clamped to bounds."""
    out: dict[str, float] = {}
    for name, spec in param_space.items():
        base = base_params[name]
        span = (spec.hi - spec.lo) * scale
        val = base + rng.uniform(-span, span)
        val = max(spec.lo, min(spec.hi, val))
        out[name] = int(round(val)) if spec.integer else round(val, 4)
    return out


def build_spec_dict(
    template: StrategyTemplate,
    params: dict[str, float],
    *,
    strategy_id: str,
    generation_id: str,
    strategy_version: str = "1.0",
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "generation_id": generation_id,
        "strategy_family": template.family,
        "status": "GENERATED",
        "symbol_scope": [symbol],
        "timeframe": template.timeframe,
        "direction": template.direction.value,
        "entry_rules": {"operator": "AND", "conditions": template.build_entry_conditions(params)},
        "exit_rules": template.build_exit_rules(params),
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
        "created_by": "StrategyGenerationAgent",
    }


def generate_batch(
    generation_id: str,
    *,
    seed: int,
    start_index: int = 1,
    count: int = DEFAULT_BATCH_SIZE,
    symbol: str = "BTCUSDT",
    templates: Sequence[StrategyTemplate] = DEFAULT_TEMPLATE_ORDER,
) -> dict[str, Any]:
    """Produce ``count`` validated, distinct candidate specs.

    Returns the batch record: the accepted specs (as dicts), their validation
    verdicts, and any rejected attempts (for diversity/observability). Strategy
    ids run ``S{start_index}``..; ids advance only on acceptance.
    """
    rng = random.Random(seed)
    accepted: list[StrategySpec] = []
    validations: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    attempts = 0
    while len(accepted) < count and attempts < count * _MAX_ATTEMPTS_PER_SPEC:
        attempts += 1
        template = templates[len(accepted) % len(templates)]
        params = mutate_params(template.base_params, template.param_space, rng)
        strategy_id = f"S{start_index + len(accepted):03d}"
        spec_dict = build_spec_dict(
            template, params, strategy_id=strategy_id, generation_id=generation_id, symbol=symbol
        )

        try:
            spec = StrategySpec.from_dict(spec_dict)
        except SpecParseError as exc:
            rejected.append({"strategy_family": template.family, "reason": f"parse: {exc}"})
            continue

        verdict = validate_strategy(spec)
        if not verdict["approved_for_backtest"]:
            rejected.append({"strategy_family": template.family, "block_reasons": verdict["block_reasons"]})
            continue

        if spec.strategy_rule_hash in seen_hashes:
            rejected.append({"strategy_family": template.family, "reason": "duplicate_rule_hash"})
            continue

        seen_hashes.add(spec.strategy_rule_hash)
        accepted.append(spec)
        validations.append(verdict)

    return {
        "generation_id": generation_id,
        "seed": seed,
        "requested_count": count,
        "accepted_count": len(accepted),
        "specs": [s.to_dict() for s in accepted],
        "validations": validations,
        "rejected": rejected,
        "batch_complete": len(accepted) == count,
    }
