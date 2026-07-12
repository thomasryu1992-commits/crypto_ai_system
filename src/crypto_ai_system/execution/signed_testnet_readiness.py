from __future__ import annotations

from typing import Any, Mapping

from crypto_ai_system.execution.exchange_adapter_contract import (
    EXCHANGE_ADAPTER_CONTRACT_VERSION,
    validate_adapter_capabilities,
)
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

SIGNED_TESTNET_READINESS_VERSION = "step273_signed_testnet_preflight_readiness_v1"
SIGNED_TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP273 = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False

_REQUIRED_APPROVAL_FIELDS = [
    "approval_packet_id",
    "approval_intake_id",
    "approver_id",
    "approver_role",
    "approval_ticket_id",
    "approval_signature",
    "timestamp_utc",
]


def required_signed_testnet_approval_fields() -> list[str]:
    return list(_REQUIRED_APPROVAL_FIELDS)


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _contains_secret_value(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, str):
        return bool(value)
    stripped = value.strip()
    if not stripped:
        return False
    placeholders = {"***", "redacted", "<redacted>", "metadata_only", "present", "not_loaded"}
    return stripped.lower() not in placeholders


def validate_signed_testnet_approval(approval: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(approval or {})
    blockers: list[str] = []
    missing = [field for field in _REQUIRED_APPROVAL_FIELDS if not data.get(field)]
    for field in missing:
        blockers.append(f"SIGNED_TESTNET_APPROVAL_{field.upper()}_MISSING")
    if data.get("timestamp_utc") and not is_canonical_utc_timestamp(data.get("timestamp_utc")):
        blockers.append("SIGNED_TESTNET_APPROVAL_TIMESTAMP_NOT_CANONICAL_UTC")
    if data.get("approval_signature") and len(str(data.get("approval_signature"))) < 12:
        blockers.append("SIGNED_TESTNET_APPROVAL_SIGNATURE_TOO_SHORT")
    payload = {
        "approval": {k: data.get(k) for k in _REQUIRED_APPROVAL_FIELDS},
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_READINESS_VERSION,
    }
    return {
        "approval_validation_id": stable_id("signed_testnet_approval_validation", payload),
        "valid": not blockers,
        "missing_fields": missing,
        "block_reasons": sorted(set(blockers)),
        "approval_sha256": sha256_json({k: data.get(k) for k in sorted(data) if "secret" not in k.lower() and "key" not in k.lower()}),
        "created_at_utc": utc_now_canonical(),
    }


def validate_testnet_secret_policy(secret_status: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate metadata-only key policy without reading secret bytes.

    Callers must provide metadata such as has_api_key/key_scope/key_environment.
    Passing actual api_key/api_secret values is blocked because Step273 must not
    access secrets or enable signed order submission.
    """

    data = dict(secret_status or {})
    blockers: list[str] = []
    warnings: list[str] = []

    if _contains_secret_value(data.get("api_key")) or _contains_secret_value(data.get("api_secret")):
        blockers.append("SECRET_VALUE_PROVIDED_BLOCKED")
    if data.get("secret_file_created") is True:
        blockers.append("SECRET_FILE_CREATION_BLOCKED")
    if data.get("secret_file_loaded") is True or data.get("secret_bytes_read") is True:
        blockers.append("SECRET_FILE_ACCESS_BLOCKED")

    has_key = _as_bool(data.get("has_api_key"))
    has_secret = _as_bool(data.get("has_api_secret"))
    if not has_key:
        blockers.append("TESTNET_API_KEY_METADATA_MISSING")
    if not has_secret:
        blockers.append("TESTNET_API_SECRET_METADATA_MISSING")

    key_scope = str(data.get("key_scope") or data.get("environment") or "").strip().lower()
    if key_scope not in {"testnet", "signed_testnet"}:
        blockers.append("TESTNET_KEY_SCOPE_NOT_TESTNET_BLOCKED")
    if "live" in key_scope or data.get("live_key_detected") is True:
        blockers.append("LIVE_KEY_DETECTED_BLOCKED")

    base_url = str(data.get("base_url") or "").strip().lower()
    if base_url and "testnet" not in base_url and "sepolia" not in base_url:
        blockers.append("TESTNET_BASE_URL_NOT_TESTNET_BLOCKED")
    if not base_url:
        warnings.append("TESTNET_BASE_URL_NOT_DECLARED")

    payload = {
        "key_scope": key_scope,
        "has_key": has_key,
        "has_secret": has_secret,
        "base_url": base_url,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_READINESS_VERSION,
    }
    return {
        "secret_policy_validation_id": stable_id("testnet_secret_policy_validation", payload),
        "valid": not blockers,
        "metadata_only": True,
        "block_reasons": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "secret_status_sha256": sha256_json({k: v for k, v in data.items() if k not in {"api_key", "api_secret"}}),
        "created_at_utc": utc_now_canonical(),
    }


def evaluate_signed_testnet_preflight(
    *,
    adapter_capabilities: Mapping[str, Any],
    secret_status: Mapping[str, Any],
    manual_approval: Mapping[str, Any] | None,
    venue_state: Mapping[str, Any] | None = None,
    risk_limits: Mapping[str, Any] | None = None,
    runtime_flags: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    venue = dict(venue_state or {})
    limits = dict(risk_limits or {})
    flags = dict(runtime_flags or {})
    blockers: list[str] = []
    warnings: list[str] = []

    adapter_validation = validate_adapter_capabilities(adapter_capabilities)
    secret_validation = validate_testnet_secret_policy(secret_status)
    approval_validation = validate_signed_testnet_approval(manual_approval)

    blockers.extend(adapter_validation.get("block_reasons", []))
    blockers.extend(secret_validation.get("block_reasons", []))
    blockers.extend(approval_validation.get("block_reasons", []))
    warnings.extend(secret_validation.get("warnings", []))

    if _as_bool(flags.get("testnet_signed_order_enabled")):
        blockers.append("TESTNET_SIGNED_ORDER_ENABLED_MUST_REMAIN_FALSE_STEP273")
    if _as_bool(flags.get("enable_real_orders")):
        blockers.append("ENABLE_REAL_ORDERS_MUST_REMAIN_FALSE_STEP273")
    if _as_bool(flags.get("live_trading_enabled")) or _as_bool(flags.get("allow_live_trading")):
        blockers.append("LIVE_TRADING_FLAGS_ENABLED_BLOCKED")
    if str(flags.get("trading_mode") or "paper").strip().lower() == "live":
        blockers.append("TRADING_MODE_LIVE_BLOCKED")

    if venue.get("balance_read_contract_available") is not True:
        blockers.append("BALANCE_READ_CONTRACT_MISSING")
    if venue.get("position_read_contract_available") is not True:
        blockers.append("POSITION_READ_CONTRACT_MISSING")
    if venue.get("open_orders_read_contract_available") is not True:
        blockers.append("OPEN_ORDERS_READ_CONTRACT_MISSING")
    if venue.get("orderbook_read_contract_available") is not True:
        blockers.append("ORDERBOOK_READ_CONTRACT_MISSING")
    if venue.get("fee_model_available") is not True:
        blockers.append("FEE_MODEL_MISSING")
    if venue.get("slippage_estimate_available") is not True:
        blockers.append("SLIPPAGE_ESTIMATE_MISSING")
    if venue.get("min_order_size_valid") is not True:
        blockers.append("MIN_ORDER_SIZE_VALIDATION_MISSING_OR_FAILED")

    max_notional = float(limits.get("max_order_notional_usdt", 0.0) or 0.0)
    max_daily_orders = int(limits.get("max_daily_order_count", 0) or 0)
    manual_kill_switch_required = _as_bool(limits.get("manual_kill_switch_required", True))
    if max_notional <= 0:
        blockers.append("TESTNET_MAX_ORDER_NOTIONAL_NOT_CONFIGURED")
    if max_daily_orders <= 0:
        blockers.append("TESTNET_MAX_DAILY_ORDER_COUNT_NOT_CONFIGURED")
    if not manual_kill_switch_required:
        blockers.append("MANUAL_KILL_SWITCH_REQUIREMENT_MISSING")

    unique_blockers = sorted(set(blockers))
    contract_review_ready = not unique_blockers
    payload = {
        "adapter_validation_id": adapter_validation.get("adapter_contract_validation_id"),
        "secret_policy_validation_id": secret_validation.get("secret_policy_validation_id"),
        "approval_validation_id": approval_validation.get("approval_validation_id"),
        "venue_state": venue,
        "risk_limits": limits,
        "runtime_flags": flags,
        "blockers": unique_blockers,
        "version": SIGNED_TESTNET_READINESS_VERSION,
    }
    return {
        "signed_testnet_preflight_id": stable_id("signed_testnet_preflight", payload),
        "readiness_version": SIGNED_TESTNET_READINESS_VERSION,
        "adapter_contract_version": EXCHANGE_ADAPTER_CONTRACT_VERSION,
        "contract_review_ready": contract_review_ready,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": SIGNED_TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP273,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        "block_reasons": unique_blockers,
        "warnings": sorted(set(warnings)),
        "adapter_validation": adapter_validation,
        "secret_policy_validation": secret_validation,
        "approval_validation": approval_validation,
        "venue_state": venue,
        "risk_limits": limits,
        "runtime_flags": flags,
        "created_at_utc": utc_now_canonical(),
    }
