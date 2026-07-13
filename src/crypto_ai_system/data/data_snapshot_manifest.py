from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from crypto_ai_system.config import AppConfig
from crypto_ai_system.utils.audit import sha256_file, sha256_json, stable_id, utc_now_canonical


DATA_SNAPSHOT_MANIFEST_VERSION = "step270_raw_data_snapshot_manifest_v1"
OPTIONAL_DATA_HEALTH_VERSION = "step270_optional_data_health_v1"

OPTIONAL_COLLECTOR_GROUPS: dict[str, dict[str, str]] = {
    "binance_futures": {
        "source": "binance_futures_public",
        "feature_frame": "binance_derivatives_features",
        "matrix_group": "extra_derivatives_features",
    },
    "coinmetrics_exchange_flow": {
        "source": "coinmetrics_community",
        "feature_frame": "exchange_flow_features",
        "matrix_group": "exchange_flow_features",
    },
    "farside_etf_flow": {
        "source": "farside_etf_flow",
        "feature_frame": "etf_flow_features",
        "matrix_group": "etf_flow_features",
    },
    "defillama_stablecoins": {
        "source": "defillama_stablecoins",
        "feature_frame": "stablecoin_liquidity_features",
        "matrix_group": "stablecoin_liquidity_features",
    },
}

PRICE_FRAME_NAME_TOKENS: tuple[str, ...] = ("ohlcv", "price", "candle")
UNSAFE_SOURCE_TOKENS: tuple[str, ...] = ("fallback", "synthetic", "sample", "mock")
LIVE_CANDIDATE_DATA_FOUNDATION_VERSION = "phase_b_live_candidate_data_foundation_v1"

FEATURE_FRAME_TO_COLLECTOR = {
    spec["feature_frame"]: name for name, spec in OPTIONAL_COLLECTOR_GROUPS.items()
}


def _canonical_ts(value: Any) -> str | None:
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_ts(now_utc: str | None = None) -> pd.Timestamp:
    value = now_utc or utc_now_canonical()
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        ts = pd.to_datetime(utc_now_canonical(), utc=True)
    return ts


