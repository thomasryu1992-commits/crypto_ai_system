from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.signed_testnet_order_executor import STATUS_SUBMITTED as EXECUTOR_STATUS_SUBMITTED
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

STEP309_SIGNED_TESTNET_RECONCILIATION_VERSION = "step309_signed_testnet_reconciliation_v1"
SIGNED_TESTNET_RECONCILIATION_REGISTRY_NAME = "signed_testnet_reconciliation_registry"

STATUS_RECONCILED = "SIGNED_TESTNET_RECONCILED_REVIEW_ONLY"
STATUS_MISMATCH = "SIGNED_TESTNET_RECONCILIATION_MISMATCH"
STATUS_BLOCKED_NO_SUBMISSION = "SIGNED_TESTNET_RECONCILIATION_BLOCKED_NO_SUBMISSION"
STATUS_BLOCKED_EVIDENCE_MISSING = "SIGNED_TESTNET_RECONCILIATION_BLOCKED_EVIDENCE_MISSING"
STATUS_BLOCKED_UNSAFE_SIDE_EFFECT = "SIGNED_TESTNET_RECONCILIATION_BLOCKED_UNSAFE_SIDE_EFFECT"

PROMOTION_BLOCKER_NONE = "NO_TESTNET_PROMOTION_BLOCKER"
PROMOTION_BLOCKER_MISMATCH = "BLOCK_TESTNET_PROMOTION_RECONCILIATION_MISMATCH"
PROMOTION_BLOCKER_EVIDENCE_MISSING = "BLOCK_TESTNET_PROMOTION_RECONCILIATION_EVIDENCE_MISSING"
PROMOTION_BLOCKER_EXECUTION_NOT_SUBMITTED = "BLOCK_TESTNET_PROMOTION_EXECUTION_NOT_SUBMITTED"
PROMOTION_BLOCKER_UNSAFE_SIDE_EFFECT = "BLOCK_TESTNET_PROMOTION_UNSAFE_SIDE_EFFECT"

LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE = False
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
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _drop_hashes(payload: Mapping[str, Any], *hash_fields: str) -> dict[str, Any]:
    drop = set(hash_fields) | {"created_at_utc"}
    return {k: v for k, v in dict(payload).items() if k not in drop}


