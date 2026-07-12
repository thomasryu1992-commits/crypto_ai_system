from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.live_canary_order_executor import STATUS_SUBMITTED as LIVE_CANARY_EXECUTOR_STATUS_SUBMITTED
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

STEP315_LIVE_CANARY_RECONCILIATION_VERSION = "step315_live_canary_reconciliation_v1"
LIVE_CANARY_RECONCILIATION_REGISTRY_NAME = "live_canary_reconciliation_registry"

STATUS_RECONCILED = "LIVE_CANARY_RECONCILED_REVIEW_ONLY"
STATUS_MISMATCH = "LIVE_CANARY_RECONCILIATION_MISMATCH"
STATUS_BLOCKED_NO_SUBMISSION = "LIVE_CANARY_RECONCILIATION_BLOCKED_NO_SUBMISSION"
STATUS_BLOCKED_EVIDENCE_MISSING = "LIVE_CANARY_RECONCILIATION_BLOCKED_EVIDENCE_MISSING"
STATUS_BLOCKED_UNSAFE_SIDE_EFFECT = "LIVE_CANARY_RECONCILIATION_BLOCKED_UNSAFE_SIDE_EFFECT"

PROMOTION_BLOCKER_NONE = "NO_LIVE_CANARY_PROMOTION_BLOCKER"
PROMOTION_BLOCKER_MISMATCH = "BLOCK_LIVE_CANARY_PROMOTION_RECONCILIATION_MISMATCH"
PROMOTION_BLOCKER_EVIDENCE_MISSING = "BLOCK_LIVE_CANARY_PROMOTION_RECONCILIATION_EVIDENCE_MISSING"
PROMOTION_BLOCKER_EXECUTION_NOT_SUBMITTED = "BLOCK_LIVE_CANARY_PROMOTION_EXECUTION_NOT_SUBMITTED"
PROMOTION_BLOCKER_UNSAFE_SIDE_EFFECT = "BLOCK_LIVE_CANARY_PROMOTION_UNSAFE_SIDE_EFFECT"

EXTERNAL_BALANCE_SYNC_PERFORMED = False
EXTERNAL_POSITION_SYNC_PERFORMED = False
EXTERNAL_EXECUTION_SYNC_PERFORMED = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False
LIVE_ORDER_EXECUTED = False


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _drop_hashes(payload: Mapping[str, Any], *hash_fields: str) -> dict[str, Any]:
    drop = set(hash_fields) | {"created_at_utc"}
    return {k: v for k, v in dict(payload).items() if k not in drop}


