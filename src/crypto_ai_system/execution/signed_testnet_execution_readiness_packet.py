from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.execution.signed_testnet_gate import validate_signed_testnet_gate_artifact
from crypto_ai_system.execution.venue_capability_evidence import validate_venue_capability_evidence
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION = "step276_signed_testnet_execution_readiness_packet_v1"
SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP276 = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP276 = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP276 = False
PLACE_ORDER_ENABLED_BY_STEP276 = False
SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP276 = False
DEFAULT_VENUE_EVIDENCE_MAX_AGE_SEC = 600

_REQUIRED_OPERATOR_FIELDS = [
    "operator_id",
    "operator_role",
    "execution_ticket_id",
    "operator_signature",
    "timestamp_utc",
]


def _payload_without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in dict(payload).items()
        if k not in {"execution_readiness_packet_sha256", "created_at_utc", "execution_readiness_packet_path"}
    }


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _parse_canonical_utc(value: Any) -> datetime | None:
    if not is_canonical_utc_timestamp(value):
        return None
    parsed = datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ")
    return parsed.replace(tzinfo=timezone.utc)


def _age_seconds(timestamp_utc: Any, *, now_utc: str | None = None) -> int | None:
    ts = _parse_canonical_utc(timestamp_utc)
    now = _parse_canonical_utc(now_utc or utc_now_canonical())
    if ts is None or now is None:
        return None
    return max(0, int((now - ts).total_seconds()))


