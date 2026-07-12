from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.real_testnet_read_only_adapter import (
    build_real_testnet_read_only_adapter_evidence,
    build_read_only_testnet_adapter,
)
from crypto_ai_system.execution.testnet_secret_metadata_intake_v2 import (
    build_testnet_secret_metadata_intake_v2,
    persist_testnet_secret_metadata_intake_v2,
    run_testnet_secret_metadata_intake_latest,
    validate_testnet_secret_metadata_intake_v2,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical
from core.json_io import atomic_write_json

STEP305_REAL_READ_ONLY_VENUE_PROBE_VERSION = "step305_real_read_only_venue_probe_v1"
REAL_READ_ONLY_VENUE_PROBE_REGISTRY_NAME = "real_read_only_venue_probe_registry"

REQUIRED_READ_PROBES = [
    "balance_read_probe",
    "positions_read_probe",
    "open_orders_read_probe",
    "orderbook_read_probe",
    "fee_estimate_probe",
    "slippage_estimate_probe",
    "min_order_size_probe",
    "fetch_order_probe",
]


def _parse_canonical_utc(value: Any) -> datetime | None:
    if not is_canonical_utc_timestamp(value):
        return None
    return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _age_sec(value: Any) -> int | None:
    parsed = _parse_canonical_utc(value)
    if parsed is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def _payload_without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dict(payload).items() if k not in {"real_read_only_venue_probe_sha256", "created_at_utc"}}


def _normalize_scope(scope: Any) -> list[str]:
    if scope is None:
        return []
    if isinstance(scope, str):
        return [scope]
    if isinstance(scope, (list, tuple, set)):
        return [str(item) for item in scope]
    return [str(scope)]


def _response_timestamp(response: Mapping[str, Any]) -> Any:
    return dict(response or {}).get("created_at_utc")


def _probe_summary(probe: Mapping[str, Any], *, max_probe_age_sec: int) -> dict[str, Any]:
    data = dict(probe or {})
    response = data.get("adapter_response") or {}
    timestamp = _response_timestamp(response if isinstance(response, Mapping) else {}) or data.get("created_at_utc")
    age = _age_sec(timestamp)
    blockers: list[str] = []
    if data.get("valid") is not True:
        blockers.append("STEP305_READ_PROBE_INVALID")
    blockers.extend(str(reason) for reason in data.get("block_reasons") or [])
    if age is None:
        blockers.append("STEP305_READ_PROBE_TIMESTAMP_NOT_CANONICAL_UTC")
    elif age > max_probe_age_sec:
        blockers.append("STEP305_READ_PROBE_STALE_BLOCKED")
    if data.get("external_order_submission_performed") is not False:
        blockers.append("STEP305_READ_PROBE_EXTERNAL_SUBMISSION_PERFORMED")
    if data.get("testnet_order_submission_allowed") is not False:
        blockers.append("STEP305_READ_PROBE_TESTNET_ORDER_SUBMISSION_ALLOWED")
    return {
        "probe_name": data.get("probe_name"),
        "probe_hash": data.get("probe_hash"),
        "status": data.get("status"),
        "fresh": age is not None and age <= max_probe_age_sec,
        "source_age_sec": age,
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
    }


