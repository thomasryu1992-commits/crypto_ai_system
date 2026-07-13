from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

DISABLED_EXECUTOR_VERSION = "disabled_signed_testnet_executor_v1"

UNSAFE_TRUTHY_FIELDS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
]

REQUIRED_PAYLOAD_FIELDS = [
    "symbol",
    "side",
    "order_type",
    "quantity",
    "notional",
    "time_in_force",
    "idempotency_key",
    "canonical_id_chain",
]

REQUIRED_ID_CHAIN_FIELDS = [
    "data_snapshot_id",
    "feature_snapshot_id",
    "research_signal_id",
    "profile_id",
    "approval_packet_id",
    "approval_intake_id",
    "decision_id",
    "risk_gate_id",
    "order_intent_id",
]


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def unsafe_truthy_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    return [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]


def _positive_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def validate_review_only_would_submit_payload(
    payload: Mapping[str, Any], *, max_notional: float | None = None
) -> dict[str, Any]:
    data = dict(payload or {})
    blockers: list[str] = []

    missing = [field for field in REQUIRED_PAYLOAD_FIELDS if data.get(field) in (None, "", [])]
    if missing:
        blockers.append("MISSING_REQUIRED_PAYLOAD_FIELDS:" + ",".join(missing))

    chain = data.get("canonical_id_chain") if isinstance(data.get("canonical_id_chain"), Mapping) else {}
    missing_chain = [field for field in REQUIRED_ID_CHAIN_FIELDS if not chain.get(field)]
    if missing_chain:
        blockers.append("MISSING_CANONICAL_ID_CHAIN_FIELDS:" + ",".join(missing_chain))

    if not _positive_number(data.get("quantity")):
        blockers.append("QUANTITY_NOT_POSITIVE_NUMERIC")
    if not _positive_number(data.get("notional")):
        blockers.append("NOTIONAL_NOT_POSITIVE_NUMERIC")

    if max_notional is None and data.get("max_testnet_notional_usd") not in (None, ""):
        try:
            max_notional = float(data.get("max_testnet_notional_usd"))
        except (TypeError, ValueError):
            blockers.append("MAX_TESTNET_NOTIONAL_NOT_NUMERIC")

    if max_notional is not None:
        try:
            if float(data.get("notional")) > max_notional:
                blockers.append("HARD_CAP_EXCEEDED_MAX_TESTNET_NOTIONAL")
        except (TypeError, ValueError):
            blockers.append("NOTIONAL_NOT_NUMERIC_FOR_HARD_CAP_CHECK")

    for field in ("kill_switch_rechecked", "hard_caps_rechecked", "pre_order_risk_gate_rechecked"):
        if data.get(field) is not True:
            blockers.append(f"{field.upper()}_NOT_TRUE")

    unsafe = unsafe_truthy_fields(data)
    if unsafe:
        blockers.append("UNSAFE_WOULD_SUBMIT_PAYLOAD_FLAG:" + ",".join(unsafe))

    blockers = sorted(dict.fromkeys(blockers))
    return {
        "payload_valid_review_only": not blockers,
        "payload_blocked_fail_closed": bool(blockers),
        "missing_required_payload_fields": missing,
        "missing_canonical_id_chain_fields": missing_chain,
        "unsafe_truthy_fields": unsafe,
        "payload_blockers": blockers,
    }


