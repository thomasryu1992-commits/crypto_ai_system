"""Strategy Factory — Phase S1 contract foundation.

A strategy is a *declarative, validatable spec* (:class:`StrategySpec`), never
generated Python code. This package holds the contract layer the rest of the
factory builds on:

* :mod:`allowed_feature_registry` — the exact feature keys a spec may reference.
* :mod:`strategy_spec` — the typed spec, its status model, and structural parse.
* :mod:`strategy_hash` — a deterministic identity hash over a spec's rules.
* :mod:`strategy_registry` — append-only persistence of candidate specs.

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
]
