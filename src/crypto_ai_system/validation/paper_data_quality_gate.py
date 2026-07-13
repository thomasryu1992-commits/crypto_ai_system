from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical

PAPER_DATA_QUALITY_GATE_VERSION = "phase2_paper_data_quality_hardening_v1"
LIVE_CANDIDATE_DATA_FOUNDATION_VERSION = "phase_b_live_candidate_data_foundation_v1"
PAPER_DATA_QUALITY_REGISTRY_NAME = "paper_data_quality_gate_registry"
STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY = "PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY"
STATUS_PAPER_DATA_QUALITY_BLOCKED_REVIEW_ONLY = "PAPER_DATA_QUALITY_BLOCKED_REVIEW_ONLY"

REQUIRED_LATEST_ARTIFACTS: tuple[str, ...] = (
    "data_health_report.json",
)
LINEAGE_ARTIFACTS: tuple[str, ...] = (
    "data_snapshot_manifest.json",
    "feature_store_manifest.json",
)
REQUIRED_DATA_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "data_snapshot_id",
    "source_bundle_sha256",
    "data_snapshot_sha256",
)
REQUIRED_FEATURE_STORE_FIELDS: tuple[str, ...] = (
    "data_snapshot_id",
    "feature_snapshot_id",
    "feature_matrix_sha256",
    "source_bundle_sha256",
)
EXPECTED_OPTIONAL_SOURCES: tuple[str, ...] = (
    "binance_futures",
    "coinmetrics",
    "farside_etf_flow",
    "defillama_stablecoin",
)
OPTIONAL_SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "binance_futures": ("binance_futures",),
    "coinmetrics": ("coinmetrics", "coinmetrics_exchange_flow"),
    "farside_etf_flow": ("farside_etf_flow",),
    "defillama_stablecoin": ("defillama_stablecoin", "defillama_stablecoins"),
}
UNSAFE_SOURCE_TOKENS: tuple[str, ...] = ("fallback", "synthetic", "sample", "mock")


def _latest(root: Path, filename: str) -> Path:
    return root / "storage" / "latest" / filename


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text_has_any(value: Any, needles: tuple[str, ...]) -> bool:
    text = str(value or "").lower()
    return any(token in text for token in needles)


