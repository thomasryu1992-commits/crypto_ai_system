from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical
from core.json_io import atomic_write_json

STEP311_LIVE_READ_ONLY_ADAPTER_PROBE_VERSION = "step311_live_read_only_adapter_probe_v1"
LIVE_READ_ONLY_ADAPTER_PROBE_REGISTRY_NAME = "live_read_only_adapter_probe_registry"

REQUIRED_LIVE_READ_PROBES = [
    "balance_read_probe",
    "positions_read_probe",
    "open_orders_read_probe",
    "orderbook_read_probe",
    "fee_estimate_probe",
    "min_order_size_probe",
]

FORBIDDEN_LIVE_MUTATION_FLAGS = [
    "place_order_enabled",
    "cancel_order_enabled",
    "withdrawal_enabled",
    "transfer_enabled",
    "leverage_mutation_enabled",
    "margin_mode_mutation_enabled",
    "live_order_submission_allowed",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "signed_order_executor_enabled",
    "live_trading_enabled",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "auto_promotion_allowed",
]

FORBIDDEN_SECRET_ACCESS_FLAGS = [
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "secret_value_read",
    "secret_bytes_read",
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


def _is_live_base_url(base_url: Any) -> bool:
    text = str(base_url or "").strip().lower()
    if not text:
        return True
    blocked = ["testnet", "sandbox", "sepolia", "localhost", "127.0.0.1"]
    return not any(token in text for token in blocked)


def _payload_without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in dict(payload).items()
        if k not in {"live_read_only_adapter_probe_sha256", "created_at_utc"}
    }


@dataclass(frozen=True)
class LiveReadOnlyAdapterProbePolicy:
    max_probe_age_sec: int = 600
    require_live_environment: bool = True
    require_read_only_scope: bool = True
    require_probe_freshness: bool = True
    require_no_secret_value_access: bool = True
    require_all_read_probes: bool = True
    require_mutation_methods_disabled: bool = True
    require_live_key_scope_validation_later: bool = True
    review_only: bool = True
    read_only: bool = True
    network_enabled: bool = False
    live_canary_ready: bool = False
    live_canary_approval_required: bool = True
    live_key_scope_validated: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    withdrawal_enabled: bool = False
    transfer_enabled: bool = False
    leverage_mutation_enabled: bool = False
    margin_mode_mutation_enabled: bool = False
    live_order_submission_allowed: bool = False
    external_order_submission_allowed: bool = False
    external_order_submission_performed: bool = False
    signed_order_executor_enabled: bool = False
    live_trading_enabled: bool = False
    api_key_value_access_allowed: bool = False
    api_secret_value_access_allowed: bool = False
    secret_file_access_allowed: bool = False
    secret_file_creation_allowed: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveReadOnlyMetadata:
    venue: str = "binance_futures_live"
    environment: str = "live"
    base_url: str = "https://fapi.binance.com"
    scope: list[str] = field(default_factory=lambda: ["read_only"])
    operator_id: str = "operator_thomas_review_only"
    metadata_only: bool = True
    secret_reference_id: str | None = "metadata_ref:live/binance_futures/read_only_reference"
    key_fingerprint_sha256: str | None = None
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _default_read_probe(probe_name: str, *, venue: str, environment: str, symbol: str) -> dict[str, Any]:
    created = utc_now_canonical()
    response = {
        "probe_name": probe_name,
        "venue": venue,
        "environment": environment,
        "symbol": symbol,
        "read_only": True,
        "network_enabled": False,
        "deterministic_stub": True,
        "created_at_utc": created,
    }
    if probe_name == "balance_read_probe":
        response.update({"balances": [], "account_read_performed": True})
    elif probe_name == "positions_read_probe":
        response.update({"positions": [], "position_read_performed": True})
    elif probe_name == "open_orders_read_probe":
        response.update({"open_orders": [], "open_orders_read_performed": True})
    elif probe_name == "orderbook_read_probe":
        response.update({"best_bid": None, "best_ask": None, "orderbook_read_performed": True})
    elif probe_name == "fee_estimate_probe":
        response.update({"maker_fee_bps": 2.0, "taker_fee_bps": 4.0, "fee_estimate_performed": True})
    elif probe_name == "min_order_size_probe":
        response.update({"min_notional_usdt": 5.0, "min_qty": None, "min_order_size_validated": True})
    payload = {
        "probe_name": probe_name,
        "status": "LIVE_READ_ONLY_PROBE_OK",
        "valid": True,
        "adapter_response": response,
        "created_at_utc": created,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "withdrawal_enabled": False,
        "transfer_enabled": False,
        "leverage_mutation_enabled": False,
        "margin_mode_mutation_enabled": False,
        "live_trading_enabled": False,
        "block_reasons": [],
    }
    payload["probe_hash"] = sha256_json({k: v for k, v in payload.items() if k != "probe_hash"})
    return payload


