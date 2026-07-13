from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from crypto_ai_system.execution.signed_testnet_readiness import validate_testnet_secret_policy
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

TESTNET_KEY_METADATA_INTAKE_VERSION = "step274_testnet_key_metadata_intake_v1"
SECRET_MANAGER_CONTRACT_VERSION = "step274_metadata_only_secret_manager_contract_v1"
SECRET_VALUE_ACCESS_ALLOWED = False
SECRET_FILE_CREATION_ALLOWED = False

_SECRET_VALUE_FIELDS = {"api_key", "api_secret", "private_key", "secret", "passphrase", "password"}
_METADATA_ALLOWED_SECRET_REFERENCE_PREFIXES = ("secret_ref:", "vault_ref:", "kms_ref:", "metadata_ref:")


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
    placeholders = {"***", "redacted", "<redacted>", "metadata_only", "present", "not_loaded"}
    return stripped.lower() not in placeholders


def _safe_public_metadata(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in data.items()
        if k.lower() not in _SECRET_VALUE_FIELDS
        and "secret_value" not in k.lower()
        and "private_key" not in k.lower()
    }


@dataclass(frozen=True)
class MetadataOnlySecretManagerContract:
    """Metadata-only contract for future testnet secrets.

    Step274 must never read secret bytes.  This contract only declares where a
    future signed-testnet key would be referenced by an external secret manager.
    The reference itself is metadata and is not dereferenced by this system.
    """

    provider: str = "metadata_only_stub"
    environment: str = "signed_testnet"
    secret_reference_id: str = "secret_ref:testnet/binance_futures/read_contract_only"
    metadata_only: bool = True
    secret_value_access_allowed: bool = SECRET_VALUE_ACCESS_ALLOWED
    secret_file_creation_allowed: bool = SECRET_FILE_CREATION_ALLOWED
    contract_version: str = SECRET_MANAGER_CONTRACT_VERSION
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contract_sha256"] = sha256_json({k: v for k, v in payload.items() if k != "created_at_utc"})
        return payload

    def read_secret(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "SECRET_VALUE_READ_DISABLED_STEP274",
            "secret_value_access_allowed": SECRET_VALUE_ACCESS_ALLOWED,
            "secret_file_creation_allowed": SECRET_FILE_CREATION_ALLOWED,
            "secret_value": None,
            "created_at_utc": utc_now_canonical(),
        }


