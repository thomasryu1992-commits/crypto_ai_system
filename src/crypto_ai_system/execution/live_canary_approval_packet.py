from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

STEP313_LIVE_CANARY_APPROVAL_PACKET_VERSION = "step313_live_canary_approval_packet_v1"
LIVE_CANARY_APPROVAL_PACKET_REGISTRY_NAME = "live_canary_approval_packet_registry"

STATUS_READY_REVIEW_ONLY = "LIVE_CANARY_APPROVAL_PACKET_READY_REVIEW_ONLY"
STATUS_BLOCKED = "LIVE_CANARY_APPROVAL_PACKET_BLOCKED"
STATUS_BLOCKED_EVIDENCE_MISSING = "LIVE_CANARY_APPROVAL_PACKET_BLOCKED_EVIDENCE_MISSING"
STATUS_BLOCKED_UNSAFE_SIDE_EFFECT = "LIVE_CANARY_APPROVAL_PACKET_BLOCKED_UNSAFE_SIDE_EFFECT"

SESSION_CLOSE_OK = "SIGNED_TESTNET_SESSION_CLOSE_REPORT_RECORDED_REVIEW_ONLY"
LIVE_PROBE_OK = "LIVE_READ_ONLY_ADAPTER_PROBE_VALID"
LIVE_KEY_SCOPE_OK = "LIVE_KEY_SCOPE_VALIDATED_METADATA_ONLY"

BLOCK_MISSING_OPERATOR_REQUEST = "STEP313_BLOCK_MISSING_OPERATOR_LIVE_CANARY_APPROVAL_REQUEST"
BLOCK_OPERATOR_STAGE_INVALID = "STEP313_BLOCK_OPERATOR_REQUEST_NOT_FOR_LIVE_CANARY"
BLOCK_OPERATOR_ID_MISSING = "STEP313_BLOCK_OPERATOR_ID_MISSING"
BLOCK_OPERATOR_SIGNATURE_MISSING = "STEP313_BLOCK_OPERATOR_TICKET_OR_SIGNATURE_MISSING"
BLOCK_OPERATOR_TIMESTAMP_INVALID = "STEP313_BLOCK_OPERATOR_TIMESTAMP_INVALID"
BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_DISABLED_EXECUTION = "STEP313_BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_DISABLED_EXECUTION"
BLOCK_OPERATOR_REQUESTS_LIVE_ORDER_SUBMISSION = "STEP313_BLOCK_OPERATOR_REQUESTS_LIVE_ORDER_SUBMISSION_ENABLED"
BLOCK_OPERATOR_REQUESTS_PLACE_ORDER = "STEP313_BLOCK_OPERATOR_REQUESTS_PLACE_ORDER_ENABLED"
BLOCK_SESSION_CLOSE_MISSING = "STEP313_BLOCK_MISSING_SIGNED_TESTNET_SESSION_CLOSE_REPORT"
BLOCK_SESSION_CLOSE_NOT_SUCCESSFUL = "STEP313_BLOCK_SIGNED_TESTNET_SESSION_NOT_SUCCESSFUL"
BLOCK_SESSION_NO_SUBMITTED_ORDER = "STEP313_BLOCK_SIGNED_TESTNET_SESSION_HAS_NO_SUBMITTED_ORDER"
BLOCK_SESSION_RECONCILIATION_MISMATCH = "STEP313_BLOCK_SIGNED_TESTNET_RECONCILIATION_MISMATCH"
BLOCK_SESSION_API_ERRORS = "STEP313_BLOCK_SIGNED_TESTNET_API_ERRORS"
BLOCK_LIVE_PROBE_MISSING = "STEP313_BLOCK_MISSING_LIVE_READ_ONLY_PROBE"
BLOCK_LIVE_PROBE_INVALID = "STEP313_BLOCK_LIVE_READ_ONLY_PROBE_INVALID"
BLOCK_LIVE_PROBE_STALE = "STEP313_BLOCK_LIVE_READ_ONLY_PROBE_STALE"
BLOCK_LIVE_KEY_SCOPE_MISSING = "STEP313_BLOCK_MISSING_LIVE_KEY_SCOPE_VALIDATION"
BLOCK_LIVE_KEY_SCOPE_INVALID = "STEP313_BLOCK_LIVE_KEY_SCOPE_NOT_VALIDATED"
BLOCK_KILL_SWITCH_NOT_RECHECKED = "STEP313_BLOCK_KILL_SWITCH_NOT_RECHECKED"
BLOCK_MANUAL_KILL_SWITCH_ACTIVE = "STEP313_BLOCK_MANUAL_KILL_SWITCH_ACTIVE"
BLOCK_HARD_CAP_NOT_RECHECKED = "STEP313_BLOCK_HARD_CAP_NOT_RECHECKED"
BLOCK_HARD_CAP_INVALID = "STEP313_BLOCK_HARD_CAP_INVALID"
BLOCK_MONITORING_NOT_READY = "STEP313_BLOCK_MONITORING_NOT_READY"
BLOCK_SECRET_VALUE_ACCESS = "STEP313_BLOCK_SECRET_VALUE_ACCESS"
BLOCK_UNSAFE_RUNTIME_FLAG = "STEP313_BLOCK_UNSAFE_RUNTIME_FLAG"
BLOCK_CANONICAL_ID_CHAIN_MISSING = "STEP313_BLOCK_MISSING_CANONICAL_ID_CHAIN"

