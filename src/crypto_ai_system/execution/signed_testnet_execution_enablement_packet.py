from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.real_read_only_venue_probe import run_real_read_only_venue_probe_latest
from crypto_ai_system.execution.signed_testnet_pre_submit_validator import run_signed_testnet_pre_submit_validator_latest
from crypto_ai_system.registry.approval_registry import VALIDATION_STATUS_VALID, run_approval_registry_latest
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical
from core.json_io import atomic_write_json, read_json

STEP307_SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_VERSION = "step307_signed_testnet_execution_enablement_packet_v1"
SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_REGISTRY_NAME = "signed_testnet_execution_enablement_packet_registry"

STATUS_READY_REVIEW_ONLY = "SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_READY_REVIEW_ONLY"
STATUS_BLOCKED = "SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_BLOCKED"

BLOCK_MISSING_OPERATOR_UNLOCK_REQUEST = "STEP307_BLOCK_MISSING_OPERATOR_UNLOCK_REQUEST"
BLOCK_OPERATOR_UNLOCK_NOT_FOR_SIGNED_TESTNET = "STEP307_BLOCK_OPERATOR_UNLOCK_NOT_FOR_SIGNED_TESTNET"
BLOCK_OPERATOR_ID_MISSING = "STEP307_BLOCK_OPERATOR_ID_MISSING"
BLOCK_OPERATOR_TICKET_OR_SIGNATURE_MISSING = "STEP307_BLOCK_OPERATOR_TICKET_OR_SIGNATURE_MISSING"
BLOCK_OPERATOR_TIMESTAMP_INVALID = "STEP307_BLOCK_OPERATOR_TIMESTAMP_INVALID"
BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_DISABLED_EXECUTION = "STEP307_BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_DISABLED_EXECUTION"
BLOCK_OPERATOR_REQUESTS_ORDER_SUBMISSION_ENABLED = "STEP307_BLOCK_OPERATOR_REQUESTS_ORDER_SUBMISSION_ENABLED"
BLOCK_OPERATOR_REQUESTS_PLACE_ORDER_ENABLED = "STEP307_BLOCK_OPERATOR_REQUESTS_PLACE_ORDER_ENABLED"
BLOCK_KILL_SWITCH_NOT_RECHECKED = "STEP307_BLOCK_KILL_SWITCH_NOT_RECHECKED"
BLOCK_MANUAL_KILL_SWITCH_ACTIVE = "STEP307_BLOCK_MANUAL_KILL_SWITCH_ACTIVE"
BLOCK_HARD_CAP_NOT_RECHECKED = "STEP307_BLOCK_HARD_CAP_NOT_RECHECKED"
BLOCK_HARD_CAP_INVALID = "STEP307_BLOCK_HARD_CAP_INVALID"
BLOCK_MISSING_APPROVAL_REGISTRY = "STEP307_BLOCK_MISSING_APPROVAL_REGISTRY"
BLOCK_APPROVAL_REGISTRY_NOT_VALID = "STEP307_BLOCK_APPROVAL_REGISTRY_NOT_VALID"
BLOCK_MISSING_PRE_SUBMIT_VALIDATION = "STEP307_BLOCK_MISSING_PRE_SUBMIT_VALIDATION"
BLOCK_PRE_SUBMIT_NOT_VALIDATED = "STEP307_BLOCK_PRE_SUBMIT_NOT_VALIDATED"
BLOCK_PRE_SUBMIT_PAYLOAD_MISSING = "STEP307_BLOCK_PRE_SUBMIT_PAYLOAD_MISSING"
BLOCK_MISSING_VENUE_PROBE = "STEP307_BLOCK_MISSING_VENUE_PROBE"
BLOCK_VENUE_PROBE_INVALID = "STEP307_BLOCK_VENUE_PROBE_INVALID"
BLOCK_VENUE_PROBE_STALE = "STEP307_BLOCK_VENUE_PROBE_STALE"
BLOCK_SECRET_VALUE_ACCESS = "STEP307_BLOCK_SECRET_VALUE_ACCESS"
BLOCK_UNSAFE_RUNTIME_FLAG = "STEP307_BLOCK_UNSAFE_RUNTIME_FLAG"
BLOCK_MISSING_CANONICAL_ID_CHAIN = "STEP307_BLOCK_MISSING_CANONICAL_ID_CHAIN"

