"""Append-only persistence for candidate strategy specs (Phase S1).

Wraps the canonical append-only registry (``registry.base_registry``) so a
generated :class:`StrategySpec` is stored with the same integrity guarantees as
the rest of the audit chain: created_at stamping, a per-record id, a tamper hash,
and fail-closed reads on a damaged file.

The API is path-based so it is testable against a tmp directory and independent
of runtime config; the generation agent (Phase S2) will supply the canonical
``storage/registries`` path. Persisting a spec grants it nothing — it remains a
candidate until a champion selection and pool registration (Phases S5/S6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from crypto_ai_system.registry.base_registry import (
    append_registry_record,
    load_registry_records,
)
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec

STRATEGY_CANDIDATE_REGISTRY_NAME = "strategy_candidate_registry"

_ID_FIELD = "strategy_candidate_record_id"
_HASH_FIELD = "strategy_candidate_record_sha256"


def persist_strategy_spec(spec: StrategySpec, registry_file: str | Path) -> dict[str, Any]:
    """Append one candidate spec record. Returns the persisted record."""
    return append_registry_record(
        registry_file,
        {"strategy_spec": spec.to_dict(), "strategy_id": spec.strategy_id,
         "strategy_rule_hash": spec.strategy_rule_hash, "status": spec.status.value},
        registry_name=STRATEGY_CANDIDATE_REGISTRY_NAME,
        id_field=_ID_FIELD,
        hash_field=_HASH_FIELD,
        id_prefix="strategy_candidate",
    )


def load_strategy_records(registry_file: str | Path) -> list[dict[str, Any]]:
    """All candidate records, oldest first. Fails closed on a damaged file."""
    return load_registry_records(registry_file)


def get_strategy_record(strategy_id: str, registry_file: str | Path) -> dict[str, Any] | None:
    """Most recent record for ``strategy_id``, or None."""
    if not strategy_id:
        return None
    matches = [r for r in load_registry_records(registry_file) if r.get("strategy_id") == strategy_id]
    return matches[-1] if matches else None
