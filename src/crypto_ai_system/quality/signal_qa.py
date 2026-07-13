from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

SIGNAL_QA_VERSION = "step289_signal_qa_agent_v1"

PASS_REVIEW_ONLY = "PASS_REVIEW_ONLY"
PASS_PAPER_ONLY = "PASS_PAPER_ONLY"
BLOCK_INVALID_LINEAGE = "BLOCK_INVALID_LINEAGE"
BLOCK_STALE_DATA = "BLOCK_STALE_DATA"
BLOCK_FALLBACK_OR_SYNTHETIC = "BLOCK_FALLBACK_OR_SYNTHETIC"
BLOCK_MISSING_SIGNAL = "BLOCK_MISSING_SIGNAL"
BLOCK_LEGACY_FALLBACK = "BLOCK_LEGACY_FALLBACK"

PASS_RESULTS = {PASS_REVIEW_ONLY, PASS_PAPER_ONLY}
BLOCK_RESULTS = {
    BLOCK_INVALID_LINEAGE,
    BLOCK_STALE_DATA,
    BLOCK_FALLBACK_OR_SYNTHETIC,
    BLOCK_MISSING_SIGNAL,
    BLOCK_LEGACY_FALLBACK,
}

REQUIRED_SIGNAL_FIELDS = (
    "research_signal_id",
    "signal_version",
    "profile_id",
    "profile_version",
    "config_version",
    "data_snapshot_id",
    "feature_snapshot_id",
    "feature_matrix_sha256",
    "source_bundle_sha256",
)

LINEAGE_MATCH_FIELDS = (
    "research_signal_id",
    "data_snapshot_id",
    "feature_snapshot_id",
    "feature_matrix_sha256",
    "source_bundle_sha256",
)

FALLBACK_OR_SYNTHETIC_STATUSES = {
    "blocked_fallback",
    "blocked_synthetic",
    "blocked_sample",
}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _optional_health_map(signal: Mapping[str, Any], registry_record: Mapping[str, Any] | None) -> Mapping[str, Any]:
    value = signal.get("optional_data_health")
    if not isinstance(value, Mapping) and registry_record:
        value = registry_record.get("optional_data_health")
    return value if isinstance(value, Mapping) else {}


def _health_has_stale_source(optional_data_health: Mapping[str, Any]) -> bool:
    for status in optional_data_health.values():
        if isinstance(status, Mapping) and _truthy(status.get("stale")):
            return True
    return False


def _missing_required_fields(signal: Mapping[str, Any]) -> list[str]:
    return [field for field in REQUIRED_SIGNAL_FIELDS if signal.get(field) in {None, ""}]


def _lineage_mismatches(signal: Mapping[str, Any], registry_record: Mapping[str, Any] | None) -> list[str]:
    if not registry_record:
        return []
    mismatches: list[str] = []
    for field in LINEAGE_MATCH_FIELDS:
        left = signal.get(field)
        right = registry_record.get(field)
        if left not in {None, ""} and right not in {None, ""} and left != right:
            mismatches.append(field)
    return mismatches


def _legacy_fallback_used(signal: Mapping[str, Any]) -> bool:
    if _truthy(signal.get("legacy_fallback_used")):
        return True
    if _truthy(signal.get("legacy_signal_used")):
        return True
    if _truthy(signal.get("used_legacy_signal")):
        return True
    if str(signal.get("signal_source") or "").lower() in {"legacy", "legacy_fallback"}:
        return True
    if "legacy" in str(signal.get("signal_version") or "").lower():
        return True
    return False


def _has_fallback_synthetic_or_sample(signal: Mapping[str, Any], registry_record: Mapping[str, Any] | None) -> bool:
    keys = (
        "fallback_flag",
        "fallback_used",
        "synthetic_flag",
        "synthetic_used",
        "sample_flag",
        "sample_used",
    )
    if any(_truthy(signal.get(key)) for key in keys):
        return True
    if registry_record and any(_truthy(registry_record.get(key)) for key in keys):
        return True
    status = str(signal.get("data_quality_status") or (registry_record or {}).get("data_quality_status") or "").lower()
    return status in FALLBACK_OR_SYNTHETIC_STATUSES


def _has_stale_data(signal: Mapping[str, Any], registry_record: Mapping[str, Any] | None) -> bool:
    if _truthy(signal.get("stale")) or _truthy(signal.get("data_stale")) or _truthy(signal.get("stale_optional_data")):
        return True
    if registry_record and (_truthy(registry_record.get("stale")) or _truthy(registry_record.get("data_stale"))):
        return True
    if _as_int(signal.get("stale_optional_source_count"), 0) > 0:
        return True
    if registry_record and _as_int(registry_record.get("stale_optional_source_count"), 0) > 0:
        return True
    status = str(signal.get("data_quality_status") or (registry_record or {}).get("data_quality_status") or "").lower()
    if status == "blocked_stale_price":
        return True
    return _health_has_stale_source(_optional_health_map(signal, registry_record))


def _missing_optional_count(signal: Mapping[str, Any], registry_record: Mapping[str, Any] | None) -> int:
    count = _as_int(signal.get("missing_optional_source_count"), -1)
    if count >= 0:
        return count
    if registry_record:
        count = _as_int(registry_record.get("missing_optional_source_count"), -1)
        if count >= 0:
            return count
    health = _optional_health_map(signal, registry_record)
    missing = 0
    for status in health.values():
        if isinstance(status, Mapping) and str(status.get("collector_status") or "").lower() in {"missing", "disabled", "error", "unavailable"}:
            missing += 1
    return missing


