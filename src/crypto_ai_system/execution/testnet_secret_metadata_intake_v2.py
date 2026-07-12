from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Mapping, Sequence

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, sha256_text, stable_id, utc_now_canonical
from core.json_io import atomic_write_json

STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION = "step304_testnet_secret_metadata_intake_v2"
TESTNET_SECRET_METADATA_REGISTRY_NAME = "testnet_secret_metadata_registry"

SECRET_VALUE_ACCESS_ALLOWED = False
API_KEY_VALUE_ACCESS_ALLOWED = False
API_SECRET_VALUE_ACCESS_ALLOWED = False
SECRET_FILE_ACCESS_ALLOWED = False
SECRET_FILE_CREATION_ALLOWED = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
SIGNED_ORDER_EXECUTOR_ENABLED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False

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
_ALLOWED_REFERENCE_PREFIXES = ("secret_ref:", "vault_ref:", "kms_ref:", "metadata_ref:")
_BLOCKED_SCOPE_TOKENS = {"live", "mainnet", "withdraw", "withdrawal", "transfer", "admin", "unrestricted"}
_ALLOWED_ENVIRONMENTS = {"testnet", "signed_testnet"}
_ALLOWED_VENUES = {"binance_futures_testnet", "extended_testnet", "generic_testnet"}


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
        values = [part.strip() for part in scope.replace(";", ",").split(",")]
        return [value for value in values if value]
    if isinstance(scope, Sequence) and not isinstance(scope, (bytes, bytearray, str)):
        return [str(value).strip() for value in scope if str(value).strip()]
    return [str(scope).strip()]


def _safe_public_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in dict(metadata or {}).items():
        lowered = key.lower()
        if lowered in _SECRET_VALUE_FIELDS or "secret_value" in lowered or "private_key" in lowered:
            continue
        redacted[key] = value
    return redacted


def _is_hex_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def _fingerprint(value: Any) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True)
class TestnetSecretMetadataContractV2:
    __test__: ClassVar[bool] = False
    """Metadata-only contract for Step304 testnet secret references.

    This contract represents *where* a future testnet key could be referenced.
    It does not dereference, read, store, create, or validate actual secret bytes.
    """

    secret_reference_id: str = "metadata_ref:testnet/binance_futures/step304_review_only"
    environment: str = "testnet"
    venue: str = "binance_futures_testnet"
    metadata_only: bool = True
    api_key_value_access_allowed: bool = API_KEY_VALUE_ACCESS_ALLOWED
    api_secret_value_access_allowed: bool = API_SECRET_VALUE_ACCESS_ALLOWED
    secret_file_access_allowed: bool = SECRET_FILE_ACCESS_ALLOWED
    secret_file_creation_allowed: bool = SECRET_FILE_CREATION_ALLOWED
    testnet_order_submission_allowed: bool = TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE
    signed_order_executor_enabled: bool = SIGNED_ORDER_EXECUTOR_ENABLED_BY_THIS_MODULE
    live_trading_allowed_by_this_module: bool = LIVE_TRADING_ALLOWED_BY_THIS_MODULE
    contract_version: str = STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contract_sha256"] = sha256_json({k: v for k, v in payload.items() if k != "created_at_utc"})
        return payload

    def read_secret(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "SECRET_VALUE_READ_DISABLED_STEP304_METADATA_ONLY",
            "secret_value": None,
            "api_key_value": None,
            "api_secret_value": None,
            "api_key_value_access_allowed": False,
            "api_secret_value_access_allowed": False,
            "secret_file_access_allowed": False,
            "secret_file_creation_allowed": False,
            "testnet_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "live_trading_allowed_by_this_module": False,
            "created_at_utc": utc_now_canonical(),
        }