_CANONICAL_ID_FIELDS = [
    "order_intent_id",
    "decision_id",
    "risk_gate_id",
    "research_signal_id",
    "profile_id",
    "venue_probe_id",
    "signed_testnet_pre_submit_validation_id",
]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except Exception:
        return default


def _age_sec(value: Any) -> int | None:
    if not is_canonical_utc_timestamp(value):
        return None
    parsed = datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _without_hash(payload: Mapping[str, Any], *hash_fields: str) -> dict[str, Any]:
    drop = set(hash_fields) | {"created_at_utc"}
    return {k: v for k, v in dict(payload).items() if k not in drop}


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


@dataclass(frozen=True)
class SignedTestnetExecutionEnablementPolicy:
    review_only: bool = True
    require_operator_unlock_request: bool = True
    require_operator_acknowledges_disabled_execution: bool = True
    require_approval_registry_valid: bool = True
    require_pre_submit_validated: bool = True
    require_pre_submit_payload: bool = True
    require_venue_probe_valid_and_fresh: bool = True
    max_venue_probe_age_sec: int = 600
    require_manual_kill_switch_recheck: bool = True
    require_manual_kill_switch_inactive: bool = True
    require_hard_cap_recheck: bool = True
    max_order_notional_usdt_limit: float = 5.0
    max_daily_order_count_limit: int = 3
    max_daily_loss_usdt_limit: float = 10.0
    require_canonical_id_chain: bool = True
    enablement_packet_may_unlock_execution: bool = False
    ready_for_signed_testnet_execution: bool = False
    testnet_order_submission_allowed: bool = False
    external_order_submission_allowed: bool = False
    external_order_submission_performed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    signed_order_executor_enabled: bool = False
    api_key_value_access_allowed: bool = False
    api_secret_value_access_allowed: bool = False
    secret_file_access_allowed: bool = False
    secret_file_creation_allowed: bool = False
    live_trading_allowed_by_this_module: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_operator_unlock_request(
    *,
    operator_id: str,
    ticket_or_signature: str,
    requested_stage: str = "signed_testnet",
    max_order_notional_usdt: float = 5.0,
    max_daily_order_count: int = 1,
    max_daily_loss_usdt: float = 10.0,
    manual_kill_switch_rechecked: bool = True,
    manual_kill_switch_active: bool = False,
    hard_cap_rechecked: bool = True,
    acknowledges_execution_remains_disabled: bool = True,
    operator_confirms_testnet_only: bool = True,
    operator_confirms_no_live_key: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "operator_id": operator_id,
        "ticket_or_signature": ticket_or_signature,
        "requested_stage": requested_stage,
        "max_order_notional_usdt": float(max_order_notional_usdt),
        "max_daily_order_count": int(max_daily_order_count),
        "max_daily_loss_usdt": float(max_daily_loss_usdt),
        "manual_kill_switch_rechecked": bool(manual_kill_switch_rechecked),
        "manual_kill_switch_active": bool(manual_kill_switch_active),
        "hard_cap_rechecked": bool(hard_cap_rechecked),
        "acknowledges_execution_remains_disabled": bool(acknowledges_execution_remains_disabled),
        "operator_confirms_testnet_only": bool(operator_confirms_testnet_only),
        "operator_confirms_no_live_key": bool(operator_confirms_no_live_key),
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "signed_order_executor_enabled": False,
        "external_order_submission_performed": False,
        "created_at_utc": utc_now_canonical(),
    }
    payload.update(extra)
    payload["operator_unlock_request_id"] = stable_id("step307_operator_unlock_request", payload, 24)
    payload["operator_unlock_request_sha256"] = sha256_json(_without_hash(payload, "operator_unlock_request_sha256"))
    return payload


