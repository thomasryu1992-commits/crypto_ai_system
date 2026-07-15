"""Strategy Factory — Phase S1 contract foundation.

A strategy is a *declarative, validatable spec* (:class:`StrategySpec`), never
generated Python code. This package holds the contract layer the rest of the
factory builds on:

* :mod:`allowed_feature_registry` — the exact feature keys a spec may reference.
* :mod:`strategy_spec` — the typed spec, its status model, and structural parse.
* :mod:`strategy_hash` — a deterministic identity hash over a spec's rules.
* :mod:`strategy_registry` — append-only persistence of candidate specs.
* :mod:`strategy_template_library` — the allowed generation templates (S2).
* :mod:`strategy_generator_agent` — batch generation by template + mutation (S2).
* :mod:`strategy_validator_agent` — the pre-backtest safety gate (S3).

Nothing here can submit an order, mutate runtime settings, read secrets, or
promote a stage. Those boundaries are enforced by the spec (``can_submit_orders``
is always false) and by later gates.
"""

from crypto_ai_system.strategy_factory.strategy_spec import (
    Direction,
    EntryRules,
    ExitRules,
    RiskConstraints,
    RuleCondition,
    SpecParseError,
    StrategySpec,
    StrategyStatus,
)
from crypto_ai_system.strategy_factory.strategy_hash import compute_strategy_rule_hash
from crypto_ai_system.strategy_factory.strategy_generator_agent import generate_batch
from crypto_ai_system.strategy_factory.strategy_validator_agent import validate_strategy
from crypto_ai_system.strategy_factory.strategy_evaluator import (
    MatchResult,
    evaluate_condition,
    evaluate_spec,
)
from crypto_ai_system.strategy_factory.active_strategy_pool import (
    add_champion,
    empty_pool,
    paper_active_specs,
    register_champion,
    set_status,
)

__all__ = [
    "Direction",
    "EntryRules",
    "ExitRules",
    "RiskConstraints",
    "RuleCondition",
    "SpecParseError",
    "StrategySpec",
    "StrategyStatus",
    "compute_strategy_rule_hash",
    "generate_batch",
    "validate_strategy",
    "MatchResult",
    "evaluate_condition",
    "evaluate_spec",
    "add_champion",
    "empty_pool",
    "paper_active_specs",
    "register_champion",
    "set_status",
]