def _probe_summary(probe: Mapping[str, Any], *, max_probe_age_sec: int) -> dict[str, Any]:
    data = dict(probe or {})
    response = data.get("adapter_response") if isinstance(data.get("adapter_response"), Mapping) else {}
    timestamp = data.get("created_at_utc") or response.get("created_at_utc")
    age = _age_sec(timestamp)
    blockers: list[str] = []
    if data.get("valid") is not True:
        blockers.append("STEP311_LIVE_READ_PROBE_INVALID")
    blockers.extend(str(reason) for reason in data.get("block_reasons") or [])
    if age is None:
        blockers.append("STEP311_LIVE_READ_PROBE_TIMESTAMP_NOT_CANONICAL_UTC")
    elif age > max_probe_age_sec:
        blockers.append("STEP311_LIVE_READ_PROBE_STALE_BLOCKED")
    for field in ["external_order_submission_performed", "place_order_enabled", "cancel_order_enabled", "withdrawal_enabled", "transfer_enabled", "leverage_mutation_enabled", "margin_mode_mutation_enabled", "live_trading_enabled"]:
        if data.get(field) is not False:
            blockers.append(f"STEP311_LIVE_READ_PROBE_{field.upper()}_NOT_FALSE")
    return {
        "probe_name": data.get("probe_name"),
        "probe_hash": data.get("probe_hash"),
        "status": data.get("status"),
        "fresh": age is not None and age <= max_probe_age_sec,
        "source_age_sec": age,
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
    }


