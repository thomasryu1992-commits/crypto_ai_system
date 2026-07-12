from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.order_lifecycle_tracker import (
    STATE_ENABLEMENT_CHECKED,
    STATE_FETCHED_STATUS,
    STATE_INTENT_RECEIVED,
    STATE_PRE_SUBMIT_VALIDATED,
    STATE_RECONCILIATION_REQUIRED,
    STATE_SUBMISSION_BLOCKED_DISABLED,
    STATE_SUBMISSION_BLOCKED_POLICY,
    build_lifecycle_event,
    persist_order_lifecycle_record,
)
from crypto_ai_system.execution.signed_testnet_execution_enablement_packet import (
    STATUS_READY_REVIEW_ONLY as ENABLEMENT_STATUS_READY_REVIEW_ONLY,
    run_signed_testnet_execution_enablement_packet_latest,
)
from crypto_ai_system.execution.venue_alignment import EXTENDED_TESTNET_VENUE
from crypto_ai_system.execution.venue_contracts import VenueOrderIntent
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from core.json_io import atomic_write_json, read_json

STEP308_SIGNED_TESTNET_ORDER_EXECUTOR_VERSION = "step308_first_signed_testnet_order_executor_v1"
SIGNED_TESTNET_ORDER_EXECUTOR_REGISTRY_NAME = "signed_testnet_order_executor_registry"

STATUS_READY_REVIEW_ONLY = "SIGNED_TESTNET_ORDER_EXECUTOR_READY_REVIEW_ONLY_DISABLED"
STATUS_BLOCKED = "NO_SIGNED_TESTNET_ORDER_SUBMITTED"
STATUS_SUBMITTED = "SIGNED_TESTNET_ORDER_SUBMITTED"

BLOCK_MISSING_ENABLEMENT_PACKET = "STEP308_BLOCK_MISSING_ENABLEMENT_PACKET"
BLOCK_ENABLEMENT_PACKET_NOT_VALID = "STEP308_BLOCK_ENABLEMENT_PACKET_NOT_VALID"
BLOCK_MISSING_PRE_SUBMIT_PAYLOAD = "STEP308_BLOCK_MISSING_PRE_SUBMIT_PAYLOAD"
BLOCK_MISSING_IDEMPOTENCY_KEY = "STEP308_BLOCK_MISSING_IDEMPOTENCY_KEY"
BLOCK_MISSING_ORDER_INTENT_ID = "STEP308_BLOCK_MISSING_ORDER_INTENT_ID"
BLOCK_MISSING_RISK_GATE_ID = "STEP308_BLOCK_MISSING_RISK_GATE_ID"
BLOCK_MISSING_CANONICAL_ID_CHAIN = "STEP308_BLOCK_MISSING_CANONICAL_ID_CHAIN"
BLOCK_TESTNET_ORDER_SUBMISSION_DISABLED = "STEP308_BLOCK_TESTNET_ORDER_SUBMISSION_DISABLED"
BLOCK_PLACE_ORDER_DISABLED = "STEP308_BLOCK_PLACE_ORDER_DISABLED"
BLOCK_SIGNED_ORDER_EXECUTOR_DISABLED = "STEP308_BLOCK_SIGNED_ORDER_EXECUTOR_DISABLED"
BLOCK_EXTERNAL_ORDER_SUBMISSION_DISABLED = "STEP308_BLOCK_EXTERNAL_ORDER_SUBMISSION_DISABLED"
BLOCK_SECRET_VALUE_ACCESS = "STEP308_BLOCK_SECRET_VALUE_ACCESS"
BLOCK_UNSAFE_RUNTIME_FLAG = "STEP308_BLOCK_UNSAFE_RUNTIME_FLAG"
BLOCK_LIVE_ENVIRONMENT_OR_KEY = "STEP308_BLOCK_LIVE_ENVIRONMENT_OR_KEY"
BLOCK_ADAPTER_NOT_AVAILABLE = "STEP308_BLOCK_ADAPTER_NOT_AVAILABLE"

