from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.research.research_signal_builder import RESEARCH_SIGNAL_LINEAGE_VERSION, RESEARCH_SIGNAL_V2_VERSION
from crypto_ai_system.utils.audit import sha256_json

RESEARCH_SIGNAL_REGISTRY_VERSION = "step288_research_signal_registry_v2"


def _score(signal: Mapping[str, Any], *keys: str) -> Any:
    components = signal.get("score_components") if isinstance(signal.get("score_components"), Mapping) else {}
    features = signal.get("features") if isinstance(signal.get("features"), Mapping) else {}
    for key in keys:
        if key in signal:
            return signal.get(key)
        if key in components:
            return components.get(key)
        if key in features:
            return features.get(key)
    return None


def _permission_result(signal: Mapping[str, Any]) -> str:
    explicit = signal.get("permission_result")
    if explicit:
        return str(explicit)
    trade_permission = signal.get("trade_permission") if isinstance(signal.get("trade_permission"), Mapping) else {}
    side = str(signal.get("entry_side") or "FLAT").upper()
    allowed = bool(signal.get("entry_allowed", False))
    risk_level = str(trade_permission.get("risk_level") or "").lower()
    blocks = signal.get("block_reasons") or trade_permission.get("block_reasons") or []

    if side == "LONG":
        if allowed and risk_level == "reduced":
            return "reduce_long"
        if allowed:
            return "allow_long"
        if blocks:
            return "block_long"
    if side == "SHORT":
        if allowed and risk_level == "reduced":
            return "reduce_short"
        if allowed:
            return "allow_short"
        if blocks:
            return "block_short"
    if blocks:
        return "review_only"
    return "neutral"


def _neutral_due_to_missing(signal: Mapping[str, Any]) -> bool:
    try:
        missing = int(signal.get("missing_optional_source_count") or 0)
    except Exception:
        missing = 0
    return bool(signal.get("neutral_due_to_missing") or signal.get("missing_optional_data_neutral") or missing > 0)


def build_research_signal_registry_record(signal: Mapping[str, Any]) -> dict[str, Any]:
    """Build the canonical Step288 ResearchSignal registry row.

    This is a summary record for append-only audit lookup. It intentionally
    does not create order intent, approve trades, mutate settings, or mutate
    score weights.
    """
    research_signal_id = signal.get("research_signal_id") or signal.get("signal_id")
    block_reasons = signal.get("blocked_reason") or signal.get("block_reasons") or []
    if isinstance(block_reasons, str):
        block_reasons = [block_reasons]
    if not isinstance(block_reasons, list):
        block_reasons = list(block_reasons) if block_reasons else []

    record = {
        "research_signal_id": research_signal_id,
        "signal_id": signal.get("signal_id") or research_signal_id,
        "signal_version": signal.get("signal_version") or RESEARCH_SIGNAL_LINEAGE_VERSION,
        "research_signal_version": signal.get("version") or RESEARCH_SIGNAL_V2_VERSION,
        "registry_version": RESEARCH_SIGNAL_REGISTRY_VERSION,
        "profile_id": signal.get("profile_id"),
        "profile_version": signal.get("profile_version"),
        "config_version": signal.get("config_version"),
        "data_snapshot_id": signal.get("data_snapshot_id"),
        "data_snapshot_manifest_sha256": signal.get("data_snapshot_manifest_sha256"),
        "feature_snapshot_id": signal.get("feature_snapshot_id"),
        "feature_matrix_sha256": signal.get("feature_matrix_sha256"),
        "source_bundle_sha256": signal.get("source_bundle_sha256"),
        "market_thesis_note_id": signal.get("market_thesis_note_id"),
        "market_thesis_note_sha256": signal.get("market_thesis_note_sha256"),
        "optional_data_health": signal.get("optional_data_health") or {},
        "missing_optional_source_count": signal.get("missing_optional_source_count"),
        "stale_optional_source_count": signal.get("stale_optional_source_count"),
        "live_candidate_eligible": bool(signal.get("live_candidate_eligible", False)),
        "price_direction_score": _score(signal, "price_direction_score", "price", "score_total"),
        "derivatives_positioning_score": _score(signal, "derivatives_positioning_score", "derivatives", "binance_derivatives_score"),
        "exchange_flow_score": _score(signal, "exchange_flow_score", "exchange_flow"),
        "etf_flow_score": _score(signal, "etf_flow_score", "etf_flow"),
        "stablecoin_liquidity_score": _score(signal, "stablecoin_liquidity_score", "stablecoin_liquidity"),
        "final_signal_direction": signal.get("entry_side") or signal.get("score_bias") or "NEUTRAL",
        "permission_result": _permission_result(signal),
        "neutral_due_to_missing": _neutral_due_to_missing(signal),
        "blocked_reason": sorted({str(reason) for reason in block_reasons if reason}),
        "entry_allowed": bool(signal.get("entry_allowed", False)),
        "entry_confidence": signal.get("entry_confidence"),
        "data_source": signal.get("data_source"),
        "data_source_role": signal.get("data_source_role"),
        "data_quality_status": signal.get("data_quality_status"),
        "order_intent_created": bool(signal.get("order_intent_created", False)),
        "trade_approved": bool(signal.get("trade_approved", False)),
        "runtime_settings_mutated": bool(signal.get("runtime_settings_mutated", False)),
        "score_weights_mutated": bool(signal.get("score_weights_mutated", False)),
        "created_at_utc": signal.get("created_at_utc"),
    }
    record["research_signal_sha256"] = signal.get("research_signal_sha256") or sha256_json(dict(signal))
    record["research_signal_registry_record_sha256"] = sha256_json(record)
    return record


def persist_research_signal_registry_record(cfg: AppConfig, signal: Mapping[str, Any]) -> dict[str, Any]:
    record = build_research_signal_registry_record(signal)
    return append_registry_record(
        registry_path(cfg, "research_signal_registry"),
        record,
        registry_name="research_signal_registry",
        id_field="research_signal_id",
        hash_field="research_signal_registry_record_sha256",
        id_prefix="research_signal",
    )
