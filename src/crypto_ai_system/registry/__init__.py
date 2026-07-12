"""Append-only canonical registries for Crypto_AI_System audit lineage."""

from crypto_ai_system.registry.base_registry import (
    REGISTRY_SCHEMA_VERSION,
    RegistryIntegrityError,
    append_registry_record,
    load_registry_records,
    registry_path,
)

__all__ = [
    "REGISTRY_SCHEMA_VERSION",
    "RegistryIntegrityError",
    "append_registry_record",
    "load_registry_records",
    "registry_path",
]
from crypto_ai_system.registry.market_thesis_registry import build_market_thesis_registry_record, persist_market_thesis_registry_record

from crypto_ai_system.registry.research_signal_registry import build_research_signal_registry_record, persist_research_signal_registry_record
from crypto_ai_system.registry.decision_pipeline_registry import (  # noqa: F401
    DECISION_PIPELINE_REGISTRY_VERSION,
    build_decision_pipeline_registry_record,
    persist_decision_pipeline_registry_record,
)

from crypto_ai_system.execution.paper_reconciliation_v2 import PAPER_RECONCILIATION_REGISTRY_NAME  # noqa: F401
