from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, sha256_text, stable_id, utc_now_canonical
from core.json_io import atomic_write_json, read_json

STEP312_LIVE_KEY_SCOPE_VALIDATOR_VERSION = "step312_live_key_scope_validator_v1"
LIVE_KEY_SCOPE_VALIDATOR_REGISTRY_NAME = "live_key_scope_validator_registry"

_ALLOWED_REFERENCE_PREFIXES = ("secret_ref:", "vault_ref:", "kms_ref:", "metadata_ref:")
_ALLOWED_LIVE_ENVIRONMENTS = {"live", "mainnet"}
_ALLOWED_LIVE_VENUES = {"binance_futures_live", "extended_live", "generic_live"}
_REQUIRED_DISABLED_PERMISSION_FLAGS = [
    "withdrawal_enabled",
    "transfer_enabled",
    "admin_enabled",
    "write_enabled",
    "trade_enabled",
    "place_order_enabled",
    "cancel_order_enabled",
    "leverage_mutation_enabled",
    "margin_mode_mutation_enabled",
]
_FORBIDDEN_SCOPE_TOKENS = {
    "trade",
    "write",
    "order",
    "orders",
    "withdraw",
    "withdrawal",
    "transfer",
    "admin",
    "leverage",
    "margin",
    "unrestricted",
}
_SECRET_VALUE_FIELDS = {
    "api_key",
    "api_secret",
    "private_key",
    "secret",
    "passphrase",
    "password",
    "api_key_value",
    "api_secret_value",
    "secret_value",
    "key_value",
}
_FORBIDDEN_RUNTIME_FLAGS = [
    "live_canary_ready",
    "live_order_submission_allowed",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "withdrawal_enabled",
    "transfer_enabled",
    "leverage_mutation_enabled",
    "margin_mode_mutation_enabled",
    "signed_order_executor_enabled",
    "live_trading_enabled",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "auto_promotion_allowed",
]
_FORBIDDEN_SECRET_ACCESS_FLAGS = [
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "secret_value_read",
    "secret_bytes_read",
]


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _contains_actual_secret_value(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, str):
        return bool(value)
    stripped = value.strip()
    if not stripped:
        return False
    placeholders = {"***", "redacted", "<redacted>", "metadata_only", "present", "not_loaded", "none", "null"}
    return stripped.lower() not in placeholders


def _normalize_scope(scope: Any) -> list[str]:
    if scope is None:
        return []
    if isinstance(scope, str):
        return [part.strip() for part in scope.replace(";", ",").split(",") if part.strip()]
    if isinstance(scope, Sequence) and not isinstance(scope, (bytes, bytearray, str)):
        return [str(part).strip() for part in scope if str(part).strip()]
    return [str(scope).strip()]


def _is_hex_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


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
        return False
    if any(token in text for token in ("testnet", "sandbox", "sepolia", "localhost", "127.0.0.1")):
        return False
    return any(token in text for token in ("binance.com", "fapi.binance.com", "api.binance.com", "live"))


def _safe_public_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in dict(metadata or {}).items():
        lowered = key.lower()
        if lowered in _SECRET_VALUE_FIELDS or "secret_value" in lowered or "private_key" in lowered:
            continue
        safe[key] = value
    return safe