def build_testnet_secret_metadata_intake_v2(
    metadata: Mapping[str, Any] | None,
    *,
    known_live_key_fingerprints_sha256: Sequence[str] | None = None,
    contract: Mapping[str, Any] | TestnetSecretMetadataContractV2 | None = None,
) -> dict[str, Any]:
    data = dict(metadata or {})
    contract_data = contract.to_dict() if isinstance(contract, TestnetSecretMetadataContractV2) else dict(contract or TestnetSecretMetadataContractV2().to_dict())
    live_fingerprints = {_fingerprint(item) for item in (known_live_key_fingerprints_sha256 or [])}
    blockers: list[str] = []
    warnings: list[str] = []

    for key in _SECRET_VALUE_FIELDS:
        if _contains_actual_secret_value(data.get(key)):
            blockers.append(f"{key.upper()}_VALUE_PROVIDED_BLOCKED")

    if _as_bool(data.get("secret_file_loaded")) or _as_bool(data.get("secret_bytes_read")) or _as_bool(data.get("secret_value_read")):
        blockers.append("SECRET_BYTES_OR_FILE_ACCESS_BLOCKED")
    if _as_bool(data.get("secret_file_created")):
        blockers.append("SECRET_FILE_CREATION_BLOCKED")

    secret_reference_id = str(data.get("secret_reference_id") or contract_data.get("secret_reference_id") or "").strip()
    if not secret_reference_id:
        blockers.append("SECRET_REFERENCE_ID_MISSING")
    elif not secret_reference_id.startswith(_ALLOWED_REFERENCE_PREFIXES):
        blockers.append("SECRET_REFERENCE_ID_NOT_METADATA_ONLY_BLOCKED")

    key_fingerprint_sha256 = _fingerprint(data.get("key_fingerprint_sha256") or data.get("api_key_fingerprint_sha256"))
    if not key_fingerprint_sha256:
        blockers.append("TESTNET_KEY_FINGERPRINT_SHA256_MISSING")
    elif not _is_hex_sha256(key_fingerprint_sha256):
        blockers.append("TESTNET_KEY_FINGERPRINT_SHA256_INVALID")
    elif key_fingerprint_sha256 in live_fingerprints:
        blockers.append("LIVE_KEY_FINGERPRINT_MATCH_BLOCKED")

    environment = str(data.get("environment") or data.get("key_scope") or contract_data.get("environment") or "").strip().lower()
    if environment not in _ALLOWED_ENVIRONMENTS:
        blockers.append("TESTNET_SECRET_ENVIRONMENT_NOT_TESTNET_BLOCKED")
    if any(token in environment for token in ("live", "mainnet", "prod")) or _as_bool(data.get("live_key_detected")):
        blockers.append("LIVE_OR_MAINNET_KEY_METADATA_BLOCKED")

    venue = str(data.get("venue") or contract_data.get("venue") or "").strip().lower()
    if venue not in _ALLOWED_VENUES:
        blockers.append("TESTNET_SECRET_VENUE_NOT_APPROVED")

    operator_id = str(data.get("operator_id") or "").strip()
    if not operator_id:
        blockers.append("OPERATOR_ID_MISSING")

    scope = _normalize_scope(data.get("scope") or data.get("key_permissions") or data.get("key_scope_detail") or ["read_only"])
    if not scope:
        blockers.append("TESTNET_SECRET_SCOPE_MISSING")
    lowered_scopes = [item.lower() for item in scope]
    if any(any(token in item for token in _BLOCKED_SCOPE_TOKENS) for item in lowered_scopes):
        blockers.append("TESTNET_SECRET_SCOPE_CONTAINS_LIVE_OR_HIGH_RISK_PERMISSION")
    if not any("read" in item or "testnet" in item for item in lowered_scopes):
        warnings.append("TESTNET_SECRET_SCOPE_DOES_NOT_DECLARE_READ_OR_TESTNET_SCOPE")

    base_url = str(data.get("base_url") or "").strip()
    base_url_lower = base_url.lower()
    if base_url and not any(token in base_url_lower for token in ("testnet", "sepolia", "sandbox")):
        blockers.append("TESTNET_SECRET_BASE_URL_NOT_TESTNET_BLOCKED")
    if any(token in base_url_lower for token in ("mainnet", "api.binance.com", "fapi.binance.com")):
        blockers.append("TESTNET_SECRET_BASE_URL_MAINNET_BLOCKED")

    created_at = str(data.get("created_at_utc") or utc_now_canonical())
    if not is_canonical_utc_timestamp(created_at):
        blockers.append("CREATED_AT_UTC_NOT_CANONICAL")
        created_at = utc_now_canonical()

    if contract_data.get("metadata_only") is not True:
        blockers.append("SECRET_METADATA_CONTRACT_METADATA_ONLY_FALSE")
    for flag_name in [
        "api_key_value_access_allowed",
        "api_secret_value_access_allowed",
        "secret_file_access_allowed",
        "secret_file_creation_allowed",
        "testnet_order_submission_allowed",
        "signed_order_executor_enabled",
        "live_trading_allowed_by_this_module",
    ]:
        if contract_data.get(flag_name) is not False:
            blockers.append(f"SECRET_METADATA_CONTRACT_{flag_name.upper()}_NOT_DISABLED")

    public_metadata = _safe_public_metadata(data)
    public_metadata.update(
        {
            "secret_reference_id": secret_reference_id,
            "key_fingerprint_sha256": key_fingerprint_sha256 or None,
            "environment": environment,
            "venue": venue,
            "scope": scope,
            "operator_id": operator_id or None,
            "base_url": base_url or None,
            "metadata_only": True,
        }
    )
    payload_base = {
        "version": STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION,
        "public_metadata_sha256": sha256_json(public_metadata),
        "contract_sha256": contract_data.get("contract_sha256") or sha256_json(contract_data),
        "blockers": sorted(set(blockers)),
    }
    intake = {
        "testnet_secret_metadata_intake_id": stable_id("step304_testnet_secret_metadata_intake", payload_base),
        "version": STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION,
        "metadata_only": True,
        "valid": not blockers,
        "validation_status": "VALID_METADATA_ONLY_TESTNET_REFERENCE" if not blockers else "BLOCKED_TESTNET_SECRET_METADATA_INTAKE",
        "secret_reference_id": secret_reference_id or None,
        "key_fingerprint_sha256": key_fingerprint_sha256 or None,
        "environment": environment or None,
        "venue": venue or None,
        "scope": scope,
        "operator_id": operator_id or None,
        "public_metadata": public_metadata,
        "public_metadata_sha256": sha256_json(public_metadata),
        "contract": contract_data,
        "contract_sha256": contract_data.get("contract_sha256") or sha256_json(contract_data),
        "block_reasons": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_value_read": False,
        "secret_file_created": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "ready_for_signed_testnet_execution": False,
        "live_trading_allowed_by_this_module": False,
        "created_at_utc": created_at,
    }
    intake["testnet_secret_metadata_intake_sha256"] = sha256_json(
        {k: v for k, v in intake.items() if k not in {"testnet_secret_metadata_intake_sha256"}}
    )
    return intake