_FORBIDDEN_FLAG_FIELDS = [
    "live_canary_ready",
    "live_order_submission_allowed",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "withdrawal_enabled",
    "transfer_enabled",
    "admin_enabled",
    "write_enabled",
    "trade_enabled",
    "leverage_mutation_enabled",
    "margin_mode_mutation_enabled",
    "signed_order_executor_enabled",
    "live_trading_enabled",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "auto_promotion_allowed",
]
_SECRET_ACCESS_FIELDS = [
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "secret_value_read",
    "secret_bytes_read",
]
_CANONICAL_FIELDS = [
    "data_snapshot_id",
    "feature_snapshot_id",
    "research_signal_id",
    "profile_id",
    "approval_packet_id",
    "approval_intake_id",
    "decision_id",
    "risk_gate_id",
    "order_intent_id",
    "execution_id",
    "reconciliation_id",
]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _age_sec(value: Any) -> int | None:
    if not is_canonical_utc_timestamp(value):
        return None
    dt = datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))


def _unsafe_flags(*sources: Mapping[str, Any], policy: "LiveCanaryApprovalPolicy") -> dict[str, bool]:
    result: dict[str, bool] = {}
    for field_name in _FORBIDDEN_FLAG_FIELDS + _SECRET_ACCESS_FIELDS:
        result[field_name] = _bool(getattr(policy, field_name, False)) or any(_bool(src.get(field_name)) for src in sources)
    return result