@dataclass(frozen=True)
class LiveKeyScopePolicy:
    require_live_environment: bool = True
    require_metadata_only: bool = True
    require_read_only_scope: bool = True
    require_no_trade_scope: bool = True
    require_withdrawal_disabled: bool = True
    require_transfer_disabled: bool = True
    require_admin_disabled: bool = True
    require_ip_whitelist_metadata: bool = True
    require_live_read_only_probe: bool = True
    max_probe_age_sec: int = 600
    review_only: bool = True
    live_canary_ready: bool = False
    live_canary_approval_required: bool = True
    live_order_submission_allowed: bool = False
    external_order_submission_allowed: bool = False
    external_order_submission_performed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    withdrawal_enabled: bool = False
    transfer_enabled: bool = False
    leverage_mutation_enabled: bool = False
    margin_mode_mutation_enabled: bool = False
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
class LiveKeyScopeMetadata:
    secret_reference_id: str = "metadata_ref:live/binance_futures/read_only_reference"
    key_fingerprint_sha256: str = field(default_factory=lambda: sha256_text("step312-live-read-only-metadata-reference"))
    environment: str = "live"
    venue: str = "binance_futures_live"
    base_url: str = "https://fapi.binance.com"
    scope: list[str] = field(default_factory=lambda: ["read_only"])
    operator_id: str = "operator_thomas_review_only"
    metadata_only: bool = True
    withdrawal_enabled: bool = False
    transfer_enabled: bool = False
    admin_enabled: bool = False
    write_enabled: bool = False
    trade_enabled: bool = False
    ip_whitelist_enabled: bool = True
    ip_whitelist_metadata_only: bool = True
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _probe_blockers(probe: Mapping[str, Any] | None, *, max_probe_age_sec: int) -> tuple[list[str], dict[str, Any]]:
    data = dict(probe or {})
    blockers: list[str] = []
    if not data:
        blockers.append("STEP312_BLOCK_MISSING_LIVE_READ_ONLY_PROBE")
        return blockers, {"present": False, "fresh": False, "source_age_sec": None, "valid": False}
    if data.get("status") != "LIVE_READ_ONLY_ADAPTER_PROBE_VALID" or data.get("valid") is not True:
        blockers.append("STEP312_BLOCK_LIVE_READ_ONLY_PROBE_INVALID")
    if data.get("environment") not in _ALLOWED_LIVE_ENVIRONMENTS:
        blockers.append("STEP312_BLOCK_LIVE_READ_ONLY_PROBE_ENVIRONMENT_INVALID")
    if data.get("all_live_read_probes_valid_and_fresh") is not True:
        blockers.append("STEP312_BLOCK_LIVE_READ_ONLY_PROBE_NOT_ALL_FRESH")
    age = _age_sec(data.get("created_at_utc"))
    if age is None:
        blockers.append("STEP312_BLOCK_LIVE_READ_ONLY_PROBE_TIMESTAMP_INVALID")
    elif age > max_probe_age_sec:
        blockers.append("STEP312_BLOCK_LIVE_READ_ONLY_PROBE_STALE")
    for field in _FORBIDDEN_RUNTIME_FLAGS + _FORBIDDEN_SECRET_ACCESS_FLAGS:
        if data.get(field) not in {False, None}:
            blockers.append(f"STEP312_BLOCK_LIVE_READ_ONLY_PROBE_{field.upper()}_NOT_FALSE")
    return blockers, {
        "present": True,
        "live_read_only_adapter_probe_id": data.get("live_read_only_adapter_probe_id"),
        "live_read_only_adapter_probe_sha256": data.get("live_read_only_adapter_probe_sha256"),
        "status": data.get("status"),
        "valid": data.get("valid") is True,
        "fresh": age is not None and age <= max_probe_age_sec,
        "source_age_sec": age,
        "venue": data.get("venue"),
        "environment": data.get("environment"),
    }