def _collect_artifact_hashes(root: Path, names: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in names:
        path = _latest(root, name)
        out[name] = {
            "exists": path.exists(),
            "path": str(path),
            "sha256": sha256_file(path) if path.exists() else None,
        }
    return out


def _normalize_optional_health(data_snapshot: Mapping[str, Any], feature_store: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_health: dict[str, Any] = {}
    for source in (data_snapshot.get("optional_data_health") or {}, feature_store.get("optional_data_health") or {}):
        if isinstance(source, Mapping):
            raw_health.update(dict(source))

    normalized: dict[str, dict[str, Any]] = {}
    for name in EXPECTED_OPTIONAL_SOURCES:
        health: dict[str, Any] = {}
        for alias in OPTIONAL_SOURCE_ALIASES.get(name, (name,)):
            health = _as_dict(raw_health.get(alias))
            if health:
                break
        collector_status = str(health.get("collector_status") or health.get("status") or "missing")
        neutral = bool(health.get("neutral_due_to_missing"))
        missing = collector_status in {"missing", "unavailable", "error", "failed", "disabled"} or neutral
        stale = bool(health.get("stale"))
        normalized[name] = {
            "source": str(health.get("source") or name),
            "collector_status": collector_status,
            "missing": bool(missing),
            "stale": stale,
            "neutral_due_to_missing": neutral,
            "neutral_due_to_missing_explicit": "neutral_due_to_missing" in health if health else missing,
            "collector_error": health.get("collector_error") or health.get("error"),
            "last_success_utc": health.get("last_success_utc"),
        }
    return normalized


def _price_hard_required_checks(data_health: Mapping[str, Any], data_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    source_type = str(data_health.get("source_type") or data_snapshot.get("source_status") or "unknown")
    quality = str(data_health.get("data_quality") or data_snapshot.get("data_quality_status") or "unknown")
    candle_count = int(data_health.get("candle_count") or 0)
    latest_candle_time = data_health.get("latest_candle_time")
    hard_required_present = candle_count > 0 or bool(data_snapshot.get("hard_required_sources_present"))
    unsafe_text = " ".join([
        source_type,
        quality,
        str(data_health.get("problems") or []),
        str(data_snapshot.get("source_status") or ""),
    ])
    quality_lower = quality.lower()
    return {
        "hard_required_price_present": hard_required_present,
        "price_latest_candle_time_present": bool(latest_candle_time) or bool(data_snapshot.get("timestamp_end_utc") or data_snapshot.get("price_timestamp_end_utc")),
        "price_source_stale": bool(data_health.get("price_source_stale") or data_snapshot.get("price_source_stale") or (data_snapshot.get("stale_source_count", 0) and data_snapshot.get("data_quality_status") == "blocked_stale_price")),
        "price_source_fallback": bool(data_health.get("is_fallback") or data_snapshot.get("fallback_flag")) or "fallback" in unsafe_text.lower() or quality_lower == "blocked_fallback",
        "price_source_synthetic": bool(data_health.get("is_synthetic") or data_snapshot.get("synthetic_flag")) or "synthetic" in unsafe_text.lower() or quality_lower == "blocked_synthetic",
        "price_source_sample": bool(data_snapshot.get("sample_flag")) or "sample" in unsafe_text.lower() or quality_lower == "blocked_sample",
        "price_source_mock": bool(data_snapshot.get("mock_flag")) or "mock" in unsafe_text.lower() or quality_lower == "blocked_mock",
        "source_type": source_type,
        "data_quality": quality,
        "candle_count": candle_count,
        "latest_candle_time": latest_candle_time or data_snapshot.get("price_timestamp_end_utc"),
        "price_timestamp_start_utc": data_snapshot.get("price_timestamp_start_utc"),
        "price_timestamp_end_utc": data_snapshot.get("price_timestamp_end_utc"),
        "price_source_age_sec": data_snapshot.get("price_source_age_sec"),
        "price_source_max_age_sec": data_snapshot.get("price_source_max_age_sec"),
    }


def _lineage_checks(data_snapshot: Mapping[str, Any], feature_store: Mapping[str, Any]) -> dict[str, Any]:
    missing_data_snapshot_fields = [field for field in REQUIRED_DATA_SNAPSHOT_FIELDS if not data_snapshot.get(field)]
    missing_feature_fields = [field for field in REQUIRED_FEATURE_STORE_FIELDS if not feature_store.get(field)]
    data_snapshot_id_match = bool(data_snapshot.get("data_snapshot_id")) and data_snapshot.get("data_snapshot_id") == feature_store.get("data_snapshot_id")
    source_bundle_match = bool(data_snapshot.get("source_bundle_sha256")) and data_snapshot.get("source_bundle_sha256") == feature_store.get("source_bundle_sha256")
    feature_snapshot_id_present = bool(feature_store.get("feature_snapshot_id"))
    feature_matrix_sha_present = bool(feature_store.get("feature_matrix_sha256"))
    return {
        "missing_data_snapshot_fields": missing_data_snapshot_fields,
        "missing_feature_store_fields": missing_feature_fields,
        "data_snapshot_id_match": data_snapshot_id_match,
        "source_bundle_sha256_match": source_bundle_match,
        "feature_snapshot_id_present": feature_snapshot_id_present,
        "feature_matrix_sha256_present": feature_matrix_sha_present,
        "lineage_complete": not missing_data_snapshot_fields and not missing_feature_fields and data_snapshot_id_match and source_bundle_match and feature_snapshot_id_present and feature_matrix_sha_present,
    }




def _live_candidate_foundation_checks(
    data_snapshot: Mapping[str, Any],
    feature_store: Mapping[str, Any],
    price_checks: Mapping[str, Any],
    optional_health: Mapping[str, Mapping[str, Any]],
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    checks = dict(data_snapshot.get("live_candidate_eligibility_checks") or {})
    if not checks:
        checks = {
            "hard_required_price_present": bool(price_checks.get("hard_required_price_present")),
            "price_timestamp_range_present": bool(price_checks.get("price_timestamp_start_utc") and price_checks.get("price_timestamp_end_utc")),
            "price_source_fresh": not bool(price_checks.get("price_source_stale")),
            "no_fallback_price": not bool(price_checks.get("price_source_fallback")),
            "no_synthetic_price": not bool(price_checks.get("price_source_synthetic")),
            "no_sample_price": not bool(price_checks.get("price_source_sample")),
            "no_mock_price": not bool(price_checks.get("price_source_mock")),
            "optional_missing_count_zero": not any(h.get("missing") for h in optional_health.values()),
            "optional_stale_count_zero": not any(h.get("stale") for h in optional_health.values()),
            "all_optional_sources_live_candidate_eligible": bool(optional_health) and all(
                not h.get("missing") and not h.get("stale") for h in optional_health.values()
            ),
        }
    feature_unsafe_clear = not any(bool(feature_store.get(field)) for field in ("fallback_used", "synthetic_used", "sample_used"))
    feature_live_candidate_match = bool(feature_store.get("live_candidate_eligible")) == bool(data_snapshot.get("live_candidate_eligible"))
    checks["feature_lineage_complete"] = bool(lineage.get("lineage_complete"))
    checks["feature_unsafe_flags_clear"] = feature_unsafe_clear
    checks["feature_live_candidate_flag_matches_data_snapshot"] = feature_live_candidate_match

    reason_by_check = {
        "hard_required_price_present": "MISSING_HARD_REQUIRED_PRICE_DATA",
        "price_timestamp_range_present": "MISSING_PRICE_TIMESTAMP_RANGE",
        "price_source_fresh": "STALE_PRICE_DATA_BLOCKS_LIVE_CANDIDATE",
        "no_fallback_price": "FALLBACK_PRICE_DATA_BLOCKS_LIVE_CANDIDATE",
        "no_synthetic_price": "SYNTHETIC_PRICE_DATA_BLOCKS_LIVE_CANDIDATE",
        "no_sample_price": "SAMPLE_PRICE_DATA_BLOCKS_LIVE_CANDIDATE",
        "no_mock_price": "MOCK_PRICE_DATA_BLOCKS_LIVE_CANDIDATE",
        "optional_missing_count_zero": "OPTIONAL_DATA_MISSING_LIVE_CANDIDATE_BLOCKED",
        "optional_stale_count_zero": "OPTIONAL_DATA_STALE_LIVE_CANDIDATE_BLOCKED",
        "all_optional_sources_live_candidate_eligible": "OPTIONAL_DATA_HEALTH_LIVE_CANDIDATE_BLOCKED",
        "feature_lineage_complete": "INCOMPLETE_DATA_FEATURE_LINEAGE",
        "feature_unsafe_flags_clear": "UNSAFE_FEATURE_MATRIX_SOURCE_FLAGS",
        "feature_live_candidate_flag_matches_data_snapshot": "FEATURE_DATA_LIVE_CANDIDATE_FLAG_MISMATCH",
    }
    block_reasons = sorted(reason for check, reason in reason_by_check.items() if not bool(checks.get(check)))
    eligible = bool(data_snapshot.get("live_candidate_eligible")) and bool(feature_store.get("live_candidate_eligible")) and not block_reasons
    return {
        "version": LIVE_CANDIDATE_DATA_FOUNDATION_VERSION,
        "eligible": eligible,
        "checks": checks,
        "block_reasons": block_reasons,
        "data_quality_status": data_snapshot.get("data_quality_status"),
        "data_snapshot_live_candidate_eligible": bool(data_snapshot.get("live_candidate_eligible")),
        "feature_store_live_candidate_eligible": bool(feature_store.get("live_candidate_eligible")),
        "runtime_permission_source": False,
        "order_submission_performed": False,
    }


def build_paper_data_quality_gate_report(*, project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root or Path.cwd()).resolve()
    created = utc_now_canonical()
    data_health = _as_dict(read_json(_latest(root, "data_health_report.json"), default={}))
    data_snapshot = _as_dict(read_json(_latest(root, "data_snapshot_manifest.json"), default={}))
    feature_store = _as_dict(read_json(_latest(root, "feature_store_manifest.json"), default={}))

    artifacts = _collect_artifact_hashes(root, REQUIRED_LATEST_ARTIFACTS + LINEAGE_ARTIFACTS)
    missing_artifacts = [name for name, meta in artifacts.items() if not meta["exists"]]
    optional_health = _normalize_optional_health(data_snapshot, feature_store)
    price_checks = _price_hard_required_checks(data_health, data_snapshot)
    lineage = _lineage_checks(data_snapshot, feature_store)
    live_candidate_foundation = _live_candidate_foundation_checks(data_snapshot, feature_store, price_checks, optional_health, lineage)

    block_reasons: list[str] = []
    if not data_health:
        block_reasons.append("MISSING_DATA_HEALTH_REPORT")
    if missing_artifacts:
        block_reasons.extend([f"MISSING_LATEST_ARTIFACT:{name}" for name in missing_artifacts])
    if not price_checks["hard_required_price_present"]:
        block_reasons.append("MISSING_HARD_REQUIRED_PRICE_DATA")
    if not price_checks["price_latest_candle_time_present"]:
        block_reasons.append("MISSING_PRICE_FRESHNESS_EVIDENCE")
    if price_checks["price_source_stale"]:
        block_reasons.append("STALE_PRICE_DATA_BLOCKS_PAPER_CANDIDATE")
    if price_checks["price_source_fallback"]:
        block_reasons.append("FALLBACK_PRICE_DATA_BLOCKS_PAPER_CANDIDATE")
    if price_checks["price_source_synthetic"]:
        block_reasons.append("SYNTHETIC_PRICE_DATA_BLOCKS_PAPER_CANDIDATE")
    if price_checks["price_source_sample"]:
        block_reasons.append("SAMPLE_PRICE_DATA_BLOCKS_PAPER_CANDIDATE")
    if price_checks["price_source_mock"]:
        block_reasons.append("MOCK_PRICE_DATA_BLOCKS_PAPER_CANDIDATE")
    if not lineage["lineage_complete"]:
        block_reasons.append("INCOMPLETE_DATA_FEATURE_LINEAGE")

    optional_missing = [name for name, health in optional_health.items() if health["missing"]]
    optional_stale = [name for name, health in optional_health.items() if health["stale"]]
    optional_without_explicit_neutral = [
        name for name, health in optional_health.items()
        if health["missing"] and not health["neutral_due_to_missing_explicit"]
    ]
    if optional_without_explicit_neutral:
        block_reasons.extend([f"OPTIONAL_MISSING_WITHOUT_EXPLICIT_NEUTRAL:{name}" for name in optional_without_explicit_neutral])

    passed = len(block_reasons) == 0
    status = STATUS_PAPER_DATA_QUALITY_PASSED_REVIEW_ONLY if passed else STATUS_PAPER_DATA_QUALITY_BLOCKED_REVIEW_ONLY
    report = {
        "paper_data_quality_gate_id": stable_id("paper_data_quality_gate", {"created_at_utc": created, "status": status, "root": str(root)}, 24),
        "version": PAPER_DATA_QUALITY_GATE_VERSION,
        "created_at_utc": created,
        "status": status,
        "passed": passed,
        "blocked": not passed,
        "fail_closed": not passed,
        "review_only": True,
        "paper_candidate_allowed": passed,
        "live_candidate_eligible": False,
        "live_candidate_data_foundation_eligible": bool(live_candidate_foundation["eligible"]),
        "live_candidate_data_foundation": live_candidate_foundation,
        "signed_testnet_unlock_authority": False,
        "live_execution_unlock_authority": False,
        "runtime_permission_source": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "order_submission_performed": False,
        "auto_promotion_allowed": False,
        "block_reasons": sorted(set(block_reasons)),
        "required_latest_artifacts": list(REQUIRED_LATEST_ARTIFACTS),
        "lineage_artifacts": list(LINEAGE_ARTIFACTS),
        "missing_latest_artifacts": missing_artifacts,
        "artifact_sha256": artifacts,
        "price_hard_required_checks": price_checks,
        "optional_data_health": optional_health,
        "missing_optional_sources": optional_missing,
        "stale_optional_sources": optional_stale,
        "optional_missing_without_explicit_neutral": optional_without_explicit_neutral,
        "neutral_due_to_missing_policy": "optional_missing_must_be_explicit_and_review_only",
        "live_candidate_block_reasons": live_candidate_foundation["block_reasons"],
        "lineage_checks": lineage,
        "data_snapshot_id": data_snapshot.get("data_snapshot_id"),
        "feature_snapshot_id": feature_store.get("feature_snapshot_id"),
        "feature_matrix_sha256": feature_store.get("feature_matrix_sha256"),
        "source_bundle_sha256": data_snapshot.get("source_bundle_sha256") or feature_store.get("source_bundle_sha256"),
        "next_phase": "Phase 3 Paper Strategy Validation" if passed else "Resolve Phase 2 data quality blockers before paper validation",
    }
    report["paper_data_quality_gate_sha256"] = sha256_json(report)
    return report


def persist_paper_data_quality_gate_report(*, cfg: AppConfig | None = None, project_root: str | Path | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    root = Path(project_root or cfg.root).resolve()
    report = build_paper_data_quality_gate_report(project_root=root)

    latest_report_path = root / "storage" / "latest" / "paper_data_quality_gate_report.json"
    archive_report_path = root / "storage" / "data_quality" / "paper_data_quality_gate_report.json"
    atomic_write_json(latest_report_path, report)
    atomic_write_json(archive_report_path, report)

    registry_record = append_registry_record(
        registry_path(cfg, PAPER_DATA_QUALITY_REGISTRY_NAME),
        report,
        registry_name=PAPER_DATA_QUALITY_REGISTRY_NAME,
        id_field="paper_data_quality_gate_id",
        hash_field="paper_data_quality_gate_registry_record_sha256",
        id_prefix="paper_data_quality_gate",
    )
    atomic_write_json(root / "storage" / "latest" / "paper_data_quality_gate_registry_record.json", registry_record)
    return report
