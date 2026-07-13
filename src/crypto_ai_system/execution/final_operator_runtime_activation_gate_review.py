from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_VERSION = "p28_final_operator_runtime_activation_gate_review_v1"
P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_REGISTRY_NAME = "p28_final_operator_runtime_activation_gate_review_registry"

P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_EXACT_PHRASE = (
    "I REQUEST FINAL REVIEW OF THE OPERATOR RUNTIME ACTIVATION GATE AND ACKNOWLEDGE THIS REVIEW DOES NOT ENABLE RUNTIME"
)

STATUS_WAITING_REVIEW_ONLY = "P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY = "P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_VALID_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_BLOCKED_FAIL_CLOSED"

_P27_SUMMARY_FILENAME = "p27_operator_runtime_activation_request_intake_validator_summary.json"
_P27_REPORT_FILENAME = "p27_operator_runtime_activation_request_intake_validator_report.json"
_P27_INTAKE_FILENAME = "p27_operator_runtime_activation_request_intake.json"
_P28_CONTROLS_FILENAME = "p28_final_operator_runtime_activation_gate_review_controls.json"

_EXECUTION_FIELDS_FOR_P28 = {
    "limited_live_scaled_auto_trading_allowed",
    "live_scaled_runtime_enablement_allowed",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "runtime_scheduler_enabled",
    "runtime_loop_started",
    "runtime_enablement_performed",
    "operator_runtime_activation_performed",
    "final_activation_gate_performed",
    "final_activation_gate_review_performed",
    "actual_live_order_submitted",
    "actual_testnet_order_submitted",
    "live_order_endpoint_called",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "secret_value_accessed",
    "secret_value_logged",
    "api_key_value_logged",
    "api_secret_value_logged",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "auto_promotion_allowed",
    "runtime_authority_claimed",
    "review_packet_is_runtime_authority",
    "activation_gate_executes_runtime",
    "request_executes_runtime",
    "scheduler_start_requested",
    "order_submission_requested",
    "endpoint_call_allowed",
    "secret_file_accessed",
    "secret_file_created",
}

_SECRET_VALUE_PATTERNS = (
    "BINANCE_API_SECRET=",
    "BINANCE_API_KEY=",
    "PRIVATE_KEY=",
    "api_secret_value:",
    "api_key_value:",
    "secret_value:",
    "BEGIN PRIVATE KEY",
)

_REQUIRED_TOP_LEVEL_ACKS = {
    "manual_operator_submission",
    "no_runtime_authority_acknowledged",
    "separate_runtime_activation_step_required_acknowledged",
    "fresh_validation_acknowledged",
    "no_execution_flags_modified_acknowledged",
    "no_order_submission_acknowledged",
    "no_scheduler_enablement_acknowledged",
    "no_secret_values_acknowledged",
    "no_endpoint_call_acknowledged",
    "rollback_and_full_shutdown_acknowledged",
    "monitoring_alerting_acknowledged",
    "daily_report_acknowledged",
    "incident_report_acknowledged",
    "all_orders_must_reconcile_acknowledged",
    "idempotency_required_acknowledged",
    "post_submit_relock_required_acknowledged",
    "canonical_id_chain_required_acknowledged",
}

_REQUIRED_FRESH_VALIDATION_CONTROLS = {
    "load_current_stage_policy_before_activation",
    "fresh_market_data_before_activation",
    "source_qa_required",
    "data_snapshot_required",
    "feature_lineage_required",
    "research_signal_v2_required",
    "signal_qa_required",
    "trading_decision_required",
    "hot_path_preorder_risk_gate_required",
    "hot_path_preorder_risk_gate_fresh_required",
    "order_intent_after_risk_gate_only",
}

_REQUIRED_KILL_SWITCH_CONTROLS = {
    "global_kill_switch_checked",
    "operator_manual_kill_switch_checked",
    "daily_loss_kill_switch_checked",
    "consecutive_loss_kill_switch_checked",
    "api_error_kill_switch_checked",
    "reconciliation_mismatch_kill_switch_checked",
    "stale_data_kill_switch_checked",
    "hard_required_source_kill_switch_checked",
    "duplicate_submit_lock_checked",
}