def validate_operator_unlock_request(operator_unlock_request: Mapping[str, Any] | None) -> dict[str, Any]:
    data = _as_mapping(operator_unlock_request)
    blockers: list[str] = []
    if not data:
        blockers.append(BLOCK_MISSING_OPERATOR_UNLOCK_REQUEST)
    if data and str(data.get("requested_stage") or "").lower() not in {"signed_testnet", "testnet"}:
        blockers.append(BLOCK_OPERATOR_UNLOCK_NOT_FOR_SIGNED_TESTNET)
    if data and not str(data.get("operator_id") or "").strip():
        blockers.append(BLOCK_OPERATOR_ID_MISSING)
    if data and not str(data.get("ticket_or_signature") or "").strip():
        blockers.append(BLOCK_OPERATOR_TICKET_OR_SIGNATURE_MISSING)
    if data and not is_canonical_utc_timestamp(data.get("created_at_utc")):
        blockers.append(BLOCK_OPERATOR_TIMESTAMP_INVALID)
    if data and data.get("acknowledges_execution_remains_disabled") is not True:
        blockers.append(BLOCK_OPERATOR_DID_NOT_ACKNOWLEDGE_DISABLED_EXECUTION)
    if data and data.get("manual_kill_switch_rechecked") is not True:
        blockers.append(BLOCK_KILL_SWITCH_NOT_RECHECKED)
    if data and data.get("manual_kill_switch_active") is not False:
        blockers.append(BLOCK_MANUAL_KILL_SWITCH_ACTIVE)
    if data and data.get("hard_cap_rechecked") is not True:
        blockers.append(BLOCK_HARD_CAP_NOT_RECHECKED)
    if data and (_safe_float(data.get("max_order_notional_usdt")) <= 0 or _safe_int(data.get("max_daily_order_count")) <= 0 or _safe_float(data.get("max_daily_loss_usdt")) <= 0):
        blockers.append(BLOCK_HARD_CAP_INVALID)
    if data and _bool(data.get("testnet_order_submission_allowed")):
        blockers.append(BLOCK_OPERATOR_REQUESTS_ORDER_SUBMISSION_ENABLED)
    if data and _bool(data.get("place_order_enabled")):
        blockers.append(BLOCK_OPERATOR_REQUESTS_PLACE_ORDER_ENABLED)
    valid = not blockers
    return {
        "operator_unlock_validation_id": stable_id("step307_operator_unlock_validation", {"request": data, "blockers": blockers}, 24),
        "valid": valid,
        "block_reasons": sorted(set(blockers)),
        "operator_unlock_request_id": data.get("operator_unlock_request_id"),
        "operator_id": data.get("operator_id"),
        "ticket_or_signature": data.get("ticket_or_signature"),
        "created_at_utc": utc_now_canonical(),
    }


def _unsafe_flags(*payloads: Mapping[str, Any]) -> dict[str, bool]:
    names = [
        "ready_for_signed_testnet_execution",
        "testnet_order_submission_allowed",
        "external_order_submission_allowed",
        "external_order_submission_performed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
        "live_trading_allowed_by_this_module",
        "runtime_settings_mutated",
        "score_weights_mutated",
        "auto_promotion_allowed",
        "api_key_value_access_allowed",
        "api_secret_value_access_allowed",
        "secret_file_access_allowed",
        "secret_file_creation_allowed",
    ]
    flags: dict[str, bool] = {}
    for name in names:
        flags[name] = any(_bool(_as_mapping(payload).get(name)) for payload in payloads)
    return flags