def validate_operator_execution_approval(
    operator_approval: Mapping[str, Any] | None,
    *,
    signed_testnet_gate_id: str | None = None,
    signed_testnet_gate_sha256: str | None = None,
) -> dict[str, Any]:
    data = dict(operator_approval or {})
    blockers: list[str] = []
    for field in _REQUIRED_OPERATOR_FIELDS:
        if not data.get(field):
            blockers.append(f"STEP276_OPERATOR_{field.upper()}_MISSING")
    if data.get("timestamp_utc") and not is_canonical_utc_timestamp(data.get("timestamp_utc")):
        blockers.append("STEP276_OPERATOR_TIMESTAMP_NOT_CANONICAL_UTC")
    if signed_testnet_gate_id and data.get("signed_testnet_gate_id") != signed_testnet_gate_id:
        blockers.append("STEP276_OPERATOR_GATE_ID_MISMATCH")
    if signed_testnet_gate_sha256 and data.get("signed_testnet_gate_sha256") != signed_testnet_gate_sha256:
        blockers.append("STEP276_OPERATOR_GATE_HASH_MISMATCH")
    if _as_bool(data.get("operator_confirms_order_submission_enabled")):
        blockers.append("STEP276_OPERATOR_ENABLED_ORDER_SUBMISSION_BLOCKED")
    if _as_bool(data.get("operator_confirms_place_order_enabled")):
        blockers.append("STEP276_OPERATOR_ENABLED_PLACE_ORDER_BLOCKED")
    payload = {
        "operator_approval": data,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION,
    }
    return {
        "operator_execution_approval_validation_id": stable_id("operator_execution_approval_validation", payload),
        "valid": not blockers,
        "operator_execution_approval_sha256": sha256_json(data),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def validate_execution_plan_and_caps(
    execution_plan: Mapping[str, Any] | None,
    *,
    gate_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    plan = dict(execution_plan or {})
    blockers: list[str] = []
    required = [
        "symbol",
        "order_intent_id",
        "planned_order_count",
        "per_order_notional_usdt",
        "max_order_notional_usdt",
        "max_daily_order_count",
        "max_daily_loss_usdt",
        "max_consecutive_losses",
    ]
    for field in required:
        if field not in plan:
            blockers.append(f"STEP276_EXECUTION_PLAN_{field.upper()}_MISSING")

    try:
        per_order_notional = float(plan.get("per_order_notional_usdt", 0.0) or 0.0)
    except (TypeError, ValueError):
        per_order_notional = -1.0
    try:
        max_order_notional = float(plan.get("max_order_notional_usdt", 0.0) or 0.0)
    except (TypeError, ValueError):
        max_order_notional = -1.0
    try:
        planned_order_count = int(plan.get("planned_order_count", 0) or 0)
    except (TypeError, ValueError):
        planned_order_count = -1
    try:
        max_daily_order_count = int(plan.get("max_daily_order_count", 0) or 0)
    except (TypeError, ValueError):
        max_daily_order_count = -1
    try:
        max_daily_loss = float(plan.get("max_daily_loss_usdt", 0.0) or 0.0)
    except (TypeError, ValueError):
        max_daily_loss = -1.0
    try:
        max_consecutive_losses = int(plan.get("max_consecutive_losses", 0) or 0)
    except (TypeError, ValueError):
        max_consecutive_losses = -1

    if per_order_notional <= 0:
        blockers.append("STEP276_PER_ORDER_NOTIONAL_NOT_POSITIVE")
    if max_order_notional <= 0:
        blockers.append("STEP276_MAX_ORDER_NOTIONAL_NOT_POSITIVE")
    if max_order_notional > 5:
        blockers.append("STEP276_MAX_ORDER_NOTIONAL_EXCEEDS_STEP275_CAP")
    if per_order_notional > max_order_notional:
        blockers.append("STEP276_PER_ORDER_NOTIONAL_EXCEEDS_MAX_ORDER_CAP")
    if planned_order_count <= 0:
        blockers.append("STEP276_PLANNED_ORDER_COUNT_NOT_POSITIVE")
    if max_daily_order_count <= 0:
        blockers.append("STEP276_MAX_DAILY_ORDER_COUNT_NOT_POSITIVE")
    if max_daily_order_count > 3:
        blockers.append("STEP276_MAX_DAILY_ORDER_COUNT_EXCEEDS_STEP275_CAP")
    if planned_order_count > max_daily_order_count:
        blockers.append("STEP276_PLANNED_ORDER_COUNT_EXCEEDS_DAILY_CAP")
    if max_daily_loss <= 0:
        blockers.append("STEP276_MAX_DAILY_LOSS_NOT_POSITIVE")
    if max_daily_loss > 10:
        blockers.append("STEP276_MAX_DAILY_LOSS_EXCEEDS_STEP275_CAP")
    if max_consecutive_losses <= 0:
        blockers.append("STEP276_MAX_CONSECUTIVE_LOSSES_NOT_POSITIVE")
    if max_consecutive_losses > 2:
        blockers.append("STEP276_MAX_CONSECUTIVE_LOSSES_EXCEEDS_STEP275_CAP")

    if _as_bool(plan.get("place_order_enabled")):
        blockers.append("STEP276_EXECUTION_PLAN_PLACE_ORDER_ENABLED_BLOCKED")
    if _as_bool(plan.get("testnet_order_submission_allowed")):
        blockers.append("STEP276_EXECUTION_PLAN_ORDER_SUBMISSION_ALLOWED_BLOCKED")

    risk_caps = ((gate_artifact or {}).get("risk_cap_validation") or {}).get("risk_caps") or {}
    if risk_caps:
        try:
            gate_max_notional = float(risk_caps.get("max_order_notional_usdt", 0) or 0)
            if max_order_notional > gate_max_notional:
                blockers.append("STEP276_MAX_ORDER_NOTIONAL_EXCEEDS_GATE_CAP")
        except (TypeError, ValueError):
            blockers.append("STEP276_GATE_MAX_ORDER_NOTIONAL_INVALID")
        try:
            gate_daily_order_count = int(risk_caps.get("max_daily_order_count", 0) or 0)
            if max_daily_order_count > gate_daily_order_count:
                blockers.append("STEP276_MAX_DAILY_ORDER_COUNT_EXCEEDS_GATE_CAP")
        except (TypeError, ValueError):
            blockers.append("STEP276_GATE_MAX_DAILY_ORDER_COUNT_INVALID")

    payload = {
        "execution_plan": plan,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION,
    }
    return {
        "execution_plan_validation_id": stable_id("step276_execution_plan_validation", payload),
        "valid": not blockers,
        "execution_plan_sha256": sha256_json(plan),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def validate_step276_operational_state(operational_state: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(operational_state or {})
    blockers: list[str] = []
    if data.get("manual_kill_switch_required") is not True:
        blockers.append("STEP276_MANUAL_KILL_SWITCH_REQUIRED_MISSING")
    if data.get("manual_kill_switch_active") is True:
        blockers.append("STEP276_MANUAL_KILL_SWITCH_ACTIVE_BLOCKED")
    if _as_bool(data.get("testnet_signed_order_enabled")):
        blockers.append("STEP276_TESTNET_SIGNED_ORDER_FLAG_ENABLED_BLOCKED")
    if _as_bool(data.get("enable_real_orders")):
        blockers.append("STEP276_ENABLE_REAL_ORDERS_BLOCKED")
    if _as_bool(data.get("live_trading_enabled")) or _as_bool(data.get("allow_live_trading")):
        blockers.append("STEP276_LIVE_TRADING_FLAGS_BLOCKED")
    if _as_bool(data.get("place_order_enabled")):
        blockers.append("STEP276_PLACE_ORDER_ENABLED_BLOCKED")
    if _as_bool(data.get("signed_order_executor_enabled")):
        blockers.append("STEP276_SIGNED_ORDER_EXECUTOR_ENABLED_BLOCKED")
    if str(data.get("trading_mode") or "paper").strip().lower() in {"testnet", "live"}:
        blockers.append("STEP276_TRADING_MODE_MUST_REMAIN_PAPER_OR_REVIEW_ONLY")

    try:
        current_orders = int(data.get("current_daily_order_count", 0) or 0)
        max_orders = int(data.get("max_daily_order_count", 3) or 3)
        planned_orders = int(data.get("planned_order_count", 1) or 1)
        if current_orders + planned_orders > max_orders:
            blockers.append("STEP276_DAILY_ORDER_COUNT_CAP_WOULD_BE_EXCEEDED")
    except (TypeError, ValueError):
        blockers.append("STEP276_DAILY_ORDER_COUNT_STATE_INVALID")

    try:
        current_loss = float(data.get("current_daily_loss_usdt", 0.0) or 0.0)
        max_loss = float(data.get("max_daily_loss_usdt", 10.0) or 10.0)
        if current_loss >= max_loss:
            blockers.append("STEP276_DAILY_LOSS_CAP_REACHED")
    except (TypeError, ValueError):
        blockers.append("STEP276_DAILY_LOSS_STATE_INVALID")

    try:
        consecutive_losses = int(data.get("current_consecutive_losses", 0) or 0)
        max_losses = int(data.get("max_consecutive_losses", 2) or 2)
        if consecutive_losses >= max_losses:
            blockers.append("STEP276_CONSECUTIVE_LOSS_CAP_REACHED")
    except (TypeError, ValueError):
        blockers.append("STEP276_CONSECUTIVE_LOSS_STATE_INVALID")

    payload = {
        "operational_state": data,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION,
    }
    return {
        "step276_operational_state_validation_id": stable_id("step276_operational_state_validation", payload),
        "valid": not blockers,
        "operational_state_sha256": sha256_json(data),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def validate_venue_evidence_freshness(
    venue_capability_evidence: Mapping[str, Any] | None,
    *,
    max_age_sec: int = DEFAULT_VENUE_EVIDENCE_MAX_AGE_SEC,
    now_utc: str | None = None,
) -> dict[str, Any]:
    evidence = dict(venue_capability_evidence or {})
    blockers: list[str] = []
    venue_validation = validate_venue_capability_evidence(evidence)
    blockers.extend(venue_validation.get("block_reasons", []))
    created_at = evidence.get("created_at_utc")
    age = _age_seconds(created_at, now_utc=now_utc)
    if age is None:
        blockers.append("STEP276_VENUE_EVIDENCE_TIMESTAMP_NOT_CANONICAL_UTC")
    elif age > max_age_sec:
        blockers.append("STEP276_VENUE_EVIDENCE_STALE_BLOCKED")
    if max_age_sec <= 0:
        blockers.append("STEP276_VENUE_EVIDENCE_MAX_AGE_INVALID")
    payload = {
        "venue_capability_evidence_id": evidence.get("venue_capability_evidence_id"),
        "venue_capability_evidence_hash": evidence.get("venue_capability_evidence_hash"),
        "max_age_sec": max_age_sec,
        "age_sec": age,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION,
    }
    return {
        "venue_evidence_freshness_validation_id": stable_id("venue_evidence_freshness_validation", payload),
        "valid": not blockers,
        "venue_capability_evidence_id": evidence.get("venue_capability_evidence_id"),
        "venue_capability_evidence_hash": evidence.get("venue_capability_evidence_hash"),
        "venue_evidence_age_sec": age,
        "venue_evidence_max_age_sec": max_age_sec,
        "venue_validation": venue_validation,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def validate_reconciliation_zero_state(reconciliation_state: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(reconciliation_state or {})
    blockers: list[str] = []
    if data.get("reconciliation_mismatch_present") is True:
        blockers.append("STEP276_RECONCILIATION_MISMATCH_PRESENT_BLOCKED")
    try:
        mismatch_rate = float(data.get("reconciliation_mismatch_rate", 0.0) or 0.0)
    except (TypeError, ValueError):
        mismatch_rate = 1.0
    if mismatch_rate > 0.0:
        blockers.append("STEP276_RECONCILIATION_MISMATCH_RATE_NOT_ZERO_BLOCKED")
    if data.get("last_reconciliation_status") not in {"RECONCILIATION_MATCHED", "matched"}:
        blockers.append("STEP276_LAST_RECONCILIATION_NOT_MATCHED_BLOCKED")
    if data.get("reconciliation_evidence_hash_valid") is not True:
        blockers.append("STEP276_RECONCILIATION_EVIDENCE_HASH_NOT_VALID")
    if data.get("reconciliation_evidence_complete") is not True:
        blockers.append("STEP276_RECONCILIATION_EVIDENCE_INCOMPLETE")
    payload = {
        "reconciliation_state": data,
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION,
    }
    return {
        "reconciliation_zero_state_validation_id": stable_id("reconciliation_zero_state_validation", payload),
        "valid": not blockers,
        "reconciliation_state_sha256": sha256_json(data),
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }


def build_signed_testnet_execution_readiness_packet(
    *,
    signed_testnet_gate_artifact: Mapping[str, Any],
    operator_approval: Mapping[str, Any],
    execution_plan: Mapping[str, Any],
    operational_state: Mapping[str, Any],
    venue_capability_evidence: Mapping[str, Any],
    reconciliation_state: Mapping[str, Any],
    venue_evidence_max_age_sec: int = DEFAULT_VENUE_EVIDENCE_MAX_AGE_SEC,
    packet_reason: str = "signed_testnet_execution_readiness_review_only",
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    gate_validation = validate_signed_testnet_gate_artifact(signed_testnet_gate_artifact)
    gate_id = signed_testnet_gate_artifact.get("signed_testnet_gate_id")
    gate_hash = signed_testnet_gate_artifact.get("signed_testnet_gate_sha256")
    operator_validation = validate_operator_execution_approval(
        operator_approval,
        signed_testnet_gate_id=gate_id,
        signed_testnet_gate_sha256=gate_hash,
    )
    execution_plan_validation = validate_execution_plan_and_caps(
        execution_plan,
        gate_artifact=signed_testnet_gate_artifact,
    )
    merged_operational_state = {**dict(execution_plan or {}), **dict(operational_state or {})}
    operational_validation = validate_step276_operational_state(merged_operational_state)
    venue_freshness_validation = validate_venue_evidence_freshness(
        venue_capability_evidence,
        max_age_sec=venue_evidence_max_age_sec,
    )
    reconciliation_validation = validate_reconciliation_zero_state(reconciliation_state)

    blockers: list[str] = []
    blockers.extend(gate_validation.get("block_reasons", []))
    blockers.extend(operator_validation.get("block_reasons", []))
    blockers.extend(execution_plan_validation.get("block_reasons", []))
    blockers.extend(operational_validation.get("block_reasons", []))
    blockers.extend(venue_freshness_validation.get("block_reasons", []))
    blockers.extend(reconciliation_validation.get("block_reasons", []))

    if signed_testnet_gate_artifact.get("gate_review_ready") is not True:
        blockers.append("STEP276_SIGNED_TESTNET_GATE_NOT_REVIEW_READY")
    if signed_testnet_gate_artifact.get("ready_for_signed_testnet_execution") is not False:
        blockers.append("STEP276_GATE_EXECUTION_READY_NOT_FALSE")
    if signed_testnet_gate_artifact.get("testnet_order_submission_allowed") is not False:
        blockers.append("STEP276_GATE_ORDER_SUBMISSION_ALLOWED_NOT_FALSE")
    if signed_testnet_gate_artifact.get("place_order_enabled") is not False:
        blockers.append("STEP276_GATE_PLACE_ORDER_ENABLED_BLOCKED")
    if signed_testnet_gate_artifact.get("signed_order_executor_enabled") is not False:
        blockers.append("STEP276_GATE_SIGNED_EXECUTOR_ENABLED_BLOCKED")

    review_ready = not blockers
    session_payload = {
        "version": SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION,
        "signed_testnet_gate_id": gate_id,
        "signed_testnet_gate_sha256": gate_hash,
        "operator_execution_approval_sha256": operator_validation.get("operator_execution_approval_sha256"),
        "execution_plan_sha256": execution_plan_validation.get("execution_plan_sha256"),
        "venue_capability_evidence_hash": venue_freshness_validation.get("venue_capability_evidence_hash"),
        "reconciliation_state_sha256": reconciliation_validation.get("reconciliation_state_sha256"),
        "packet_reason": packet_reason,
    }
    packet_payload = {
        **session_payload,
        "blockers": sorted(set(blockers)),
        "review_ready": review_ready,
    }
    packet = {
        "signed_testnet_execution_readiness_packet_id": stable_id("signed_testnet_execution_readiness_packet", packet_payload),
        "testnet_execution_session_id": stable_id("testnet_execution_session", session_payload),
        "version": SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION,
        "signed_testnet_gate_id": gate_id,
        "signed_testnet_gate_sha256": gate_hash,
        "signed_testnet_gate_validation": gate_validation,
        "operator_execution_approval_validation": operator_validation,
        "execution_plan_validation": execution_plan_validation,
        "operational_state_validation": operational_validation,
        "venue_evidence_freshness_validation": venue_freshness_validation,
        "reconciliation_zero_state_validation": reconciliation_validation,
        "execution_plan_sha256": execution_plan_validation.get("execution_plan_sha256"),
        "operational_state_sha256": operational_validation.get("operational_state_sha256"),
        "venue_capability_evidence_id": venue_freshness_validation.get("venue_capability_evidence_id"),
        "venue_capability_evidence_hash": venue_freshness_validation.get("venue_capability_evidence_hash"),
        "reconciliation_state_sha256": reconciliation_validation.get("reconciliation_state_sha256"),
        "packet_review_ready": review_ready,
        "ready_for_signed_testnet_execution": SIGNED_TESTNET_EXECUTION_ALLOWED_BY_STEP276,
        "testnet_order_submission_allowed": TESTNET_ORDER_SUBMISSION_ALLOWED_BY_STEP276,
        "external_order_submission_performed": EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_STEP276,
        "place_order_enabled": PLACE_ORDER_ENABLED_BY_STEP276,
        "signed_order_executor_enabled": SIGNED_ORDER_EXECUTOR_ENABLED_BY_STEP276,
        "order_submission_remains_disabled": True,
        "block_reasons": sorted(set(blockers)),
        "packet_reason": packet_reason,
        "created_at_utc": utc_now_canonical(),
    }
    packet["execution_readiness_packet_sha256"] = sha256_json(_payload_without_hash(packet))
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        packet["execution_readiness_packet_path"] = str(path)
        packet["execution_readiness_packet_sha256"] = sha256_json(_payload_without_hash(packet))
        path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    return packet


def validate_signed_testnet_execution_readiness_packet(packet: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(packet or {})
    blockers: list[str] = []
    if data.get("version") != SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION:
        blockers.append("STEP276_EXECUTION_READINESS_PACKET_VERSION_INVALID")
    if not data.get("signed_testnet_execution_readiness_packet_id"):
        blockers.append("STEP276_EXECUTION_READINESS_PACKET_ID_MISSING")
    if not data.get("testnet_execution_session_id"):
        blockers.append("STEP276_TESTNET_EXECUTION_SESSION_ID_MISSING")
    if not data.get("signed_testnet_gate_id"):
        blockers.append("STEP276_PACKET_GATE_ID_MISSING")
    if not data.get("signed_testnet_gate_sha256"):
        blockers.append("STEP276_PACKET_GATE_HASH_MISSING")
    if not data.get("venue_capability_evidence_hash"):
        blockers.append("STEP276_PACKET_VENUE_EVIDENCE_HASH_MISSING")
    if data.get("ready_for_signed_testnet_execution") is not False:
        blockers.append("STEP276_PACKET_EXECUTION_READY_NOT_FALSE")
    if data.get("testnet_order_submission_allowed") is not False:
        blockers.append("STEP276_PACKET_ORDER_SUBMISSION_ALLOWED_NOT_FALSE")
    if data.get("external_order_submission_performed") is not False:
        blockers.append("STEP276_PACKET_EXTERNAL_SUBMISSION_PERFORMED")
    if data.get("place_order_enabled") is not False:
        blockers.append("STEP276_PACKET_PLACE_ORDER_ENABLED")
    if data.get("signed_order_executor_enabled") is not False:
        blockers.append("STEP276_PACKET_SIGNED_EXECUTOR_ENABLED")
    if data.get("order_submission_remains_disabled") is not True:
        blockers.append("STEP276_PACKET_ORDER_SUBMISSION_DISABLED_INVARIANT_MISSING")
    expected_hash = sha256_json(_payload_without_hash(data))
    if data.get("execution_readiness_packet_sha256") != expected_hash:
        blockers.append("STEP276_EXECUTION_READINESS_PACKET_HASH_INVALID")
    for reason in data.get("block_reasons") or []:
        blockers.append(str(reason))
    payload = {
        "packet_id": data.get("signed_testnet_execution_readiness_packet_id"),
        "packet_hash": data.get("execution_readiness_packet_sha256"),
        "blockers": sorted(set(blockers)),
        "version": SIGNED_TESTNET_EXECUTION_READINESS_PACKET_VERSION,
    }
    return {
        "signed_testnet_execution_readiness_packet_validation_id": stable_id("signed_testnet_execution_readiness_packet_validation", payload),
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "created_at_utc": utc_now_canonical(),
    }
