from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.execution.signed_testnet_one_order_runtime_package import (
    OneOrderRuntimeIntent,
    RuntimeSecretBindingMetadata,
    validate_one_order_guard,
    validate_runtime_secret_binding_metadata,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P5_ACTION_TIME_SUBMIT_APPROVAL_BOUNDARY_VERSION = "p5_action_time_submit_approval_boundary_v1"
P5_ACTION_TIME_SUBMIT_APPROVAL_BOUNDARY_REGISTRY_NAME = "p5_action_time_submit_approval_boundary_registry"
STATUS_VALID_REVIEW_ONLY = "P5_ACTION_TIME_SUBMIT_APPROVAL_BOUNDARY_VALID_REVIEW_ONLY_NO_SUBMIT"
STATUS_BLOCKED_REVIEW_ONLY = "P5_ACTION_TIME_SUBMIT_APPROVAL_BOUNDARY_BLOCKED_REVIEW_ONLY"

EXPLICIT_APPROVAL_PHRASE = "I APPROVE ONE SIGNED TESTNET BTCUSDT ORDER AT ACTION TIME"
_ALLOWED_RISK_GATE_RESULTS = {"PASS_SIGNED_TESTNET", "PASS_TESTNET", "PASS_TESTNET_PRE_SUBMIT"}

_DISABLED_RUNTIME_FLAGS = {
    "ready_for_signed_testnet_execution": False,
    "testnet_order_submission_allowed": False,
    "signed_testnet_promotion_allowed": False,
    "external_order_submission_allowed": False,
    "external_order_submission_performed": False,
    "place_order_enabled": False,
    "cancel_order_enabled": False,
    "signed_order_executor_enabled": False,
    "order_endpoint_call_allowed": False,
    "order_status_endpoint_call_allowed": False,
    "cancel_endpoint_call_allowed": False,
    "http_request_allowed": False,
    "signature_creation_allowed": False,
    "signed_request_creation_allowed": False,
    "order_endpoint_called": False,
    "order_status_endpoint_called": False,
    "cancel_endpoint_called": False,
    "http_request_sent": False,
    "signature_created": False,
    "signed_request_created": False,
    "actual_order_submission_performed": False,
    "actual_testnet_order_submitted": False,
    "real_exchange_order_id_present": False,
    "runtime_submit_action_executed": False,
    "runtime_submit_action_performed": False,
    "runtime_settings_mutated": False,
    "score_weights_mutated": False,
    "candidate_profile_applied": False,
    "auto_promotion_allowed": False,
    "secret_value_accessed": False,
    "secret_value_logged": False,
    "api_key_value_logged": False,
    "api_secret_value_logged": False,
    "secret_file_accessed": False,
    "secret_file_created": False,
    "live_canary_execution_enabled": False,
    "live_scaled_execution_enabled": False,
}


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _storage_dir(cfg: AppConfig, rel: str) -> Path:
    path = cfg.root / rel
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _public_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "p4_signed_testnet_runtime_package_sha256",
        "p4_signed_testnet_one_order_runtime_package_sha256",
        "p4_summary_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


@dataclass(frozen=True)
class ActionTimeSubmitApprovalEvidence:
    """Operator-provided action-time approval metadata.

    This carries a precise approval phrase and public evidence references only. It
    is intentionally not a key, order submit command, signed payload, or endpoint
    authorization switch.
    """

    operator_id: str = "operator_thomas_review_fixture"
    approval_ticket_id: str = "ticket_signed_testnet_action_time_review_1"
    explicit_approval_text: str = EXPLICIT_APPROVAL_PHRASE
    approval_packet_id: str | None = None
    approval_intake_id: str | None = None
    source_p4_runtime_package_sha256: str | None = None
    action_time_utc: str | None = None
    max_order_count: int = 1
    testnet_only: bool = True
    single_order_scope: bool = True
    no_auto_generated_approval_file: bool = True
    human_operator_submitted: bool = True
    runtime_submit_action_is_separate: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["action_time_utc"] = payload.get("action_time_utc") or utc_now_canonical()
        payload["explicit_approval_phrase_expected"] = EXPLICIT_APPROVAL_PHRASE
        payload["approval_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class ActionTimeRuntimeFreshnessEvidence:
    endpoint_time_sync_age_ms: int = 250
    hot_path_preorder_risk_gate_age_sec: int = 5
    hot_path_preorder_risk_gate_result: str = "PASS_SIGNED_TESTNET"
    hot_path_preorder_risk_gate_id: str = "risk_gate_signed_testnet_action_time_1"
    duplicate_submit_lock_acquired: bool = True
    idempotency_key_already_seen: bool = False
    manual_kill_switch_confirmed_safe: bool = True
    config_kill_switch_enabled: bool = False
    api_error_rate_within_limit: bool = True
    reconciliation_mismatch_within_limit: bool = True
    stale_data_kill_switch_active: bool = False
    hard_required_source_missing: bool = False
    endpoint_policy_preview_complete: bool = True
    executor_policy_preview_complete: bool = True
    runtime_secret_binding_metadata_present: bool = True
    post_submit_relock_planned: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["freshness_evidence_sha256"] = sha256_json(payload)
        return payload


def validate_action_time_submit_approval_evidence(evidence: Mapping[str, Any] | ActionTimeSubmitApprovalEvidence | None, *, expected_p4_sha256: str | None = None) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, ActionTimeSubmitApprovalEvidence) else dict(evidence or {})
    blockers: list[str] = []
    if not _is_nonempty(payload.get("operator_id")):
        blockers.append("P5_OPERATOR_ID_MISSING")
    if not _is_nonempty(payload.get("approval_ticket_id")):
        blockers.append("P5_APPROVAL_TICKET_ID_MISSING")
    if payload.get("explicit_approval_text") != EXPLICIT_APPROVAL_PHRASE:
        blockers.append("P5_EXPLICIT_ACTION_TIME_APPROVAL_PHRASE_MISSING_OR_MISMATCHED")
    if payload.get("max_order_count") != 1:
        blockers.append("P5_MAX_ORDER_COUNT_NOT_ONE")
    if payload.get("testnet_only") is not True:
        blockers.append("P5_TESTNET_ONLY_NOT_TRUE")
    if payload.get("single_order_scope") is not True:
        blockers.append("P5_SINGLE_ORDER_SCOPE_NOT_TRUE")
    if payload.get("no_auto_generated_approval_file") is not True:
        blockers.append("P5_AUTO_GENERATED_APPROVAL_FILE_NOT_ALLOWED")
    if payload.get("human_operator_submitted") is not True:
        blockers.append("P5_HUMAN_OPERATOR_SUBMISSION_REQUIRED")
    if payload.get("runtime_submit_action_is_separate") is not True:
        blockers.append("P5_RUNTIME_SUBMIT_ACTION_MUST_REMAIN_SEPARATE")
    if expected_p4_sha256 and payload.get("source_p4_runtime_package_sha256") and payload.get("source_p4_runtime_package_sha256") != expected_p4_sha256:
        blockers.append("P5_SOURCE_P4_RUNTIME_PACKAGE_HASH_MISMATCH")
    if expected_p4_sha256 and not payload.get("source_p4_runtime_package_sha256"):
        blockers.append("P5_SOURCE_P4_RUNTIME_PACKAGE_HASH_MISSING")
    validation = {
        "action_time_submit_approval_evidence_valid": not blockers,
        "approval_evidence_block_reasons": sorted(dict.fromkeys(blockers)),
        "operator_id": payload.get("operator_id"),
        "approval_ticket_id": payload.get("approval_ticket_id"),
        "explicit_approval_phrase_matched": payload.get("explicit_approval_text") == EXPLICIT_APPROVAL_PHRASE,
        "max_order_count": payload.get("max_order_count"),
        "testnet_only": payload.get("testnet_only") is True,
        "single_order_scope": payload.get("single_order_scope") is True,
        "source_p4_runtime_package_sha256": payload.get("source_p4_runtime_package_sha256"),
        "expected_p4_runtime_package_sha256": expected_p4_sha256,
    }
    validation["action_time_submit_approval_evidence_validation_sha256"] = sha256_json(validation)
    return validation


def validate_action_time_runtime_freshness(evidence: Mapping[str, Any] | ActionTimeRuntimeFreshnessEvidence | None, *, max_endpoint_time_sync_age_ms: int = 1000, max_hot_path_risk_gate_age_sec: int = 30) -> dict[str, Any]:
    payload = evidence.to_dict() if isinstance(evidence, ActionTimeRuntimeFreshnessEvidence) else dict(evidence or {})
    blockers: list[str] = []
    endpoint_age = int(payload.get("endpoint_time_sync_age_ms", 10**9) or 10**9)
    risk_age = int(payload.get("hot_path_preorder_risk_gate_age_sec", 10**9) or 10**9)
    if endpoint_age > max_endpoint_time_sync_age_ms:
        blockers.append("P5_ENDPOINT_TIME_SYNC_STALE_AT_ACTION_TIME")
    if risk_age > max_hot_path_risk_gate_age_sec:
        blockers.append("P5_HOT_PATH_PREORDER_RISK_GATE_STALE_AT_ACTION_TIME")
    if payload.get("hot_path_preorder_risk_gate_result") not in _ALLOWED_RISK_GATE_RESULTS:
        blockers.append("P5_HOT_PATH_PREORDER_RISK_GATE_RESULT_NOT_PASS")
    if not _is_nonempty(payload.get("hot_path_preorder_risk_gate_id")):
        blockers.append("P5_HOT_PATH_PREORDER_RISK_GATE_ID_MISSING")
    if payload.get("duplicate_submit_lock_acquired") is not True:
        blockers.append("P5_DUPLICATE_SUBMIT_LOCK_NOT_ACQUIRED")
    if payload.get("idempotency_key_already_seen") is True:
        blockers.append("P5_IDEMPOTENCY_KEY_ALREADY_SEEN")
    if payload.get("manual_kill_switch_confirmed_safe") is not True:
        blockers.append("P5_MANUAL_KILL_SWITCH_NOT_CONFIRMED_SAFE")
    if payload.get("config_kill_switch_enabled") is True:
        blockers.append("P5_CONFIG_KILL_SWITCH_ENABLED")
    if payload.get("api_error_rate_within_limit") is not True:
        blockers.append("P5_API_ERROR_RATE_LIMIT_EXCEEDED")
    if payload.get("reconciliation_mismatch_within_limit") is not True:
        blockers.append("P5_RECONCILIATION_MISMATCH_LIMIT_EXCEEDED")
    if payload.get("stale_data_kill_switch_active") is True:
        blockers.append("P5_STALE_DATA_KILL_SWITCH_ACTIVE")
    if payload.get("hard_required_source_missing") is True:
        blockers.append("P5_HARD_REQUIRED_SOURCE_MISSING")
    if payload.get("endpoint_policy_preview_complete") is not True:
        blockers.append("P5_ENDPOINT_POLICY_PREVIEW_NOT_COMPLETE")
    if payload.get("executor_policy_preview_complete") is not True:
        blockers.append("P5_EXECUTOR_POLICY_PREVIEW_NOT_COMPLETE")
    if payload.get("runtime_secret_binding_metadata_present") is not True:
        blockers.append("P5_RUNTIME_SECRET_BINDING_METADATA_NOT_PRESENT")
    if payload.get("post_submit_relock_planned") is not True:
        blockers.append("P5_POST_SUBMIT_RELOCK_NOT_PLANNED")
    validation = {
        "action_time_runtime_freshness_valid": not blockers,
        "runtime_freshness_block_reasons": sorted(dict.fromkeys(blockers)),
        "endpoint_time_sync_age_ms": endpoint_age,
        "max_endpoint_time_sync_age_ms": max_endpoint_time_sync_age_ms,
        "hot_path_preorder_risk_gate_age_sec": risk_age,
        "max_hot_path_risk_gate_age_sec": max_hot_path_risk_gate_age_sec,
        "hot_path_preorder_risk_gate_result": payload.get("hot_path_preorder_risk_gate_result"),
        "duplicate_submit_lock_acquired": payload.get("duplicate_submit_lock_acquired") is True,
        "idempotency_key_already_seen": payload.get("idempotency_key_already_seen") is True,
        "manual_kill_switch_confirmed_safe": payload.get("manual_kill_switch_confirmed_safe") is True,
        "post_submit_relock_planned": payload.get("post_submit_relock_planned") is True,
    }
    validation["action_time_runtime_freshness_validation_sha256"] = sha256_json(validation)
    return validation


def _p4_ready(p4_report: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    data = dict(p4_report or {})
    if data.get("status") != "P4_SIGNED_TESTNET_ONE_ORDER_RUNTIME_PACKAGE_READY_REVIEW_ONLY_DISABLED":
        blockers.append("P5_P4_RUNTIME_PACKAGE_STATUS_NOT_READY")
    if data.get("runtime_package_ready_for_separate_operator_submit_action_review_only") is not True:
        blockers.append("P5_P4_RUNTIME_PACKAGE_NOT_READY_FOR_SEPARATE_ACTION")
    if data.get("actual_order_submission_performed") is not False:
        blockers.append("P5_P4_ACTUAL_ORDER_SUBMISSION_PERFORMED_NOT_FALSE")
    if data.get("order_endpoint_called") is not False:
        blockers.append("P5_P4_ORDER_ENDPOINT_CALLED_NOT_FALSE")
    if data.get("testnet_order_submission_allowed") is not False:
        blockers.append("P5_P4_TESTNET_ORDER_SUBMISSION_ALLOWED_NOT_FALSE")
    if data.get("secret_value_accessed") is not False:
        blockers.append("P5_P4_SECRET_VALUE_ACCESSED_NOT_FALSE")
    return not blockers, blockers


def _disabled_payload() -> dict[str, Any]:
    payload = default_execution_flag_state()
    payload.update(_DISABLED_RUNTIME_FLAGS)
    return payload


def build_action_time_submit_approval_boundary_report(
    *,
    cfg: AppConfig | None = None,
    intent: OneOrderRuntimeIntent | None = None,
    approval_evidence: ActionTimeSubmitApprovalEvidence | Mapping[str, Any] | None = None,
    freshness_evidence: ActionTimeRuntimeFreshnessEvidence | Mapping[str, Any] | None = None,
    secret_binding: RuntimeSecretBindingMetadata | Mapping[str, Any] | None = None,
    existing_idempotency_keys: Sequence[str] | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    p4_report = _read_latest_json(cfg, "p4_signed_testnet_one_order_runtime_package_report.json")
    p4_ok, p4_blockers = _p4_ready(p4_report)
    p4_hash = _public_hash(p4_report)

    intent = intent or OneOrderRuntimeIntent(idempotency_key="p5_action_time_idempotency_key")
    resolved_idempotency_key = intent.resolved_idempotency_key()
    approval_evidence = approval_evidence or ActionTimeSubmitApprovalEvidence(
        approval_packet_id=intent.approval_packet_id,
        approval_intake_id=intent.approval_intake_id,
        source_p4_runtime_package_sha256=p4_hash,
    )
    freshness_evidence = freshness_evidence or ActionTimeRuntimeFreshnessEvidence()
    secret_binding = secret_binding or RuntimeSecretBindingMetadata(
        secret_reference_id="metadata_only_testnet_key_ref_action_time",
        key_fingerprint_sha256="2" * 64,
    )

    approval_payload = approval_evidence.to_dict() if isinstance(approval_evidence, ActionTimeSubmitApprovalEvidence) else dict(approval_evidence or {})
    freshness_payload = freshness_evidence.to_dict() if isinstance(freshness_evidence, ActionTimeRuntimeFreshnessEvidence) else dict(freshness_evidence or {})
    secret_payload = secret_binding.to_dict() if isinstance(secret_binding, RuntimeSecretBindingMetadata) else dict(secret_binding or {})

    approval_validation = validate_action_time_submit_approval_evidence(approval_payload, expected_p4_sha256=p4_hash)
    freshness_validation = validate_action_time_runtime_freshness(freshness_payload)
    secret_validation = validate_runtime_secret_binding_metadata(secret_payload)
    one_order_guard = validate_one_order_guard(intent, idempotency_key=resolved_idempotency_key, existing_idempotency_keys=existing_idempotency_keys)

    blockers = sorted(dict.fromkeys(
        p4_blockers
        + list(approval_validation["approval_evidence_block_reasons"])
        + list(freshness_validation["runtime_freshness_block_reasons"])
        + list(secret_validation["secret_binding_block_reasons"])
        + list(one_order_guard["one_order_guard_block_reasons"])
    ))
    valid = bool(
        p4_ok
        and approval_validation["action_time_submit_approval_evidence_valid"]
        and freshness_validation["action_time_runtime_freshness_valid"]
        and secret_validation["secret_binding_metadata_valid"]
        and one_order_guard["one_order_guard_passed"]
    )
    report = {
        "artifact_type": "p5_action_time_submit_approval_boundary_review_only_no_submit",
        "p5_action_time_submit_approval_boundary_version": P5_ACTION_TIME_SUBMIT_APPROVAL_BOUNDARY_VERSION,
        "status": STATUS_VALID_REVIEW_ONLY if valid else STATUS_BLOCKED_REVIEW_ONLY,
        "blocked": not valid,
        "fail_closed": not valid,
        "review_only": True,
        "still_disabled": True,
        "action_time_submit_approval_boundary_valid_review_only": valid,
        "action_time_submit_preconditions_valid_review_only": valid,
        "does_not_grant_submit_permission": True,
        "separate_runtime_submit_action_required": True,
        "runtime_boundary_separate_from_review_package": True,
        "p4_runtime_package_ready": p4_ok,
        "source_p4_runtime_package_hash": p4_hash,
        "source_p4_runtime_package_id": p4_report.get("p4_signed_testnet_runtime_package_id"),
        "approval_validation": approval_validation,
        "approval_evidence": approval_payload,
        "runtime_freshness_validation": freshness_validation,
        "runtime_freshness_evidence": freshness_payload,
        "secret_binding_validation": secret_validation,
        "secret_binding_metadata_evidence": secret_payload,
        "one_order_guard": one_order_guard,
        "idempotency_key": resolved_idempotency_key,
        "post_submit_relock_policy": {
            "post_submit_relock_required": True,
            "place_order_enabled_after_action": False,
            "cancel_order_enabled_after_action": False,
            "signed_order_executor_enabled_after_action": False,
            "testnet_order_submission_allowed_after_action": False,
            "order_endpoint_call_allowed_after_action": False,
            "signature_creation_allowed_after_action": False,
            "http_request_allowed_after_action": False,
        },
        "next_runtime_action_boundary": {
            "actual_submit_must_be_run_in_separate_signed_testnet_runtime_process": True,
            "must_recheck_all_p5_preconditions_at_runtime": True,
            "must_record_real_endpoint_call_evidence_if_submit_is_later_performed": True,
            "must_record_exchange_order_id_if_submit_is_later_performed": True,
            "must_run_status_polling_reconciliation_session_close_after_real_submit": True,
        },
        "block_reasons": blockers,
        "created_at_utc": created_at_utc,
        **_disabled_payload(),
    }
    report["unsafe_truthy_execution_flags"] = truthy_execution_flags(report)
    if report["unsafe_truthy_execution_flags"]:
        report["blocked"] = True
        report["fail_closed"] = True
        report["status"] = STATUS_BLOCKED_REVIEW_ONLY
        report["block_reasons"] = sorted(dict.fromkeys(blockers + ["P5_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
        report["action_time_submit_approval_boundary_valid_review_only"] = False
        report["action_time_submit_preconditions_valid_review_only"] = False
    report["p5_action_time_submit_approval_boundary_id"] = stable_id("p5_action_time_submit_approval_boundary", report, 24)
    report["p5_action_time_submit_approval_boundary_sha256"] = sha256_json(report)
    return report


def build_p5_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    p4 = _read_latest_json(cfg, "p4_signed_testnet_one_order_runtime_package_report.json")
    p4_hash = _public_hash(p4)
    base_approval = ActionTimeSubmitApprovalEvidence(source_p4_runtime_package_sha256=p4_hash)
    base_secret = RuntimeSecretBindingMetadata(secret_reference_id="metadata_only_testnet_key_ref_action_time", key_fingerprint_sha256="3" * 64)
    base_intent = OneOrderRuntimeIntent(idempotency_key="p5_negative_fixture_base")
    duplicate_key = "p5_duplicate_fixture_key"
    cases: dict[str, dict[str, Any]] = {
        "missing_explicit_approval_phrase": {
            "approval": {**base_approval.to_dict(), "explicit_approval_text": "approve"},
            "freshness": ActionTimeRuntimeFreshnessEvidence(),
            "secret": base_secret,
            "intent": base_intent,
            "existing": [],
        },
        "stale_hot_path_risk_gate": {
            "approval": base_approval,
            "freshness": ActionTimeRuntimeFreshnessEvidence(hot_path_preorder_risk_gate_age_sec=999),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="p5_stale_risk_fixture"),
            "existing": [],
        },
        "endpoint_time_stale": {
            "approval": base_approval,
            "freshness": ActionTimeRuntimeFreshnessEvidence(endpoint_time_sync_age_ms=9999),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="p5_stale_endpoint_fixture"),
            "existing": [],
        },
        "duplicate_idempotency": {
            "approval": base_approval,
            "freshness": ActionTimeRuntimeFreshnessEvidence(idempotency_key_already_seen=True),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key=duplicate_key),
            "existing": [duplicate_key],
        },
        "kill_switch_enabled": {
            "approval": base_approval,
            "freshness": ActionTimeRuntimeFreshnessEvidence(config_kill_switch_enabled=True),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="p5_kill_switch_fixture"),
            "existing": [],
        },
        "invalid_secret_scope": {
            "approval": base_approval,
            "freshness": ActionTimeRuntimeFreshnessEvidence(),
            "secret": {**base_secret.to_dict(), "key_scope": "live_trade"},
            "intent": OneOrderRuntimeIntent(idempotency_key="p5_invalid_secret_fixture"),
            "existing": [],
        },
        "hard_cap_exceeded": {
            "approval": base_approval,
            "freshness": ActionTimeRuntimeFreshnessEvidence(),
            "secret": base_secret,
            "intent": OneOrderRuntimeIntent(idempotency_key="p5_hard_cap_fixture", quantity=1.0, reference_price=50000.0, max_notional=10.0),
            "existing": [],
        },
    }
    results: dict[str, Any] = {}
    for name, fixture in cases.items():
        report = build_action_time_submit_approval_boundary_report(
            cfg=cfg,
            approval_evidence=fixture["approval"],
            freshness_evidence=fixture["freshness"],
            secret_binding=fixture["secret"],
            intent=fixture["intent"],
            existing_idempotency_keys=fixture["existing"],
        )
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True and report["fail_closed"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
        }
    payload = {
        "artifact_type": "p5_action_time_submit_approval_boundary_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
        **_disabled_payload(),
    }
    payload["p5_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_action_time_submit_approval_boundary(
    *,
    cfg: AppConfig | None = None,
    intent: OneOrderRuntimeIntent | None = None,
    approval_evidence: ActionTimeSubmitApprovalEvidence | Mapping[str, Any] | None = None,
    freshness_evidence: ActionTimeRuntimeFreshnessEvidence | Mapping[str, Any] | None = None,
    secret_binding: RuntimeSecretBindingMetadata | Mapping[str, Any] | None = None,
    existing_idempotency_keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_action_time_submit_approval_boundary_report(
        cfg=cfg,
        intent=intent,
        approval_evidence=approval_evidence,
        freshness_evidence=freshness_evidence,
        secret_binding=secret_binding,
        existing_idempotency_keys=existing_idempotency_keys,
    )
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p5_action_time_submit_approval_boundary")
    negative = build_p5_negative_fixture_results(cfg=cfg)
    registry_record = append_registry_record(
        registry_path(cfg, P5_ACTION_TIME_SUBMIT_APPROVAL_BOUNDARY_REGISTRY_NAME),
        {
            "artifact_type": "p5_action_time_submit_approval_boundary_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "action_time_submit_approval_boundary_valid_review_only": report["action_time_submit_approval_boundary_valid_review_only"],
            "p5_action_time_submit_approval_boundary_id": report["p5_action_time_submit_approval_boundary_id"],
            "p5_action_time_submit_approval_boundary_sha256": report["p5_action_time_submit_approval_boundary_sha256"],
            "source_p4_runtime_package_hash": report.get("source_p4_runtime_package_hash"),
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "secret_value_accessed": False,
            "testnet_order_submission_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        },
        registry_name=P5_ACTION_TIME_SUBMIT_APPROVAL_BOUNDARY_REGISTRY_NAME,
        id_field="p5_action_time_submit_approval_boundary_registry_record_id",
        hash_field="p5_action_time_submit_approval_boundary_registry_record_sha256",
        id_prefix="p5_action_time_submit_approval_boundary_registry_record",
    )
    report["p5_action_time_submit_approval_boundary_registry_record_id"] = registry_record["p5_action_time_submit_approval_boundary_registry_record_id"]
    report["p5_action_time_submit_approval_boundary_registry_record_sha256"] = registry_record["p5_action_time_submit_approval_boundary_registry_record_sha256"]
    report["p5_action_time_submit_approval_boundary_sha256"] = sha256_json(report)
    summary = {
        "artifact_type": "p5_action_time_submit_approval_boundary_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "action_time_submit_approval_boundary_valid_review_only": report["action_time_submit_approval_boundary_valid_review_only"],
        "action_time_submit_preconditions_valid_review_only": report["action_time_submit_preconditions_valid_review_only"],
        "does_not_grant_submit_permission": True,
        "separate_runtime_submit_action_required": True,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
        "testnet_order_submission_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "p5_action_time_submit_approval_boundary_id": report["p5_action_time_submit_approval_boundary_id"],
        "p5_action_time_submit_approval_boundary_sha256": report["p5_action_time_submit_approval_boundary_sha256"],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p5_summary_sha256"] = sha256_json(summary)
    for path in [
        latest / "p5_action_time_submit_approval_boundary_report.json",
        storage / "p5_action_time_submit_approval_boundary_report.json",
    ]:
        atomic_write_json(path, report)
    atomic_write_json(latest / "p5_action_time_submit_approval_boundary_negative_fixture_results.json", negative)
    atomic_write_json(storage / "p5_action_time_submit_approval_boundary_negative_fixture_results.json", negative)
    atomic_write_json(latest / "p5_action_time_submit_approval_boundary_registry_record.json", registry_record)
    atomic_write_json(storage / "p5_action_time_submit_approval_boundary_registry_record.json", registry_record)
    atomic_write_json(latest / "p5_action_time_submit_approval_boundary_summary.json", summary)
    atomic_write_json(storage / "p5_action_time_submit_approval_boundary_summary.json", summary)
    return report


__all__ = [
    "P5_ACTION_TIME_SUBMIT_APPROVAL_BOUNDARY_VERSION",
    "STATUS_VALID_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "EXPLICIT_APPROVAL_PHRASE",
    "ActionTimeSubmitApprovalEvidence",
    "ActionTimeRuntimeFreshnessEvidence",
    "validate_action_time_submit_approval_evidence",
    "validate_action_time_runtime_freshness",
    "build_action_time_submit_approval_boundary_report",
    "build_p5_negative_fixture_results",
    "persist_action_time_submit_approval_boundary",
]