def _safe_payload(execution_record: Mapping[str, Any], explicit_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if explicit_payload:
        return dict(explicit_payload)
    embedded = execution_record.get("live_canary_order_payload") or execution_record.get("would_submit_order_payload")
    return dict(embedded) if isinstance(embedded, Mapping) else {}


def _safe_approval(execution_record: Mapping[str, Any], explicit_approval_packet: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if explicit_approval_packet:
        return dict(explicit_approval_packet)
    embedded = execution_record.get("live_canary_approval_packet")
    return dict(embedded) if isinstance(embedded, Mapping) else {}


@dataclass(frozen=True)
class LiveCanaryReconciliationPolicy:
    review_only: bool = True
    require_execution_record: bool = True
    require_order_payload: bool = True
    require_approval_packet: bool = True
    require_idempotency_match: bool = True
    require_order_intent_match: bool = True
    require_request_hash_match: bool = True
    require_lifecycle_evidence: bool = True
    require_exchange_order_id_if_submitted: bool = True
    allow_live_canary_promotion: bool = False
    external_balance_sync_performed: bool = False
    external_position_sync_performed: bool = False
    external_execution_sync_performed: bool = False
    external_order_submission_performed: bool = False
    live_order_executed: bool = False
    live_trading_allowed_by_this_module: bool = False
    api_key_value_access_allowed: bool = False
    api_secret_value_access_allowed: bool = False
    secret_file_access_allowed: bool = False
    secret_file_creation_allowed: bool = False
    runtime_settings_mutated: bool = False
    score_weights_mutated: bool = False
    auto_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _check(name: str, passed: bool, ok: str, bad: str, *, severity: str = "mismatch") -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "severity": severity, "message": ok if passed else bad}


def _unsafe_side_effects(execution_record: Mapping[str, Any], policy: LiveCanaryReconciliationPolicy) -> dict[str, bool]:
    return {
        "external_balance_sync_performed_by_this_module": policy.external_balance_sync_performed or EXTERNAL_BALANCE_SYNC_PERFORMED,
        "external_position_sync_performed_by_this_module": policy.external_position_sync_performed or EXTERNAL_POSITION_SYNC_PERFORMED,
        "external_execution_sync_performed_by_this_module": policy.external_execution_sync_performed or EXTERNAL_EXECUTION_SYNC_PERFORMED,
        "external_order_submission_performed_by_this_module": policy.external_order_submission_performed or EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        "live_order_executed_by_this_module": policy.live_order_executed or LIVE_ORDER_EXECUTED,
        "live_trading_allowed_by_this_module": policy.live_trading_allowed_by_this_module or _bool(execution_record.get("live_trading_allowed_by_this_module")) or _bool(execution_record.get("live_trading_enabled")),
        "api_key_value_access_allowed": policy.api_key_value_access_allowed or _bool(execution_record.get("api_key_value_access_allowed")),
        "api_secret_value_access_allowed": policy.api_secret_value_access_allowed or _bool(execution_record.get("api_secret_value_access_allowed")),
        "secret_file_access_allowed": policy.secret_file_access_allowed or _bool(execution_record.get("secret_file_access_allowed")),
        "secret_file_creation_allowed": policy.secret_file_creation_allowed or _bool(execution_record.get("secret_file_creation_allowed")),
        "runtime_settings_mutated": policy.runtime_settings_mutated or _bool(execution_record.get("runtime_settings_mutated")),
        "score_weights_mutated": policy.score_weights_mutated or _bool(execution_record.get("score_weights_mutated")),
        "auto_promotion_allowed": policy.auto_promotion_allowed or _bool(execution_record.get("auto_promotion_allowed")),
    }


def build_live_canary_reconciliation_checks(
    *,
    execution_record: Mapping[str, Any],
    live_canary_order_payload: Mapping[str, Any] | None = None,
    approval_packet: Mapping[str, Any] | None = None,
    lifecycle_record: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    execution = dict(execution_record or {})
    payload = _safe_payload(execution, live_canary_order_payload)
    approval = _safe_approval(execution, approval_packet)
    lifecycle = dict(lifecycle_record or {})
    lifecycle_events = execution.get("lifecycle_events") or []
    lifecycle_states = lifecycle.get("lifecycle_states") or [event.get("state") for event in lifecycle_events if isinstance(event, Mapping)]
    expected_request_hash = sha256_json(payload) if payload else None

    checks = [
        _check("LIVE_CANARY_EXECUTION_RECORD_EXISTS", bool(execution), "Live canary execution record exists.", "Live canary execution record is missing.", severity="fatal"),
        _check("LIVE_CANARY_ORDER_PAYLOAD_EXISTS", bool(payload), "Live canary order payload exists.", "Live canary order payload is missing.", severity="fatal"),
        _check("LIVE_CANARY_APPROVAL_PACKET_EXISTS", bool(approval or execution.get("live_canary_approval_packet_id")), "Live canary approval packet evidence exists.", "Live canary approval packet evidence is missing.", severity="fatal"),
        _check(
            "LIVE_CANARY_APPROVAL_ID_MATCH",
            not approval or not execution.get("live_canary_approval_packet_id") or _text(approval.get("live_canary_approval_packet_id")) == _text(execution.get("live_canary_approval_packet_id")),
            "Live canary approval packet ID matches execution record.",
            "Live canary approval packet ID mismatch.",
        ),
        _check(
            "ORDER_INTENT_ID_MATCH",
            bool(_text(execution.get("order_intent_id"))) and _text(execution.get("order_intent_id")) == _text(payload.get("order_intent_id")),
            "Order intent ID matches execution and payload.",
            "Order intent ID mismatch between live execution record and live payload.",
        ),
        _check("EXECUTION_ID_PRESENT", bool(_text(execution.get("execution_id"))), "Execution ID is present.", "Execution ID is missing."),
        _check(
            "RISK_GATE_ID_MATCH",
            bool(_text(execution.get("risk_gate_id"))) and _text(execution.get("risk_gate_id")) == _text(payload.get("risk_gate_id")),
            "Risk gate ID matches execution and payload.",
            "Risk gate ID mismatch between live execution record and live payload.",
        ),
        _check(
            "IDEMPOTENCY_KEY_MATCH",
            bool(_text(execution.get("idempotency_key"))) and _text(execution.get("idempotency_key")) == _text(payload.get("idempotency_key")),
            "Idempotency key matches execution and payload.",
            "Idempotency key mismatch between live execution record and live payload.",
        ),
        _check(
            "REQUEST_HASH_MATCH",
            bool(expected_request_hash) and _text(execution.get("request_hash")) == _text(expected_request_hash),
            "Request hash matches live order payload.",
            "Request hash mismatch for live order payload.",
        ),
        _check("LIFECYCLE_EVIDENCE_PRESENT", bool(lifecycle_events or lifecycle_states), "Lifecycle evidence is present.", "Live canary lifecycle evidence is missing."),
        _check(
            "EXCHANGE_ORDER_ID_PRESENT_IF_SUBMITTED",
            execution.get("submitted_to_exchange") is not True or bool(_text(execution.get("exchange_order_id"))),
            "Submitted live canary execution has exchange order ID.",
            "Submitted live canary execution is missing exchange order ID.",
        ),
        _check(
            "EXCHANGE_RESPONSE_HASH_PRESENT_IF_SUBMITTED",
            execution.get("submitted_to_exchange") is not True or bool(_text(execution.get("exchange_response_hash"))),
            "Submitted live canary execution has exchange response hash.",
            "Submitted live canary execution is missing exchange response hash.",
        ),
        _check(
            "LIVE_CANARY_ENVIRONMENT_ONLY",
            _text(payload.get("environment") or "live_canary").lower() in {"live", "live_canary"},
            "Payload is live-canary scoped.",
            "Payload is not live-canary scoped.",
        ),
        _check(
            "NO_EXTERNAL_POSITION_OR_BALANCE_SYNC_BY_THIS_MODULE",
            not any(_bool(execution.get(name)) for name in ["external_balance_sync_performed", "external_position_sync_performed", "external_execution_sync_performed"]),
            "No external balance/position/execution sync was performed by this module.",
            "External sync flag is unexpectedly enabled.",
            severity="unsafe",
        ),
        _check(
            "NO_SECRET_VALUE_ACCESS",
            not any(_bool(execution.get(name)) for name in ["api_key_value_access_allowed", "api_secret_value_access_allowed", "secret_file_access_allowed", "secret_file_creation_allowed"]),
            "Secret value/file access remains disabled.",
            "Secret value/file access flag is unexpectedly enabled.",
            severity="unsafe",
        ),
    ]
    return checks


def build_live_canary_reconciliation_record(
    *,
    execution_record: Mapping[str, Any] | None,
    live_canary_order_payload: Mapping[str, Any] | None = None,
    approval_packet: Mapping[str, Any] | None = None,
    lifecycle_record: Mapping[str, Any] | None = None,
    policy: LiveCanaryReconciliationPolicy | None = None,
) -> dict[str, Any]:
    execution = dict(execution_record or {})
    payload = _safe_payload(execution, live_canary_order_payload)
    approval = _safe_approval(execution, approval_packet)
    lifecycle = dict(lifecycle_record or {})
    policy = policy or LiveCanaryReconciliationPolicy()
    checks = build_live_canary_reconciliation_checks(
        execution_record=execution,
        live_canary_order_payload=payload,
        approval_packet=approval,
        lifecycle_record=lifecycle,
    )
    failed = [check for check in checks if not check.get("passed")]
    unsafe_flags = _unsafe_side_effects(execution, policy)
    unsafe_detected = any(unsafe_flags.values()) or any(check.get("severity") == "unsafe" and not check.get("passed") for check in checks)
    submitted = execution.get("submitted_to_exchange") is True or execution.get("status") == LIVE_CANARY_EXECUTOR_STATUS_SUBMITTED

    if not execution or not payload:
        status = STATUS_BLOCKED_EVIDENCE_MISSING
        promotion_blocker = PROMOTION_BLOCKER_EVIDENCE_MISSING
    elif unsafe_detected:
        status = STATUS_BLOCKED_UNSAFE_SIDE_EFFECT
        promotion_blocker = PROMOTION_BLOCKER_UNSAFE_SIDE_EFFECT
    elif not submitted:
        status = STATUS_BLOCKED_NO_SUBMISSION
        promotion_blocker = PROMOTION_BLOCKER_EXECUTION_NOT_SUBMITTED
    elif failed:
        status = STATUS_MISMATCH
        promotion_blocker = PROMOTION_BLOCKER_MISMATCH
    else:
        status = STATUS_RECONCILED
        promotion_blocker = PROMOTION_BLOCKER_NONE

    reconciliation_id_source = {
        "execution_id": execution.get("execution_id"),
        "order_intent_id": execution.get("order_intent_id"),
        "idempotency_key": execution.get("idempotency_key"),
        "status": status,
    }
    record = {
        "version": STEP315_LIVE_CANARY_RECONCILIATION_VERSION,
        "live_canary_reconciliation_id": stable_id("step315_live_canary_reconciliation", reconciliation_id_source, 24),
        "reconciliation_id": stable_id("step315_live_canary_reconciliation", reconciliation_id_source, 24),
        "status": status,
        "reconciliation_status": status,
        "promotion_blocked": promotion_blocker != PROMOTION_BLOCKER_NONE,
        "promotion_blocker": promotion_blocker,
        "checks": checks,
        "failed_checks": failed,
        "failed_check_names": [check.get("name") for check in failed],
        "unsafe_side_effect_evidence": unsafe_flags,
        "live_canary_execution_id": execution.get("live_canary_execution_id"),
        "execution_id": execution.get("execution_id"),
        "order_intent_id": execution.get("order_intent_id"),
        "decision_id": execution.get("decision_id"),
        "risk_gate_id": execution.get("risk_gate_id"),
        "research_signal_id": execution.get("research_signal_id"),
        "profile_id": execution.get("profile_id"),
        "idempotency_key": execution.get("idempotency_key"),
        "request_hash": execution.get("request_hash"),
        "exchange_order_id": execution.get("exchange_order_id"),
        "exchange_response_hash": execution.get("exchange_response_hash"),
        "submitted_to_exchange": execution.get("submitted_to_exchange") is True,
        "actual_submission_performed": execution.get("actual_submission_performed") is True,
        "external_order_submission_performed": execution.get("external_order_submission_performed") is True,
        "adapter_called_for_write": execution.get("adapter_called_for_write") is True,
        "live_canary_approval_packet_id": execution.get("live_canary_approval_packet_id") or approval.get("live_canary_approval_packet_id"),
        "live_canary_approval_packet_sha256": execution.get("live_canary_approval_packet_sha256") or approval.get("live_canary_approval_packet_sha256"),
        "live_canary_order_payload_sha256": payload.get("live_canary_order_payload_sha256") or sha256_json(payload) if payload else None,
        "live_canary_order_executor_record_sha256": execution.get("live_canary_order_executor_record_sha256"),
        "live_canary_order_lifecycle_record_id": execution.get("live_canary_order_lifecycle_registry_record_id") or lifecycle.get("live_canary_order_lifecycle_registry_record_id"),
        "live_canary_order_lifecycle_record_sha256": execution.get("live_canary_order_lifecycle_registry_record_sha256") or lifecycle.get("live_canary_order_lifecycle_registry_record_sha256"),
        "canonical_id_chain": dict(execution.get("canonical_id_chain") or {}),
        "missing_canonical_id_fields": list(execution.get("missing_canonical_id_fields") or []),
        "external_balance_sync_performed_by_this_module": False,
        "external_position_sync_performed_by_this_module": False,
        "external_execution_sync_performed_by_this_module": False,
        "external_order_submission_performed_by_this_module": False,
        "live_order_executed_by_this_module": False,
        "live_canary_promotion_allowed_by_this_module": False,
        "live_scaled_promotion_allowed_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["live_canary_reconciliation_record_sha256"] = sha256_json(_drop_hashes(record, "live_canary_reconciliation_record_sha256"))
    return record


def build_live_canary_reconciliation_registry_record(reconciliation_record: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(reconciliation_record or {})
    record = {
        "version": STEP315_LIVE_CANARY_RECONCILIATION_VERSION,
        "live_canary_reconciliation_id": data.get("live_canary_reconciliation_id"),
        "reconciliation_id": data.get("reconciliation_id"),
        "live_canary_reconciliation_record_sha256": data.get("live_canary_reconciliation_record_sha256"),
        "status": data.get("status"),
        "promotion_blocked": data.get("promotion_blocked") is True,
        "promotion_blocker": data.get("promotion_blocker"),
        "execution_id": data.get("execution_id"),
        "order_intent_id": data.get("order_intent_id"),
        "decision_id": data.get("decision_id"),
        "risk_gate_id": data.get("risk_gate_id"),
        "research_signal_id": data.get("research_signal_id"),
        "profile_id": data.get("profile_id"),
        "live_canary_approval_packet_id": data.get("live_canary_approval_packet_id"),
        "idempotency_key": data.get("idempotency_key"),
        "request_hash": data.get("request_hash"),
        "exchange_order_id": data.get("exchange_order_id"),
        "exchange_response_hash": data.get("exchange_response_hash"),
        "submitted_to_exchange": data.get("submitted_to_exchange") is True,
        "actual_submission_performed": data.get("actual_submission_performed") is True,
        "external_order_submission_performed": data.get("external_order_submission_performed") is True,
        "failed_check_names": list(data.get("failed_check_names") or []),
        "live_canary_promotion_allowed_by_this_module": False,
        "live_scaled_promotion_allowed_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["live_canary_reconciliation_registry_record_id"] = stable_id("step315_live_canary_reconciliation_registry", record, 24)
    record["live_canary_reconciliation_registry_record_sha256"] = sha256_json(record)
    return record


def persist_live_canary_reconciliation_record(cfg: AppConfig, reconciliation_record: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    session_dir = cfg.root / "storage" / "live_canary_reconciliation"
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(reconciliation_record)
    registry_record = build_live_canary_reconciliation_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, LIVE_CANARY_RECONCILIATION_REGISTRY_NAME),
        registry_record,
        registry_name=LIVE_CANARY_RECONCILIATION_REGISTRY_NAME,
        id_field="live_canary_reconciliation_registry_record_id",
        hash_field="live_canary_reconciliation_registry_record_sha256",
        id_prefix="step315_live_canary_reconciliation_registry",
    )
    payload["live_canary_reconciliation_registry_record_id"] = persisted.get("live_canary_reconciliation_registry_record_id")
    payload["live_canary_reconciliation_registry_record_sha256"] = persisted.get("live_canary_reconciliation_registry_record_sha256")
    atomic_write_json(latest_dir / "live_canary_reconciliation_record.json", payload)
    atomic_write_json(latest_dir / "live_canary_reconciliation_registry_record.json", persisted)
    atomic_write_json(session_dir / "live_canary_reconciliation_record.json", payload)
    return payload


def _latest_json(path: Path) -> dict[str, Any]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def run_live_canary_reconciliation_latest(
    *,
    project_root: str | Path = ".",
    execution_record: Mapping[str, Any] | None = None,
    live_canary_order_payload: Mapping[str, Any] | None = None,
    approval_packet: Mapping[str, Any] | None = None,
    lifecycle_record: Mapping[str, Any] | None = None,
    policy: LiveCanaryReconciliationPolicy | None = None,
) -> dict[str, Any]:
    cfg = load_config(Path(project_root))
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    execution = dict(execution_record or _latest_json(latest_dir / "live_canary_order_execution_record.json"))
    payload = dict(live_canary_order_payload or _safe_payload(execution) or {})
    approval = dict(approval_packet or _latest_json(latest_dir / "live_canary_approval_packet.json"))
    lifecycle = dict(lifecycle_record or _latest_json(latest_dir / "live_canary_order_lifecycle_registry_record.json"))
    record = build_live_canary_reconciliation_record(
        execution_record=execution,
        live_canary_order_payload=payload,
        approval_packet=approval,
        lifecycle_record=lifecycle,
        policy=policy,
    )
    return persist_live_canary_reconciliation_record(cfg, record)