def build_live_key_scope_validation(
    metadata: Mapping[str, Any] | None,
    *,
    live_read_only_probe: Mapping[str, Any] | None = None,
    known_non_live_key_fingerprints_sha256: Sequence[str] | None = None,
    known_blocked_live_key_fingerprints_sha256: Sequence[str] | None = None,
    max_probe_age_sec: int = 600,
) -> dict[str, Any]:
    data = dict(metadata or LiveKeyScopeMetadata().to_dict())
    policy = LiveKeyScopePolicy(max_probe_age_sec=max_probe_age_sec)
    blockers: list[str] = []
    warnings: list[str] = []

    for key in _SECRET_VALUE_FIELDS:
        if _contains_actual_secret_value(data.get(key)):
            blockers.append(f"STEP312_BLOCK_{key.upper()}_VALUE_PROVIDED")
    if _as_bool(data.get("secret_file_loaded")) or _as_bool(data.get("secret_bytes_read")) or _as_bool(data.get("secret_value_read")):
        blockers.append("STEP312_BLOCK_SECRET_BYTES_OR_FILE_ACCESS")
    if _as_bool(data.get("secret_file_created")):
        blockers.append("STEP312_BLOCK_SECRET_FILE_CREATION")

    secret_reference_id = str(data.get("secret_reference_id") or "").strip()
    if not secret_reference_id:
        blockers.append("STEP312_BLOCK_SECRET_REFERENCE_ID_MISSING")
    elif not secret_reference_id.startswith(_ALLOWED_REFERENCE_PREFIXES):
        blockers.append("STEP312_BLOCK_SECRET_REFERENCE_ID_NOT_METADATA_ONLY")

    key_fingerprint_sha256 = str(data.get("key_fingerprint_sha256") or data.get("api_key_fingerprint_sha256") or "").strip().lower()
    if not key_fingerprint_sha256:
        blockers.append("STEP312_BLOCK_LIVE_KEY_FINGERPRINT_SHA256_MISSING")
    elif not _is_hex_sha256(key_fingerprint_sha256):
        blockers.append("STEP312_BLOCK_LIVE_KEY_FINGERPRINT_SHA256_INVALID")
    blocked_fingerprints = {str(item).strip().lower() for item in (known_blocked_live_key_fingerprints_sha256 or [])}
    non_live_fingerprints = {str(item).strip().lower() for item in (known_non_live_key_fingerprints_sha256 or [])}
    if key_fingerprint_sha256 and key_fingerprint_sha256 in blocked_fingerprints:
        blockers.append("STEP312_BLOCK_LIVE_KEY_FINGERPRINT_BLOCKLIST_MATCH")
    if key_fingerprint_sha256 and key_fingerprint_sha256 in non_live_fingerprints:
        blockers.append("STEP312_BLOCK_NON_LIVE_KEY_FINGERPRINT_MATCH")

    environment = str(data.get("environment") or "").strip().lower()
    if environment not in _ALLOWED_LIVE_ENVIRONMENTS:
        blockers.append("STEP312_BLOCK_ENVIRONMENT_NOT_LIVE")

    venue = str(data.get("venue") or "").strip().lower()
    if venue not in _ALLOWED_LIVE_VENUES:
        blockers.append("STEP312_BLOCK_VENUE_NOT_APPROVED_FOR_LIVE_SCOPE_VALIDATION")

    base_url = str(data.get("base_url") or "").strip()
    if not _is_live_base_url(base_url):
        blockers.append("STEP312_BLOCK_BASE_URL_NOT_LIVE")

    operator_id = str(data.get("operator_id") or "").strip()
    if not operator_id:
        blockers.append("STEP312_BLOCK_OPERATOR_ID_MISSING")

    if data.get("metadata_only") is not True:
        blockers.append("STEP312_BLOCK_METADATA_ONLY_FALSE")

    scope = [item.lower() for item in _normalize_scope(data.get("scope") or data.get("permissions") or [])]
    if not scope:
        blockers.append("STEP312_BLOCK_SCOPE_MISSING")
    if "read_only" not in scope and "read" not in scope:
        blockers.append("STEP312_BLOCK_READ_ONLY_SCOPE_MISSING")
    for item in scope:
        for forbidden in _FORBIDDEN_SCOPE_TOKENS:
            if forbidden in item and item not in {"read_only", "read"}:
                blockers.append(f"STEP312_BLOCK_FORBIDDEN_SCOPE_{forbidden.upper()}")

    for flag_name in _REQUIRED_DISABLED_PERMISSION_FLAGS:
        if data.get(flag_name) not in {False, None}:
            blockers.append(f"STEP312_BLOCK_{flag_name.upper()}_NOT_DISABLED")

    if data.get("ip_whitelist_enabled") is not True:
        warnings.append("STEP312_WARN_IP_WHITELIST_NOT_CONFIRMED")
    if data.get("ip_whitelist_metadata_only") is not True:
        blockers.append("STEP312_BLOCK_IP_WHITELIST_METADATA_ONLY_FALSE")

    for field in _FORBIDDEN_RUNTIME_FLAGS + _FORBIDDEN_SECRET_ACCESS_FLAGS:
        if data.get(field) not in {False, None}:
            blockers.append(f"STEP312_BLOCK_{field.upper()}_NOT_FALSE")

    probe_blockers, probe_summary = _probe_blockers(live_read_only_probe, max_probe_age_sec=max_probe_age_sec)
    blockers.extend(probe_blockers)
    if probe_summary.get("venue") and venue and probe_summary.get("venue") != venue:
        blockers.append("STEP312_BLOCK_LIVE_PROBE_VENUE_MISMATCH")
    if probe_summary.get("environment") and environment and probe_summary.get("environment") != environment:
        blockers.append("STEP312_BLOCK_LIVE_PROBE_ENVIRONMENT_MISMATCH")

    created_at = str(data.get("created_at_utc") or utc_now_canonical())
    if not is_canonical_utc_timestamp(created_at):
        blockers.append("STEP312_BLOCK_CREATED_AT_UTC_NOT_CANONICAL")
        created_at = utc_now_canonical()

    public_metadata = _safe_public_metadata(data)
    public_metadata.update(
        {
            "secret_reference_id": secret_reference_id or None,
            "key_fingerprint_sha256": key_fingerprint_sha256 or None,
            "environment": environment or None,
            "venue": venue or None,
            "base_url": base_url or None,
            "scope": scope,
            "operator_id": operator_id or None,
            "metadata_only": True,
        }
    )
    valid = not blockers
    base = {
        "version": STEP312_LIVE_KEY_SCOPE_VALIDATOR_VERSION,
        "public_metadata_sha256": sha256_json(public_metadata),
        "probe_summary": probe_summary,
        "block_reasons": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "created_at_utc": created_at,
    }
    payload = {
        "live_key_scope_validation_id": stable_id("live_key_scope_validation", base, 24),
        "version": STEP312_LIVE_KEY_SCOPE_VALIDATOR_VERSION,
        "status": "LIVE_KEY_SCOPE_VALIDATED_METADATA_ONLY" if valid else "LIVE_KEY_SCOPE_VALIDATION_BLOCKED",
        "valid": valid,
        "metadata_only": True,
        "review_ready": valid,
        "live_canary_ready": False,
        "live_canary_approval_required": True,
        "live_order_submission_allowed": False,
        "secret_reference_id": secret_reference_id or None,
        "key_fingerprint_sha256": key_fingerprint_sha256 or None,
        "environment": environment or None,
        "venue": venue or None,
        "base_url": base_url or None,
        "scope": scope,
        "operator_id": operator_id or None,
        "public_metadata": public_metadata,
        "public_metadata_sha256": sha256_json(public_metadata),
        "live_read_only_probe_summary": probe_summary,
        "live_read_only_probe_required": True,
        "live_read_only_probe_valid_and_fresh": probe_summary.get("valid") is True and probe_summary.get("fresh") is True,
        "policy": policy.to_dict(),
        "block_reasons": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "created_at_utc": created_at,
        "withdrawal_enabled": False,
        "transfer_enabled": False,
        "admin_enabled": False,
        "write_enabled": False,
        "trade_enabled": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "leverage_mutation_enabled": False,
        "margin_mode_mutation_enabled": False,
        "signed_order_executor_enabled": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "live_trading_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_value_read": False,
        "secret_bytes_read": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    payload["live_key_scope_validation_sha256"] = sha256_json(
        {k: v for k, v in payload.items() if k != "live_key_scope_validation_sha256"}
    )
    return payload


def build_live_key_scope_validator_registry_record(validation: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(validation or {})
    record = {
        "version": STEP312_LIVE_KEY_SCOPE_VALIDATOR_VERSION,
        "live_key_scope_validation_id": data.get("live_key_scope_validation_id"),
        "live_key_scope_validation_sha256": data.get("live_key_scope_validation_sha256"),
        "status": data.get("status"),
        "valid": data.get("valid") is True,
        "metadata_only": data.get("metadata_only") is True,
        "review_ready": data.get("review_ready"),
        "live_canary_ready": data.get("live_canary_ready"),
        "live_canary_approval_required": data.get("live_canary_approval_required"),
        "live_order_submission_allowed": data.get("live_order_submission_allowed"),
        "secret_reference_id": data.get("secret_reference_id"),
        "key_fingerprint_sha256": data.get("key_fingerprint_sha256"),
        "environment": data.get("environment"),
        "venue": data.get("venue"),
        "scope": data.get("scope"),
        "operator_id": data.get("operator_id"),
        "public_metadata_sha256": data.get("public_metadata_sha256"),
        "live_read_only_probe_valid_and_fresh": data.get("live_read_only_probe_valid_and_fresh"),
        "live_read_only_adapter_probe_id": (data.get("live_read_only_probe_summary") or {}).get("live_read_only_adapter_probe_id"),
        "block_reasons": data.get("block_reasons") or [],
        "warnings": data.get("warnings") or [],
        "withdrawal_enabled": False,
        "transfer_enabled": False,
        "admin_enabled": False,
        "write_enabled": False,
        "trade_enabled": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "leverage_mutation_enabled": False,
        "margin_mode_mutation_enabled": False,
        "signed_order_executor_enabled": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "live_trading_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["live_key_scope_validator_registry_record_id"] = stable_id("live_key_scope_registry", record, 24)
    record["live_key_scope_validator_registry_record_sha256"] = sha256_json(record)
    return record


def persist_live_key_scope_validation(cfg: AppConfig, validation: Mapping[str, Any]) -> dict[str, Any]:
    latest = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest.mkdir(parents=True, exist_ok=True)
    payload = dict(validation)
    record = build_live_key_scope_validator_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, LIVE_KEY_SCOPE_VALIDATOR_REGISTRY_NAME),
        record,
        registry_name=LIVE_KEY_SCOPE_VALIDATOR_REGISTRY_NAME,
        id_field="live_key_scope_validator_registry_record_id",
        hash_field="live_key_scope_validator_registry_record_sha256",
        id_prefix="live_key_scope_registry",
    )
    payload["live_key_scope_validator_registry_record_id"] = persisted.get("live_key_scope_validator_registry_record_id")
    payload["live_key_scope_validator_registry_record_sha256"] = persisted.get("live_key_scope_validator_registry_record_sha256")
    atomic_write_json(latest / "live_key_scope_validation.json", payload)
    atomic_write_json(latest / "live_key_scope_validator_registry_record.json", persisted)
    return payload


def _default_live_metadata(cfg_node: Mapping[str, Any] | None = None) -> dict[str, Any]:
    node = dict(cfg_node or {})
    return {
        "secret_reference_id": node.get("secret_reference_id", "metadata_ref:live/binance_futures/read_only_reference"),
        "key_fingerprint_sha256": node.get("key_fingerprint_sha256") or sha256_text("step312-live-read-only-metadata-reference"),
        "environment": node.get("environment", "live"),
        "venue": node.get("venue", "binance_futures_live"),
        "base_url": node.get("base_url", "https://fapi.binance.com"),
        "scope": node.get("scope", ["read_only"]),
        "operator_id": node.get("operator_id", "operator_thomas_review_only"),
        "metadata_only": True,
        "withdrawal_enabled": False,
        "transfer_enabled": False,
        "admin_enabled": False,
        "write_enabled": False,
        "trade_enabled": False,
        "ip_whitelist_enabled": node.get("ip_whitelist_enabled", True),
        "ip_whitelist_metadata_only": True,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_value_read": False,
        "secret_bytes_read": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "live_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "signed_order_executor_enabled": False,
        "live_trading_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }


def run_live_key_scope_validator_latest(
    *,
    project_root: str | Path | None = None,
    metadata: Mapping[str, Any] | None = None,
    live_read_only_probe: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_config(project_root)
    cfg_node = cfg.get("execution.live_key_scope_validator", {}) or {}
    probe = dict(live_read_only_probe or {})
    if not probe:
        latest_probe = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest")) / "live_read_only_adapter_probe.json"
        if latest_probe.exists():
            probe = read_json(latest_probe)
    validation = build_live_key_scope_validation(
        metadata or _default_live_metadata(cfg_node),
        live_read_only_probe=probe,
        max_probe_age_sec=int(cfg_node.get("max_probe_age_sec", 600)),
    )
    return persist_live_key_scope_validation(cfg, validation)