def _safe_payload(execution_record: Mapping[str, Any], explicit_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if explicit_payload:
        return dict(explicit_payload)
    embedded = execution_record.get("would_submit_order_payload")
    return dict(embedded) if isinstance(embedded, Mapping) else {}


@dataclass(frozen=True)
class SignedTestnetReconciliationPolicy:
    review_only: bool = True
    require_execution_record: bool = True
    require_would_submit_payload: bool = True
    require_idempotency_match: bool = True
    require_order_intent_match: bool = True
    require_request_hash_match: bool = True
    require_lifecycle_evidence: bool = True
    require_exchange_order_id_if_submitted: bool = True
    allow_testnet_promotion: bool = False
    live_position_sync_enabled_by_this_module: bool = False
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


def _unsafe_side_effects(execution_record: Mapping[str, Any], policy: SignedTestnetReconciliationPolicy) -> dict[str, bool]:
    return {
        "live_position_sync_enabled_by_this_module": policy.live_position_sync_enabled_by_this_module or LIVE_POSITION_SYNC_ENABLED_BY_THIS_MODULE,
        "external_execution_sync_performed": policy.external_execution_sync_performed or EXTERNAL_EXECUTION_SYNC_PERFORMED,
        "external_order_submission_performed_by_this_module": policy.external_order_submission_performed or EXTERNAL_ORDER_SUBMISSION_PERFORMED,
        "live_order_executed_by_this_module": policy.live_order_executed or LIVE_ORDER_EXECUTED,
        "live_trading_allowed_by_this_module": policy.live_trading_allowed_by_this_module or _bool(execution_record.get("live_trading_allowed_by_this_module")),
        "api_key_value_access_allowed": policy.api_key_value_access_allowed or _bool(execution_record.get("api_key_value_access_allowed")),
        "api_secret_value_access_allowed": policy.api_secret_value_access_allowed or _bool(execution_record.get("api_secret_value_access_allowed")),
        "secret_file_access_allowed": policy.secret_file_access_allowed or _bool(execution_record.get("secret_file_access_allowed")),
        "secret_file_creation_allowed": policy.secret_file_creation_allowed or _bool(execution_record.get("secret_file_creation_allowed")),
        "runtime_settings_mutated": policy.runtime_settings_mutated or _bool(execution_record.get("runtime_settings_mutated")),
        "score_weights_mutated": policy.score_weights_mutated or _bool(execution_record.get("score_weights_mutated")),
        "auto_promotion_allowed": policy.auto_promotion_allowed or _bool(execution_record.get("auto_promotion_allowed")),
    }


def build_signed_testnet_reconciliation_checks(
    *,
    execution_record: Mapping[str, Any],
    would_submit_payload: Mapping[str, Any] | None = None,
    lifecycle_record: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    execution = dict(execution_record or {})
    payload = _safe_payload(execution, would_submit_payload)
    lifecycle = dict(lifecycle_record or {})
    lifecycle_events = execution.get("lifecycle_events") or []
    lifecycle_states = lifecycle.get("lifecycle_states") or [event.get("state") for event in lifecycle_events if isinstance(event, Mapping)]
    expected_request_hash = sha256_json(payload) if payload else None

    checks = [
        _check("SIGNED_TESTNET_EXECUTION_RECORD_EXISTS", bool(execution), "Execution record exists.", "Signed testnet execution record is missing.", severity="fatal"),
        _check("WOULD_SUBMIT_PAYLOAD_EXISTS", bool(payload), "Would-submit payload exists.", "Would-submit payload is missing.", severity="fatal"),
        _check(
            "ORDER_INTENT_ID_MATCH",
            bool(_text(execution.get("order_intent_id"))) and _text(execution.get("order_intent_id")) == _text(payload.get("order_intent_id")),
            "Order intent ID matches execution and payload.",
            "Order intent ID mismatch between execution record and would-submit payload.",
        ),
        _check("EXECUTION_ID_PRESENT", bool(_text(execution.get("execution_id"))), "Execution ID is present.", "Execution ID is missing."),
        _check(
            "RISK_GATE_ID_MATCH",
            bool(_text(execution.get("risk_gate_id"))) and _text(execution.get("risk_gate_id")) == _text(payload.get("risk_gate_id")),
            "Risk gate ID matches execution and payload.",
            "Risk gate ID mismatch between execution record and would-submit payload.",
        ),
        _check(
            "IDEMPOTENCY_KEY_MATCH",
            bool(_text(execution.get("idempotency_key"))) and _text(execution.get("idempotency_key")) == _text(payload.get("idempotency_key")),
            "Idempotency key matches execution and payload.",
            "Idempotency key mismatch between execution record and would-submit payload.",
        ),
        _check(
            "REQUEST_HASH_MATCH",
            bool(expected_request_hash) and _text(execution.get("request_hash")) == _text(expected_request_hash),
            "Request hash matches would-submit payload.",
            "Request hash mismatch for would-submit payload.",
        ),
        _check(
            "LIFECYCLE_EVIDENCE_PRESENT",
            bool(lifecycle_events or lifecycle_states),
            "Lifecycle evidence is present.",
            "Signed testnet lifecycle evidence is missing.",
        ),
        _check(
            "LIFECYCLE_RECONCILIATION_REQUIRED_STATE_PRESENT_IF_SUBMITTED",
            execution.get("submitted_to_exchange") is not True or "SIGNED_TESTNET_RECONCILIATION_REQUIRED" in lifecycle_states,
            "Submitted execution includes reconciliation-required lifecycle state.",
            "Submitted execution is missing reconciliation-required lifecycle state.",
        ),
        _check(
            "EXCHANGE_ORDER_ID_PRESENT_IF_SUBMITTED",
            execution.get("submitted_to_exchange") is not True or bool(_text(execution.get("exchange_order_id"))),
            "Submitted execution has exchange order ID.",
            "Submitted execution is missing exchange order ID.",
        ),
        _check(
            "EXCHANGE_RESPONSE_HASH_PRESENT_IF_SUBMITTED",
            execution.get("submitted_to_exchange") is not True or bool(_text(execution.get("exchange_response_hash"))),
            "Submitted execution has exchange response hash.",
            "Submitted execution is missing exchange response hash.",
        ),
        _check(
            "TESTNET_ENVIRONMENT_ONLY",
            _text(payload.get("environment") or "testnet").lower() == "testnet",
            "Would-submit payload is testnet-only.",
            "Would-submit payload is not testnet-only.",
        ),
        _check(
            "NO_LIVE_TRADING_FLAG",
            not _bool(execution.get("live_trading_allowed_by_this_module")),
            "Live trading flag is disabled.",
            "Live trading flag is unexpectedly enabled.",
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


def build_signed_testnet_reconciliation_record(
    *,
    execution_record: Mapping[str, Any] | None,
    would_submit_payload: Mapping[str, Any] | None = None,
    lifecycle_record: Mapping[str, Any] | None = None,
    policy: SignedTestnetReconciliationPolicy | None = None,
) -> dict[str, Any]:
    execution = dict(execution_record or {})
    payload = _safe_payload(execution, would_submit_payload)
    lifecycle = dict(lifecycle_record or {})
    policy = policy or SignedTestnetReconciliationPolicy()
    checks = build_signed_testnet_reconciliation_checks(execution_record=execution, would_submit_payload=payload, lifecycle_record=lifecycle)
    failed = [check for check in checks if not check.get("passed")]
    unsafe_flags = _unsafe_side_effects(execution, policy)
    unsafe_detected = any(unsafe_flags.values()) or any(check.get("severity") == "unsafe" and not check.get("passed") for check in checks)
    submitted = execution.get("submitted_to_exchange") is True or execution.get("status") == EXECUTOR_STATUS_SUBMITTED

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
        "version": STEP309_SIGNED_TESTNET_RECONCILIATION_VERSION,
        "signed_testnet_reconciliation_id": stable_id("step309_signed_testnet_reconciliation", reconciliation_id_source, 24),
        "reconciliation_id": stable_id("step309_signed_testnet_reconciliation", reconciliation_id_source, 24),
        "status": status,
        "reconciliation_status": status,
        "promotion_blocked": promotion_blocker != PROMOTION_BLOCKER_NONE,
        "promotion_blocker": promotion_blocker,
        "checks": checks,
        "failed_checks": failed,
        "failed_check_names": [check.get("name") for check in failed],
        "unsafe_side_effect_evidence": unsafe_flags,
        "signed_testnet_execution_id": execution.get("signed_testnet_execution_id"),
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
        "would_submit_order_payload_sha256": payload.get("would_submit_order_payload_sha256") or execution.get("would_submit_order_payload_sha256"),
        "signed_testnet_order_executor_record_sha256": execution.get("signed_testnet_order_executor_record_sha256"),
        "signed_testnet_order_lifecycle_record_id": execution.get("signed_testnet_order_lifecycle_record_id") or lifecycle.get("signed_testnet_order_lifecycle_record_id"),
        "signed_testnet_order_lifecycle_record_sha256": execution.get("signed_testnet_order_lifecycle_record_sha256") or lifecycle.get("signed_testnet_order_lifecycle_record_sha256"),
        "canonical_id_chain": dict(execution.get("canonical_id_chain") or {}),
        "missing_canonical_id_fields": list(execution.get("missing_canonical_id_fields") or []),
        "live_position_sync_enabled_by_this_module": False,
        "external_execution_sync_performed": False,
        "external_order_submission_performed_by_this_module": False,
        "live_order_executed_by_this_module": False,
        "testnet_promotion_allowed_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["signed_testnet_reconciliation_record_sha256"] = sha256_json(_drop_hashes(record, "signed_testnet_reconciliation_record_sha256"))
    return record


def build_signed_testnet_reconciliation_registry_record(reconciliation_record: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(reconciliation_record or {})
    record = {
        "version": STEP309_SIGNED_TESTNET_RECONCILIATION_VERSION,
        "signed_testnet_reconciliation_id": data.get("signed_testnet_reconciliation_id"),
        "reconciliation_id": data.get("reconciliation_id"),
        "signed_testnet_reconciliation_record_sha256": data.get("signed_testnet_reconciliation_record_sha256"),
        "status": data.get("status"),
        "promotion_blocked": data.get("promotion_blocked") is True,
        "promotion_blocker": data.get("promotion_blocker"),
        "execution_id": data.get("execution_id"),
        "order_intent_id": data.get("order_intent_id"),
        "decision_id": data.get("decision_id"),
        "risk_gate_id": data.get("risk_gate_id"),
        "research_signal_id": data.get("research_signal_id"),
        "profile_id": data.get("profile_id"),
        "idempotency_key": data.get("idempotency_key"),
        "request_hash": data.get("request_hash"),
        "exchange_order_id": data.get("exchange_order_id"),
        "exchange_response_hash": data.get("exchange_response_hash"),
        "submitted_to_exchange": data.get("submitted_to_exchange") is True,
        "actual_submission_performed": data.get("actual_submission_performed") is True,
        "external_order_submission_performed": data.get("external_order_submission_performed") is True,
        "failed_check_names": list(data.get("failed_check_names") or []),
        "testnet_promotion_allowed_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
        "created_at_utc": utc_now_canonical(),
    }
    record["signed_testnet_reconciliation_registry_record_id"] = stable_id("step309_signed_testnet_reconciliation_registry", record, 24)
    record["signed_testnet_reconciliation_registry_record_sha256"] = sha256_json(record)
    return record


def persist_signed_testnet_reconciliation_record(cfg: AppConfig, reconciliation_record: Mapping[str, Any]) -> dict[str, Any]:
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    session_dir = cfg.root / "storage" / "signed_testnet_reconciliation"
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(reconciliation_record)
    registry_record = build_signed_testnet_reconciliation_registry_record(payload)
    persisted = append_registry_record(
        registry_path(cfg, SIGNED_TESTNET_RECONCILIATION_REGISTRY_NAME),
        registry_record,
        registry_name=SIGNED_TESTNET_RECONCILIATION_REGISTRY_NAME,
        id_field="signed_testnet_reconciliation_registry_record_id",
        hash_field="signed_testnet_reconciliation_registry_record_sha256",
        id_prefix="step309_signed_testnet_reconciliation_registry",
    )
    payload["signed_testnet_reconciliation_registry_record_id"] = persisted.get("signed_testnet_reconciliation_registry_record_id")
    payload["signed_testnet_reconciliation_registry_record_sha256"] = persisted.get("signed_testnet_reconciliation_registry_record_sha256")
    atomic_write_json(latest_dir / "signed_testnet_reconciliation_record.json", payload)
    atomic_write_json(latest_dir / "signed_testnet_reconciliation_registry_record.json", persisted)
    atomic_write_json(session_dir / "signed_testnet_reconciliation_record.json", payload)
    return payload


def _latest_json(path: Path) -> dict[str, Any]:
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def run_signed_testnet_reconciliation_latest(
    *,
    project_root: str | Path = ".",
    execution_record: Mapping[str, Any] | None = None,
    would_submit_payload: Mapping[str, Any] | None = None,
    lifecycle_record: Mapping[str, Any] | None = None,
    policy: SignedTestnetReconciliationPolicy | None = None,
) -> dict[str, Any]:
    cfg = load_config(Path(project_root))
    latest_dir = cfg.root / str(cfg.get("storage.latest_dir", "storage/latest"))
    latest_dir.mkdir(parents=True, exist_ok=True)
    execution = dict(execution_record or _latest_json(latest_dir / "signed_testnet_order_execution_record.json"))
    payload = dict(would_submit_payload or _latest_json(latest_dir / "would_submit_order_payload.json"))
    lifecycle = dict(lifecycle_record or _latest_json(latest_dir / "signed_testnet_order_lifecycle_registry_record.json"))
    record = build_signed_testnet_reconciliation_record(
        execution_record=execution,
        would_submit_payload=payload,
        lifecycle_record=lifecycle,
        policy=policy,
    )
    return persist_signed_testnet_reconciliation_record(cfg, record)