@dataclass(frozen=True)
class RealReadOnlyVenueProbePolicy:
    max_probe_age_sec: int = 600
    require_adapter_evidence: bool = True
    require_secret_metadata_validation: bool = True
    require_venue_match: bool = True
    require_environment_testnet: bool = True
    require_all_read_probes: bool = True
    require_place_cancel_disabled: bool = True
    require_metadata_only_secret: bool = True
    ready_for_signed_testnet_execution: bool = False
    testnet_order_submission_allowed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    signed_order_executor_enabled: bool = False
    external_order_submission_performed: bool = False
    live_trading_allowed_by_this_module: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_real_read_only_venue_probe(
    *,
    adapter_evidence: Mapping[str, Any] | None,
    secret_metadata_intake: Mapping[str, Any] | None,
    max_probe_age_sec: int = 600,
) -> dict[str, Any]:
    adapter_data = dict(adapter_evidence or {})
    secret_data = dict(secret_metadata_intake or {})
    embedded_secret_validation = secret_data.get("testnet_secret_metadata_validation") if isinstance(secret_data.get("testnet_secret_metadata_validation"), Mapping) else None
    secret_validation = dict(embedded_secret_validation) if embedded_secret_validation else validate_testnet_secret_metadata_intake_v2(secret_data)
    policy = RealReadOnlyVenueProbePolicy(max_probe_age_sec=max_probe_age_sec)
    blockers: list[str] = []

    if not adapter_data:
        blockers.append("STEP305_ADAPTER_EVIDENCE_MISSING")
    if not secret_data:
        blockers.append("STEP305_SECRET_METADATA_INTAKE_MISSING")
    if adapter_data.get("adapter_ready_for_read_only_testnet_probe") is not True:
        blockers.append("STEP305_ADAPTER_NOT_READY_FOR_READ_ONLY_PROBE")
    if adapter_data.get("all_read_probes_valid") is not True:
        blockers.append("STEP305_ADAPTER_READ_PROBES_NOT_ALL_VALID")
    if adapter_data.get("place_cancel_disabled_evidence_valid") is not True:
        blockers.append("STEP305_PLACE_CANCEL_DISABLED_EVIDENCE_INVALID")
    if adapter_data.get("external_order_submission_performed") is not False:
        blockers.append("STEP305_ADAPTER_EXTERNAL_SUBMISSION_PERFORMED")
    for field in [
        "ready_for_signed_testnet_execution",
        "testnet_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
        "live_trading_allowed_by_this_module",
    ]:
        if adapter_data.get(field) is not False:
            blockers.append(f"STEP305_ADAPTER_{field.upper()}_NOT_FALSE")

    if secret_validation.get("valid") is not True:
        blockers.append("STEP305_SECRET_METADATA_VALIDATION_INVALID")
        blockers.extend(str(reason) for reason in secret_validation.get("block_reasons") or [])
    if secret_data.get("metadata_only") is not True:
        blockers.append("STEP305_SECRET_METADATA_ONLY_FALSE")
    if secret_data.get("environment") != "testnet":
        blockers.append("STEP305_SECRET_ENVIRONMENT_NOT_TESTNET")
    if secret_data.get("api_key_value_access_allowed") is not False or secret_data.get("api_secret_value_access_allowed") is not False:
        blockers.append("STEP305_SECRET_KEY_VALUE_ACCESS_ALLOWED")
    if secret_data.get("secret_file_access_allowed") is not False or secret_data.get("secret_file_creation_allowed") is not False:
        blockers.append("STEP305_SECRET_FILE_ACCESS_OR_CREATION_ALLOWED")

    adapter_venue = adapter_data.get("venue")
    secret_venue = secret_data.get("venue")
    adapter_environment = adapter_data.get("environment")
    secret_environment = secret_data.get("environment")
    if adapter_venue and secret_venue and adapter_venue != secret_venue:
        blockers.append("STEP305_VENUE_MISMATCH")
    if adapter_environment and secret_environment and adapter_environment != secret_environment:
        blockers.append("STEP305_ENVIRONMENT_MISMATCH")

    read_probe_results: dict[str, Any] = {}
    read_probes = adapter_data.get("read_only_probes") or {}
    if not isinstance(read_probes, Mapping):
        blockers.append("STEP305_READ_PROBES_CONTAINER_INVALID")
        read_probes = {}
    for name in REQUIRED_READ_PROBES:
        probe = read_probes.get(name)
        if not isinstance(probe, Mapping):
            blockers.append(f"STEP305_{name.upper()}_MISSING")
            read_probe_results[name] = {"valid": False, "missing": True, "block_reasons": ["STEP305_READ_PROBE_MISSING"]}
            continue
        summary = _probe_summary(probe, max_probe_age_sec=max_probe_age_sec)
        read_probe_results[name] = summary
        if summary.get("valid") is not True:
            blockers.append(f"STEP305_{name.upper()}_INVALID")
            blockers.extend(summary.get("block_reasons") or [])

    blocked_write_results: dict[str, Any] = {}
    blocked_writes = adapter_data.get("blocked_write_probes") or {}
    if not isinstance(blocked_writes, Mapping):
        blockers.append("STEP305_BLOCKED_WRITE_PROBES_CONTAINER_INVALID")
        blocked_writes = {}
    for name in ["place_order_block_probe", "cancel_order_block_probe"]:
        probe = blocked_writes.get(name)
        if not isinstance(probe, Mapping):
            blockers.append(f"STEP305_{name.upper()}_MISSING")
            blocked_write_results[name] = {"valid": False, "missing": True}
            continue
        valid = probe.get("valid") is True and probe.get("external_order_submission_performed") is False and probe.get("testnet_order_submission_allowed") is False
        if not valid:
            blockers.append(f"STEP305_{name.upper()}_INVALID")
        blocked_write_results[name] = {
            "probe_hash": probe.get("probe_hash"),
            "status": probe.get("status"),
            "valid": valid,
            "external_order_submission_performed": False,
            "testnet_order_submission_allowed": False,
            "block_reasons": list(probe.get("block_reasons") or []),
        }

    adapter_age = _age_sec(adapter_data.get("created_at_utc"))
    secret_age = _age_sec(secret_data.get("created_at_utc"))
    if adapter_age is None:
        blockers.append("STEP305_ADAPTER_EVIDENCE_TIMESTAMP_NOT_CANONICAL_UTC")
    elif adapter_age > max_probe_age_sec:
        blockers.append("STEP305_ADAPTER_EVIDENCE_STALE_BLOCKED")
    if secret_age is None:
        blockers.append("STEP305_SECRET_METADATA_TIMESTAMP_NOT_CANONICAL_UTC")
    elif secret_age > max_probe_age_sec:
        blockers.append("STEP305_SECRET_METADATA_STALE_BLOCKED")

    scope = _normalize_scope(secret_data.get("scope"))
    payload_base = {
        "version": STEP305_REAL_READ_ONLY_VENUE_PROBE_VERSION,
        "adapter_evidence_id": adapter_data.get("real_testnet_read_only_adapter_evidence_id"),
        "secret_metadata_intake_id": secret_data.get("testnet_secret_metadata_intake_id"),
        "adapter_venue": adapter_venue,
        "secret_venue": secret_venue,
        "blockers": sorted(set(blockers)),
    }
    valid = not blockers
    probe = {
        "real_read_only_venue_probe_id": stable_id("step305_real_read_only_venue_probe", payload_base),
        "version": STEP305_REAL_READ_ONLY_VENUE_PROBE_VERSION,
        "status": "REAL_READ_ONLY_VENUE_PROBE_VALID" if valid else "REAL_READ_ONLY_VENUE_PROBE_BLOCKED",
        "valid": valid,
        "review_ready": valid,
        "adapter_evidence_id": adapter_data.get("real_testnet_read_only_adapter_evidence_id"),
        "adapter_evidence_sha256": adapter_data.get("adapter_evidence_sha256"),
        "secret_metadata_intake_id": secret_data.get("testnet_secret_metadata_intake_id"),
        "secret_metadata_intake_sha256": secret_data.get("testnet_secret_metadata_intake_sha256"),
        "secret_metadata_validation_id": secret_validation.get("testnet_secret_metadata_validation_id"),
        "adapter_registry_record_id": adapter_data.get("real_testnet_read_only_adapter_registry_record_id"),
        "secret_metadata_registry_record_id": secret_data.get("testnet_secret_metadata_registry_record_id"),
        "venue": adapter_venue or secret_venue,
        "environment": adapter_environment or secret_environment,
        "base_url": adapter_data.get("base_url") or (secret_data.get("public_metadata") or {}).get("base_url"),
        "operator_id": secret_data.get("operator_id"),
        "secret_reference_id": secret_data.get("secret_reference_id"),
        "key_fingerprint_sha256": secret_data.get("key_fingerprint_sha256"),
        "scope": scope,
        "metadata_only": True,
        "max_probe_age_sec": max_probe_age_sec,
        "adapter_source_age_sec": adapter_age,
        "secret_metadata_source_age_sec": secret_age,
        "all_read_probes_valid_and_fresh": all(v.get("valid") is True and v.get("fresh") is True for v in read_probe_results.values()),
        "place_cancel_disabled_evidence_valid": all(v.get("valid") is True for v in blocked_write_results.values()),
        "read_probe_results": read_probe_results,
        "blocked_write_probe_results": blocked_write_results,
        "policy": policy.to_dict(),
        "block_reasons": sorted(set(blockers)),
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_allowed_by_this_module": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    probe["real_read_only_venue_probe_sha256"] = sha256_json(_payload_without_hash(probe))
    return probe


def build_real_read_only_venue_probe_registry_record(probe: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(probe or {})
    record = {
        "version": STEP305_REAL_READ_ONLY_VENUE_PROBE_VERSION,
        "real_read_only_venue_probe_id": data.get("real_read_only_venue_probe_id"),
        "real_read_only_venue_probe_sha256": data.get("real_read_only_venue_probe_sha256"),
        "status": data.get("status"),
        "valid": data.get("valid") is True,
        "review_ready": data.get("review_ready") is True,
        "adapter_evidence_id": data.get("adapter_evidence_id"),
        "adapter_evidence_sha256": data.get("adapter_evidence_sha256"),
        "secret_metadata_intake_id": data.get("secret_metadata_intake_id"),
        "secret_metadata_intake_sha256": data.get("secret_metadata_intake_sha256"),
        "venue": data.get("venue"),
        "environment": data.get("environment"),
        "operator_id": data.get("operator_id"),
        "metadata_only": True,
        "all_read_probes_valid_and_fresh": data.get("all_read_probes_valid_and_fresh") is True,
        "place_cancel_disabled_evidence_valid": data.get("place_cancel_disabled_evidence_valid") is True,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_allowed_by_this_module": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "block_reasons": list(data.get("block_reasons") or []),
        "created_at_utc": utc_now_canonical(),
    }
    record["real_read_only_venue_probe_registry_record_id"] = stable_id("step305_real_read_only_venue_probe_registry", record, 24)
    record["real_read_only_venue_probe_registry_record_sha256"] = sha256_json(record)
    return record


def persist_real_read_only_venue_probe(cfg: AppConfig, probe: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(probe)
    registry_record = build_real_read_only_venue_probe_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, REAL_READ_ONLY_VENUE_PROBE_REGISTRY_NAME),
        registry_record,
        registry_name=REAL_READ_ONLY_VENUE_PROBE_REGISTRY_NAME,
        id_field="real_read_only_venue_probe_registry_record_id",
        hash_field="real_read_only_venue_probe_registry_record_sha256",
        id_prefix="step305_real_read_only_venue_probe_registry",
    )
    payload["real_read_only_venue_probe_registry_record_id"] = persisted.get("real_read_only_venue_probe_registry_record_id")
    payload["real_read_only_venue_probe_registry_record_sha256"] = persisted.get("real_read_only_venue_probe_registry_record_sha256")
    atomic_write_json(latest_dir / "real_read_only_venue_probe.json", payload)
    atomic_write_json(latest_dir / "real_read_only_venue_probe_registry_record.json", persisted)
    return payload


def run_real_read_only_venue_probe_latest(
    *,
    project_root: str | Path | None = None,
    adapter_kind: str = "binance_futures_testnet",
    symbol: str = "BTCUSDT",
    max_probe_age_sec: int = 600,
    secret_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_config(project_root)
    adapter = build_read_only_testnet_adapter(adapter_kind)
    order_intent = {
        "order_intent_id": "step305_real_read_only_probe_order_intent",
        "symbol": symbol,
        "notional_usdt": 5,
        "min_notional_usdt": 1,
        "fee_bps": 2.5,
        "slippage_bps": 3.0,
    }
    adapter_evidence = build_real_testnet_read_only_adapter_evidence(adapter=adapter, order_intent=order_intent, symbol=symbol)
    from crypto_ai_system.execution.real_testnet_read_only_adapter import persist_real_testnet_read_only_adapter_evidence

    adapter_evidence = persist_real_testnet_read_only_adapter_evidence(cfg, adapter_evidence)
    if secret_metadata is None:
        secret_intake = run_testnet_secret_metadata_intake_latest(project_root=cfg.root)
    else:
        intake = build_testnet_secret_metadata_intake_v2(secret_metadata)
        secret_intake = persist_testnet_secret_metadata_intake_v2(cfg, intake)
    probe = build_real_read_only_venue_probe(
        adapter_evidence=adapter_evidence,
        secret_metadata_intake=secret_intake,
        max_probe_age_sec=max_probe_age_sec,
    )
    return persist_real_read_only_venue_probe(cfg, probe)