@dataclass
class DisabledSignedTestnetExecutor:
    """Review-only executor stub that can never submit or cancel real orders."""

    executor_id: str = "disabled_signed_testnet_executor_review_only"
    endpoint_call_count: int = 0
    endpoint_calls: list[dict[str, Any]] = field(default_factory=list)

    def _common_disabled_flags(self) -> dict[str, Any]:
        return {
            "runtime_permission_source": False,
            "signed_testnet_unlock_authority": False,
            "secret_value_accessed": False,
            "secret_file_read": False,
            "secret_file_created": False,
            "api_key_value_access_allowed": False,
            "api_secret_value_access_allowed": False,
            "secret_file_access_allowed": False,
            "secret_file_creation_allowed": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "signed_testnet_promotion_allowed": False,
            "external_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "candidate_profile_applied": False,
            "settings_write_preview_applied": False,
            "live_trading_allowed": False,
            "auto_promotion_allowed": False,
        }

    def submit_order(self, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        data = dict(payload or {})
        created = utc_now_canonical()
        validation = validate_review_only_would_submit_payload(data)
        blockers = ["SIGNED_TESTNET_EXECUTOR_DISABLED_REVIEW_ONLY"]
        blockers.extend(validation.get("payload_blockers") or [])
        blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
        evidence_id = stable_id(
            "blocked_signed_testnet_execution_evidence",
            {"payload_hash": sha256_json(data), "blockers": blockers, "created_at_utc": created},
            24,
        )
        return {
            "evidence_type": "disabled_signed_testnet_blocked_execution_evidence_review_only",
            "disabled_executor_version": DISABLED_EXECUTOR_VERSION,
            "executor_id": self.executor_id,
            "execution_id": evidence_id,
            "status": "SIGNED_TESTNET_ORDER_SUBMISSION_BLOCKED_EXECUTOR_DISABLED_REVIEW_ONLY",
            "blocked": True,
            "fail_closed": True,
            "review_only": True,
            "submit_order_blocked_review_only": True,
            "payload_valid_review_only": validation.get("payload_valid_review_only") is True,
            "payload_validation": validation,
            "block_reasons": blockers,
            "exchange_endpoint_called": False,
            "endpoint_call_count": self.endpoint_call_count,
            "actual_order_submission_performed": False,
            "external_order_submission_performed": False,
            "would_submit_payload_sha256": sha256_json(data),
            "created_at_utc": created,
            **self._common_disabled_flags(),
        }

    def cancel_order(self, *, execution_id: str | None = None, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = dict(payload or {})
        created = utc_now_canonical()
        blockers = ["SIGNED_TESTNET_CANCEL_BLOCKED_EXECUTOR_DISABLED_REVIEW_ONLY"]
        unsafe = unsafe_truthy_fields(data)
        if unsafe:
            blockers.append("UNSAFE_CANCEL_PAYLOAD_FLAG:" + ",".join(unsafe))
        if not execution_id and not data.get("execution_id"):
            blockers.append("MISSING_BLOCKED_EXECUTION_ID_FOR_CANCEL_REVIEW")
        blockers = sorted(dict.fromkeys(blockers))
        cancel_id = stable_id(
            "blocked_signed_testnet_cancel_evidence",
            {"execution_id": execution_id or data.get("execution_id"), "payload_hash": sha256_json(data), "created_at_utc": created},
            24,
        )
        return {
            "evidence_type": "disabled_signed_testnet_blocked_cancel_evidence_review_only",
            "disabled_executor_version": DISABLED_EXECUTOR_VERSION,
            "executor_id": self.executor_id,
            "cancel_evidence_id": cancel_id,
            "source_execution_id": execution_id or data.get("execution_id"),
            "status": "SIGNED_TESTNET_CANCEL_BLOCKED_EXECUTOR_DISABLED_REVIEW_ONLY",
            "blocked": True,
            "fail_closed": True,
            "review_only": True,
            "cancel_order_blocked_review_only": True,
            "block_reasons": blockers,
            "unsafe_truthy_fields": unsafe,
            "exchange_endpoint_called": False,
            "endpoint_call_count": self.endpoint_call_count,
            "actual_cancel_performed": False,
            "external_order_submission_performed": False,
            "created_at_utc": created,
            **self._common_disabled_flags(),
        }


__all__ = [
    "DISABLED_EXECUTOR_VERSION",
    "DisabledSignedTestnetExecutor",
    "REQUIRED_ID_CHAIN_FIELDS",
    "REQUIRED_PAYLOAD_FIELDS",
    "UNSAFE_TRUTHY_FIELDS",
    "unsafe_truthy_fields",
    "validate_review_only_would_submit_payload",
]