def build_testnet_key_metadata_intake(
    metadata: Mapping[str, Any] | None,
    *,
    known_live_key_fingerprints_sha256: list[str] | None = None,
    secret_manager_contract: Mapping[str, Any] | MetadataOnlySecretManagerContract | None = None,
) -> dict[str, Any]:
    data = dict(metadata or {})
    contract_data = (
        secret_manager_contract.to_dict()
        if isinstance(secret_manager_contract, MetadataOnlySecretManagerContract)
        else dict(secret_manager_contract or MetadataOnlySecretManagerContract().to_dict())
    )
    live_fingerprints = set(known_live_key_fingerprints_sha256 or [])
    blockers: list[str] = []
    warnings: list[str] = []

    for key in _SECRET_VALUE_FIELDS:
        if _contains_actual_secret_value(data.get(key)):
            blockers.append(f"{key.upper()}_VALUE_PROVIDED_BLOCKED")

    if _as_bool(data.get("secret_file_loaded")) or _as_bool(data.get("secret_bytes_read")):
        blockers.append("SECRET_BYTES_OR_FILE_ACCESS_BLOCKED")
    if _as_bool(data.get("secret_file_created")):
        blockers.append("SECRET_FILE_CREATION_BLOCKED")

    key_scope = str(data.get("key_scope") or data.get("environment") or "").strip().lower()
    if key_scope not in {"testnet", "signed_testnet"}:
        blockers.append("TESTNET_KEY_SCOPE_NOT_TESTNET_BLOCKED")
    if "live" in key_scope or _as_bool(data.get("live_key_detected")):
        blockers.append("LIVE_KEY_DETECTED_BLOCKED")

    base_url = str(data.get("base_url") or "").strip().lower()
    if base_url and "testnet" not in base_url and "sepolia" not in base_url:
        blockers.append("TESTNET_BASE_URL_NOT_TESTNET_BLOCKED")
    if not base_url:
        warnings.append("TESTNET_BASE_URL_NOT_DECLARED")

    key_fp = str(data.get("api_key_fingerprint_sha256") or data.get("key_fingerprint_sha256") or "").strip()
    if not key_fp:
        blockers.append("TESTNET_KEY_FINGERPRINT_SHA256_MISSING")
    elif len(key_fp) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in key_fp):
        blockers.append("TESTNET_KEY_FINGERPRINT_SHA256_INVALID")
    elif key_fp.lower() in {x.lower() for x in live_fingerprints}:
        blockers.append("LIVE_KEY_FINGERPRINT_MATCH_BLOCKED")

    reference = str(data.get("secret_reference_id") or contract_data.get("secret_reference_id") or "")
    if not reference.startswith(_METADATA_ALLOWED_SECRET_REFERENCE_PREFIXES):
        blockers.append("SECRET_REFERENCE_ID_NOT_METADATA_ONLY_BLOCKED")

    if contract_data.get("metadata_only") is not True:
        blockers.append("SECRET_MANAGER_CONTRACT_METADATA_ONLY_FALSE_BLOCKED")
    if contract_data.get("secret_value_access_allowed") is not False:
        blockers.append("SECRET_MANAGER_CONTRACT_VALUE_ACCESS_NOT_DISABLED")
    if contract_data.get("secret_file_creation_allowed") is not False:
        blockers.append("SECRET_MANAGER_CONTRACT_FILE_CREATION_NOT_DISABLED")

    policy_validation = validate_testnet_secret_policy({**data, "secret_file_created": False if data.get("secret_file_created") is None else data.get("secret_file_created")})
    blockers.extend(policy_validation.get("block_reasons", []))
    warnings.extend(policy_validation.get("warnings", []))

    public_metadata = _safe_public_metadata(data)
    public_metadata["secret_reference_id"] = reference
    public_metadata["key_scope"] = key_scope
    public_metadata["base_url"] = base_url
    public_metadata["api_key_fingerprint_sha256"] = key_fp or None

    payload = {
        "version": TESTNET_KEY_METADATA_INTAKE_VERSION,
        "public_metadata": public_metadata,
        "secret_manager_contract_sha256": contract_data.get("contract_sha256") or sha256_json(contract_data),
        "policy_validation_id": policy_validation.get("secret_policy_validation_id"),
        "blockers": sorted(set(blockers)),
    }
    return {
        "testnet_key_intake_id": stable_id("testnet_key_intake", payload),
        "version": TESTNET_KEY_METADATA_INTAKE_VERSION,
        "metadata_only": True,
        "valid": not blockers,
        "secret_value_access_allowed": SECRET_VALUE_ACCESS_ALLOWED,
        "secret_file_creation_allowed": SECRET_FILE_CREATION_ALLOWED,
        "secret_reference_id": reference,
        "key_scope": key_scope,
        "base_url": base_url,
        "api_key_fingerprint_sha256": key_fp or None,
        "public_metadata": public_metadata,
        "public_metadata_sha256": sha256_json(public_metadata),
        "secret_manager_contract": contract_data,
        "secret_manager_contract_sha256": contract_data.get("contract_sha256") or sha256_json(contract_data),
        "secret_policy_validation": policy_validation,
        "block_reasons": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "created_at_utc": utc_now_canonical(),
    }


def validate_testnet_key_metadata_intake(intake: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(intake or {})
    blockers: list[str] = []
    if data.get("version") != TESTNET_KEY_METADATA_INTAKE_VERSION:
        blockers.append("TESTNET_KEY_INTAKE_VERSION_INVALID")
    if data.get("metadata_only") is not True:
        blockers.append("TESTNET_KEY_INTAKE_METADATA_ONLY_FALSE")
    if data.get("secret_value_access_allowed") is not False:
        blockers.append("TESTNET_KEY_INTAKE_SECRET_VALUE_ACCESS_NOT_DISABLED")
    if data.get("secret_file_creation_allowed") is not False:
        blockers.append("TESTNET_KEY_INTAKE_SECRET_FILE_CREATION_NOT_DISABLED")
    if data.get("valid") is not True:
        blockers.append("TESTNET_KEY_INTAKE_NOT_VALID")
    public_metadata = data.get("public_metadata") or {}
    if data.get("public_metadata_sha256") != sha256_json(public_metadata):
        blockers.append("TESTNET_KEY_INTAKE_PUBLIC_METADATA_HASH_INVALID")
    if not data.get("testnet_key_intake_id"):
        blockers.append("TESTNET_KEY_INTAKE_ID_MISSING")
    for reason in data.get("block_reasons") or []:
        blockers.append(str(reason))
    payload = {
        "intake_id": data.get("testnet_key_intake_id"),
        "public_metadata_sha256": data.get("public_metadata_sha256"),
        "blockers": sorted(set(blockers)),
        "version": TESTNET_KEY_METADATA_INTAKE_VERSION,
    }
    return {
        "testnet_key_intake_validation_id": stable_id("testnet_key_intake_validation", payload),
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