@dataclass(frozen=True)
class LiveCanaryApprovalPolicy:
    review_only: bool = True
    require_operator_live_canary_request: bool = True
    require_signed_testnet_success: bool = True
    require_submitted_signed_testnet_order: bool = True
    require_zero_reconciliation_mismatch: bool = True
    require_zero_api_error_count: bool = True
    require_fresh_live_read_only_probe: bool = True
    require_live_key_scope_validation: bool = True
    max_live_probe_age_sec: int = 600
    require_manual_kill_switch_recheck: bool = True
    require_hard_cap_recheck: bool = True
    require_monitoring_ready: bool = True
    max_order_notional_usdt_limit: float = 5.0
    max_daily_order_count_limit: int = 1
    max_daily_loss_usdt_limit: float = 10.0
    live_canary_ready: bool = False
    live_order_submission_allowed: bool = False
    external_order_submission_allowed: bool = False
    external_order_submission_performed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    withdrawal_enabled: bool = False
    transfer_enabled: bool = False
    admin_enabled: bool = False
    write_enabled: bool = False
    trade_enabled: bool = False
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
class OperatorLiveCanaryApprovalRequest:
    requested_stage: str = "live_canary"
    operator_id: str = "operator_thomas_review_only"
    ticket_or_signature: str = field(default_factory=lambda: f"LIVE-CANARY-REVIEW-{stable_id('ticket', {'step': 313}, 8)}")
    acknowledged_live_execution_disabled_by_default: bool = True
    request_live_order_submission_enabled: bool = False
    request_place_order_enabled: bool = False
    kill_switch_rechecked: bool = True
    manual_kill_switch_active: bool = False
    hard_cap_rechecked: bool = True
    max_order_notional_usdt: float = 5.0
    max_daily_order_count: int = 1
    max_daily_loss_usdt: float = 10.0
    monitoring_ready: bool = True
    alerting_ready: bool = True
    heartbeat_ready: bool = True
    incident_runbook_ready: bool = True
    requested_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _operator_request_blockers(request: Mapping[str, Any], policy: LiveCanaryApprovalPolicy) -> tuple[list[str], dict[str, Any]]:
    if not request:
        return [BLOCK_MISSING_OPERATOR_REQUEST], {"present": False, "operator_id": None}
    blockers: list[str] = []
    stage = str(request.get("requested_stage") or "").strip().lower()
    if stage != "live_canary":
        blockers.append(BLOCK_OPERATOR_STAGE_INVALID)
    operator_id = str(request.get("operator_id") or "").strip()
    if not operator_id:
        blockers.append(BLOCK_OPERATOR_ID_MISSING)
    if not str(request.get("ticket_or_signature") or "").strip():
        blockers.append(BLOCK_OPERATOR_SIGNATURE_MISSING)
    requested_at = request.get("requested_at_utc") or request.get("created_at_utc")
    if not is_canonical_utc_timestamp(requested_at):
        blockers.append(BLOCK_OPERATOR_TIMESTAMP_INVALID)
    if request.get("acknowledged_live_execution_disabled_by_default") is not True:
        blockers.append(BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_DISABLED_EXECUTION)
    if _bool(request.get("request_live_order_submission_enabled")):
        blockers.append(BLOCK_OPERATOR_REQUESTS_LIVE_ORDER_SUBMISSION)
    if _bool(request.get("request_place_order_enabled")):
        blockers.append(BLOCK_OPERATOR_REQUESTS_PLACE_ORDER)
    if policy.require_manual_kill_switch_recheck and request.get("kill_switch_rechecked") is not True:
        blockers.append(BLOCK_KILL_SWITCH_NOT_RECHECKED)
    if _bool(request.get("manual_kill_switch_active")):
        blockers.append(BLOCK_MANUAL_KILL_SWITCH_ACTIVE)
    if policy.require_hard_cap_recheck and request.get("hard_cap_rechecked") is not True:
        blockers.append(BLOCK_HARD_CAP_NOT_RECHECKED)
    max_order = _num(request.get("max_order_notional_usdt"))
    max_daily_count = _num(request.get("max_daily_order_count"))
    max_daily_loss = _num(request.get("max_daily_loss_usdt"))
    if (
        max_order is None
        or max_order <= 0
        or max_order > policy.max_order_notional_usdt_limit
        or max_daily_count is None
        or max_daily_count <= 0
        or max_daily_count > policy.max_daily_order_count_limit
        or max_daily_loss is None
        or max_daily_loss <= 0
        or max_daily_loss > policy.max_daily_loss_usdt_limit
    ):
        blockers.append(BLOCK_HARD_CAP_INVALID)
    if policy.require_monitoring_ready:
        if not (request.get("monitoring_ready") is True and request.get("alerting_ready") is True and request.get("heartbeat_ready") is True):
            blockers.append(BLOCK_MONITORING_NOT_READY)
    return blockers, {
        "present": True,
        "requested_stage": stage,
        "operator_id": operator_id or None,
        "ticket_or_signature_present": bool(str(request.get("ticket_or_signature") or "").strip()),
        "requested_at_utc": requested_at,
        "kill_switch_rechecked": request.get("kill_switch_rechecked") is True,
        "manual_kill_switch_active": _bool(request.get("manual_kill_switch_active")),
        "hard_cap_rechecked": request.get("hard_cap_rechecked") is True,
        "max_order_notional_usdt": max_order,
        "max_daily_order_count": int(max_daily_count) if max_daily_count is not None else None,
        "max_daily_loss_usdt": max_daily_loss,
        "monitoring_ready": request.get("monitoring_ready") is True,
        "alerting_ready": request.get("alerting_ready") is True,
        "heartbeat_ready": request.get("heartbeat_ready") is True,
        "incident_runbook_ready": request.get("incident_runbook_ready") is True,
    }