def _hard_cap_validation(operator_request: Mapping[str, Any], policy: SignedTestnetExecutionEnablementPolicy) -> dict[str, Any]:
    max_notional = _safe_float(operator_request.get("max_order_notional_usdt"))
    max_daily_count = _safe_int(operator_request.get("max_daily_order_count"))
    max_daily_loss = _safe_float(operator_request.get("max_daily_loss_usdt"))
    blockers: list[str] = []
    if max_notional <= 0 or max_notional > policy.max_order_notional_usdt_limit:
        blockers.append(BLOCK_HARD_CAP_INVALID)
    if max_daily_count <= 0 or max_daily_count > policy.max_daily_order_count_limit:
        blockers.append(BLOCK_HARD_CAP_INVALID)
    if max_daily_loss <= 0 or max_daily_loss > policy.max_daily_loss_usdt_limit:
        blockers.append(BLOCK_HARD_CAP_INVALID)
    return {
        "valid": not blockers,
        "block_reasons": sorted(set(blockers)),
        "max_order_notional_usdt": max_notional,
        "max_daily_order_count": max_daily_count,
        "max_daily_loss_usdt": max_daily_loss,
        "policy_limits": {
            "max_order_notional_usdt_limit": policy.max_order_notional_usdt_limit,
            "max_daily_order_count_limit": policy.max_daily_order_count_limit,
            "max_daily_loss_usdt_limit": policy.max_daily_loss_usdt_limit,
        },
    }


