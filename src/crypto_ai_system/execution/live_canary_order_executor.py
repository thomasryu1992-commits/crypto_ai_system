from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.live_canary_approval_packet import (
    STATUS_READY_REVIEW_ONLY as LIVE_CANARY_APPROVAL_STATUS_READY_REVIEW_ONLY,
    run_live_canary_approval_packet_latest,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from core.json_io import atomic_write_json, read_json

STEP314_LIVE_CANARY_ORDER_EXECUTOR_VERSION = "step314_live_canary_executor_v1"
LIVE_CANARY_ORDER_EXECUTOR_REGISTRY_NAME = "live_canary_order_executor_registry"
LIVE_CANARY_ORDER_LIFECYCLE_REGISTRY_NAME = "live_canary_order_lifecycle_registry"

STATUS_BLOCKED = "NO_LIVE_CANARY_ORDER_SUBMITTED"
STATUS_READY_REVIEW_ONLY = "LIVE_CANARY_EXECUTOR_READY_REVIEW_ONLY_DISABLED"
STATUS_SUBMITTED = "LIVE_CANARY_ORDER_SUBMITTED"

STATE_APPROVAL_PACKET_RECEIVED = "LIVE_CANARY_APPROVAL_PACKET_RECEIVED"
STATE_ORDER_PAYLOAD_VALIDATED = "LIVE_CANARY_ORDER_PAYLOAD_VALIDATED"
STATE_LIVE_CANARY_UNLOCK_CHECKED = "LIVE_CANARY_UNLOCK_CHECKED"
STATE_SUBMISSION_BLOCKED_DISABLED = "LIVE_CANARY_SUBMISSION_BLOCKED_DISABLED"
STATE_SUBMISSION_BLOCKED_POLICY = "LIVE_CANARY_SUBMISSION_BLOCKED_POLICY"
STATE_SUBMISSION_NOT_PERFORMED = "LIVE_CANARY_SUBMISSION_NOT_PERFORMED"

BLOCK_MISSING_APPROVAL_PACKET = "STEP314_BLOCK_MISSING_LIVE_CANARY_APPROVAL_PACKET"
BLOCK_APPROVAL_PACKET_NOT_VALID = "STEP314_BLOCK_LIVE_CANARY_APPROVAL_PACKET_NOT_VALID"
BLOCK_MISSING_ORDER_PAYLOAD = "STEP314_BLOCK_MISSING_LIVE_CANARY_ORDER_PAYLOAD"
BLOCK_MISSING_IDEMPOTENCY_KEY = "STEP314_BLOCK_MISSING_IDEMPOTENCY_KEY"
BLOCK_MISSING_ORDER_INTENT_ID = "STEP314_BLOCK_MISSING_ORDER_INTENT_ID"
BLOCK_MISSING_RISK_GATE_ID = "STEP314_BLOCK_MISSING_RISK_GATE_ID"
BLOCK_MISSING_CANONICAL_ID_CHAIN = "STEP314_BLOCK_MISSING_CANONICAL_ID_CHAIN"
BLOCK_LIVE_CANARY_EXECUTION_DISABLED = "STEP314_BLOCK_LIVE_CANARY_EXECUTION_DISABLED"
BLOCK_LIVE_ORDER_SUBMISSION_DISABLED = "STEP314_BLOCK_LIVE_ORDER_SUBMISSION_DISABLED"
BLOCK_EXTERNAL_ORDER_SUBMISSION_DISABLED = "STEP314_BLOCK_EXTERNAL_ORDER_SUBMISSION_DISABLED"
BLOCK_PLACE_ORDER_DISABLED = "STEP314_BLOCK_PLACE_ORDER_DISABLED"
BLOCK_SIGNED_ORDER_EXECUTOR_DISABLED = "STEP314_BLOCK_SIGNED_ORDER_EXECUTOR_DISABLED"
BLOCK_WRITE_OR_TRADE_SCOPE_DISABLED = "STEP314_BLOCK_WRITE_OR_TRADE_SCOPE_DISABLED"
BLOCK_WITHDRAWAL_TRANSFER_ADMIN_FORBIDDEN = "STEP314_BLOCK_WITHDRAWAL_TRANSFER_ADMIN_FORBIDDEN"
BLOCK_SECRET_VALUE_ACCESS = "STEP314_BLOCK_SECRET_VALUE_ACCESS"
BLOCK_UNSAFE_RUNTIME_FLAG = "STEP314_BLOCK_UNSAFE_RUNTIME_FLAG"
BLOCK_TESTNET_ENVIRONMENT = "STEP314_BLOCK_TESTNET_ENVIRONMENT_NOT_LIVE_CANARY"
BLOCK_ADAPTER_WRITE_ROUTING_FORBIDDEN = "STEP314_BLOCK_ADAPTER_WRITE_ROUTING_FORBIDDEN"

_REQUIRED_CHAIN_FIELDS = [
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


@dataclass(frozen=True)
class LiveCanaryOrderExecutorPolicy:
    review_only: bool = True
    enabled: bool = False
    require_approval_packet_valid: bool = True
    require_live_canary_order_payload: bool = True
    require_idempotency_key: bool = True
    require_canonical_id_chain: bool = True
    live_canary_execution_enabled: bool = False
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
    adapter_write_routing_enabled: bool = False
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


def _extract_order_payload(approval_packet: Mapping[str, Any], explicit_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(explicit_payload, Mapping) and explicit_payload:
        return dict(explicit_payload)
    embedded = approval_packet.get("live_canary_order_payload") or approval_packet.get("would_submit_order_payload")
    if isinstance(embedded, Mapping):
        return dict(embedded)
    chain = dict((approval_packet.get("canonical_id_chain_summary") or {}).get("available_ids") or {})
    operator = approval_packet.get("operator_request_summary") or {}
    return {
        "order_intent_id": chain.get("order_intent_id"),
        "decision_id": chain.get("decision_id"),
        "risk_gate_id": chain.get("risk_gate_id"),
        "research_signal_id": chain.get("research_signal_id"),
        "profile_id": chain.get("profile_id"),
        "venue": "binance_futures_live",
        "environment": "live_canary",
        "symbol": "BTCUSDT",
        "side": None,
        "type": "MARKET",
        "quantity": 0.0,
        "notional_usdt": operator.get("max_order_notional_usdt"),
        "idempotency_key": stable_id("live_canary_idempotency", {"packet": approval_packet.get("live_canary_approval_packet_id"), "order_intent_id": chain.get("order_intent_id")}, 24) if approval_packet else None,
        "review_only": True,
        "would_submit_only": True,
        "actual_submission_performed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "live_order_submission_allowed": False,
    }


def _canonical_chain(packet: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    available = dict((packet.get("canonical_id_chain_summary") or {}).get("available_ids") or {})
    return {
        "data_snapshot_id": available.get("data_snapshot_id"),
        "feature_snapshot_id": available.get("feature_snapshot_id"),
        "research_signal_id": payload.get("research_signal_id") or available.get("research_signal_id"),
        "profile_id": payload.get("profile_id") or available.get("profile_id"),
        "approval_packet_id": available.get("approval_packet_id"),
        "approval_intake_id": available.get("approval_intake_id"),
        "decision_id": payload.get("decision_id") or available.get("decision_id"),
        "risk_gate_id": payload.get("risk_gate_id") or available.get("risk_gate_id"),
        "order_intent_id": payload.get("order_intent_id") or available.get("order_intent_id"),
        "execution_id": available.get("execution_id"),
        "reconciliation_id": available.get("reconciliation_id"),
        "live_canary_approval_packet_id": packet.get("live_canary_approval_packet_id"),
        "signed_testnet_session_close_report_id": (packet.get("signed_testnet_session_close_summary") or {}).get("signed_testnet_session_close_report_id"),
        "live_read_only_adapter_probe_id": (packet.get("live_read_only_probe_summary") or {}).get("live_read_only_adapter_probe_id"),
        "live_key_scope_validation_id": (packet.get("live_key_scope_validation_summary") or {}).get("live_key_scope_validation_id"),
    }


def _unsafe_flags(packet: Mapping[str, Any], payload: Mapping[str, Any], policy: LiveCanaryOrderExecutorPolicy) -> dict[str, bool]:
    sources = [packet, payload]
    fields = [
        "live_canary_execution_enabled",
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
        "adapter_write_routing_enabled",
        "live_trading_enabled",
        "api_key_value_access_allowed",
        "api_secret_value_access_allowed",
        "secret_file_access_allowed",
        "secret_file_creation_allowed",
        "runtime_settings_mutated",
        "score_weights_mutated",
        "auto_promotion_allowed",
    ]
    return {field: _bool(getattr(policy, field, False)) or any(_bool(src.get(field)) for src in sources) for field in fields}


def build_live_canary_lifecycle_event(*, live_canary_execution_id: str | None, order_intent_id: str | None, state: str, status: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    event = {
        "version": STEP314_LIVE_CANARY_ORDER_EXECUTOR_VERSION,
        "live_canary_execution_id": live_canary_execution_id,
        "execution_id": live_canary_execution_id,
        "order_intent_id": order_intent_id,
        "state": state,
        "status": status,
        "details": dict(details or {}),
        "created_at_utc": utc_now_canonical(),
    }
    event["live_canary_lifecycle_event_id"] = stable_id("step314_live_canary_lifecycle_event", event, 24)
    event["live_canary_lifecycle_event_sha256"] = sha256_json(event)
    return event


def build_live_canary_order_execution_record(*, approval_packet: Mapping[str, Any] | None, live_canary_order_payload: Mapping[str, Any] | None = None, policy: LiveCanaryOrderExecutorPolicy | None = None, exchange_response: Mapping[str, Any] | None = None) -> dict[str, Any]:
    packet = dict(approval_packet or {})
    payload = _extract_order_payload(packet, live_canary_order_payload)
    policy = policy or LiveCanaryOrderExecutorPolicy()
    exchange = dict(exchange_response or {})
    blockers: list[str] = []
    warnings: list[str] = []

    if not packet:
        blockers.append(BLOCK_MISSING_APPROVAL_PACKET)
    if packet and packet.get("valid") is not True:
        blockers.append(BLOCK_APPROVAL_PACKET_NOT_VALID)
    if packet and packet.get("status") != LIVE_CANARY_APPROVAL_STATUS_READY_REVIEW_ONLY:
        blockers.append(BLOCK_APPROVAL_PACKET_NOT_VALID)
    if not payload:
        blockers.append(BLOCK_MISSING_ORDER_PAYLOAD)
    if not payload.get("idempotency_key"):
        blockers.append(BLOCK_MISSING_IDEMPOTENCY_KEY)
    if not payload.get("order_intent_id"):
        blockers.append(BLOCK_MISSING_ORDER_INTENT_ID)
    if not payload.get("risk_gate_id"):
        blockers.append(BLOCK_MISSING_RISK_GATE_ID)
    if str(payload.get("environment") or "").lower() not in {"live", "live_canary"}:
        blockers.append(BLOCK_TESTNET_ENVIRONMENT)

    chain = _canonical_chain(packet, payload)
    missing_chain = [field for field in _REQUIRED_CHAIN_FIELDS if not chain.get(field)]
    if missing_chain:
        blockers.append(BLOCK_MISSING_CANONICAL_ID_CHAIN)

    unsafe = _unsafe_flags(packet, payload, policy)
    if not unsafe["live_canary_execution_enabled"]:
        blockers.append(BLOCK_LIVE_CANARY_EXECUTION_DISABLED)
    if not unsafe["live_order_submission_allowed"]:
        blockers.append(BLOCK_LIVE_ORDER_SUBMISSION_DISABLED)
    if not unsafe["external_order_submission_allowed"]:
        blockers.append(BLOCK_EXTERNAL_ORDER_SUBMISSION_DISABLED)
    if not unsafe["place_order_enabled"]:
        blockers.append(BLOCK_PLACE_ORDER_DISABLED)
    if not unsafe["signed_order_executor_enabled"]:
        blockers.append(BLOCK_SIGNED_ORDER_EXECUTOR_DISABLED)
    if not (unsafe["write_enabled"] and unsafe["trade_enabled"]):
        blockers.append(BLOCK_WRITE_OR_TRADE_SCOPE_DISABLED)
    if unsafe["withdrawal_enabled"] or unsafe["transfer_enabled"] or unsafe["admin_enabled"]:
        blockers.append(BLOCK_WITHDRAWAL_TRANSFER_ADMIN_FORBIDDEN)
    if unsafe["api_key_value_access_allowed"] or unsafe["api_secret_value_access_allowed"] or unsafe["secret_file_access_allowed"] or unsafe["secret_file_creation_allowed"]:
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)
    if unsafe["external_order_submission_performed"] or unsafe["runtime_settings_mutated"] or unsafe["score_weights_mutated"] or unsafe["auto_promotion_allowed"] or unsafe["live_trading_enabled"]:
        blockers.append(BLOCK_UNSAFE_RUNTIME_FLAG)
    if unsafe["adapter_write_routing_enabled"]:
        blockers.append(BLOCK_ADAPTER_WRITE_ROUTING_FORBIDDEN)

    # Step314 deliberately never submits live orders. Future unlock work must add
    # a separate explicit execution approval before this can change.
    submitted = False
    if exchange:
        warnings.append("STEP314_EXCHANGE_RESPONSE_IGNORED_BECAUSE_LIVE_SUBMISSION_IS_DISABLED_BY_DESIGN")

    status = STATUS_BLOCKED if blockers else STATUS_READY_REVIEW_ONLY
    state = STATE_SUBMISSION_BLOCKED_DISABLED if blockers else STATE_SUBMISSION_NOT_PERFORMED
    execution_id = stable_id("step314_live_canary_execution", {"packet": packet.get("live_canary_approval_packet_id"), "order_intent_id": payload.get("order_intent_id"), "status": status}, 24)
    events = [
        build_live_canary_lifecycle_event(live_canary_execution_id=execution_id, order_intent_id=chain.get("order_intent_id"), state=STATE_APPROVAL_PACKET_RECEIVED, status="VALID" if packet.get("valid") is True else "NOT_VALID", details={"live_canary_approval_packet_id": packet.get("live_canary_approval_packet_id")}),
        build_live_canary_lifecycle_event(live_canary_execution_id=execution_id, order_intent_id=chain.get("order_intent_id"), state=STATE_ORDER_PAYLOAD_VALIDATED, status="VALID" if payload and not any(r in blockers for r in [BLOCK_MISSING_ORDER_PAYLOAD, BLOCK_MISSING_IDEMPOTENCY_KEY, BLOCK_MISSING_ORDER_INTENT_ID, BLOCK_MISSING_RISK_GATE_ID]) else "NOT_VALID", details={"idempotency_key": payload.get("idempotency_key")}),
        build_live_canary_lifecycle_event(live_canary_execution_id=execution_id, order_intent_id=chain.get("order_intent_id"), state=STATE_LIVE_CANARY_UNLOCK_CHECKED, status="DISABLED", details={"live_order_submission_allowed": False, "place_order_enabled": False}),
        build_live_canary_lifecycle_event(live_canary_execution_id=execution_id, order_intent_id=chain.get("order_intent_id"), state=STATE_SUBMISSION_BLOCKED_DISABLED if blockers else STATE_SUBMISSION_NOT_PERFORMED, status="BLOCKED" if blockers else "REVIEW_ONLY_DISABLED", details={"block_reasons": sorted(set(blockers))}),
    ]
    record = {
        "version": STEP314_LIVE_CANARY_ORDER_EXECUTOR_VERSION,
        "live_canary_execution_id": execution_id,
        "execution_id": execution_id,
        "status": status,
        "state": state,
        "submitted_to_exchange": submitted,
        "actual_submission_performed": False,
        "external_order_submission_performed": False,
        "adapter_called_for_write": False,
        "adapter_write_routing_enabled": False,
        "exchange_order_id": None,
        "exchange_response_hash": None,
        "request_hash": sha256_json(payload) if payload else None,
        "live_canary_approval_packet_id": packet.get("live_canary_approval_packet_id"),
        "live_canary_approval_packet_sha256": packet.get("live_canary_approval_packet_sha256"),
        "idempotency_key": payload.get("idempotency_key"),
        "order_intent_id": chain.get("order_intent_id"),
        "decision_id": chain.get("decision_id"),
        "risk_gate_id": chain.get("risk_gate_id"),
        "research_signal_id": chain.get("research_signal_id"),
        "profile_id": chain.get("profile_id"),
        "approval_packet_id": chain.get("approval_packet_id"),
        "approval_intake_id": chain.get("approval_intake_id"),
        "signed_testnet_session_close_report_id": chain.get("signed_testnet_session_close_report_id"),
        "live_read_only_adapter_probe_id": chain.get("live_read_only_adapter_probe_id"),
        "live_key_scope_validation_id": chain.get("live_key_scope_validation_id"),
        "canonical_id_chain": chain,
        "missing_canonical_id_fields": missing_chain,
        "block_reasons": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "unsafe_flag_evidence": unsafe,
        "policy": policy.to_dict(),
        "live_canary_order_payload": payload,
        "lifecycle_events": events,
        "reconciliation_required": False,
        "ready_for_live_canary_reconciliation": False,
        "live_canary_execution_enabled": False,
        "live_canary_ready": False,
        "live_order_submission_allowed": False,
        "external_order_submission_allowed": False,
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
        "created_at_utc": utc_now_canonical(),
    }
    record["live_canary_order_executor_record_sha256"] = sha256_json({k: v for k, v in record.items() if k != "live_canary_order_executor_record_sha256" and k != "created_at_utc"})
    return record


def build_live_canary_order_executor_registry_record(execution_record: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(execution_record or {})
    record = {
        "version": STEP314_LIVE_CANARY_ORDER_EXECUTOR_VERSION,
        "live_canary_execution_id": data.get("live_canary_execution_id"),
        "execution_id": data.get("execution_id"),
        "live_canary_order_executor_record_sha256": data.get("live_canary_order_executor_record_sha256"),
        "status": data.get("status"),
        "state": data.get("state"),
        "order_intent_id": data.get("order_intent_id"),
        "decision_id": data.get("decision_id"),
        "risk_gate_id": data.get("risk_gate_id"),
        "research_signal_id": data.get("research_signal_id"),
        "profile_id": data.get("profile_id"),
        "live_canary_approval_packet_id": data.get("live_canary_approval_packet_id"),
        "idempotency_key": data.get("idempotency_key"),
        "request_hash": data.get("request_hash"),
        "exchange_order_id": None,
        "exchange_response_hash": None,
        "submitted_to_exchange": False,
        "actual_submission_performed": False,
        "external_order_submission_performed": False,
        "adapter_called_for_write": False,
        "block_reasons": list(data.get("block_reasons") or []),
        "reconciliation_required": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_enabled": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["live_canary_order_executor_registry_record_id"] = stable_id("step314_live_canary_order_executor_registry", record, 24)
    record["live_canary_order_executor_registry_record_sha256"] = sha256_json(record)
    return record


def build_live_canary_order_lifecycle_registry_record(execution_record: Mapping[str, Any]) -> dict[str, Any]:
    events = list(execution_record.get("lifecycle_events") or [])
    record = {
        "version": STEP314_LIVE_CANARY_ORDER_EXECUTOR_VERSION,
        "live_canary_execution_id": execution_record.get("live_canary_execution_id"),
        "execution_id": execution_record.get("execution_id"),
        "order_intent_id": execution_record.get("order_intent_id"),
        "status": execution_record.get("status"),
        "state": execution_record.get("state"),
        "submitted_to_exchange": False,
        "external_order_submission_performed": False,
        "actual_submission_performed": False,
        "lifecycle_state_count": len(events),
        "lifecycle_states": [event.get("state") for event in events],
        "lifecycle_event_hashes": [event.get("live_canary_lifecycle_event_sha256") for event in events],
        "reconciliation_required": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["live_canary_order_lifecycle_registry_record_id"] = stable_id("step314_live_canary_order_lifecycle_registry", record, 24)
    record["live_canary_order_lifecycle_registry_record_sha256"] = sha256_json(record)
    return record


def persist_live_canary_order_execution_record(cfg: AppConfig, execution_record: Mapping[str, Any]) -> dict[str, Any]:
    latest = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    executor_dir = cfg.root / "storage" / "live_canary_order_executor"
    latest.mkdir(parents=True, exist_ok=True)
    executor_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(execution_record)
    registry_record = build_live_canary_order_executor_registry_record(payload)
    lifecycle_record = build_live_canary_order_lifecycle_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, LIVE_CANARY_ORDER_EXECUTOR_REGISTRY_NAME),
        registry_record,
        registry_name=LIVE_CANARY_ORDER_EXECUTOR_REGISTRY_NAME,
        id_field="live_canary_order_executor_registry_record_id",
        hash_field="live_canary_order_executor_registry_record_sha256",
        id_prefix="step314_live_canary_order_executor_registry",
    )
    lifecycle_persisted = append_registry_record(
        registry_path(cfg, LIVE_CANARY_ORDER_LIFECYCLE_REGISTRY_NAME),
        lifecycle_record,
        registry_name=LIVE_CANARY_ORDER_LIFECYCLE_REGISTRY_NAME,
        id_field="live_canary_order_lifecycle_registry_record_id",
        hash_field="live_canary_order_lifecycle_registry_record_sha256",
        id_prefix="step314_live_canary_order_lifecycle_registry",
    )
    payload["live_canary_order_executor_registry_record_id"] = persisted.get("live_canary_order_executor_registry_record_id")
    payload["live_canary_order_executor_registry_record_sha256"] = persisted.get("live_canary_order_executor_registry_record_sha256")
    payload["live_canary_order_lifecycle_registry_record_id"] = lifecycle_persisted.get("live_canary_order_lifecycle_registry_record_id")
    payload["live_canary_order_lifecycle_registry_record_sha256"] = lifecycle_persisted.get("live_canary_order_lifecycle_registry_record_sha256")
    atomic_write_json(latest / "live_canary_order_execution_record.json", payload)
    atomic_write_json(latest / "live_canary_order_lifecycle_events.json", list(payload.get("lifecycle_events") or []))
    atomic_write_json(latest / "live_canary_order_executor_registry_record.json", persisted)
    atomic_write_json(latest / "live_canary_order_lifecycle_registry_record.json", lifecycle_persisted)
    atomic_write_json(executor_dir / "live_canary_order_execution_record.json", payload)
    return payload


def _latest_json(path: Path) -> dict[str, Any]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def run_live_canary_order_executor_latest(*, project_root: str | Path = ".", approval_packet: Mapping[str, Any] | None = None, live_canary_order_payload: Mapping[str, Any] | None = None, policy: LiveCanaryOrderExecutorPolicy | None = None) -> dict[str, Any]:
    cfg = load_config(Path(project_root))
    latest = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest.mkdir(parents=True, exist_ok=True)
    packet = dict(approval_packet or _latest_json(latest / "live_canary_approval_packet.json"))
    if not packet:
        packet = run_live_canary_approval_packet_latest(project_root=cfg.root)
    payload = dict(live_canary_order_payload or _latest_json(latest / "live_canary_order_payload.json"))
    record = build_live_canary_order_execution_record(approval_packet=packet, live_canary_order_payload=payload, policy=policy)
    return persist_live_canary_order_execution_record(cfg, record)