def _session_close_blockers(report: Mapping[str, Any], policy: LiveCanaryApprovalPolicy) -> tuple[list[str], dict[str, Any]]:
    if not report:
        return [BLOCK_SESSION_CLOSE_MISSING], {"present": False}
    blockers: list[str] = []
    if report.get("status") != SESSION_CLOSE_OK:
        blockers.append(BLOCK_SESSION_CLOSE_NOT_SUCCESSFUL)
    if policy.require_submitted_signed_testnet_order and int(report.get("orders_submitted_count") or 0) <= 0:
        blockers.append(BLOCK_SESSION_NO_SUBMITTED_ORDER)
    if policy.require_zero_reconciliation_mismatch and int(report.get("reconciliation_mismatch_count") or 0) != 0:
        blockers.append(BLOCK_SESSION_RECONCILIATION_MISMATCH)
    if policy.require_zero_api_error_count and int(report.get("api_error_count") or 0) != 0:
        blockers.append(BLOCK_SESSION_API_ERRORS)
    return blockers, {
        "present": True,
        "signed_testnet_session_close_report_id": report.get("signed_testnet_session_close_report_id"),
        "signed_testnet_session_close_report_sha256": report.get("signed_testnet_session_close_report_sha256"),
        "status": report.get("status"),
        "orders_submitted_count": report.get("orders_submitted_count"),
        "orders_filled_count": report.get("orders_filled_count"),
        "orders_rejected_count": report.get("orders_rejected_count"),
        "reconciliation_mismatch_count": report.get("reconciliation_mismatch_count"),
        "api_error_count": report.get("api_error_count"),
        "promotion_recommendation": report.get("promotion_recommendation"),
    }


def _live_probe_blockers(probe: Mapping[str, Any], policy: LiveCanaryApprovalPolicy) -> tuple[list[str], dict[str, Any]]:
    if not probe:
        return [BLOCK_LIVE_PROBE_MISSING], {"present": False, "fresh": False}
    blockers: list[str] = []
    if probe.get("status") != LIVE_PROBE_OK or probe.get("valid") is not True:
        blockers.append(BLOCK_LIVE_PROBE_INVALID)
    age = _age_sec(probe.get("created_at_utc"))
    if age is None or age > policy.max_live_probe_age_sec or probe.get("all_live_read_probes_valid_and_fresh") is not True:
        blockers.append(BLOCK_LIVE_PROBE_STALE)
    return blockers, {
        "present": True,
        "live_read_only_adapter_probe_id": probe.get("live_read_only_adapter_probe_id"),
        "live_read_only_adapter_probe_sha256": probe.get("live_read_only_adapter_probe_sha256"),
        "status": probe.get("status"),
        "valid": probe.get("valid") is True,
        "fresh": age is not None and age <= policy.max_live_probe_age_sec,
        "source_age_sec": age,
        "venue": probe.get("venue"),
        "environment": probe.get("environment"),
    }


