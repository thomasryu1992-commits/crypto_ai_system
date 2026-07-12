from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import json

from crypto_ai_system.execution.signed_testnet_preflight_artifact import validate_signed_testnet_preflight_artifact
from crypto_ai_system.execution.signed_testnet_readiness import validate_signed_testnet_approval
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

SIGNED_TESTNET_GATE_VERSION = "step275_signed_testnet_gate_v1"
SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP275 = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP275 = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP275 = False

_REQUIRED_RISK_CAP_FIELDS = [
    "max_order_notional_usdt",
    "max_daily_order_count",
    "max_daily_loss_usdt",
    "max_consecutive_losses",
    "manual_kill_switch_required",
    "manual_kill_switch_active",
]


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _payload_without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dict(payload).items() if k not in {"signed_testnet_gate_sha256", "created_at_utc", "gate_artifact_path"}}


def _validate_risk_caps(risk_caps: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(risk_caps or {})
    blockers: list[str] = []
    missing = [field for field in _REQUIRED_RISK_CAP_FIELDS if field not in data]
    for field in missing:
        blockers.append(f"SIGNED_TESTNET_RISK_CAP_{field.upper()}_MISSING")

    try:
        max_notional = float(data.get("max_order_notional_usdt", 0.0) or 0.0)
    except (TypeError, ValueError):
        max_notional = -1.0
    try:
        max_daily_orders = int(data.get("max_daily_order_count", 0) or 0)
    except (TypeError, ValueError):
        max_daily_orders = -1
    try:
        max_daily_loss = float(data.get("max_daily_loss_usdt", 0.0) or 0.0)
    except (TypeError, ValueError):
        max_daily_loss = -1.0
    try:
        max_consecutive_losses = int(data.get("max_consecutive_losses", 0) or 0)
    except (TypeError, ValueError):
        max_consecutive_losses = -1

    if max_notional <= 0:
        blockers.append("SIGNED_TESTNET_MAX_ORDER_NOTIONAL_NOT_POSITIVE")
    if max_notional > 5:
        blockers.append("SIGNED_TESTNET_MAX_ORDER_NOTIONAL_EXCEEDS_STEP275_CAP")
    if max_daily_orders <= 0:
        blockers.append("SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT_NOT_POSITIVE")
    if max_daily_orders > 3:
        blockers.append("SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT_EXCEEDS_STEP275_CAP")
    if max_daily_loss <= 0:
        blockers.append("SIGNED_TESTNET_MAX_DAILY_LOSS_NOT_POSITIVE")
    if max_daily_loss > 10:
        blockers.append("SIGNED_TESTNET_MAX_DAILY_LOSS_EXCEEDS_STEP275_CAP")
    if max_consecutive_losses <= 0:
        blockers.append("SIGNED_TESTNET_MAX_CONSECUTIVE_LOSSES_NOT_POSITIVE")
    if max_consecutive_losses > 2:
        blockers.append("SIGNED_TESTNET_MAX_CONSECUTIVE_LOSSES_EXCEEDS_STEP275_CAP")

    if data.get("manual_kill_switch_required") is not True:
        blockers.append("SIGNED_TESTNET_MANUAL_KILL_SWITCH_REQUIREMENT_MISSING")
    if data.get("manual_kill_switch_active") is True:
        blockers.append("SIGNED_TESTNET_MANUAL_KILL_SWITCH_ACTIVE_BLOCKED")

    payload = {
        "risk_caps": data,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_GATE_VERSION,
    }
    return {
        "signed_testnet_risk_cap_validation_id": stable_id("signed_testnet_risk_cap_validation", payload),
        "valid": not blockers,
        "risk_caps_sha256": sha256_json(data),
        "missing_fields": missing,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def _validate_operational_state(operational_state: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(operational_state or {})
    blockers: list[str] = []

    if _as_bool(data.get("testnet_signed_order_enabled")):
        blockers.append("SIGNED_TESTNET_ORDER_FLAG_ENABLED_MUST_REMAIN_FALSE_STEP275")
    if _as_bool(data.get("enable_real_orders")):
        blockers.append("ENABLE_REAL_ORDERS_MUST_REMAIN_FALSE_STEP275")
    if _as_bool(data.get("live_trading_enabled")) or _as_bool(data.get("allow_live_trading")):
        blockers.append("LIVE_TRADING_FLAGS_ENABLED_BLOCKED_STEP275")
    if str(data.get("trading_mode") or "paper").strip().lower() in {"testnet", "live"}:
        blockers.append("TRADING_MODE_MUST_REMAIN_PAPER_OR_REVIEW_ONLY_STEP275")

    try:
        daily_order_count = int(data.get("current_daily_order_count", 0) or 0)
    except (TypeError, ValueError):
        daily_order_count = 999999
    try:
        current_daily_loss = float(data.get("current_daily_loss_usdt", 0.0) or 0.0)
    except (TypeError, ValueError):
        current_daily_loss = 999999.0
    try:
        consecutive_losses = int(data.get("current_consecutive_losses", 0) or 0)
    except (TypeError, ValueError):
        consecutive_losses = 999999

    max_daily_orders = int(data.get("max_daily_order_count", 3) or 3)
    max_daily_loss = float(data.get("max_daily_loss_usdt", 10.0) or 10.0)
    max_consecutive_losses = int(data.get("max_consecutive_losses", 2) or 2)
    if daily_order_count >= max_daily_orders:
        blockers.append("SIGNED_TESTNET_DAILY_ORDER_COUNT_CAP_REACHED")
    if current_daily_loss >= max_daily_loss:
        blockers.append("SIGNED_TESTNET_DAILY_LOSS_CAP_REACHED")
    if consecutive_losses >= max_consecutive_losses:
        blockers.append("SIGNED_TESTNET_CONSECUTIVE_LOSS_CAP_REACHED")

    if data.get("reconciliation_mismatch_present") is True:
        blockers.append("SIGNED_TESTNET_RECONCILIATION_MISMATCH_PRESENT_BLOCKED")
    try:
        mismatch_rate = float(data.get("reconciliation_mismatch_rate", 0.0) or 0.0)
    except (TypeError, ValueError):
        mismatch_rate = 1.0
    if mismatch_rate > 0.0:
        blockers.append("SIGNED_TESTNET_RECONCILIATION_MISMATCH_RATE_NOT_ZERO_BLOCKED")

    if data.get("last_reconciliation_status") not in {None, "RECONCILIATION_MATCHED", "matched"}:
        blockers.append("SIGNED_TESTNET_LAST_RECONCILIATION_NOT_MATCHED_BLOCKED")

    payload = {
        "operational_state": data,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_GATE_VERSION,
    }
    return {
        "signed_testnet_operational_state_validation_id": stable_id("signed_testnet_operational_state_validation", payload),
        "valid": not blockers,
        "operational_state_sha256": sha256_json(data),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def build_signed_testnet_gate_artifact(
    *,
    preflight_artifact: Mapping[str, Any],
    manual_approval: Mapping[str, Any],
    risk_caps: Mapping[str, Any],
    operational_state: Mapping[str, Any],
    gate_reason: str = "signed_testnet_gate_review_only",
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    preflight_validation = validate_signed_testnet_preflight_artifact(preflight_artifact)
    approval_validation = validate_signed_testnet_approval(manual_approval)
    risk_cap_validation = _validate_risk_caps(risk_caps)
    operational_validation = _validate_operational_state({**dict(risk_caps or {}), **dict(operational_state or {})})

    blockers: list[str] = []
    blockers.extend(preflight_validation.get("block_reasons", []))
    blockers.extend(approval_validation.get("block_reasons", []))
    blockers.extend(risk_cap_validation.get("block_reasons", []))
    blockers.extend(operational_validation.get("block_reasons", []))

    if not preflight_artifact.get("preflight_artifact_sha256"):
        blockers.append("SIGNED_TESTNET_PREFLIGHT_ARTIFACT_HASH_MISSING")
    if preflight_artifact.get("ready_for_signed_testnet_execution") is not False:
        blockers.append("SIGNED_TESTNET_PREFLIGHT_EXECUTION_READY_NOT_FALSE")
    if preflight_artifact.get("testnet_order_submission_allowed") is not False:
        blockers.append("SIGNED_TESTNET_PREFLIGHT_ORDER_ALLOWED_NOT_FALSE")
    if preflight_artifact.get("external_order_submission_performed") is not False:
        blockers.append("SIGNED_TESTNET_PREFLIGHT_EXTERNAL_SUBMISSION_PERFORMED")

    if manual_approval.get("timestamp_utc") and not is_canonical_utc_timestamp(manual_approval.get("timestamp_utc")):
        blockers.append("SIGNED_TESTNET_GATE_APPROVAL_TIMESTAMP_NOT_CANONICAL_UTC")

    review_ready = not blockers
    payload = {
        "version": SIGNED_TESTNET_GATE_VERSION,
        "preflight_artifact_id": preflight_artifact.get("signed_testnet_preflight_artifact_id"),
        "preflight_artifact_sha256": preflight_artifact.get("preflight_artifact_sha256"),
        "approval_sha256": approval_validation.get("approval_sha256"),
        "risk_caps_sha256": risk_cap_validation.get("risk_caps_sha256"),
        "operational_state_sha256": operational_validation.get("operational_state_sha256"),
        "gate_reason": gate_reason,
        "blockers": sorted(set(blockers)),
    }
    artifact = {
        "signed_testnet_gate_id": stable_id("signed_testnet_gate", payload),
        **payload,
        "preflight_validation": preflight_validation,
        "approval_validation": approval_validation,
        "risk_cap_validation": risk_cap_validation,
        "operational_state_validation": operational_validation,
        "gate_review_ready": review_ready,
        "ready_for_signed_testnet_execution": SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP275,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP275,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP275,
        "place_order_enabled": False,
        "signed_order_executor_enabled": False,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
    artifact["signed_testnet_gate_sha256"] = sha256_json(_payload_without_hash(artifact))
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        artifact["gate_artifact_path"] = str(path)
        artifact["signed_testnet_gate_sha256"] = sha256_json(_payload_without_hash(artifact))
        path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return artifact


def validate_signed_testnet_gate_artifact(artifact: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(artifact or {})
    blockers: list[str] = []
    if data.get("version") != SIGNED_TESTNET_GATE_VERSION:
        blockers.append("SIGNED_TESTNET_GATE_VERSION_INVALID")
    if not data.get("signed_testnet_gate_id"):
        blockers.append("SIGNED_TESTNET_GATE_ID_MISSING")
    if not data.get("preflight_artifact_id"):
        blockers.append("SIGNED_TESTNET_GATE_PREFLIGHT_ARTIFACT_ID_MISSING")
    if not data.get("preflight_artifact_sha256"):
        blockers.append("SIGNED_TESTNET_GATE_PREFLIGHT_ARTIFACT_HASH_MISSING")
    if not data.get("approval_sha256"):
        blockers.append("SIGNED_TESTNET_GATE_APPROVAL_HASH_MISSING")
    if data.get("ready_for_signed_testnet_execution") is not False:
        blockers.append("SIGNED_TESTNET_GATE_EXECUTION_READY_NOT_FALSE")
    if data.get("testnet_order_submission_allowed") is not False:
        blockers.append("SIGNED_TESTNET_GATE_ORDER_SUBMISSION_ALLOWED_NOT_FALSE")
    if data.get("external_order_submission_performed") is not False:
        blockers.append("SIGNED_TESTNET_GATE_EXTERNAL_SUBMISSION_PERFORMED")
    if data.get("place_order_enabled") is not False:
        blockers.append("SIGNED_TESTNET_GATE_PLACE_ORDER_ENABLED")
    if data.get("signed_order_executor_enabled") is not False:
        blockers.append("SIGNED_TESTNET_GATE_SIGNED_ORDER_EXECUTOR_ENABLED")
    if data.get("signed_testnet_gate_sha256") != sha256_json(_payload_without_hash(data)):
        blockers.append("SIGNED_TESTNET_GATE_HASH_INVALID")
    for reason in data.get("block_reasons") or []:
        blockers.append(str(reason))
    payload = {
        "gate_id": data.get("signed_testnet_gate_id"),
        "gate_hash": data.get("signed_testnet_gate_sha256"),
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_GATE_VERSION,
    }
    return {
        "signed_testnet_gate_validation_id": stable_id("signed_testnet_gate_validation", payload),
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