def _frame_hash(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty:
        return sha256_json([])
    canonical = frame.copy().replace({np.nan: None})
    canonical = canonical.reindex(sorted(canonical.columns), axis=1)
    return sha256_json(canonical.to_dict(orient="records"))


def _frame_timestamp_range(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    if frame is None or frame.empty or "timestamp" not in frame.columns:
        return None, None
    ts = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dropna()
    if ts.empty:
        return None, None
    return ts.min().strftime("%Y-%m-%dT%H:%M:%SZ"), ts.max().strftime("%Y-%m-%dT%H:%M:%SZ")


def _latest_timestamp_for_frames(frames: Mapping[str, pd.DataFrame], frame_names: list[str]) -> str | None:
    latest: pd.Timestamp | None = None
    for name in frame_names:
        frame = frames.get(name)
        if frame is None or frame.empty or "timestamp" not in frame.columns:
            continue
        ts = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dropna()
        if ts.empty:
            continue
        candidate = ts.max()
        if latest is None or candidate > latest:
            latest = candidate
    return latest.strftime("%Y-%m-%dT%H:%M:%SZ") if latest is not None else None


def _collector_frame_names(collector_name: str, raw_frames: Mapping[str, pd.DataFrame]) -> list[str]:
    if collector_name == "binance_futures":
        return [name for name in raw_frames if name.startswith("binance_")]
    if collector_name == "coinmetrics_exchange_flow":
        return ["coinmetrics_exchange_flow"]
    if collector_name == "farside_etf_flow":
        return ["farside_btc_etf_flow"]
    if collector_name == "defillama_stablecoins":
        return [name for name in raw_frames if name.startswith("defillama_")]
    return []


def _max_age_sec_for(cfg: AppConfig | None, collector_name: str) -> float:
    if cfg is None:
        return 72 * 3600.0
    specific = cfg.get(f"additional_data.health.{collector_name}.max_age_sec")
    if specific is not None:
        try:
            return float(specific)
        except Exception:
            pass
    default = cfg.get("additional_data.health.max_age_sec", 72 * 3600)
    try:
        return float(default)
    except Exception:
        return 72 * 3600.0


def _error_text(status: Mapping[str, Any]) -> str | None:
    error = status.get("error")
    if error:
        return str(error)
    errors = status.get("errors")
    if isinstance(errors, dict) and errors:
        return json.dumps(errors, sort_keys=True, ensure_ascii=False, default=str)
    if isinstance(errors, list) and errors:
        return json.dumps(errors, sort_keys=True, ensure_ascii=False, default=str)
    return None


def build_optional_source_health(
    collector_name: str,
    status: Mapping[str, Any] | None,
    raw_frames: Mapping[str, pd.DataFrame],
    cfg: AppConfig | None = None,
    *,
    now_utc: str | None = None,
) -> dict[str, Any]:
    spec = OPTIONAL_COLLECTOR_GROUPS[collector_name]
    status = dict(status or {})
    frame_names = _collector_frame_names(collector_name, raw_frames)
    rows = int(sum(len(raw_frames.get(name, pd.DataFrame())) for name in frame_names))
    enabled = bool(status.get("enabled", True))
    data_available = bool(status.get("data_available", rows > 0 or bool(status.get("frames"))))
    ok = bool(status.get("ok", False))
    collector_error = _error_text(status)
    last_success_utc = _latest_timestamp_for_frames(raw_frames, frame_names) if data_available else None
    source_age_sec: float | None = None
    stale = False
    if last_success_utc:
        age = (_now_ts(now_utc) - pd.to_datetime(last_success_utc, utc=True)).total_seconds()
        source_age_sec = max(0.0, float(age))
        stale = source_age_sec > _max_age_sec_for(cfg, collector_name)

    if not enabled:
        collector_status = "disabled"
    elif collector_error and not data_available:
        collector_status = "error"
    elif not data_available:
        collector_status = "missing"
    elif stale:
        collector_status = "stale"
    elif ok or data_available:
        collector_status = "ok"
    else:
        collector_status = "error"

    return {
        "collector": collector_name,
        "source": str(status.get("source") or spec["source"]),
        "feature_frame": spec["feature_frame"],
        "matrix_group": spec["matrix_group"],
        "enabled": enabled,
        "ok": bool(ok and data_available and not stale),
        "data_available": data_available,
        "rows": rows,
        "collector_status": collector_status,
        "collector_error": collector_error,
        "source_age_sec": source_age_sec,
        "stale": bool(stale),
        "neutral_due_to_missing": bool(not data_available),
        "last_success_utc": last_success_utc,
        "live_candidate_eligible": bool(data_available and not stale and collector_status == "ok"),
        "version": OPTIONAL_DATA_HEALTH_VERSION,
    }


def build_optional_data_health(
    source_status: Mapping[str, Any],
    raw_frames: Mapping[str, pd.DataFrame],
    cfg: AppConfig | None = None,
    *,
    now_utc: str | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        collector: build_optional_source_health(collector, source_status.get(collector, {}), raw_frames, cfg, now_utc=now_utc)
        for collector in OPTIONAL_COLLECTOR_GROUPS
    }


def annotate_feature_frames_with_optional_health(
    feature_frames: Mapping[str, pd.DataFrame],
    optional_data_health: Mapping[str, Mapping[str, Any]],
) -> dict[str, pd.DataFrame]:
    annotated: dict[str, pd.DataFrame] = {}
    for name, frame in (feature_frames or {}).items():
        if frame is None:
            continue
        out = frame.copy()
        collector = FEATURE_FRAME_TO_COLLECTOR.get(name)
        health = optional_data_health.get(collector, {}) if collector else {}
        if health:
            matrix_group = str(health.get("matrix_group") or name)
            values = {
                "collector_status": health.get("collector_status"),
                "collector_error": health.get("collector_error"),
                "source_age_sec": health.get("source_age_sec"),
                "stale": bool(health.get("stale", False)),
                "neutral_due_to_missing": bool(health.get("neutral_due_to_missing", False)),
                "last_success_utc": health.get("last_success_utc"),
                "live_candidate_eligible": bool(health.get("live_candidate_eligible", False)),
            }
            for key, value in values.items():
                out[key] = value
                out[f"{matrix_group}_{key}"] = value
        annotated[name] = out
    return annotated


def _is_price_frame_name(name: str) -> bool:
    low = str(name).lower()
    return any(token in low for token in PRICE_FRAME_NAME_TOKENS)


def _timestamp_bounds_from_summaries(
    frame_summaries: Mapping[str, Mapping[str, Any]],
    *,
    names: set[str] | None = None,
) -> tuple[str | None, str | None]:
    starts: list[str] = []
    ends: list[str] = []
    for name, summary in frame_summaries.items():
        if names is not None and name not in names:
            continue
        if not isinstance(summary, Mapping):
            continue
        if summary.get("min_timestamp_utc"):
            starts.append(str(summary["min_timestamp_utc"]))
        if summary.get("max_timestamp_utc"):
            ends.append(str(summary["max_timestamp_utc"]))
    return (min(starts) if starts else None, max(ends) if ends else None)


def _price_frame_names(frame_summaries: Mapping[str, Mapping[str, Any]]) -> set[str]:
    out: set[str] = set()
    for name, summary in frame_summaries.items():
        if _is_price_frame_name(name) and int((summary or {}).get("rows") or 0) > 0:
            out.add(name)
    return out


def _configured_price_max_age_sec(cfg: AppConfig | None) -> float | None:
    if cfg is None:
        return None
    for path in (
        "data.live_candidate.max_price_age_sec",
        "data.live_candidate_price_max_age_sec",
        "data.price_source_max_age_sec",
    ):
        value = cfg.get(path)
        if value is not None:
            try:
                return float(value)
            except Exception:
                continue
    hours = cfg.get("data.local_price_data_max_age_hours")
    if hours is not None:
        try:
            return float(hours) * 3600.0
        except Exception:
            return None
    return None


def _truthy_nested(mapping: Mapping[str, Any], names: tuple[str, ...]) -> bool:
    for name in names:
        if bool(mapping.get(name)):
            return True
    for value in mapping.values():
        if isinstance(value, Mapping) and _truthy_nested(value, names):
            return True
    return False


def _unsafe_tokens_in_payload(*payloads: Any) -> list[str]:
    text = json.dumps(payloads, sort_keys=True, ensure_ascii=False, default=str).lower()
    return sorted(token for token in UNSAFE_SOURCE_TOKENS if token in text)


def _build_optional_health_summary(optional_health: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    missing = sorted(str(name) for name, health in optional_health.items() if bool((health or {}).get("neutral_due_to_missing")))
    stale = sorted(str(name) for name, health in optional_health.items() if bool((health or {}).get("stale")))
    unavailable = sorted(
        str(name)
        for name, health in optional_health.items()
        if str((health or {}).get("collector_status") or "").lower() in {"missing", "error", "failed", "disabled", "unavailable"}
    )
    eligible = sorted(str(name) for name, health in optional_health.items() if bool((health or {}).get("live_candidate_eligible")))
    return {
        "expected_optional_source_count": len(OPTIONAL_COLLECTOR_GROUPS),
        "eligible_optional_source_count": len(eligible),
        "missing_optional_source_count": len(missing),
        "stale_optional_source_count": len(stale),
        "unavailable_optional_source_count": len(unavailable),
        "missing_optional_sources": missing,
        "stale_optional_sources": stale,
        "unavailable_optional_sources": unavailable,
        "eligible_optional_sources": eligible,
        "all_optional_sources_live_candidate_eligible": bool(optional_health) and len(eligible) == len(OPTIONAL_COLLECTOR_GROUPS),
    }


def _candidate_block_reasons(checks: Mapping[str, bool]) -> list[str]:
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
    }
    return sorted(reason for check, reason in reason_by_check.items() if not bool(checks.get(check)))


def build_data_snapshot_manifest(
    raw_frames: Mapping[str, pd.DataFrame],
    source_status: Mapping[str, Any],
    cfg: AppConfig | None = None,
    *,
    source_files: Mapping[str, str] | None = None,
    optional_data_health: Mapping[str, Mapping[str, Any]] | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = created_at_utc or utc_now_canonical()
    optional_health = dict(optional_data_health or build_optional_data_health(source_status, raw_frames, cfg, now_utc=created))
    frame_summaries: dict[str, dict[str, Any]] = {}
    for name, frame in sorted((raw_frames or {}).items()):
        if not isinstance(frame, pd.DataFrame):
            continue
        min_ts, max_ts = _frame_timestamp_range(frame)
        frame_summaries[name] = {
            "rows": int(len(frame)),
            "columns": sorted(map(str, frame.columns)),
            "frame_sha256": _frame_hash(frame),
            "min_timestamp_utc": min_ts,
            "max_timestamp_utc": max_ts,
        }

    file_summaries: dict[str, dict[str, Any]] = {}
    for name, path_text in sorted((source_files or {}).items()):
        path = Path(path_text)
        file_summaries[name] = {
            "path": str(path),
            "exists": path.exists(),
            "sha256": sha256_file(path) if path.exists() else None,
        }

    source_bundle_sha256 = sha256_json({
        "frames": {k: v["frame_sha256"] for k, v in frame_summaries.items()},
        "files": {k: v["sha256"] for k, v in file_summaries.items()},
        "optional_data_health": optional_health,
    })
    payload = {
        "source_bundle_sha256": source_bundle_sha256,
        "frame_count": len(frame_summaries),
        "source_status": source_status,
        "optional_data_health": optional_health,
    }
    data_snapshot_id = stable_id("data_snapshot", payload, 24)
    price_frame_names = _price_frame_names(frame_summaries)
    price_frames_present = bool(price_frame_names)
    timestamp_start_utc, timestamp_end_utc = _timestamp_bounds_from_summaries(frame_summaries)
    price_timestamp_start_utc, price_timestamp_end_utc = _timestamp_bounds_from_summaries(frame_summaries, names=price_frame_names)

    price_source_max_age_sec = _configured_price_max_age_sec(cfg)
    price_source_age_sec: float | None = None
    if price_timestamp_end_utc:
        price_source_age_sec = max(
            0.0,
            float((_now_ts(created) - pd.to_datetime(price_timestamp_end_utc, utc=True)).total_seconds()),
        )
    explicit_price_stale = _truthy_nested(source_status, ("price_source_stale", "stale_price", "price_stale", "stale"))
    price_source_stale = bool(
        explicit_price_stale
        or (
            price_source_max_age_sec is not None
            and price_source_age_sec is not None
            and price_source_age_sec > price_source_max_age_sec
        )
    )

    optional_summary = _build_optional_health_summary(optional_health)
    optional_sources_missing = list(optional_summary["missing_optional_sources"])
    stale_optional_sources = list(optional_summary["stale_optional_sources"])
    stale_optional_source_count = int(optional_summary["stale_optional_source_count"])
    unsafe_tokens = _unsafe_tokens_in_payload(source_status, file_summaries, frame_summaries)
    fallback_flag = "fallback" in unsafe_tokens
    synthetic_flag = "synthetic" in unsafe_tokens
    sample_flag = "sample" in unsafe_tokens
    mock_flag = "mock" in unsafe_tokens

    live_candidate_checks = {
        "hard_required_price_present": bool(price_frames_present),
        "price_timestamp_range_present": bool(price_timestamp_start_utc and price_timestamp_end_utc),
        "price_source_fresh": bool(price_frames_present and not price_source_stale),
        "no_fallback_price": not fallback_flag,
        "no_synthetic_price": not synthetic_flag,
        "no_sample_price": not sample_flag,
        "no_mock_price": not mock_flag,
        "optional_missing_count_zero": int(optional_summary["missing_optional_source_count"]) == 0,
        "optional_stale_count_zero": int(optional_summary["stale_optional_source_count"]) == 0,
        "all_optional_sources_live_candidate_eligible": bool(optional_summary["all_optional_sources_live_candidate_eligible"]),
    }
    live_candidate_block_reasons = _candidate_block_reasons(live_candidate_checks)

    if not price_frames_present:
        data_quality_status = "blocked_missing_price"
    elif price_source_stale:
        data_quality_status = "blocked_stale_price"
    elif fallback_flag:
        data_quality_status = "blocked_fallback"
    elif synthetic_flag:
        data_quality_status = "blocked_synthetic"
    elif sample_flag:
        data_quality_status = "blocked_sample"
    elif mock_flag:
        data_quality_status = "blocked_mock"
    elif stale_optional_sources:
        data_quality_status = "valid_with_optional_stale"
    elif optional_sources_missing:
        data_quality_status = "valid_with_optional_missing"
    else:
        data_quality_status = "valid"
    live_candidate_eligible = bool(data_quality_status == "valid" and not live_candidate_block_reasons)
    manifest_without_sha = {
        "data_snapshot_id": data_snapshot_id,
        "source_bundle_sha256": source_bundle_sha256,
        "raw_frames": frame_summaries,
        "source_files": file_summaries,
        "source_status": source_status,
        "optional_data_health": optional_health,
        "optional_data_health_summary": optional_summary,
        "hard_required_sources_present": bool(price_frames_present),
        "price_frame_names": sorted(price_frame_names),
        "timestamp_start_utc": timestamp_start_utc,
        "timestamp_end_utc": timestamp_end_utc,
        "price_timestamp_start_utc": price_timestamp_start_utc,
        "price_timestamp_end_utc": price_timestamp_end_utc,
        "price_source_age_sec": price_source_age_sec,
        "price_source_max_age_sec": price_source_max_age_sec,
        "price_source_stale": price_source_stale,
        "price_source_fresh": bool(price_frames_present and not price_source_stale),
        "optional_sources_missing": optional_sources_missing,
        "stale_optional_sources": stale_optional_sources,
        "missing_optional_source_count": int(optional_summary["missing_optional_source_count"]),
        "stale_optional_source_count": stale_optional_source_count,
        "stale_source_count": stale_optional_source_count + int(price_source_stale),
        "fallback_flag": bool(fallback_flag),
        "synthetic_flag": bool(synthetic_flag),
        "sample_flag": bool(sample_flag),
        "mock_flag": bool(mock_flag),
        "unsafe_price_source_tokens_detected": unsafe_tokens,
        "data_quality_status": data_quality_status,
        "live_candidate_eligibility_checks": live_candidate_checks,
        "live_candidate_block_reasons": live_candidate_block_reasons,
        "live_candidate_eligible": live_candidate_eligible,
        "created_at_utc": created,
        "version": DATA_SNAPSHOT_MANIFEST_VERSION,
        "hardening_version": "step285_data_snapshot_registry_hardening_v1",
        "live_candidate_data_foundation_version": LIVE_CANDIDATE_DATA_FOUNDATION_VERSION,
    }
    data_snapshot_sha256 = sha256_json(manifest_without_sha)
    manifest = dict(manifest_without_sha)
    manifest["data_snapshot_sha256"] = data_snapshot_sha256
    return manifest


def write_data_snapshot_manifest(path: str | Path, manifest: Mapping[str, Any]) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(manifest), indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    return str(p)


def persist_data_snapshot_registries(cfg: AppConfig, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Persist source and data snapshot registry records for an immutable manifest.

    Registry files are append-only. Damaged existing registries fail closed via
    RegistryIntegrityError and are not regenerated silently.
    """
    from crypto_ai_system.registry.data_snapshot_registry import persist_data_snapshot_registry_record
    from crypto_ai_system.registry.source_registry import persist_source_registry_records

    source_records = persist_source_registry_records(cfg, manifest)
    data_snapshot_record = persist_data_snapshot_registry_record(
        cfg,
        manifest,
        source_registry_records=source_records,
    )
    return {
        "source_registry_records": source_records,
        "data_snapshot_registry_record": data_snapshot_record,
    }
