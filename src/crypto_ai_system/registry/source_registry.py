from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import stable_id, utc_now_canonical

SOURCE_REGISTRY_VERSION = "step283_source_registry_v1"
PRICE_FRAME_HINTS = ("price", "ohlcv", "candle")
OPTIONAL_HINTS = ("binance", "coinmetrics", "farside", "defillama", "etf", "stablecoin", "exchange_flow")


def _timestamp_range(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "start_utc": summary.get("min_timestamp_utc"),
        "end_utc": summary.get("max_timestamp_utc"),
    }


def _data_group(name: str) -> str:
    low = name.lower()
    if any(token in low for token in ("ohlcv", "price", "candle")):
        return "price_structure"
    if "binance" in low or "funding" in low or "open_interest" in low or "derivatives" in low:
        return "derivatives_positioning"
    if "coinmetrics" in low or "exchange_flow" in low or "netflow" in low:
        return "exchange_flow"
    if "farside" in low or "etf" in low:
        return "etf_flow"
    if "defillama" in low or "stablecoin" in low:
        return "stablecoin_liquidity"
    return "unknown"


def _required_or_optional(name: str) -> str:
    low = name.lower()
    if any(token in low for token in PRICE_FRAME_HINTS):
        return "required"
    if any(token in low for token in OPTIONAL_HINTS):
        return "optional"
    return "optional"


def _flag_from_text(*values: Any, needle: str) -> bool:
    haystack = " ".join(str(v).lower() for v in values if v is not None)
    return needle in haystack


def build_source_registry_records(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    created = str(manifest.get("created_at_utc") or utc_now_canonical())
    source_bundle_sha256 = manifest.get("source_bundle_sha256")
    records: list[dict[str, Any]] = []

    for name, summary in sorted((manifest.get("raw_frames") or {}).items()):
        summary = dict(summary or {})
        required = _required_or_optional(name)
        fallback = bool(_flag_from_text(name, manifest.get("source_status"), needle="fallback"))
        synthetic = bool(_flag_from_text(name, manifest.get("source_status"), needle="synthetic"))
        sample = bool(_flag_from_text(name, manifest.get("source_status"), needle="sample"))
        stale = bool(summary.get("stale") or False)
        payload = {
            "source_name": name,
            "source_type": "raw_frame",
            "data_group": _data_group(name),
            "endpoint_or_file": name,
            "timestamp_range": _timestamp_range(summary),
            "fetched_at_utc": created,
            "freshness_status": "stale" if stale else "fresh_or_unchecked",
            "reliability_score": 1.0 if required == "required" and not any([fallback, synthetic, sample, stale]) else 0.5,
            "required_or_optional": required,
            "missing_policy": "fail_closed" if required == "required" else "neutral_due_to_missing",
            "neutral_due_to_missing": False,
            "fallback_flag": fallback,
            "synthetic_flag": synthetic,
            "sample_flag": sample,
            "stale_flag": stale,
            "source_file_hash": summary.get("frame_sha256"),
            "source_bundle_sha256": source_bundle_sha256,
            "created_at_utc": created,
            "version": SOURCE_REGISTRY_VERSION,
        }
        payload["source_id"] = stable_id("source", payload, 24)
        records.append(payload)

    for collector, health in sorted((manifest.get("optional_data_health") or {}).items()):
        health = dict(health or {})
        neutral = bool(health.get("neutral_due_to_missing"))
        stale = bool(health.get("stale"))
        payload = {
            "source_name": str(health.get("source") or collector),
            "source_type": "optional_collector",
            "data_group": str(health.get("matrix_group") or _data_group(collector)),
            "endpoint_or_file": str(health.get("source") or collector),
            "timestamp_range": {"start_utc": health.get("last_success_utc"), "end_utc": health.get("last_success_utc")},
            "fetched_at_utc": created,
            "freshness_status": "stale" if stale else str(health.get("collector_status") or "unknown"),
            "reliability_score": 1.0 if health.get("collector_status") == "ok" and not stale else 0.0,
            "required_or_optional": "optional",
            "missing_policy": "neutral_due_to_missing",
            "neutral_due_to_missing": neutral,
            "fallback_flag": False,
            "synthetic_flag": False,
            "sample_flag": False,
            "stale_flag": stale,
            "source_file_hash": None,
            "source_bundle_sha256": source_bundle_sha256,
            "collector_status": health.get("collector_status"),
            "collector_error": health.get("collector_error"),
            "source_age_sec": health.get("source_age_sec"),
            "last_success_utc": health.get("last_success_utc"),
            "created_at_utc": created,
            "version": SOURCE_REGISTRY_VERSION,
        }
        payload["source_id"] = stable_id("source", payload, 24)
        records.append(payload)

    for name, summary in sorted((manifest.get("source_files") or {}).items()):
        summary = dict(summary or {})
        path_text = str(summary.get("path") or name)
        payload = {
            "source_name": name,
            "source_type": "source_file",
            "data_group": _data_group(name),
            "endpoint_or_file": path_text,
            "timestamp_range": {"start_utc": None, "end_utc": None},
            "fetched_at_utc": created,
            "freshness_status": "file_present" if summary.get("exists") else "missing",
            "reliability_score": 1.0 if summary.get("exists") else 0.0,
            "required_or_optional": _required_or_optional(name),
            "missing_policy": "fail_closed" if _required_or_optional(name) == "required" else "neutral_due_to_missing",
            "neutral_due_to_missing": not bool(summary.get("exists")),
            "fallback_flag": _flag_from_text(path_text, needle="fallback"),
            "synthetic_flag": _flag_from_text(path_text, needle="synthetic"),
            "sample_flag": _flag_from_text(path_text, needle="sample"),
            "stale_flag": False,
            "source_file_hash": summary.get("sha256"),
            "source_bundle_sha256": source_bundle_sha256,
            "created_at_utc": created,
            "version": SOURCE_REGISTRY_VERSION,
        }
        payload["source_id"] = stable_id("source", payload, 24)
        records.append(payload)

    return records


def persist_source_registry_records(cfg: AppConfig, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    path = registry_path(cfg, "source_registry")
    for record in build_source_registry_records(manifest):
        out.append(
            append_registry_record(
                path,
                record,
                registry_name="source_registry",
                id_field="source_id",
                hash_field="source_registry_record_sha256",
                id_prefix="source",
            )
        )
    return out
