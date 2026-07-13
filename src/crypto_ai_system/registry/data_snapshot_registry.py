from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.registry.source_registry import build_source_registry_records
from crypto_ai_system.utils.audit import sha256_json

DATA_SNAPSHOT_REGISTRY_VERSION = "step285_data_snapshot_registry_v1"


def _time_bounds(manifest: Mapping[str, Any]) -> tuple[str | None, str | None]:
    starts: list[str] = []
    ends: list[str] = []
    for summary in (manifest.get("raw_frames") or {}).values():
        if not isinstance(summary, Mapping):
            continue
        if summary.get("min_timestamp_utc"):
            starts.append(str(summary["min_timestamp_utc"]))
        if summary.get("max_timestamp_utc"):
            ends.append(str(summary["max_timestamp_utc"]))
    return (min(starts) if starts else None, max(ends) if ends else None)


def _infer_flags(manifest: Mapping[str, Any]) -> dict[str, bool]:
    text = " ".join(
        [
            str(manifest.get("source_status") or ""),
            " ".join((manifest.get("raw_frames") or {}).keys()),
            " ".join(str(v) for v in (manifest.get("source_files") or {}).values()),
        ]
    ).lower()
    return {
        "fallback_flag": "fallback" in text,
        "synthetic_flag": "synthetic" in text,
        "sample_flag": "sample" in text,
        "mock_flag": "mock" in text,
    }


def _price_source_present(manifest: Mapping[str, Any]) -> bool:
    for name, summary in (manifest.get("raw_frames") or {}).items():
        low = str(name).lower()
        if any(token in low for token in ("price", "ohlcv", "candle")) and int((summary or {}).get("rows") or 0) > 0:
            return True
    return False


def _optional_sources_missing(manifest: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    for collector, health in sorted((manifest.get("optional_data_health") or {}).items()):
        if bool((health or {}).get("neutral_due_to_missing")):
            missing.append(str(collector))
    return missing


def determine_data_quality_status(manifest: Mapping[str, Any]) -> str:
    flags = _infer_flags(manifest)
    if not _price_source_present(manifest):
        return "blocked_missing_price"
    if bool(manifest.get("price_source_stale")):
        return "blocked_stale_price"
    if flags["fallback_flag"]:
        return "blocked_fallback"
    if flags["synthetic_flag"]:
        return "blocked_synthetic"
    if flags["sample_flag"]:
        return "blocked_sample"
    if flags["mock_flag"]:
        return "blocked_mock"
    if int(manifest.get("stale_optional_source_count") or 0) > 0:
        return "valid_with_optional_stale"
    if _optional_sources_missing(manifest):
        return "valid_with_optional_missing"
    return "valid"


def build_data_snapshot_registry_record(
    manifest: Mapping[str, Any],
    *,
    source_registry_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    source_records = list(source_registry_records or build_source_registry_records(manifest))
    start, end = _time_bounds(manifest)
    flags = _infer_flags(manifest)
    optional_missing = _optional_sources_missing(manifest)
    optional_health = manifest.get("optional_data_health") or {}
    status = determine_data_quality_status(manifest)
    record = {
        "data_snapshot_id": manifest.get("data_snapshot_id"),
        "data_snapshot_sha256": manifest.get("data_snapshot_sha256"),
        "source_bundle_sha256": manifest.get("source_bundle_sha256"),
        "source_ids": [r.get("source_id") for r in source_records if r.get("source_id")],
        "timestamp_start_utc": start,
        "timestamp_end_utc": end,
        "created_at_utc": manifest.get("created_at_utc"),
        "hard_required_sources_present": _price_source_present(manifest),
        "optional_sources_missing": optional_missing,
        "fallback_flag": flags["fallback_flag"],
        "synthetic_flag": flags["synthetic_flag"],
        "sample_flag": flags["sample_flag"],
        "mock_flag": flags["mock_flag"],
        "price_source_stale": bool(manifest.get("price_source_stale")),
        "price_timestamp_start_utc": manifest.get("price_timestamp_start_utc"),
        "price_timestamp_end_utc": manifest.get("price_timestamp_end_utc"),
        "price_source_age_sec": manifest.get("price_source_age_sec"),
        "price_source_max_age_sec": manifest.get("price_source_max_age_sec"),
        "stale_source_count": int(sum(bool((h or {}).get("stale")) for h in optional_health.values())) + int(bool(manifest.get("price_source_stale"))),
        "stale_optional_source_count": int(manifest.get("stale_optional_source_count") or 0),
        "missing_optional_source_count": int(manifest.get("missing_optional_source_count") or len(optional_missing)),
        "live_candidate_eligibility_checks": manifest.get("live_candidate_eligibility_checks") or {},
        "live_candidate_block_reasons": manifest.get("live_candidate_block_reasons") or [],
        "data_quality_status": status,
        "live_candidate_eligible": bool(manifest.get("live_candidate_eligible")) and status == "valid",
        "version": DATA_SNAPSHOT_REGISTRY_VERSION,
    }
    record["data_snapshot_registry_record_sha256"] = sha256_json(record)
    return record


def persist_data_snapshot_registry_record(
    cfg: AppConfig,
    manifest: Mapping[str, Any],
    *,
    source_registry_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    record = build_data_snapshot_registry_record(manifest, source_registry_records=source_registry_records)
    return append_registry_record(
        registry_path(cfg, "data_snapshot_registry"),
        record,
        registry_name="data_snapshot_registry",
        id_field="data_snapshot_id",
        hash_field="data_snapshot_registry_record_sha256",
        id_prefix="data_snapshot",
    )
