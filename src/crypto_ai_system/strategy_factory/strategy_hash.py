"""Deterministic identity hash for a strategy's rule set.

``strategy_rule_hash`` is the stable identity of *what a strategy does*, not of a
particular record. Two specs that would trade identically hash identically, even
with different ids, versions, or generation batches — which is exactly what the
diversity guard and duplicate detection (Phase S11) need. Volatile metadata
(id, version, status, timestamps, author) is deliberately excluded.

The hash uses the same canonical JSON as the rest of the audit chain
(``utils.audit.sha256_json``) so it is reproducible across processes and OSes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crypto_ai_system.utils.audit import sha256_json

if TYPE_CHECKING:
    from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec

STRATEGY_RULE_HASH_VERSION = "strategy_rule_hash.v1"


def strategy_rule_fingerprint(spec: "StrategySpec") -> dict:
    """The canonical subset of a spec that defines its trading behaviour."""
    return {
        "hash_version": STRATEGY_RULE_HASH_VERSION,
        "strategy_family": spec.strategy_family,
        "timeframe": spec.timeframe,
        "direction": spec.direction.value,
        "symbol_scope": sorted(spec.symbol_scope),
        "entry_rules": {
            "operator": spec.entry_rules.operator,
            "conditions": [
                {
                    "feature": c.feature,
                    "comparison": c.comparison,
                    "value": c.value,
                    "value_from": c.value_from,
                }
                for c in spec.entry_rules.conditions
            ],
        },
        "exit_rules": {
            "stop_model": spec.exit_rules.stop_model,
            "stop_atr": spec.exit_rules.stop_atr,
            "target_atr": spec.exit_rules.target_atr,
            "max_holding_bars": spec.exit_rules.max_holding_bars,
        },
        "risk_constraints": {
            "max_risk_per_trade_R": spec.risk_constraints.max_risk_per_trade_R,
        },
    }


def compute_strategy_rule_hash(spec: "StrategySpec") -> str:
    return sha256_json(strategy_rule_fingerprint(spec))