def _live_key_scope_blockers(validation: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    if not validation:
        return [BLOCK_LIVE_KEY_SCOPE_MISSING], {"present": False}
    blockers: list[str] = []
    if validation.get("status") != LIVE_KEY_SCOPE_OK or validation.get("valid") is not True:
        blockers.append(BLOCK_LIVE_KEY_SCOPE_INVALID)
    return blockers, {
        "present": True,
        "live_key_scope_validation_id": validation.get("live_key_scope_validation_id"),
        "live_key_scope_validation_sha256": validation.get("live_key_scope_validation_sha256"),
        "status": validation.get("status"),
        "valid": validation.get("valid") is True,
        "metadata_only": validation.get("metadata_only") is True,
        "live_read_only_probe_valid_and_fresh": validation.get("live_read_only_probe_valid_and_fresh"),
        "venue": validation.get("venue"),
        "environment": validation.get("environment"),
    }


def _canonical_chain_summary(*sources: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    merged: dict[str, Any] = {}
    for field_name in _CANONICAL_FIELDS:
        for src in sources:
            if src.get(field_name):
                merged[field_name] = src.get(field_name)
                break
    missing = [field for field in _CANONICAL_FIELDS if not merged.get(field)]
    return missing, {"present_fields": merged, "missing_fields": missing, "complete_for_live_canary_review": not missing}


def build_live_canary_approval_packet(
    *,
    signed_testnet_session_close_report: Mapping[str, Any] | None,
    live_read_only_probe: Mapping[str, Any] | None,
    live_key_scope_validation: Mapping[str, Any] | None,
    operator_live_canary_approval_request: Mapping[str, Any] | None = None,
    monitoring_evidence: Mapping[str, Any] | None = None,
    policy: LiveCanaryApprovalPolicy | None = None,
) -> dict[str, Any]:
    session = dict(signed_testnet_session_close_report or {})
    probe = dict(live_read_only_probe or {})
    key_scope = dict(live_key_scope_validation or {})
    request = dict(operator_live_canary_approval_request or {})
    monitoring = dict(monitoring_evidence or {})
    policy = policy or LiveCanaryApprovalPolicy()
    blockers: list[str] = []
    warnings: list[str] = []

    for fn, payload in (
        (_operator_request_blockers, request),
        (_session_close_blockers, session),
        (_live_probe_blockers, probe),
        (_live_key_scope_blockers, key_scope),
    ):
        if fn is _operator_request_blockers:
            new_blockers, operator_summary = fn(payload, policy)  # type: ignore[misc]
        elif fn is _session_close_blockers:
            new_blockers, session_summary = fn(payload, policy)  # type: ignore[misc]
        elif fn is _live_probe_blockers:
            new_blockers, probe_summary = fn(payload, policy)  # type: ignore[misc]
        else:
            new_blockers, key_scope_summary = fn(payload)  # type: ignore[misc]
        blockers.extend(new_blockers)

    if monitoring:
        if not (monitoring.get("monitoring_ready") is True and monitoring.get("alerting_ready") is True and monitoring.get("heartbeat_ready") is True):
            blockers.append(BLOCK_MONITORING_NOT_READY)
    # operator summary already requires monitoring; this block allows explicit monitoring evidence to reinforce it.

    unsafe_flags = _unsafe_flags(session, probe, key_scope, request, monitoring, policy=policy)
    if any(unsafe_flags.values()):
        blockers.append(BLOCK_UNSAFE_RUNTIME_FLAG)
    if any(unsafe_flags[field] for field in _SECRET_ACCESS_FIELDS):
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)

    canonical_missing, canonical_summary = _canonical_chain_summary(session, key_scope, probe)
    if canonical_missing:
        blockers.append(BLOCK_CANONICAL_ID_CHAIN_MISSING)

    valid = not blockers
    base = {
        "version": STEP313_LIVE_CANARY_APPROVAL_PACKET_VERSION,
        "session": session_summary,
        "live_probe": probe_summary,
        "live_key_scope": key_scope_summary,
        "operator": operator_summary,
        "canonical": canonical_summary,
        "block_reasons": sorted(set(blockers)),
    }
    packet = {
        "live_canary_approval_packet_id": stable_id("live_canary_approval_packet", base, 24),
        "version": STEP313_LIVE_CANARY_APPROVAL_PACKET_VERSION,
        "status": STATUS_READY_REVIEW_ONLY if valid else (STATUS_BLOCKED_UNSAFE_SIDE_EFFECT if BLOCK_UNSAFE_RUNTIME_FLAG in blockers else STATUS_BLOCKED),
        "valid": valid,
        "review_only": True,
        "live_canary_approval_review_ready": valid,
        "live_canary_execution_enabled": False,
        "live_canary_ready": False,
        "live_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "withdrawal_enabled": False,
        "transfer_enabled": False,
        "admin_enabled": False,
        "write_enabled": False,
        "trade_enabled": False,
        "leverage_mutation_enabled": False,
        "margin_mode_mutation_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "operator_request_summary": operator_summary,
        "signed_testnet_session_close_summary": session_summary,
        "live_read_only_probe_summary": probe_summary,
        "live_key_scope_validation_summary": key_scope_summary,
        "canonical_id_chain_summary": canonical_summary,
        "monitoring_summary": {
            "monitoring_ready": monitoring.get("monitoring_ready") if monitoring else operator_summary.get("monitoring_ready"),
            "alerting_ready": monitoring.get("alerting_ready") if monitoring else operator_summary.get("alerting_ready"),
            "heartbeat_ready": monitoring.get("heartbeat_ready") if monitoring else operator_summary.get("heartbeat_ready"),
            "incident_runbook_ready": monitoring.get("incident_runbook_ready") if monitoring else operator_summary.get("incident_runbook_ready"),
        },
        "unsafe_flags": unsafe_flags,
        "policy": policy.to_dict(),
        "block_reasons": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "created_at_utc": utc_now_canonical(),
    }
    if BLOCK_SESSION_CLOSE_MISSING in blockers or BLOCK_LIVE_PROBE_MISSING in blockers or BLOCK_LIVE_KEY_SCOPE_MISSING in blockers:
        packet["status"] = STATUS_BLOCKED_EVIDENCE_MISSING
    packet["live_canary_approval_packet_sha256"] = sha256_json(
        {k: v for k, v in packet.items() if k != "live_canary_approval_packet_sha256"}
    )
    return packet


def build_live_canary_approval_registry_record(packet: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(packet or {})
    record = {
        "version": STEP313_LIVE_CANARY_APPROVAL_PACKET_VERSION,
        "live_canary_approval_packet_id": data.get("live_canary_approval_packet_id"),
        "live_canary_approval_packet_sha256": data.get("live_canary_approval_packet_sha256"),
        "status": data.get("status"),
        "valid": data.get("valid") is True,
        "review_only": True,
        "live_canary_approval_review_ready": data.get("live_canary_approval_review_ready"),
        "live_canary_execution_enabled": False,
        "live_canary_ready": False,
        "live_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "withdrawal_enabled": False,
        "transfer_enabled": False,
        "admin_enabled": False,
        "write_enabled": False,
        "trade_enabled": False,
        "leverage_mutation_enabled": False,
        "margin_mode_mutation_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "operator_id": (data.get("operator_request_summary") or {}).get("operator_id"),
        "signed_testnet_session_close_report_id": (data.get("signed_testnet_session_close_summary") or {}).get("signed_testnet_session_close_report_id"),
        "live_read_only_adapter_probe_id": (data.get("live_read_only_probe_summary") or {}).get("live_read_only_adapter_probe_id"),
        "live_key_scope_validation_id": (data.get("live_key_scope_validation_summary") or {}).get("live_key_scope_validation_id"),
        "block_reasons": data.get("block_reasons") or [],
        "created_at_utc": utc_now_canonical(),
    }
    record["live_canary_approval_registry_record_id"] = stable_id("live_canary_approval_registry", record, 24)
    record["live_canary_approval_registry_record_sha256"] = sha256_json(record)
    return record


def persist_live_canary_approval_packet(cfg: AppConfig, packet: Mapping[str, Any]) -> dict[str, Any]:
    latest = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    packet_dir = cfg.root / "storage" / "live_canary_approval"
    latest.mkdir(parents=True, exist_ok=True)
    packet_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(packet)
    record = build_live_canary_approval_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, LIVE_CANARY_APPROVAL_PACKET_REGISTRY_NAME),
        record,
        registry_name=LIVE_CANARY_APPROVAL_PACKET_REGISTRY_NAME,
        id_field="live_canary_approval_registry_record_id",
        hash_field="live_canary_approval_registry_record_sha256",
        id_prefix="live_canary_approval_registry",
    )
    payload["live_canary_approval_registry_record_id"] = persisted.get("live_canary_approval_registry_record_id")
    payload["live_canary_approval_registry_record_sha256"] = persisted.get("live_canary_approval_registry_record_sha256")
    atomic_write_json(latest / "live_canary_approval_packet.json", payload)
    atomic_write_json(latest / "live_canary_approval_registry_record.json", persisted)
    atomic_write_json(packet_dir / "live_canary_approval_packet.json", payload)
    return payload