def _neutral_due_to_missing(signal: Mapping[str, Any], registry_record: Mapping[str, Any] | None) -> bool:
    if _truthy(signal.get("neutral_due_to_missing")) or _truthy(signal.get("missing_optional_data_neutral")):
        return True
    if registry_record and _truthy(registry_record.get("neutral_due_to_missing")):
        return True
    return False


def _use_research_signal_gate(cfg: AppConfig | None) -> bool:
    if cfg is None:
        return True
    return bool(cfg.get("trading.use_research_signal_gate", True))


def validate_research_signal_quality(
    signal: Mapping[str, Any] | None,
    *,
    registry_record: Mapping[str, Any] | None = None,
    cfg: AppConfig | None = None,
) -> dict[str, Any]:
    """Validate a ResearchSignal v2 before decision/risk consumption.

    The agent is review-only. It records PASS/BLOCK evidence and never creates
    order intent, approves trades, mutates runtime settings, mutates score
    weights, or promotes signed-testnet/live execution.
    """
    signal = dict(signal or {})
    registry_record = dict(registry_record or {})
    block_reasons: list[str] = []
    lineage_missing: list[str] = []
    lineage_mismatches: list[str] = []
    missing_optional_count = 0
    neutral_due_to_missing = False

    if not signal:
        block_reasons.append(BLOCK_MISSING_SIGNAL)
    else:
        if _legacy_fallback_used(signal):
            block_reasons.append(BLOCK_LEGACY_FALLBACK)
        lineage_missing = _missing_required_fields(signal)
        if lineage_missing:
            block_reasons.append(BLOCK_INVALID_LINEAGE)
        lineage_mismatches = _lineage_mismatches(signal, registry_record)
        if lineage_mismatches:
            block_reasons.append(BLOCK_INVALID_LINEAGE)
        missing_optional_count = _missing_optional_count(signal, registry_record)
        neutral_due_to_missing = _neutral_due_to_missing(signal, registry_record)
        if missing_optional_count > 0 and not neutral_due_to_missing:
            # Optional missing data may score neutral, but hidden missing data is invalid.
            block_reasons.append(BLOCK_INVALID_LINEAGE)
        if _has_stale_data(signal, registry_record):
            block_reasons.append(BLOCK_STALE_DATA)
        if _has_fallback_synthetic_or_sample(signal, registry_record):
            block_reasons.append(BLOCK_FALLBACK_OR_SYNTHETIC)

    block_reasons = sorted(set(block_reasons))
    if block_reasons:
        signal_qa_result = block_reasons[0] if _use_research_signal_gate(cfg) else PASS_REVIEW_ONLY
    elif missing_optional_count > 0 or not bool(signal.get("live_candidate_eligible", False)):
        signal_qa_result = PASS_REVIEW_ONLY
    else:
        signal_qa_result = PASS_PAPER_ONLY

    payload = {
        "signal_qa_version": SIGNAL_QA_VERSION,
        "signal_qa_result": signal_qa_result,
        "research_signal_gate_enabled": _use_research_signal_gate(cfg),
        "research_signal_id": signal.get("research_signal_id") or signal.get("signal_id"),
        "signal_version": signal.get("signal_version"),
        "profile_id": signal.get("profile_id"),
        "profile_version": signal.get("profile_version"),
        "config_version": signal.get("config_version"),
        "data_snapshot_id": signal.get("data_snapshot_id"),
        "feature_snapshot_id": signal.get("feature_snapshot_id"),
        "feature_matrix_sha256": signal.get("feature_matrix_sha256"),
        "source_bundle_sha256": signal.get("source_bundle_sha256"),
        "research_signal_registry_record_sha256": registry_record.get("research_signal_registry_record_sha256"),
        "missing_required_fields": sorted(set(lineage_missing)),
        "lineage_mismatches": sorted(set(lineage_mismatches)),
        "missing_optional_source_count": missing_optional_count,
        "stale_optional_source_count": _as_int(signal.get("stale_optional_source_count") or registry_record.get("stale_optional_source_count"), 0),
        "neutral_due_to_missing": neutral_due_to_missing,
        "live_candidate_eligible": bool(signal.get("live_candidate_eligible", False)),
        "legacy_fallback_used": _legacy_fallback_used(signal),
        "fallback_or_synthetic_or_sample_used": _has_fallback_synthetic_or_sample(signal, registry_record) if signal else False,
        "stale_data_detected": _has_stale_data(signal, registry_record) if signal else False,
        "block_reasons": block_reasons,
        "allowed_for_decision": signal_qa_result in PASS_RESULTS,
        "allowed_for_paper": signal_qa_result == PASS_PAPER_ONLY,
        "allowed_for_signed_testnet": False,
        "allowed_for_live": False,
        "order_intent_created": False,
        "trade_approved": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "created_at_utc": utc_now_canonical(),
    }
    payload["signal_qa_report_id"] = stable_id("signal_qa_report", payload, 24)
    payload["signal_qa_report_sha256"] = sha256_json(payload)
    return payload


def assert_research_signal_quality_passes(
    signal: Mapping[str, Any] | None,
    *,
    registry_record: Mapping[str, Any] | None = None,
    cfg: AppConfig | None = None,
) -> dict[str, Any]:
    report = validate_research_signal_quality(signal, registry_record=registry_record, cfg=cfg)
    if report["signal_qa_result"] not in PASS_RESULTS:
        reasons = ",".join(report.get("block_reasons") or [])
        raise ValueError(f"ResearchSignal QA failed closed: {reasons}")
    return report


def persist_signal_qa_report(cfg: AppConfig, report: Mapping[str, Any]) -> dict[str, Any]:
    return append_registry_record(
        registry_path(cfg, "signal_qa_registry"),
        report,
        registry_name="signal_qa_registry",
        id_field="signal_qa_report_id",
        hash_field="signal_qa_report_sha256",
        id_prefix="signal_qa_report",
    )