def validate_testnet_secret_metadata_intake_v2(intake: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(intake or {})
    blockers: list[str] = []
    if not data:
        blockers.append("TESTNET_SECRET_METADATA_INTAKE_MISSING")
    if data.get("version") != STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION:
        blockers.append("TESTNET_SECRET_METADATA_INTAKE_VERSION_INVALID")
    if data.get("metadata_only") is not True:
        blockers.append("TESTNET_SECRET_METADATA_ONLY_FALSE")
    if data.get("valid") is not True:
        blockers.append("TESTNET_SECRET_METADATA_INTAKE_NOT_VALID")
    if not data.get("testnet_secret_metadata_intake_id"):
        blockers.append("TESTNET_SECRET_METADATA_INTAKE_ID_MISSING")
    public_metadata = data.get("public_metadata") or {}
    if data.get("public_metadata_sha256") != sha256_json(public_metadata):
        blockers.append("TESTNET_SECRET_METADATA_PUBLIC_METADATA_HASH_INVALID")
    if data.get("testnet_secret_metadata_intake_sha256") != sha256_json(
        {k: v for k, v in data.items() if k != "testnet_secret_metadata_intake_sha256"}
    ):
        blockers.append("TESTNET_SECRET_METADATA_INTAKE_HASH_INVALID")
    if data.get("environment") not in _ALLOWED_ENVIRONMENTS:
        blockers.append("TESTNET_SECRET_METADATA_ENVIRONMENT_INVALID")
    if data.get("venue") not in _ALLOWED_VENUES:
        blockers.append("TESTNET_SECRET_METADATA_VENUE_INVALID")
    if not _is_hex_sha256(str(data.get("key_fingerprint_sha256") or "")):
        blockers.append("TESTNET_SECRET_METADATA_FINGERPRINT_INVALID")
    for field_name in [
        "api_key_value_access_allowed",
        "api_secret_value_access_allowed",
        "secret_file_access_allowed",
        "secret_file_creation_allowed",
        "secret_value_read",
        "secret_file_created",
        "testnet_order_submission_allowed",
        "external_order_submission_allowed",
        "external_order_submission_performed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
        "ready_for_signed_testnet_execution",
        "live_trading_allowed_by_this_module",
    ]:
        if data.get(field_name) is not False:
            blockers.append(f"TESTNET_SECRET_METADATA_{field_name.upper()}_NOT_FALSE")
    for reason in data.get("block_reasons") or []:
        blockers.append(str(reason))
    payload = {
        "intake_id": data.get("testnet_secret_metadata_intake_id"),
        "intake_hash": data.get("testnet_secret_metadata_intake_sha256"),
        "blockers": sorted(set(blockers)),
        "version": STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION,
    }
    return {
        "testnet_secret_metadata_validation_id": stable_id("step304_testnet_secret_metadata_validation", payload),
        "version": STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION,
        "valid": not blockers,
        "validation_status": "VALID_METADATA_ONLY_TESTNET_REFERENCE" if not blockers else "BLOCKED_TESTNET_SECRET_METADATA_VALIDATION",
        "block_reasons": sorted(set(blockers)),
        "metadata_only": True,
        "secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "live_trading_allowed_by_this_module": False,
        "created_at_utc": utc_now_canonical(),
    }


def build_testnet_secret_metadata_registry_record(
    intake: Mapping[str, Any], validation: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    data = dict(intake or {})
    validation_data = dict(validation or validate_testnet_secret_metadata_intake_v2(data))
    record = {
        "version": STEP304_TESTNET_SECRET_METADATA_INTAKE_VERSION,
        "testnet_secret_metadata_intake_id": data.get("testnet_secret_metadata_intake_id"),
        "testnet_secret_metadata_intake_sha256": data.get("testnet_secret_metadata_intake_sha256"),
        "testnet_secret_metadata_validation_id": validation_data.get("testnet_secret_metadata_validation_id"),
        "validation_status": validation_data.get("validation_status"),
        "valid": validation_data.get("valid") is True,
        "secret_reference_id": data.get("secret_reference_id"),
        "key_fingerprint_sha256": data.get("key_fingerprint_sha256"),
        "environment": data.get("environment"),
        "venue": data.get("venue"),
        "scope": list(data.get("scope") or []),
        "operator_id": data.get("operator_id"),
        "public_metadata_sha256": data.get("public_metadata_sha256"),
        "contract_sha256": data.get("contract_sha256"),
        "metadata_only": True,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "ready_for_signed_testnet_execution": False,
        "live_trading_allowed_by_this_module": False,
        "block_reasons": list(validation_data.get("block_reasons") or []),
        "created_at_utc": utc_now_canonical(),
    }
    record["testnet_secret_metadata_registry_record_id"] = stable_id("step304_secret_metadata_registry", record, 24)
    record["testnet_secret_metadata_registry_record_sha256"] = sha256_json(record)
    return record


def persist_testnet_secret_metadata_intake_v2(cfg: AppConfig, intake: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    intake_payload = dict(intake)
    validation = validate_testnet_secret_metadata_intake_v2(intake_payload)
    registry_record = build_testnet_secret_metadata_registry_record(intake_payload, validation)
    persisted = append_registry_record(
        registry_path(cfg, TESTNET_SECRET_METADATA_REGISTRY_NAME),
        registry_record,
        registry_name=TESTNET_SECRET_METADATA_REGISTRY_NAME,
        id_field="testnet_secret_metadata_registry_record_id",
        hash_field="testnet_secret_metadata_registry_record_sha256",
        id_prefix="step304_secret_metadata_registry",
    )
    intake_payload["testnet_secret_metadata_validation"] = validation
    intake_payload["testnet_secret_metadata_registry_record_id"] = persisted.get("testnet_secret_metadata_registry_record_id")
    intake_payload["testnet_secret_metadata_registry_record_sha256"] = persisted.get("testnet_secret_metadata_registry_record_sha256")
    atomic_write_json(latest_dir / "testnet_secret_metadata_intake_v2.json", intake_payload)
    atomic_write_json(latest_dir / "testnet_secret_metadata_validation_v2.json", validation)
    atomic_write_json(latest_dir / "testnet_secret_metadata_registry_record.json", persisted)
    return intake_payload


def _default_metadata() -> dict[str, Any]:
    return {
        "secret_reference_id": "metadata_ref:testnet/binance_futures/step304_review_only",
        "key_fingerprint_sha256": sha256_text("step304-testnet-metadata-only-reference"),
        "environment": "testnet",
        "venue": "binance_futures_testnet",
        "scope": ["read_only", "signed_testnet_preparation"],
        "operator_id": "operator_review_only",
        "base_url": "https://testnet.binancefuture.com",
        "secret_file_loaded": False,
        "secret_file_created": False,
        "secret_bytes_read": False,
        "secret_value_read": False,
        "live_key_detected": False,
        "created_at_utc": utc_now_canonical(),
    }


def run_testnet_secret_metadata_intake_latest(
    *,
    project_root: str | Path | None = None,
    metadata: Mapping[str, Any] | None = None,
    known_live_key_fingerprints_sha256: Sequence[str] | None = None,
) -> dict[str, Any]:
    cfg = load_config(project_root)
    intake = build_testnet_secret_metadata_intake_v2(
        metadata or _default_metadata(),
        known_live_key_fingerprints_sha256=known_live_key_fingerprints_sha256,
    )
    return persist_testnet_secret_metadata_intake_v2(cfg, intake)