def _latest_json(latest: Path, name: str) -> dict[str, Any]:
    path = latest / name
    return read_json(path) if path.exists() else {}


def run_live_canary_approval_packet_latest(
    *,
    project_root: str | Path | None = None,
    signed_testnet_session_close_report: Mapping[str, Any] | None = None,
    live_read_only_probe: Mapping[str, Any] | None = None,
    live_key_scope_validation: Mapping[str, Any] | None = None,
    operator_live_canary_approval_request: Mapping[str, Any] | None = None,
    monitoring_evidence: Mapping[str, Any] | None = None,
    policy: LiveCanaryApprovalPolicy | None = None,
) -> dict[str, Any]:
    cfg = load_config(project_root)
    cfg_node = cfg.get("execution.live_canary_approval_packet", {}) or {}
    latest = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    session = dict(signed_testnet_session_close_report or _latest_json(latest, "signed_testnet_session_close_report.json"))
    probe = dict(live_read_only_probe or _latest_json(latest, "live_read_only_adapter_probe.json"))
    key_scope = dict(live_key_scope_validation or _latest_json(latest, "live_key_scope_validation.json"))
    request = dict(operator_live_canary_approval_request or {})
    if not request and cfg_node.get("default_operator_request_enabled") is True:
        request = OperatorLiveCanaryApprovalRequest().to_dict()
    policy = policy or LiveCanaryApprovalPolicy(
        max_order_notional_usdt_limit=float(cfg_node.get("max_order_notional_usdt_limit", 5)),
        max_daily_order_count_limit=int(cfg_node.get("max_daily_order_count_limit", 1)),
        max_daily_loss_usdt_limit=float(cfg_node.get("max_daily_loss_usdt_limit", 10)),
        max_live_probe_age_sec=int(cfg_node.get("max_live_probe_age_sec", 600)),
    )
    packet = build_live_canary_approval_packet(
        signed_testnet_session_close_report=session,
        live_read_only_probe=probe,
        live_key_scope_validation=key_scope,
        operator_live_canary_approval_request=request,
        monitoring_evidence=monitoring_evidence,
        policy=policy,
    )
    return persist_live_canary_approval_packet(cfg, packet)