def build_signed_testnet_execution_enablement_packet(
    *,
    operator_unlock_request: Mapping[str, Any] | None,
    approval_registry_record: Mapping[str, Any] | None,
    pre_submit_validation_report: Mapping[str, Any] | None,
    venue_probe: Mapping[str, Any] | None,
    max_venue_probe_age_sec: int = 600,
) -> dict[str, Any]:
    request = _as_mapping(operator_unlock_request)
    approval = _as_mapping(approval_registry_record)
    pre_submit = _as_mapping(pre_submit_validation_report)
    probe = _as_mapping(venue_probe)
    policy = SignedTestnetExecutionEnablementPolicy(max_venue_probe_age_sec=max_venue_probe_age_sec)
    blockers: list[str] = []

    operator_validation = validate_operator_unlock_request(request)
    blockers.extend(operator_validation.get("block_reasons") or [])

    hard_cap_validation = _hard_cap_validation(request, policy)
    blockers.extend(hard_cap_validation.get("block_reasons") or [])

    if not approval:
        blockers.append(BLOCK_MISSING_APPROVAL_REGISTRY)
    elif approval.get("validation_status") != VALIDATION_STATUS_VALID or approval.get("approval_registry_status") != "APPROVAL_REGISTRY_VALID_REVIEW_ONLY":
        blockers.append(BLOCK_APPROVAL_REGISTRY_NOT_VALID)

    if not pre_submit:
        blockers.append(BLOCK_MISSING_PRE_SUBMIT_VALIDATION)
    elif pre_submit.get("status") != "SIGNED_TESTNET_PRE_SUBMIT_VALIDATED_REVIEW_ONLY" or pre_submit.get("valid") is not True:
        blockers.append(BLOCK_PRE_SUBMIT_NOT_VALIDATED)
    if pre_submit and not pre_submit.get("would_submit_order_payload"):
        blockers.append(BLOCK_PRE_SUBMIT_PAYLOAD_MISSING)

    if not probe:
        blockers.append(BLOCK_MISSING_VENUE_PROBE)
    elif probe.get("status") != "REAL_READ_ONLY_VENUE_PROBE_VALID" or probe.get("valid") is not True:
        blockers.append(BLOCK_VENUE_PROBE_INVALID)
    probe_age = _age_sec(probe.get("created_at_utc")) if probe else None
    if probe and (probe_age is None or probe_age > max_venue_probe_age_sec):
        blockers.append(BLOCK_VENUE_PROBE_STALE)
    if probe and probe.get("metadata_only") is not True:
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)

    unsafe = _unsafe_flags(request, approval, pre_submit, probe)
    if any(unsafe.values()):
        blockers.append(BLOCK_UNSAFE_RUNTIME_FLAG)
    if any(unsafe.get(name) for name in ["api_key_value_access_allowed", "api_secret_value_access_allowed", "secret_file_access_allowed", "secret_file_creation_allowed"]):
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)

    id_chain = {
        "approval_packet_id": approval.get("approval_packet_id"),
        "approval_intake_id": approval.get("approval_intake_id"),
        "candidate_profile_id": approval.get("candidate_profile_id"),
        "order_intent_id": pre_submit.get("order_intent_id"),
        "decision_id": pre_submit.get("decision_id"),
        "risk_gate_id": pre_submit.get("risk_gate_id"),
        "research_signal_id": pre_submit.get("research_signal_id"),
        "profile_id": pre_submit.get("profile_id"),
        "venue_probe_id": pre_submit.get("venue_probe_id") or probe.get("real_read_only_venue_probe_id"),
        "signed_testnet_pre_submit_validation_id": pre_submit.get("signed_testnet_pre_submit_validation_id"),
    }
    missing_chain = [name for name, value in id_chain.items() if not value and name in _CANONICAL_ID_FIELDS]
    # Approval IDs are required for enablement readiness as well, but keep them visible separately.
    missing_approval_chain = [name for name in ["approval_packet_id", "approval_intake_id"] if not id_chain.get(name)]
    if missing_chain or missing_approval_chain:
        blockers.append(BLOCK_MISSING_CANONICAL_ID_CHAIN)

    valid = not blockers
    base = {
        "operator_unlock_request_id": request.get("operator_unlock_request_id"),
        "approval_registry_record_id": approval.get("approval_registry_record_id"),
        "signed_testnet_pre_submit_validation_id": pre_submit.get("signed_testnet_pre_submit_validation_id"),
        "venue_probe_id": id_chain.get("venue_probe_id"),
        "block_reasons": sorted(set(blockers)),
    }
    packet = {
        "signed_testnet_execution_enablement_packet_id": stable_id("step307_signed_testnet_execution_enablement_packet", base, 24),
        "version": STEP307_SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_VERSION,
        "status": STATUS_READY_REVIEW_ONLY if valid else STATUS_BLOCKED,
        "valid": valid,
        "review_only": True,
        "enablement_packet_created": True,
        "enablement_packet_ready_for_manual_review": valid,
        "enablement_packet_may_unlock_execution": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "operator_unlock_request_id": request.get("operator_unlock_request_id"),
        "operator_unlock_validation": operator_validation,
        "hard_cap_validation": hard_cap_validation,
        "approval_registry_record_id": approval.get("approval_registry_record_id"),
        "approval_registry_status": approval.get("approval_registry_status"),
        "approval_validation_status": approval.get("validation_status"),
        "signed_testnet_pre_submit_validation_id": pre_submit.get("signed_testnet_pre_submit_validation_id"),
        "pre_submit_status": pre_submit.get("status"),
        "pre_submit_valid": pre_submit.get("valid") is True,
        "would_submit_order_payload_sha256": (pre_submit.get("would_submit_order_payload") or {}).get("would_submit_order_payload_sha256"),
        "idempotency_key": pre_submit.get("idempotency_key"),
        "venue_probe_id": id_chain.get("venue_probe_id"),
        "venue_probe_status": probe.get("status"),
        "venue_probe_valid": probe.get("valid") is True,
        "venue_probe_source_age_sec": probe_age,
        "canonical_id_chain": id_chain,
        "missing_canonical_id_fields": sorted(set(missing_chain + missing_approval_chain)),
        "unsafe_flag_evidence": unsafe,
        "block_reasons": sorted(set(blockers)),
        "policy": policy.to_dict(),
        "created_at_utc": utc_now_canonical(),
    }
    packet["signed_testnet_execution_enablement_packet_sha256"] = sha256_json(
        _without_hash(packet, "signed_testnet_execution_enablement_packet_sha256")
    )
    return packet