_REQUIRED_CAP_CONTROLS = {
    "btc_usdt_only",
    "fixed_max_notional_cap_checked",
    "daily_loss_cap_checked",
    "max_daily_order_count_checked",
    "max_consecutive_loss_checked",
    "max_open_position_count_checked",
    "max_leverage_checked",
    "max_slippage_checked",
    "max_api_error_rate_checked",
    "max_rejection_rate_checked",
}

_REQUIRED_RUNTIME_LOOP_CONTROLS = {
    "scheduler_dry_run_completed",
    "scheduler_dry_run_review_only",
    "runtime_loop_not_started",
    "runtime_scheduler_not_enabled",
    "would_submit_only",
    "no_http_request_sent",
    "no_signature_created",
    "post_submit_relock_confirmed_review_only",
    "status_polling_required",
    "reconciliation_required",
    "outcome_feedback_required",
    "daily_report_required",
    "incident_report_required",
    "monitoring_alerting_required",
    "rollback_required",
    "full_shutdown_required",
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


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower())


def _scan_truthy_execution_fields(payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                next_path = f"{path}.{key}"
                if key in _EXECUTION_FIELDS_FOR_P28 and _bool(value):
                    hits.append({"path": next_path, "field": str(key), "value": True})
                walk(value, next_path)
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                walk(item, f"{path}[{idx}]")

    for source, payload in payloads:
        before = len(hits)
        walk(payload)
        for hit in hits[before:]:
            hit["source"] = source
    return hits


def _scan_secret_value_patterns(payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def walk(payload: Any, source: str, path: str = "$") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                walk(value, source, f"{path}.{key}")
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                walk(item, source, f"{path}[{idx}]")
        elif isinstance(payload, str):
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.lower() in payload.lower():
                    hits.append({"source": source, "path": path, "pattern": pattern})

    for source, payload in payloads:
        walk(payload, source)
    return hits


def build_final_operator_runtime_activation_gate_review_controls_template(
    *,
    p27_validator_report_sha256: str | None = None,
    p27_intake_sha256: str | None = None,
) -> dict[str, Any]:
    template: dict[str, Any] = {
        "request_type": "final_operator_runtime_activation_gate_review_controls_review_only",
        "stage": "final_operator_runtime_activation_gate_review",
        "operator_id": "OPERATOR_ID_REQUIRED",
        "ticket_or_signature": "TICKET_OR_SIGNATURE_REQUIRED",
        "reviewed_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
        "exact_final_operator_runtime_activation_gate_review_phrase": P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_EXACT_PHRASE,
        "source_p27_operator_runtime_activation_request_intake_validator_report_sha256": p27_validator_report_sha256 or "P27_VALIDATOR_REPORT_SHA256_REQUIRED",
        "source_p27_operator_runtime_activation_request_intake_sha256": p27_intake_sha256 or "P27_ACTIVATION_REQUEST_INTAKE_SHA256_REQUIRED",
        "manual_operator_submission": True,
        "auto_generated_final_activation_review": False,
        "review_packet_is_runtime_authority": False,
        "activation_gate_executes_runtime": False,
        "request_executes_runtime": False,
        "no_runtime_authority_acknowledged": True,
        "separate_runtime_activation_step_required_acknowledged": True,
        "fresh_validation_acknowledged": True,
        "no_execution_flags_modified_acknowledged": True,
        "no_order_submission_acknowledged": True,
        "no_scheduler_enablement_acknowledged": True,
        "no_secret_values_acknowledged": True,
        "no_endpoint_call_acknowledged": True,
        "rollback_and_full_shutdown_acknowledged": True,
        "monitoring_alerting_acknowledged": True,
        "daily_report_acknowledged": True,
        "incident_report_acknowledged": True,
        "all_orders_must_reconcile_acknowledged": True,
        "idempotency_required_acknowledged": True,
        "post_submit_relock_required_acknowledged": True,
        "canonical_id_chain_required_acknowledged": True,
        "fresh_validation_controls": {field: True for field in sorted(_REQUIRED_FRESH_VALIDATION_CONTROLS)},
        "kill_switch_controls": {field: True for field in sorted(_REQUIRED_KILL_SWITCH_CONTROLS)},
        "cap_controls": {field: True for field in sorted(_REQUIRED_CAP_CONTROLS)},
        "runtime_loop_controls": {field: True for field in sorted(_REQUIRED_RUNTIME_LOOP_CONTROLS)},
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "runtime_enablement_performed": False,
        "operator_runtime_activation_performed": False,
        "final_activation_gate_performed": False,
        "actual_live_order_submitted": False,
        "actual_testnet_order_submitted": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    template["p28_final_operator_runtime_activation_gate_review_controls_template_sha256"] = sha256_json(template)
    return template


def _validate_p27_source(p27_summary: Mapping[str, Any], p27_report: Mapping[str, Any], p27_intake: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not p27_summary:
        waiting.append("P28_SOURCE_P27_SUMMARY_MISSING")
    if not p27_report:
        waiting.append("P28_SOURCE_P27_REPORT_MISSING")
    if not p27_intake:
        waiting.append("P28_SOURCE_P27_INTAKE_MISSING")
    if waiting:
        return waiting, blocked

    if p27_summary.get("status") == "P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_BLOCKED_FAIL_CLOSED":
        blocked.append("P28_SOURCE_P27_SUMMARY_BLOCKED")
    if p27_report.get("status") == "P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_BLOCKED_FAIL_CLOSED":
        blocked.append("P28_SOURCE_P27_REPORT_BLOCKED")
    if p27_summary.get("p27_operator_runtime_activation_request_intake_valid_review_only") is not True:
        waiting.append("P28_SOURCE_P27_INTAKE_NOT_VALID")
    if p27_summary.get("operator_runtime_activation_request_validated_review_only") is not True:
        waiting.append("P28_SOURCE_P27_REQUEST_NOT_VALIDATED")
    if p27_report.get("p27_operator_runtime_activation_request_intake_valid_review_only") is not True:
        waiting.append("P28_SOURCE_P27_REPORT_INTAKE_NOT_VALID")
    if p27_report.get("operator_runtime_activation_request_validated_review_only") is not True:
        waiting.append("P28_SOURCE_P27_REPORT_REQUEST_NOT_VALIDATED")
    if p27_report.get("operator_runtime_activation_request_is_runtime_authority") is not False:
        blocked.append("P28_SOURCE_P27_RUNTIME_AUTHORITY_CLAIMED")
    if p27_report.get("separate_final_operator_runtime_activation_gate_required") is not True:
        blocked.append("P28_SOURCE_P27_FINAL_GATE_NOT_REQUIRED")

    report_hash_summary = p27_summary.get("p27_operator_runtime_activation_request_intake_validator_sha256")
    report_hash_report = p27_report.get("p27_operator_runtime_activation_request_intake_validator_sha256")
    if not _is_sha256(report_hash_summary):
        waiting.append("P28_SOURCE_P27_SUMMARY_VALIDATOR_HASH_MISSING_OR_INVALID")
    if not _is_sha256(report_hash_report):
        waiting.append("P28_SOURCE_P27_REPORT_VALIDATOR_HASH_MISSING_OR_INVALID")
    if _is_sha256(report_hash_summary) and _is_sha256(report_hash_report) and report_hash_summary != report_hash_report:
        blocked.append("P28_SOURCE_P27_VALIDATOR_HASH_MISMATCH")
    intake_hash_summary = p27_summary.get("p27_operator_runtime_activation_request_intake_sha256")
    intake_hash_report = p27_report.get("p27_operator_runtime_activation_request_intake_sha256")
    if not _is_sha256(intake_hash_summary):
        waiting.append("P28_SOURCE_P27_SUMMARY_INTAKE_HASH_MISSING_OR_INVALID")
    if not _is_sha256(intake_hash_report):
        waiting.append("P28_SOURCE_P27_REPORT_INTAKE_HASH_MISSING_OR_INVALID")
    if _is_sha256(intake_hash_summary) and _is_sha256(intake_hash_report) and intake_hash_summary != intake_hash_report:
        blocked.append("P28_SOURCE_P27_INTAKE_HASH_MISMATCH")
    if _is_sha256(intake_hash_summary) and p27_intake and sha256_json(dict(p27_intake)) != intake_hash_summary:
        blocked.append("P28_SOURCE_P27_INTAKE_CONTENT_HASH_MISMATCH")
    return waiting, blocked


def _validate_named_bool_map(payload: Mapping[str, Any], field_name: str, required: set[str], prefix: str) -> list[str]:
    blocked: list[str] = []
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        return [f"{prefix}_{field_name.upper()}_MISSING"]
    for field in sorted(required):
        if value.get(field) is not True:
            blocked.append(f"{prefix}_{field_name.upper()}_MISSING_{field.upper()}")
    return blocked


def _validate_controls(
    controls: Mapping[str, Any],
    *,
    p27_report_hash: Any,
    p27_intake_hash: Any,
) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not controls:
        waiting.append("P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_CONTROLS_MISSING")
        return waiting, blocked
    if controls.get("request_type") != "final_operator_runtime_activation_gate_review_controls_review_only":
        blocked.append("P28_CONTROLS_REQUEST_TYPE_INVALID")
    if not str(controls.get("operator_id") or "").strip() or str(controls.get("operator_id")).endswith("REQUIRED"):
        waiting.append("P28_OPERATOR_ID_MISSING")
    if not str(controls.get("ticket_or_signature") or "").strip() or str(controls.get("ticket_or_signature")).endswith("REQUIRED"):
        waiting.append("P28_TICKET_OR_SIGNATURE_MISSING")
    if controls.get("exact_final_operator_runtime_activation_gate_review_phrase") != P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_EXACT_PHRASE:
        blocked.append("P28_CONTROLS_EXACT_PHRASE_INVALID")
    if controls.get("source_p27_operator_runtime_activation_request_intake_validator_report_sha256") != p27_report_hash:
        blocked.append("P28_CONTROLS_P27_VALIDATOR_REPORT_HASH_MISMATCH")
    if controls.get("source_p27_operator_runtime_activation_request_intake_sha256") != p27_intake_hash:
        blocked.append("P28_CONTROLS_P27_INTAKE_HASH_MISMATCH")
    if controls.get("auto_generated_final_activation_review") is not False:
        blocked.append("P28_CONTROLS_AUTO_GENERATED_FINAL_REVIEW_BLOCKED")
    if controls.get("review_packet_is_runtime_authority") is not False:
        blocked.append("P28_CONTROLS_RUNTIME_AUTHORITY_CLAIMED")
    if controls.get("activation_gate_executes_runtime") is not False:
        blocked.append("P28_CONTROLS_EXECUTES_RUNTIME_BLOCKED")
    if controls.get("request_executes_runtime") is not False:
        blocked.append("P28_CONTROLS_REQUEST_EXECUTES_RUNTIME_BLOCKED")
    for ack in sorted(_REQUIRED_TOP_LEVEL_ACKS):
        if controls.get(ack) is not True:
            blocked.append(f"P28_REQUIRED_ACK_MISSING_{ack.upper()}")
    blocked.extend(_validate_named_bool_map(controls, "fresh_validation_controls", _REQUIRED_FRESH_VALIDATION_CONTROLS, "P28"))
    blocked.extend(_validate_named_bool_map(controls, "kill_switch_controls", _REQUIRED_KILL_SWITCH_CONTROLS, "P28"))
    blocked.extend(_validate_named_bool_map(controls, "cap_controls", _REQUIRED_CAP_CONTROLS, "P28"))
    blocked.extend(_validate_named_bool_map(controls, "runtime_loop_controls", _REQUIRED_RUNTIME_LOOP_CONTROLS, "P28"))
    return waiting, blocked


def build_final_operator_runtime_activation_gate_review_report(
    *,
    root: Path,
    p27_summary: Mapping[str, Any] | None = None,
    p27_report: Mapping[str, Any] | None = None,
    p27_intake: Mapping[str, Any] | None = None,
    p28_controls: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    del root
    p27_summary = dict(p27_summary or {})
    p27_report = dict(p27_report or {})
    p27_intake = dict(p27_intake or {})
    p28_controls = dict(p28_controls or {})

    p27_report_hash = p27_summary.get("p27_operator_runtime_activation_request_intake_validator_sha256") or p27_report.get("p27_operator_runtime_activation_request_intake_validator_sha256")
    p27_intake_hash = p27_summary.get("p27_operator_runtime_activation_request_intake_sha256") or p27_report.get("p27_operator_runtime_activation_request_intake_sha256")
    controls_template = build_final_operator_runtime_activation_gate_review_controls_template(
        p27_validator_report_sha256=str(p27_report_hash) if p27_report_hash else None,
        p27_intake_sha256=str(p27_intake_hash) if p27_intake_hash else None,
    )

    named_payloads: list[tuple[str, Mapping[str, Any]]] = [
        ("p27_summary", p27_summary),
        ("p27_report", p27_report),
        ("p27_operator_runtime_activation_request_intake", p27_intake),
        ("p28_final_operator_runtime_activation_gate_review_controls", p28_controls),
        ("p28_final_operator_runtime_activation_gate_review_controls_template", controls_template),
    ]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)
    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P28})
    truthy_disabled = truthy_execution_flags(disabled_state)

    waiting_reasons, block_reasons = _validate_p27_source(p27_summary, p27_report, p27_intake)
    controls_waiting, controls_blocked = _validate_controls(
        p28_controls,
        p27_report_hash=p27_report_hash,
        p27_intake_hash=p27_intake_hash,
    )
    waiting_reasons.extend(controls_waiting)
    block_reasons.extend(controls_blocked)
    if unsafe_hits:
        block_reasons.append("P28_UNSAFE_TRUTHY_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P28_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P28_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    valid = not blocked and not waiting_reasons
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else (STATUS_VALID_REVIEW_ONLY if valid else STATUS_WAITING_REVIEW_ONLY)
    controls_hash = sha256_json(p28_controls) if p28_controls else None
    final_gate_review_packet = {
        "packet_type": "p28_final_operator_runtime_activation_gate_review_packet_review_only",
        "status": status,
        "valid_review_only": valid,
        "source_p27_operator_runtime_activation_request_intake_validator_report_sha256": p27_report_hash,
        "source_p27_operator_runtime_activation_request_intake_sha256": p27_intake_hash,
        "p28_final_operator_runtime_activation_gate_review_controls_sha256": controls_hash,
        "runtime_authority": False,
        "runtime_activation_performed": False,
        "scheduler_enabled": False,
        "order_submission_allowed": False,
        "secret_value_accessed": False,
        "endpoint_called": False,
    }
    final_gate_review_packet["p28_final_operator_runtime_activation_gate_review_packet_sha256"] = sha256_json(final_gate_review_packet)

    report: dict[str, Any] = {
        "p28_final_operator_runtime_activation_gate_review_version": P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": valid,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p27_operator_runtime_activation_request_intake_validator_report_sha256": p27_report_hash,
        "source_p27_operator_runtime_activation_request_intake_sha256": p27_intake_hash,
        "p28_final_operator_runtime_activation_gate_review_controls_sha256": controls_hash,
        "p28_final_operator_runtime_activation_gate_review_controls_template": controls_template,
        "p28_final_operator_runtime_activation_gate_review_packet": final_gate_review_packet,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "p28_final_operator_runtime_activation_gate_review_valid_review_only": valid,
        "final_operator_runtime_activation_gate_ready_review_only": valid,
        "final_operator_runtime_activation_gate_review_is_runtime_authority": False,
        "separate_operator_runtime_activation_execution_required_after_this_review": True,
        "fresh_validation_required_before_runtime_activation": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "runtime_enablement_performed": False,
        "operator_runtime_activation_performed": False,
        "final_activation_gate_performed": False,
        "final_activation_gate_review_performed": False,
        "actual_live_order_submitted": False,
        "actual_testnet_order_submitted": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    report["p28_final_operator_runtime_activation_gate_review_id"] = stable_id("p28_final_operator_runtime_activation_gate_review", report, 24)
    report["p28_final_operator_runtime_activation_gate_review_sha256"] = sha256_json(report)
    return report


def _valid_p27_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    report_hash = "a" * 64
    intake_hash = "b" * 64
    p27_intake = {
        "request_type": "operator_runtime_activation_request_intake_review_only",
        "operator_id": "operator-thomas",
        "ticket_or_signature": "TICKET-P27-VALID-001",
        "manual_operator_submission": True,
        "intake_is_runtime_authority": False,
        "request_executes_runtime": False,
        "activation_request_executes_runtime": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    intake_hash = sha256_json(p27_intake)
    p27_summary = {
        "status": "P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_VALID_REVIEW_ONLY",
        "p27_operator_runtime_activation_request_intake_validator_sha256": report_hash,
        "p27_operator_runtime_activation_request_intake_sha256": intake_hash,
        "p27_operator_runtime_activation_request_intake_valid_review_only": True,
        "operator_runtime_activation_request_validated_review_only": True,
        "operator_runtime_activation_request_is_runtime_authority": False,
        "separate_final_operator_runtime_activation_gate_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p27_report = {
        "status": "P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_VALID_REVIEW_ONLY",
        "p27_operator_runtime_activation_request_intake_validator_sha256": report_hash,
        "p27_operator_runtime_activation_request_intake_sha256": intake_hash,
        "p27_operator_runtime_activation_request_intake_valid_review_only": True,
        "operator_runtime_activation_request_validated_review_only": True,
        "operator_runtime_activation_request_is_runtime_authority": False,
        "separate_final_operator_runtime_activation_gate_required": True,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    controls = build_final_operator_runtime_activation_gate_review_controls_template(
        p27_validator_report_sha256=report_hash,
        p27_intake_sha256=intake_hash,
    )
    controls.update({"operator_id": "operator-thomas", "ticket_or_signature": "TICKET-P28-VALID-001", "reviewed_at_utc": "2026-07-08T00:00:00Z"})
    return p27_summary, p27_report, p27_intake, controls


def build_p28_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    p27_summary, p27_report, p27_intake, controls = _valid_p27_fixture()
    base = {"p27_summary": p27_summary, "p27_report": p27_report, "p27_intake": p27_intake, "p28_controls": controls}
    cases = {
        "p27_not_valid": {**base, "p27_summary": {**p27_summary, "p27_operator_runtime_activation_request_intake_valid_review_only": False}},
        "missing_controls": {**base, "p28_controls": {}},
        "missing_exact_phrase": {**base, "p28_controls": {**controls, "exact_final_operator_runtime_activation_gate_review_phrase": "WRONG"}},
        "p27_report_hash_mismatch": {**base, "p28_controls": {**controls, "source_p27_operator_runtime_activation_request_intake_validator_report_sha256": "c" * 64}},
        "p27_intake_hash_mismatch": {**base, "p28_controls": {**controls, "source_p27_operator_runtime_activation_request_intake_sha256": "d" * 64}},
        "runtime_authority_claimed": {**base, "p28_controls": {**controls, "review_packet_is_runtime_authority": True}},
        "request_executes_runtime": {**base, "p28_controls": {**controls, "request_executes_runtime": True}},
        "fresh_validation_missing": {**base, "p28_controls": {**controls, "fresh_validation_controls": {**controls["fresh_validation_controls"], "fresh_market_data_before_activation": False}}},
        "kill_switch_missing": {**base, "p28_controls": {**controls, "kill_switch_controls": {**controls["kill_switch_controls"], "operator_manual_kill_switch_checked": False}}},
        "cap_missing": {**base, "p28_controls": {**controls, "cap_controls": {**controls["cap_controls"], "max_leverage_checked": False}}},
        "scheduler_dry_run_missing": {**base, "p28_controls": {**controls, "runtime_loop_controls": {**controls["runtime_loop_controls"], "scheduler_dry_run_completed": False}}},
        "scheduler_enabled": {**base, "p28_controls": {**controls, "runtime_scheduler_enabled": True}},
        "endpoint_called": {**base, "p28_controls": {**controls, "order_endpoint_called": True}},
        "secret_pattern_found": {**base, "p28_controls": {**controls, "operator_note": "BINANCE_API_SECRET=leaked"}},
        "runtime_mutation_requested": {**base, "p28_controls": {**controls, "runtime_settings_mutated": True}},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_final_operator_runtime_activation_gate_review_report(root=root, **kwargs)
        blocked_or_waiting = report["blocked"] or report["waiting"]
        results[name] = {
            "blocked_or_waiting": blocked_or_waiting,
            "blocked": report["blocked"],
            "waiting": report["waiting"],
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
            "order_endpoint_called": report["order_endpoint_called"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    return {
        "p28_final_operator_runtime_activation_gate_review_version": P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_VERSION,
        "status": "P28_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_final_operator_runtime_activation_gate_review(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p28_final_operator_runtime_activation_gate_review")
    p27_summary = _read_latest_json(cfg, _P27_SUMMARY_FILENAME)
    p27_report = _read_latest_json(cfg, _P27_REPORT_FILENAME)
    p27_intake = _read_latest_json(cfg, _P27_INTAKE_FILENAME)
    p28_controls = _read_latest_json(cfg, _P28_CONTROLS_FILENAME)
    report = build_final_operator_runtime_activation_gate_review_report(
        root=cfg.root,
        p27_summary=p27_summary,
        p27_report=p27_report,
        p27_intake=p27_intake,
        p28_controls=p28_controls,
    )
    negative_results = build_p28_negative_fixture_results(root=cfg.root)
    atomic_write_json(latest / "p28_final_operator_runtime_activation_gate_review_report.json", report)
    atomic_write_json(storage / "p28_final_operator_runtime_activation_gate_review_report.json", report)
    atomic_write_json(latest / "p28_final_operator_runtime_activation_gate_review_controls_TEMPLATE.json", report["p28_final_operator_runtime_activation_gate_review_controls_template"])
    atomic_write_json(latest / "p28_final_operator_runtime_activation_gate_review_packet.json", report["p28_final_operator_runtime_activation_gate_review_packet"])
    atomic_write_json(latest / "p28_final_operator_runtime_activation_gate_review_negative_fixture_results.json", negative_results)
    summary = {
        "status": report["status"],
        "p28_final_operator_runtime_activation_gate_review_sha256": report["p28_final_operator_runtime_activation_gate_review_sha256"],
        "p28_final_operator_runtime_activation_gate_review_valid_review_only": report["p28_final_operator_runtime_activation_gate_review_valid_review_only"],
        "final_operator_runtime_activation_gate_ready_review_only": report["final_operator_runtime_activation_gate_ready_review_only"],
        "final_operator_runtime_activation_gate_review_is_runtime_authority": False,
        "separate_operator_runtime_activation_execution_required_after_this_review": True,
        "fresh_validation_required_before_runtime_activation": True,
        "source_p27_operator_runtime_activation_request_intake_validator_report_sha256": report["source_p27_operator_runtime_activation_request_intake_validator_report_sha256"],
        "source_p27_operator_runtime_activation_request_intake_sha256": report["source_p27_operator_runtime_activation_request_intake_sha256"],
        "p28_final_operator_runtime_activation_gate_review_controls_sha256": report["p28_final_operator_runtime_activation_gate_review_controls_sha256"],
        "waiting_reasons": report["waiting_reasons"],
        "block_reasons": report["block_reasons"],
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "runtime_enablement_performed": False,
        "operator_runtime_activation_performed": False,
        "final_activation_gate_performed": False,
        "actual_live_order_submitted": False,
        "actual_testnet_order_submitted": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary["p28_final_operator_runtime_activation_gate_review_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p28_final_operator_runtime_activation_gate_review_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_REGISTRY_NAME),
        report,
        registry_name=P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_REGISTRY_NAME,
        id_field="p28_final_operator_runtime_activation_gate_review_registry_id",
        hash_field="p28_final_operator_runtime_activation_gate_review_registry_sha256",
        id_prefix="p28_final_operator_runtime_activation_gate_review",
    )
    atomic_write_json(latest / "p28_final_operator_runtime_activation_gate_review_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_final_operator_runtime_activation_gate_review()
    print(result["status"])
    print(result["p28_final_operator_runtime_activation_gate_review_sha256"])