_REQUIRED_CHAIN_FIELDS = [
    "order_intent_id",
    "decision_id",
    "risk_gate_id",
    "research_signal_id",
    "profile_id",
    "signed_testnet_pre_submit_validation_id",
    "venue_probe_id",
    "operator_unlock_request_id",
]


def _safe_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _drop_hashes(payload: Mapping[str, Any], *hash_fields: str) -> dict[str, Any]:
    drop = set(hash_fields) | {"created_at_utc"}
    return {k: v for k, v in dict(payload).items() if k not in drop}


@dataclass(frozen=True)
class SignedTestnetOrderExecutorPolicy:
    review_only: bool = True
    enabled: bool = False
    require_enablement_packet_valid: bool = True
    require_would_submit_payload: bool = True
    require_idempotency_key: bool = True
    require_canonical_id_chain: bool = True
    ready_for_signed_testnet_execution: bool = False
    testnet_order_submission_allowed: bool = False
    external_order_submission_allowed: bool = False
    external_order_submission_performed: bool = False
    place_order_enabled: bool = False
    cancel_order_enabled: bool = False
    signed_order_executor_enabled: bool = False
    adapter_write_routing_enabled: bool = False
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


def _extract_would_submit_payload(enablement_packet: Mapping[str, Any], explicit_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not enablement_packet and not explicit_payload:
        return {}
    if isinstance(explicit_payload, Mapping) and explicit_payload:
        return dict(explicit_payload)
    embedded = enablement_packet.get("would_submit_order_payload")
    if isinstance(embedded, Mapping):
        return dict(embedded)
    # Step307 only stores the payload hash/idempotency in the packet. Use the
    # canonical chain visible in the packet to build a deterministic review-only
    # executor payload without assuming missing order values.
    chain = enablement_packet.get("canonical_id_chain") or {}
    if not isinstance(chain, Mapping):
        chain = {}
    intent = VenueOrderIntent(
        order_intent_id=str(enablement_packet.get("order_intent_id") or chain.get("order_intent_id") or "MISSING_ORDER_INTENT_ID"),
        decision_id=chain.get("decision_id"),
        risk_gate_id=chain.get("risk_gate_id"),
        research_signal_id=chain.get("research_signal_id"),
        profile_id=chain.get("profile_id"),
        venue=EXTENDED_TESTNET_VENUE,
        environment="testnet",
        market="BTC-USD",
        side="UNSPECIFIED",
        order_type="MARKET",
        quantity="0",
        idempotency_key=enablement_packet.get("idempotency_key"),
        submit_allowed=False,
    )
    payload = {
        **intent.to_dict(),
        # Compatibility aliases for the pre-P70 review-only validators.
        "symbol": intent.market,
        "type": intent.order_type,
        "would_submit_only": True,
        "actual_submission_performed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "signed_order_executor_enabled": False,
    }
    return {k: v for k, v in payload.items() if v is not None}


def _unsafe_flags(enablement_packet: Mapping[str, Any], would_submit_payload: Mapping[str, Any], policy: SignedTestnetOrderExecutorPolicy) -> dict[str, bool]:
    sources = [enablement_packet, would_submit_payload]
    return {
        "ready_for_signed_testnet_execution": policy.ready_for_signed_testnet_execution or any(_safe_bool(src.get("ready_for_signed_testnet_execution")) for src in sources),
        "testnet_order_submission_allowed": policy.testnet_order_submission_allowed or any(_safe_bool(src.get("testnet_order_submission_allowed")) for src in sources),
        "external_order_submission_allowed": policy.external_order_submission_allowed or any(_safe_bool(src.get("external_order_submission_allowed")) for src in sources),
        "external_order_submission_performed": policy.external_order_submission_performed or any(_safe_bool(src.get("external_order_submission_performed")) for src in sources),
        "place_order_enabled": policy.place_order_enabled or any(_safe_bool(src.get("place_order_enabled")) for src in sources),
        "cancel_order_enabled": policy.cancel_order_enabled or any(_safe_bool(src.get("cancel_order_enabled")) for src in sources),
        "signed_order_executor_enabled": policy.signed_order_executor_enabled or any(_safe_bool(src.get("signed_order_executor_enabled")) for src in sources),
        "adapter_write_routing_enabled": policy.adapter_write_routing_enabled or any(_safe_bool(src.get("adapter_write_routing_enabled")) for src in sources),
        "api_key_value_access_allowed": policy.api_key_value_access_allowed or any(_safe_bool(src.get("api_key_value_access_allowed")) for src in sources),
        "api_secret_value_access_allowed": policy.api_secret_value_access_allowed or any(_safe_bool(src.get("api_secret_value_access_allowed")) for src in sources),
        "secret_file_access_allowed": policy.secret_file_access_allowed or any(_safe_bool(src.get("secret_file_access_allowed")) for src in sources),
        "secret_file_creation_allowed": policy.secret_file_creation_allowed or any(_safe_bool(src.get("secret_file_creation_allowed")) for src in sources),
        "live_trading_allowed_by_this_module": policy.live_trading_allowed_by_this_module or any(_safe_bool(src.get("live_trading_allowed_by_this_module")) for src in sources),
    }


def build_signed_testnet_order_execution_record(
    *,
    enablement_packet: Mapping[str, Any] | None,
    would_submit_payload: Mapping[str, Any] | None = None,
    policy: SignedTestnetOrderExecutorPolicy | None = None,
    exchange_response: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    packet = dict(enablement_packet or {})
    payload = _extract_would_submit_payload(packet, would_submit_payload)
    policy = policy or SignedTestnetOrderExecutorPolicy()
    exchange = dict(exchange_response or {})
    blockers: list[str] = []
    warnings: list[str] = []

    if not packet:
        blockers.append(BLOCK_MISSING_ENABLEMENT_PACKET)
    if packet and packet.get("valid") is not True:
        blockers.append(BLOCK_ENABLEMENT_PACKET_NOT_VALID)
    if packet and packet.get("status") != ENABLEMENT_STATUS_READY_REVIEW_ONLY:
        blockers.append(BLOCK_ENABLEMENT_PACKET_NOT_VALID)
    if not payload or payload.get("would_submit_order_payload_sha256") == "WOULD_SUBMIT_ORDER_PAYLOAD_NOT_CREATED":
        blockers.append(BLOCK_MISSING_PRE_SUBMIT_PAYLOAD)
    if not payload.get("idempotency_key"):
        blockers.append(BLOCK_MISSING_IDEMPOTENCY_KEY)
    if not payload.get("order_intent_id"):
        blockers.append(BLOCK_MISSING_ORDER_INTENT_ID)
    if not payload.get("risk_gate_id") and not (packet.get("canonical_id_chain") or {}).get("risk_gate_id"):
        blockers.append(BLOCK_MISSING_RISK_GATE_ID)

    chain = dict(packet.get("canonical_id_chain") or {})
    merged_chain = {
        "order_intent_id": payload.get("order_intent_id") or chain.get("order_intent_id"),
        "decision_id": payload.get("decision_id") or chain.get("decision_id"),
        "risk_gate_id": payload.get("risk_gate_id") or chain.get("risk_gate_id"),
        "research_signal_id": payload.get("research_signal_id") or chain.get("research_signal_id"),
        "profile_id": payload.get("profile_id") or chain.get("profile_id"),
        "signed_testnet_pre_submit_validation_id": packet.get("signed_testnet_pre_submit_validation_id") or chain.get("signed_testnet_pre_submit_validation_id"),
        "venue_probe_id": packet.get("venue_probe_id") or chain.get("venue_probe_id"),
        "operator_unlock_request_id": packet.get("operator_unlock_request_id") or chain.get("operator_unlock_request_id"),
        "approval_registry_record_id": packet.get("approval_registry_record_id") or chain.get("approval_registry_record_id"),
        "approval_packet_id": chain.get("approval_packet_id"),
        "approval_intake_id": chain.get("approval_intake_id"),
    }
    missing_chain = [field for field in _REQUIRED_CHAIN_FIELDS if not merged_chain.get(field)]
    if missing_chain:
        blockers.append(BLOCK_MISSING_CANONICAL_ID_CHAIN)

    unsafe = _unsafe_flags(packet, payload, policy)
    # In Step308, disabled execution flags are expected and must block actual
    # submission. They are reported separately from unexpected unsafe flags.
    if not unsafe["testnet_order_submission_allowed"]:
        blockers.append(BLOCK_TESTNET_ORDER_SUBMISSION_DISABLED)
    if not unsafe["place_order_enabled"]:
        blockers.append(BLOCK_PLACE_ORDER_DISABLED)
    if not unsafe["signed_order_executor_enabled"]:
        blockers.append(BLOCK_SIGNED_ORDER_EXECUTOR_DISABLED)
    if not unsafe["external_order_submission_allowed"]:
        blockers.append(BLOCK_EXTERNAL_ORDER_SUBMISSION_DISABLED)

    secret_flags = [
        "api_key_value_access_allowed",
        "api_secret_value_access_allowed",
        "secret_file_access_allowed",
        "secret_file_creation_allowed",
    ]
    if any(unsafe[name] for name in secret_flags):
        blockers.append(BLOCK_SECRET_VALUE_ACCESS)
    if unsafe["live_trading_allowed_by_this_module"] or str(payload.get("environment") or "testnet").lower() != "testnet":
        blockers.append(BLOCK_LIVE_ENVIRONMENT_OR_KEY)
    if unsafe["adapter_write_routing_enabled"]:
        warnings.append("STEP308_ADAPTER_WRITE_ROUTING_REQUESTED_BUT_NOT_USED_WITHOUT_VALID_UNLOCK")
    if any(unsafe[name] for name in ["external_order_submission_performed"]):
        blockers.append(BLOCK_UNSAFE_RUNTIME_FLAG)

    actual_submission_allowed = not blockers and all(
        unsafe[name]
        for name in [
            "ready_for_signed_testnet_execution",
            "testnet_order_submission_allowed",
            "external_order_submission_allowed",
            "place_order_enabled",
            "signed_order_executor_enabled",
            "adapter_write_routing_enabled",
        ]
    )

    submitted = bool(actual_submission_allowed and exchange)
    status = STATUS_SUBMITTED if submitted else STATUS_BLOCKED
    state = "SIGNED_TESTNET_SUBMITTED" if submitted else "SIGNED_TESTNET_SUBMISSION_BLOCKED_DISABLED"
    execution_id_source = {
        "order_intent_id": merged_chain.get("order_intent_id"),
        "risk_gate_id": merged_chain.get("risk_gate_id"),
        "idempotency_key": payload.get("idempotency_key"),
        "status": status,
    }
    execution_id = stable_id("step308_signed_testnet_execution", execution_id_source, 24)
    lifecycle_events = [
        build_lifecycle_event(execution_id=execution_id, order_intent_id=merged_chain.get("order_intent_id"), state=STATE_INTENT_RECEIVED, status="RECORDED", details={"order_intent_id": merged_chain.get("order_intent_id")}),
        build_lifecycle_event(execution_id=execution_id, order_intent_id=merged_chain.get("order_intent_id"), state=STATE_PRE_SUBMIT_VALIDATED, status="VALID" if packet.get("pre_submit_valid") is True else "NOT_VALID", details={"signed_testnet_pre_submit_validation_id": packet.get("signed_testnet_pre_submit_validation_id")}),
        build_lifecycle_event(execution_id=execution_id, order_intent_id=merged_chain.get("order_intent_id"), state=STATE_ENABLEMENT_CHECKED, status="VALID" if packet.get("valid") is True else "NOT_VALID", details={"signed_testnet_execution_enablement_packet_id": packet.get("signed_testnet_execution_enablement_packet_id")}),
    ]
    if submitted:
        lifecycle_events.extend([
            build_lifecycle_event(execution_id=execution_id, order_intent_id=merged_chain.get("order_intent_id"), state=STATE_FETCHED_STATUS, status=str(exchange.get("status") or "UNKNOWN"), details={"exchange_order_id": exchange.get("exchange_order_id")}),
            build_lifecycle_event(execution_id=execution_id, order_intent_id=merged_chain.get("order_intent_id"), state=STATE_RECONCILIATION_REQUIRED, status="REQUIRED", details={"reconciliation_required": True}),
        ])
    else:
        lifecycle_events.append(
            build_lifecycle_event(
                execution_id=execution_id,
                order_intent_id=merged_chain.get("order_intent_id"),
                state=STATE_SUBMISSION_BLOCKED_DISABLED if any(reason in blockers for reason in [BLOCK_TESTNET_ORDER_SUBMISSION_DISABLED, BLOCK_PLACE_ORDER_DISABLED, BLOCK_SIGNED_ORDER_EXECUTOR_DISABLED, BLOCK_EXTERNAL_ORDER_SUBMISSION_DISABLED]) else STATE_SUBMISSION_BLOCKED_POLICY,
                status="BLOCKED",
                details={"block_reasons": sorted(set(blockers))},
            )
        )

    record = {
        "version": STEP308_SIGNED_TESTNET_ORDER_EXECUTOR_VERSION,
        "signed_testnet_execution_id": execution_id,
        "execution_id": execution_id,
        "status": status,
        "state": state,
        "submitted_to_exchange": submitted,
        "actual_submission_performed": False,
        "external_order_submission_performed": False,
        "adapter_called_for_write": False,
        "adapter_write_routing_enabled": False,
        "exchange_order_id": exchange.get("exchange_order_id") if submitted else None,
        "exchange_response_hash": sha256_json(exchange) if submitted else None,
        "request_hash": sha256_json(payload) if payload else None,
        "signed_testnet_execution_enablement_packet_id": packet.get("signed_testnet_execution_enablement_packet_id"),
        "signed_testnet_execution_enablement_packet_sha256": packet.get("signed_testnet_execution_enablement_packet_sha256"),
        "signed_testnet_pre_submit_validation_id": packet.get("signed_testnet_pre_submit_validation_id"),
        "would_submit_order_payload_sha256": payload.get("would_submit_order_payload_sha256"),
        "idempotency_key": payload.get("idempotency_key"),
        "order_intent_id": merged_chain.get("order_intent_id"),
        "decision_id": merged_chain.get("decision_id"),
        "risk_gate_id": merged_chain.get("risk_gate_id"),
        "research_signal_id": merged_chain.get("research_signal_id"),
        "profile_id": merged_chain.get("profile_id"),
        "venue_probe_id": merged_chain.get("venue_probe_id"),
        "operator_unlock_request_id": merged_chain.get("operator_unlock_request_id"),
        "approval_registry_record_id": merged_chain.get("approval_registry_record_id"),
        "approval_packet_id": merged_chain.get("approval_packet_id"),
        "approval_intake_id": merged_chain.get("approval_intake_id"),
        "canonical_id_chain": merged_chain,
        "missing_canonical_id_fields": missing_chain,
        "block_reasons": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "unsafe_flag_evidence": unsafe,
        "policy": policy.to_dict(),
        "would_submit_order_payload": payload,
        "lifecycle_events": lifecycle_events,
        "reconciliation_required": submitted,
        "ready_for_signed_testnet_reconciliation": submitted,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["signed_testnet_order_executor_record_sha256"] = sha256_json(_drop_hashes(record, "signed_testnet_order_executor_record_sha256"))
    return record


def build_signed_testnet_order_executor_registry_record(execution_record: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(execution_record or {})
    record = {
        "version": STEP308_SIGNED_TESTNET_ORDER_EXECUTOR_VERSION,
        "signed_testnet_execution_id": data.get("signed_testnet_execution_id"),
        "execution_id": data.get("execution_id"),
        "signed_testnet_order_executor_record_sha256": data.get("signed_testnet_order_executor_record_sha256"),
        "status": data.get("status"),
        "state": data.get("state"),
        "order_intent_id": data.get("order_intent_id"),
        "decision_id": data.get("decision_id"),
        "risk_gate_id": data.get("risk_gate_id"),
        "research_signal_id": data.get("research_signal_id"),
        "profile_id": data.get("profile_id"),
        "signed_testnet_pre_submit_validation_id": data.get("signed_testnet_pre_submit_validation_id"),
        "signed_testnet_execution_enablement_packet_id": data.get("signed_testnet_execution_enablement_packet_id"),
        "idempotency_key": data.get("idempotency_key"),
        "request_hash": data.get("request_hash"),
        "exchange_order_id": data.get("exchange_order_id"),
        "exchange_response_hash": data.get("exchange_response_hash"),
        "submitted_to_exchange": data.get("submitted_to_exchange") is True,
        "actual_submission_performed": False,
        "external_order_submission_performed": False,
        "adapter_called_for_write": False,
        "block_reasons": list(data.get("block_reasons") or []),
        "reconciliation_required": data.get("reconciliation_required") is True,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "live_trading_allowed_by_this_module": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["signed_testnet_order_executor_registry_record_id"] = stable_id("step308_signed_testnet_order_executor_registry", record, 24)
    record["signed_testnet_order_executor_registry_record_sha256"] = sha256_json(record)
    return record


def persist_signed_testnet_order_execution_record(cfg: AppConfig, execution_record: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    session_dir = cfg.root / "storage" / "signed_testnet_order_executor"
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(execution_record)
    record = build_signed_testnet_order_executor_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, SIGNED_TESTNET_ORDER_EXECUTOR_REGISTRY_NAME),
        record,
        registry_name=SIGNED_TESTNET_ORDER_EXECUTOR_REGISTRY_NAME,
        id_field="signed_testnet_order_executor_registry_record_id",
        hash_field="signed_testnet_order_executor_registry_record_sha256",
        id_prefix="step308_signed_testnet_order_executor_registry",
    )
    lifecycle_record = persist_order_lifecycle_record(cfg, execution_record=payload, lifecycle_events=list(payload.get("lifecycle_events") or []))
    payload["signed_testnet_order_executor_registry_record_id"] = persisted.get("signed_testnet_order_executor_registry_record_id")
    payload["signed_testnet_order_executor_registry_record_sha256"] = persisted.get("signed_testnet_order_executor_registry_record_sha256")
    payload["signed_testnet_order_lifecycle_record_id"] = lifecycle_record.get("signed_testnet_order_lifecycle_record_id")
    payload["signed_testnet_order_lifecycle_record_sha256"] = lifecycle_record.get("signed_testnet_order_lifecycle_record_sha256")
    atomic_write_json(latest_dir / "signed_testnet_order_execution_record.json", payload)
    atomic_write_json(latest_dir / "signed_testnet_order_executor_registry_record.json", persisted)
    atomic_write_json(session_dir / "signed_testnet_order_execution_record.json", payload)
    return payload


def _latest_json(path: Path) -> dict[str, Any]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def run_signed_testnet_order_executor_latest(
    *,
    project_root: str | Path = ".",
    enablement_packet: Mapping[str, Any] | None = None,
    would_submit_payload: Mapping[str, Any] | None = None,
    policy: SignedTestnetOrderExecutorPolicy | None = None,
) -> dict[str, Any]:
    cfg = load_config(Path(project_root))
    latest = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest.mkdir(parents=True, exist_ok=True)
    packet = dict(enablement_packet or _latest_json(latest / "signed_testnet_execution_enablement_packet.json"))
    if not packet:
        packet = run_signed_testnet_execution_enablement_packet_latest(project_root=cfg.root)
    payload = dict(would_submit_payload or _latest_json(latest / "would_submit_order_payload.json"))
    record = build_signed_testnet_order_execution_record(enablement_packet=packet, would_submit_payload=payload, policy=policy)
    return persist_signed_testnet_order_execution_record(cfg, record)