def build_signed_testnet_execution_enablement_registry_record(packet: Mapping[str, Any]) -> dict[str, Any]:
    data = _as_mapping(packet)
    record = {
        "version": STEP307_SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_VERSION,
        "signed_testnet_execution_enablement_packet_id": data.get("signed_testnet_execution_enablement_packet_id"),
        "signed_testnet_execution_enablement_packet_sha256": data.get("signed_testnet_execution_enablement_packet_sha256"),
        "status": data.get("status"),
        "valid": data.get("valid") is True,
        "review_only": True,
        "operator_unlock_request_id": data.get("operator_unlock_request_id"),
        "approval_registry_record_id": data.get("approval_registry_record_id"),
        "signed_testnet_pre_submit_validation_id": data.get("signed_testnet_pre_submit_validation_id"),
        "venue_probe_id": data.get("venue_probe_id"),
        "idempotency_key": data.get("idempotency_key"),
        "block_reasons": list(data.get("block_reasons") or []),
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["signed_testnet_execution_enablement_registry_record_id"] = stable_id(
        "step307_signed_testnet_execution_enablement_registry", record, 24
    )
    record["signed_testnet_execution_enablement_registry_record_sha256"] = sha256_json(record)
    return record


def persist_signed_testnet_execution_enablement_packet(cfg: AppConfig, packet: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    packet_dir = cfg.root / "storage" / "signed_testnet_execution_enablement"
    packet_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(packet)
    record = build_signed_testnet_execution_enablement_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_REGISTRY_NAME),
        record,
        registry_name=SIGNED_TESTNET_EXECUTION_ENABLEMENT_PACKET_REGISTRY_NAME,
        id_field="signed_testnet_execution_enablement_registry_record_id",
        hash_field="signed_testnet_execution_enablement_registry_record_sha256",
        id_prefix="step307_signed_testnet_execution_enablement_registry",
    )
    payload["signed_testnet_execution_enablement_registry_record_id"] = persisted.get("signed_testnet_execution_enablement_registry_record_id")
    payload["signed_testnet_execution_enablement_registry_record_sha256"] = persisted.get("signed_testnet_execution_enablement_registry_record_sha256")
    atomic_write_json(latest_dir / "signed_testnet_execution_enablement_packet.json", payload)
    atomic_write_json(latest_dir / "signed_testnet_execution_enablement_registry_record.json", persisted)
    atomic_write_json(packet_dir / "signed_testnet_execution_enablement_packet.json", payload)
    return payload


def run_signed_testnet_execution_enablement_packet_latest(
    *,
    project_root: str | Path = ".",
    operator_unlock_request: Mapping[str, Any] | None = None,
    approval_registry_record: Mapping[str, Any] | None = None,
    pre_submit_validation_report: Mapping[str, Any] | None = None,
    venue_probe: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_config(Path(project_root))
    latest = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest.mkdir(parents=True, exist_ok=True)

    if operator_unlock_request is None:
        operator_unlock_request = read_json(latest / "operator_unlock_request.json", default={})
    if approval_registry_record is None:
        approval_registry_record = read_json(latest / "approval_registry_record.json", default={})
        if not approval_registry_record:
            approval_registry_record = run_approval_registry_latest(cfg=cfg)
    if venue_probe is None:
        venue_probe = read_json(latest / "real_read_only_venue_probe.json", default={})
        if not venue_probe:
            venue_probe = run_real_read_only_venue_probe_latest(project_root=cfg.root)
    if pre_submit_validation_report is None:
        pre_submit_validation_report = read_json(latest / "signed_testnet_pre_submit_validation_report.json", default={})
        if not pre_submit_validation_report:
            pre_submit_validation_report = run_signed_testnet_pre_submit_validator_latest(project_root=cfg.root, venue_probe=venue_probe)

    packet = build_signed_testnet_execution_enablement_packet(
        operator_unlock_request=operator_unlock_request,
        approval_registry_record=approval_registry_record,
        pre_submit_validation_report=pre_submit_validation_report,
        venue_probe=venue_probe,
    )
    return persist_signed_testnet_execution_enablement_packet(cfg, packet)