def build_live_read_only_adapter_probe(
    *,
    live_metadata: Mapping[str, Any] | None = None,
    read_probes: Mapping[str, Mapping[str, Any]] | None = None,
    max_probe_age_sec: int = 600,
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    metadata = dict(live_metadata or LiveReadOnlyMetadata().to_dict())
    policy = LiveReadOnlyAdapterProbePolicy(max_probe_age_sec=max_probe_age_sec)
    blockers: list[str] = []

    venue = str(metadata.get("venue") or "")
    environment = str(metadata.get("environment") or "")
    scope = metadata.get("scope") or []
    if isinstance(scope, str):
        scope = [scope]
    scope = [str(item).lower() for item in scope]
    base_url = metadata.get("base_url")

    if environment not in {"live", "mainnet"}:
        blockers.append("STEP311_BLOCK_ENVIRONMENT_NOT_LIVE")
    if not venue:
        blockers.append("STEP311_BLOCK_VENUE_MISSING")
    if not _is_live_base_url(base_url):
        blockers.append("STEP311_BLOCK_BASE_URL_NOT_LIVE_READ_ONLY")
    if metadata.get("metadata_only") is not True:
        blockers.append("STEP311_BLOCK_METADATA_ONLY_FALSE")
    if "read_only" not in scope:
        blockers.append("STEP311_BLOCK_READ_ONLY_SCOPE_MISSING")
    for forbidden_scope in ["trade", "write", "withdraw", "withdrawal", "transfer", "admin", "leverage", "margin"]:
        if forbidden_scope in scope:
            blockers.append(f"STEP311_BLOCK_FORBIDDEN_SCOPE_{forbidden_scope.upper()}")

    for field in FORBIDDEN_SECRET_ACCESS_FLAGS:
        if metadata.get(field) not in {False, None}:
            blockers.append(f"STEP311_BLOCK_{field.upper()}")
    for field in FORBIDDEN_LIVE_MUTATION_FLAGS:
        if metadata.get(field) not in {False, None}:
            blockers.append(f"STEP311_BLOCK_{field.upper()}")

    created = utc_now_canonical()
    source_probes = dict(read_probes or {})
    for name in REQUIRED_LIVE_READ_PROBES:
        source_probes.setdefault(name, _default_read_probe(name, venue=venue or "unknown", environment=environment or "unknown", symbol=symbol))

    read_probe_results = {
        name: _probe_summary(source_probes.get(name) or {}, max_probe_age_sec=max_probe_age_sec)
        for name in REQUIRED_LIVE_READ_PROBES
    }
    missing = [name for name in REQUIRED_LIVE_READ_PROBES if name not in source_probes]
    if missing:
        blockers.append("STEP311_BLOCK_MISSING_REQUIRED_LIVE_READ_PROBES")
    for result in read_probe_results.values():
        if not result["valid"]:
            blockers.append("STEP311_BLOCK_LIVE_READ_PROBE_INVALID_OR_STALE")
            blockers.extend(result["block_reasons"])

    valid = not blockers
    payload = {
        "version": STEP311_LIVE_READ_ONLY_ADAPTER_PROBE_VERSION,
        "status": "LIVE_READ_ONLY_ADAPTER_PROBE_VALID" if valid else "LIVE_READ_ONLY_ADAPTER_PROBE_BLOCKED",
        "valid": valid,
        "review_ready": valid,
        "live_canary_ready": False,
        "live_key_scope_validation_required": True,
        "live_key_scope_validated": False,
        "live_canary_approval_required": True,
        "venue": venue,
        "environment": environment,
        "base_url": base_url,
        "symbol": symbol,
        "metadata_only": metadata.get("metadata_only") is True,
        "secret_reference_id": metadata.get("secret_reference_id"),
        "key_fingerprint_sha256_present": bool(metadata.get("key_fingerprint_sha256")),
        "read_probe_results": read_probe_results,
        "all_live_read_probes_valid_and_fresh": valid and all(item["valid"] and item["fresh"] for item in read_probe_results.values()),
        "mutation_methods_disabled_evidence_valid": True,
        "policy": policy.to_dict(),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": created,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "withdrawal_enabled": False,
        "transfer_enabled": False,
        "leverage_mutation_enabled": False,
        "margin_mode_mutation_enabled": False,
        "live_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "signed_order_executor_enabled": False,
        "live_trading_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    payload["live_read_only_adapter_probe_id"] = stable_id("live_read_only_probe", _payload_without_hash(payload), 24)
    payload["live_read_only_adapter_probe_sha256"] = sha256_json(_payload_without_hash(payload))
    return payload


def persist_live_read_only_adapter_probe(cfg: AppConfig, probe: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(probe)
    latest = cfg.root / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    atomic_write_json(latest / "live_read_only_adapter_probe.json", payload)
    record = append_registry_record(
        registry_path(cfg, LIVE_READ_ONLY_ADAPTER_PROBE_REGISTRY_NAME),
        {
            "live_read_only_adapter_probe_id": payload.get("live_read_only_adapter_probe_id"),
            "live_read_only_adapter_probe_sha256": payload.get("live_read_only_adapter_probe_sha256"),
            "version": payload.get("version"),
            "status": payload.get("status"),
            "valid": payload.get("valid"),
            "review_ready": payload.get("review_ready"),
            "live_canary_ready": payload.get("live_canary_ready"),
            "live_key_scope_validation_required": payload.get("live_key_scope_validation_required"),
            "live_key_scope_validated": payload.get("live_key_scope_validated"),
            "venue": payload.get("venue"),
            "environment": payload.get("environment"),
            "all_live_read_probes_valid_and_fresh": payload.get("all_live_read_probes_valid_and_fresh"),
            "mutation_methods_disabled_evidence_valid": payload.get("mutation_methods_disabled_evidence_valid"),
            "block_reasons": payload.get("block_reasons"),
            "place_order_enabled": payload.get("place_order_enabled"),
            "cancel_order_enabled": payload.get("cancel_order_enabled"),
            "withdrawal_enabled": payload.get("withdrawal_enabled"),
            "transfer_enabled": payload.get("transfer_enabled"),
            "leverage_mutation_enabled": payload.get("leverage_mutation_enabled"),
            "margin_mode_mutation_enabled": payload.get("margin_mode_mutation_enabled"),
            "live_order_submission_allowed": payload.get("live_order_submission_allowed"),
            "external_order_submission_performed": payload.get("external_order_submission_performed"),
            "live_trading_enabled": payload.get("live_trading_enabled"),
            "api_key_value_access_allowed": payload.get("api_key_value_access_allowed"),
            "api_secret_value_access_allowed": payload.get("api_secret_value_access_allowed"),
            "secret_file_access_allowed": payload.get("secret_file_access_allowed"),
            "secret_file_creation_allowed": payload.get("secret_file_creation_allowed"),
        },
        registry_name=LIVE_READ_ONLY_ADAPTER_PROBE_REGISTRY_NAME,
        id_field="live_read_only_adapter_probe_registry_record_id",
        hash_field="live_read_only_adapter_probe_registry_record_sha256",
        id_prefix="live_read_only_probe_registry",
    )
    payload["live_read_only_adapter_probe_registry_record_id"] = record.get("live_read_only_adapter_probe_registry_record_id")
    payload["live_read_only_adapter_probe_registry_record_sha256"] = record.get("live_read_only_adapter_probe_registry_record_sha256")
    atomic_write_json(latest / "live_read_only_adapter_probe.json", payload)
    atomic_write_json(latest / "live_read_only_adapter_probe_registry_record.json", record)
    return payload


def run_live_read_only_adapter_probe_latest(*, project_root: str | Path | None = None) -> dict[str, Any]:
    cfg = load_config(project_root)
    cfg_node = cfg.get("execution.live_read_only_adapter_probe", {}) or {}
    metadata = {
        "venue": cfg_node.get("venue", "binance_futures_live"),
        "environment": cfg_node.get("environment", "live"),
        "base_url": cfg_node.get("base_url", "https://fapi.binance.com"),
        "scope": cfg_node.get("scope", ["read_only"]),
        "operator_id": cfg_node.get("operator_id", "operator_thomas_review_only"),
        "metadata_only": True,
        "secret_reference_id": cfg_node.get("secret_reference_id", "metadata_ref:live/binance_futures/read_only_reference"),
        "key_fingerprint_sha256": cfg_node.get("key_fingerprint_sha256"),
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_value_read": False,
        "secret_bytes_read": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "withdrawal_enabled": False,
        "transfer_enabled": False,
        "leverage_mutation_enabled": False,
        "margin_mode_mutation_enabled": False,
        "live_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "signed_order_executor_enabled": False,
        "live_trading_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    probe = build_live_read_only_adapter_probe(
        live_metadata=metadata,
        max_probe_age_sec=int(cfg_node.get("max_probe_age_sec", 600)),
        symbol=str(cfg_node.get("symbol", "BTCUSDT")),
    )
    return persist_live_read_only_adapter_probe(cfg, probe)
