from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.research.market_thesis_note import MARKET_THESIS_NOTE_VERSION
from crypto_ai_system.utils.audit import sha256_json

MARKET_THESIS_REGISTRY_VERSION = "step287_market_thesis_registry_v1"


def build_market_thesis_registry_record(note: Mapping[str, Any]) -> dict[str, Any]:
    record = {
        "market_thesis_note_id": note.get("market_thesis_note_id"),
        "thesis_version": note.get("thesis_version") or MARKET_THESIS_NOTE_VERSION,
        "profile_id": note.get("profile_id"),
        "profile_version": note.get("profile_version"),
        "config_version": note.get("config_version"),
        "data_snapshot_id": note.get("data_snapshot_id"),
        "data_snapshot_manifest_sha256": note.get("data_snapshot_manifest_sha256"),
        "feature_snapshot_id": note.get("feature_snapshot_id"),
        "feature_matrix_sha256": note.get("feature_matrix_sha256"),
        "source_bundle_sha256": note.get("source_bundle_sha256"),
        "optional_data_health": note.get("optional_data_health") or {},
        "missing_optional_source_count": note.get("missing_optional_source_count"),
        "stale_optional_source_count": note.get("stale_optional_source_count"),
        "live_candidate_eligible": bool(note.get("live_candidate_eligible", False)),
        "directional_bias": note.get("directional_bias"),
        "main_market_question": note.get("main_market_question"),
        "core_thesis": note.get("core_thesis"),
        "long_argument_count": len(note.get("long_arguments") or []),
        "short_argument_count": len(note.get("short_arguments") or []),
        "neutral_argument_count": len(note.get("neutral_arguments") or []),
        "counterargument_count": len(note.get("counterarguments") or []),
        "invalidation_condition_count": len(note.get("invalidation_conditions") or []),
        "order_intent_created": bool(note.get("order_intent_created", False)),
        "trade_approved": bool(note.get("trade_approved", False)),
        "runtime_settings_mutated": bool(note.get("runtime_settings_mutated", False)),
        "score_weights_mutated": bool(note.get("score_weights_mutated", False)),
        "market_thesis_note_sha256": note.get("market_thesis_note_sha256") or sha256_json(note),
        "created_at_utc": note.get("created_at_utc"),
        "version": MARKET_THESIS_REGISTRY_VERSION,
    }
    record["market_thesis_registry_record_sha256"] = sha256_json(record)
    return record


def persist_market_thesis_registry_record(cfg: AppConfig, note: Mapping[str, Any]) -> dict[str, Any]:
    record = build_market_thesis_registry_record(note)
    return append_registry_record(
        registry_path(cfg, "market_thesis_registry"),
        record,
        registry_name="market_thesis_registry",
        id_field="market_thesis_note_id",
        hash_field="market_thesis_registry_record_sha256",
        id_prefix="market_thesis_note",
    )
