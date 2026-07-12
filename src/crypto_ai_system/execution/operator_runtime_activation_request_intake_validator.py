from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_runtime_activation_request_template_gate import P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_VERSION = "p27_operator_runtime_activation_request_intake_validator_v1"
P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_REGISTRY_NAME = "p27_operator_runtime_activation_request_intake_validator_registry"

STATUS_WAITING_REVIEW_ONLY = "P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY = "P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_VALID_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_BLOCKED_FAIL_CLOSED"

_P26_SUMMARY_FILENAME = "p26_operator_runtime_activation_request_template_gate_summary.json"
_P26_REPORT_FILENAME = "p26_operator_runtime_activation_request_template_gate_report.json"
_P26_TEMPLATE_FILENAME = "p26_operator_runtime_activation_request_TEMPLATE.json"
_P26_SKELETON_FILENAME = "p26_final_activation_gate_skeleton.json"
_P27_INTAKE_FILENAME = "p27_operator_runtime_activation_request_intake.json"

_EXECUTION_FIELDS_FOR_P27 = {
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
    "request_executes_runtime",
    "activation_request_executes_runtime",
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

_REQUIRED_ACKS = {
    "no_runtime_authority_acknowledged",
    "separate_final_activation_gate_required_acknowledged",
    "fresh_validation_required_acknowledged",
    "no_execution_flags_modified_acknowledged",
    "no_order_submission_allowed_acknowledged",
    "no_scheduler_enablement_allowed_acknowledged",
    "no_secret_values_inserted_acknowledged",
    "no_endpoint_call_allowed_by_this_intake_acknowledged",
    "caps_acknowledged",
    "kill_switch_acknowledged",
    "rollback_and_full_shutdown_acknowledged",
    "monitoring_alerting_acknowledged",
    "daily_report_acknowledged",
    "incident_report_acknowledged",
    "all_orders_must_reconcile_acknowledged",
    "idempotency_required_acknowledged",
    "post_submit_relock_required_acknowledged",
    "canonical_id_chain_required_acknowledged",
    "p26_gate_skeleton_reviewed_acknowledged",
}

_REQUIRED_CAP_FIELDS = {
    "symbol_scope_btcusdt_only",
    "fixed_max_notional_cap_acknowledged",
    "daily_loss_cap_acknowledged",
    "max_daily_order_count_acknowledged",
    "max_consecutive_loss_acknowledged",
    "max_open_position_count_acknowledged",
    "max_leverage_acknowledged",
    "max_slippage_acknowledged",
    "max_api_error_rate_acknowledged",
}

_REQUIRED_SKELETON_CONTROLS = {
    "load_current_stage_policy_before_every_tick",
    "fresh_market_data_before_every_tick",
    "source_qa_before_signal",
    "data_snapshot_and_feature_lineage_required",
    "research_signal_v2_required",
    "signal_qa_required",
    "trading_decision_required",
    "hot_path_preorder_risk_gate_required",
    "order_intent_after_risk_gate_only",
    "duplicate_submit_lock_required",
    "idempotency_key_required",
    "hard_caps_required",
    "post_submit_relock_required",
    "status_polling_required",
    "reconciliation_required",
    "outcome_feedback_required",
    "daily_report_required",
    "incident_report_required",
    "monitoring_alerting_required",
    "rollback_required",
    "full_shutdown_required",
    "all_kill_switches_required",
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
                if key in _EXECUTION_FIELDS_FOR_P27 and _bool(value):
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


def build_operator_runtime_activation_request_intake_template(
    *,
    p26_gate_report_sha256: str | None = None,
    p26_template_sha256: str | None = None,
    p26_skeleton_sha256: str | None = None,
) -> dict[str, Any]:
    template: dict[str, Any] = {
        "request_type": "operator_runtime_activation_request_intake_review_only",
        "stage": "operator_runtime_activation_request_intake_validation",
        "operator_id": "OPERATOR_ID_REQUIRED",
        "ticket_or_signature": "TICKET_OR_SIGNATURE_REQUIRED",
        "requested_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
        "exact_operator_runtime_activation_request_phrase": P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE,
        "source_p26_operator_runtime_activation_request_template_gate_report_sha256": p26_gate_report_sha256 or "P26_GATE_REPORT_SHA256_REQUIRED",
        "source_p26_operator_runtime_activation_request_template_sha256": p26_template_sha256 or "P26_ACTIVATION_REQUEST_TEMPLATE_SHA256_REQUIRED",
        "source_p26_final_activation_gate_skeleton_sha256": p26_skeleton_sha256 or "P26_FINAL_ACTIVATION_GATE_SKELETON_SHA256_REQUIRED",
        "manual_operator_submission": True,
        "auto_generated_runtime_activation_request": False,
        "intake_is_runtime_authority": False,
        "request_executes_runtime": False,
        "activation_request_executes_runtime": False,
        "no_runtime_authority_acknowledged": True,
        "separate_final_activation_gate_required_acknowledged": True,
        "fresh_validation_required_acknowledged": True,
        "no_execution_flags_modified_acknowledged": True,
        "no_order_submission_allowed_acknowledged": True,
        "no_scheduler_enablement_allowed_acknowledged": True,
        "no_secret_values_inserted_acknowledged": True,
        "no_endpoint_call_allowed_by_this_intake_acknowledged": True,
        "caps_acknowledged": True,
        "cap_acknowledgements": {field: True for field in sorted(_REQUIRED_CAP_FIELDS)},
        "kill_switch_acknowledged": True,
        "rollback_and_full_shutdown_acknowledged": True,
        "monitoring_alerting_acknowledged": True,
        "daily_report_acknowledged": True,
        "incident_report_acknowledged": True,
        "all_orders_must_reconcile_acknowledged": True,
        "idempotency_required_acknowledged": True,
        "post_submit_relock_required_acknowledged": True,
        "canonical_id_chain_required_acknowledged": True,
        "p26_gate_skeleton_reviewed_acknowledged": True,
        "skeleton_control_acknowledgements": {field: True for field in sorted(_REQUIRED_SKELETON_CONTROLS)},
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
    template["p27_operator_runtime_activation_request_intake_template_sha256"] = sha256_json(template)
    return template


def _validate_p26_source(
    p26_summary: Mapping[str, Any],
    p26_report: Mapping[str, Any],
    p26_template: Mapping[str, Any],
    p26_skeleton: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not p26_summary:
        waiting.append("P27_SOURCE_P26_SUMMARY_MISSING")
    if not p26_report:
        waiting.append("P27_SOURCE_P26_REPORT_MISSING")
    if not p26_template:
        waiting.append("P27_SOURCE_P26_TEMPLATE_MISSING")
    if not p26_skeleton:
        waiting.append("P27_SOURCE_P26_SKELETON_MISSING")
    if waiting:
        return waiting, blocked

    if p26_summary.get("status") == "P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_BLOCKED_FAIL_CLOSED":
        blocked.append("P27_SOURCE_P26_SUMMARY_BLOCKED")
    if p26_report.get("status") == "P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_BLOCKED_FAIL_CLOSED":
        blocked.append("P27_SOURCE_P26_REPORT_BLOCKED")
    if p26_summary.get("p26_operator_runtime_activation_request_template_generated_review_only") is not True:
        waiting.append("P27_SOURCE_P26_TEMPLATE_NOT_GENERATED")
    if p26_summary.get("p26_final_activation_gate_skeleton_generated_review_only") is not True:
        waiting.append("P27_SOURCE_P26_SKELETON_NOT_GENERATED")
    if p26_summary.get("p26_operator_runtime_activation_gate_ready_review_only") is not True:
        waiting.append("P27_SOURCE_P26_GATE_NOT_READY")
    if p26_report.get("p26_operator_runtime_activation_gate_ready_review_only") is not True:
        waiting.append("P27_SOURCE_P26_REPORT_GATE_NOT_READY")
    if p26_report.get("p26_operator_runtime_activation_request_template_generated_review_only") is not True:
        waiting.append("P27_SOURCE_P26_REPORT_TEMPLATE_NOT_GENERATED")
    if p26_report.get("p26_final_activation_gate_skeleton_generated_review_only") is not True:
        waiting.append("P27_SOURCE_P26_REPORT_SKELETON_NOT_GENERATED")

    report_hash_summary = p26_summary.get("p26_operator_runtime_activation_request_template_gate_report_sha256")
    report_hash_report = p26_report.get("p26_operator_runtime_activation_request_template_gate_report_sha256")
    if not _is_sha256(report_hash_summary):
        waiting.append("P27_SOURCE_P26_SUMMARY_REPORT_HASH_MISSING_OR_INVALID")
    if not _is_sha256(report_hash_report):
        waiting.append("P27_SOURCE_P26_REPORT_HASH_MISSING_OR_INVALID")
    if _is_sha256(report_hash_summary) and _is_sha256(report_hash_report) and report_hash_summary != report_hash_report:
        blocked.append("P27_SOURCE_P26_SUMMARY_REPORT_HASH_MISMATCH")

    template_hash = p26_template.get("p26_operator_runtime_activation_request_template_sha256")
    if not _is_sha256(template_hash):
        waiting.append("P27_SOURCE_P26_TEMPLATE_HASH_MISSING_OR_INVALID")
    skeleton_hash = p26_skeleton.get("p26_final_activation_gate_skeleton_sha256")
    if not _is_sha256(skeleton_hash):
        waiting.append("P27_SOURCE_P26_SKELETON_HASH_MISSING_OR_INVALID")

    if p26_template.get("exact_operator_runtime_activation_request_phrase") != P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE:
        blocked.append("P27_SOURCE_P26_TEMPLATE_EXACT_PHRASE_INVALID")
    if p26_template.get("request_is_runtime_authority") is not False:
        blocked.append("P27_SOURCE_P26_TEMPLATE_RUNTIME_AUTHORITY_CLAIMED")
    if p26_template.get("request_executes_runtime") is not False:
        blocked.append("P27_SOURCE_P26_TEMPLATE_EXECUTES_RUNTIME")
    if p26_skeleton.get("activation_gate_is_runtime_authority") is not False:
        blocked.append("P27_SOURCE_P26_SKELETON_RUNTIME_AUTHORITY_CLAIMED")
    if p26_skeleton.get("activation_gate_executes_runtime") is not False:
        blocked.append("P27_SOURCE_P26_SKELETON_EXECUTES_RUNTIME")
    if p26_skeleton.get("separate_filled_operator_activation_request_required") is not True:
        blocked.append("P27_SOURCE_P26_SKELETON_SEPARATE_REQUEST_NOT_REQUIRED")
    gate_controls = p26_skeleton.get("gate_controls")
    if not isinstance(gate_controls, Mapping):
        blocked.append("P27_SOURCE_P26_SKELETON_CONTROLS_MISSING")
    else:
        for control in sorted(_REQUIRED_SKELETON_CONTROLS):
            if gate_controls.get(control) is not True:
                blocked.append(f"P27_SOURCE_P26_SKELETON_CONTROL_MISSING_{control.upper()}")
    return waiting, blocked


def _validate_intake(
    intake: Mapping[str, Any],
    *,
    p26_report_hash: Any,
    p26_template_hash: Any,
    p26_skeleton_hash: Any,
) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not intake:
        waiting.append("P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_MISSING")
        return waiting, blocked
    if intake.get("request_type") != "operator_runtime_activation_request_intake_review_only":
        blocked.append("P27_INTAKE_REQUEST_TYPE_INVALID")
    if not str(intake.get("operator_id") or "").strip() or str(intake.get("operator_id")).endswith("REQUIRED"):
        waiting.append("P27_OPERATOR_ID_MISSING")
    if not str(intake.get("ticket_or_signature") or "").strip() or str(intake.get("ticket_or_signature")).endswith("REQUIRED"):
        waiting.append("P27_TICKET_OR_SIGNATURE_MISSING")
    if intake.get("exact_operator_runtime_activation_request_phrase") != P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE:
        blocked.append("P27_INTAKE_EXACT_OPERATOR_RUNTIME_ACTIVATION_REQUEST_PHRASE_INVALID")
    if intake.get("source_p26_operator_runtime_activation_request_template_gate_report_sha256") != p26_report_hash:
        blocked.append("P27_INTAKE_P26_GATE_REPORT_HASH_MISMATCH")
    if intake.get("source_p26_operator_runtime_activation_request_template_sha256") != p26_template_hash:
        blocked.append("P27_INTAKE_P26_TEMPLATE_HASH_MISMATCH")
    if intake.get("source_p26_final_activation_gate_skeleton_sha256") != p26_skeleton_hash:
        blocked.append("P27_INTAKE_P26_SKELETON_HASH_MISMATCH")
    if intake.get("manual_operator_submission") is not True:
        blocked.append("P27_INTAKE_MANUAL_OPERATOR_SUBMISSION_REQUIRED")
    if intake.get("auto_generated_runtime_activation_request") is not False:
        blocked.append("P27_INTAKE_AUTO_GENERATED_RUNTIME_ACTIVATION_REQUEST_BLOCKED")
    if intake.get("intake_is_runtime_authority") is not False:
        blocked.append("P27_INTAKE_RUNTIME_AUTHORITY_CLAIMED")
    if intake.get("request_executes_runtime") is not False:
        blocked.append("P27_INTAKE_EXECUTES_RUNTIME_BLOCKED")
    if intake.get("activation_request_executes_runtime") is not False:
        blocked.append("P27_INTAKE_ACTIVATION_REQUEST_EXECUTES_RUNTIME_BLOCKED")
    for ack in sorted(_REQUIRED_ACKS):
        if intake.get(ack) is not True:
            blocked.append(f"P27_REQUIRED_ACK_MISSING_{ack.upper()}")
    cap_ack = intake.get("cap_acknowledgements")
    if not isinstance(cap_ack, Mapping):
        blocked.append("P27_CAP_ACKNOWLEDGEMENTS_MISSING")
    else:
        for cap_field in sorted(_REQUIRED_CAP_FIELDS):
            if cap_ack.get(cap_field) is not True:
                blocked.append(f"P27_REQUIRED_CAP_ACK_MISSING_{cap_field.upper()}")
    skeleton_ack = intake.get("skeleton_control_acknowledgements")
    if not isinstance(skeleton_ack, Mapping):
        blocked.append("P27_SKELETON_CONTROL_ACKNOWLEDGEMENTS_MISSING")
    else:
        for control in sorted(_REQUIRED_SKELETON_CONTROLS):
            if skeleton_ack.get(control) is not True:
                blocked.append(f"P27_REQUIRED_SKELETON_CONTROL_ACK_MISSING_{control.upper()}")
    return waiting, blocked


def build_operator_runtime_activation_request_intake_validator_report(
    *,
    root: Path,
    p26_summary: Mapping[str, Any] | None = None,
    p26_report: Mapping[str, Any] | None = None,
    p26_template: Mapping[str, Any] | None = None,
    p26_skeleton: Mapping[str, Any] | None = None,
    p27_intake: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    del root
    p26_summary = dict(p26_summary or {})
    p26_report = dict(p26_report or {})
    p26_template = dict(p26_template or {})
    p26_skeleton = dict(p26_skeleton or {})
    p27_intake = dict(p27_intake or {})

    p26_report_hash = p26_summary.get("p26_operator_runtime_activation_request_template_gate_report_sha256") or p26_report.get("p26_operator_runtime_activation_request_template_gate_report_sha256")
    p26_template_hash = p26_template.get("p26_operator_runtime_activation_request_template_sha256")
    p26_skeleton_hash = p26_skeleton.get("p26_final_activation_gate_skeleton_sha256")
    intake_template = build_operator_runtime_activation_request_intake_template(
        p26_gate_report_sha256=str(p26_report_hash) if p26_report_hash else None,
        p26_template_sha256=str(p26_template_hash) if p26_template_hash else None,
        p26_skeleton_sha256=str(p26_skeleton_hash) if p26_skeleton_hash else None,
    )

    named_payloads: list[tuple[str, Mapping[str, Any]]] = [
        ("p26_summary", p26_summary),
        ("p26_report", p26_report),
        ("p26_operator_runtime_activation_request_template", p26_template),
        ("p26_final_activation_gate_skeleton", p26_skeleton),
        ("p27_operator_runtime_activation_request_intake", p27_intake),
        ("p27_operator_runtime_activation_request_intake_template", intake_template),
    ]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)
    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P27})
    truthy_disabled = truthy_execution_flags(disabled_state)

    waiting_reasons, block_reasons = _validate_p26_source(p26_summary, p26_report, p26_template, p26_skeleton)
    intake_waiting, intake_blocked = _validate_intake(
        p27_intake,
        p26_report_hash=p26_report_hash,
        p26_template_hash=p26_template_hash,
        p26_skeleton_hash=p26_skeleton_hash,
    )
    waiting_reasons.extend(intake_waiting)
    block_reasons.extend(intake_blocked)
    if unsafe_hits:
        block_reasons.append("P27_UNSAFE_TRUTHY_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P27_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P27_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    valid = not blocked and not waiting_reasons
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else (STATUS_VALID_REVIEW_ONLY if valid else STATUS_WAITING_REVIEW_ONLY)
    intake_sha = sha256_json(p27_intake) if p27_intake else None
    report: dict[str, Any] = {
        "p27_operator_runtime_activation_request_intake_validator_version": P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": valid,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p26_operator_runtime_activation_request_template_gate_report_sha256": p26_report_hash,
        "source_p26_operator_runtime_activation_request_template_sha256": p26_template_hash,
        "source_p26_final_activation_gate_skeleton_sha256": p26_skeleton_hash,
        "p27_operator_runtime_activation_request_intake_sha256": intake_sha,
        "operator_runtime_activation_request_intake_template": intake_template,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "p27_operator_runtime_activation_request_intake_valid_review_only": valid,
        "operator_runtime_activation_request_validated_review_only": valid,
        "operator_runtime_activation_request_is_runtime_authority": False,
        "separate_final_operator_runtime_activation_gate_required": True,
        "fresh_validation_required_before_activation": True,
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
    report["p27_operator_runtime_activation_request_intake_validator_id"] = stable_id("p27_operator_runtime_activation_request_intake_validator", report, 24)
    report["p27_operator_runtime_activation_request_intake_validator_sha256"] = sha256_json(report)
    return report


def _valid_p26_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    gate_hash = "a" * 64
    template_hash = "b" * 64
    skeleton_hash = "c" * 64
    p26_summary = {
        "status": "P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_GENERATED_REVIEW_ONLY",
        "p26_operator_runtime_activation_request_template_gate_report_sha256": gate_hash,
        "p26_operator_runtime_activation_request_template_generated_review_only": True,
        "p26_final_activation_gate_skeleton_generated_review_only": True,
        "p26_operator_runtime_activation_gate_ready_review_only": True,
        "activation_request_template_is_runtime_authority": False,
        "final_activation_gate_skeleton_is_runtime_authority": False,
        "separate_filled_operator_activation_request_required_after_this_template": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p26_report = {
        "status": "P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_GENERATED_REVIEW_ONLY",
        "p26_operator_runtime_activation_request_template_gate_report_sha256": gate_hash,
        "p26_operator_runtime_activation_request_template_generated_review_only": True,
        "p26_final_activation_gate_skeleton_generated_review_only": True,
        "p26_operator_runtime_activation_gate_ready_review_only": True,
        "activation_request_template_is_runtime_authority": False,
        "final_activation_gate_skeleton_is_runtime_authority": False,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p26_template = {
        "request_type": "operator_runtime_activation_request_template_review_only",
        "exact_operator_runtime_activation_request_phrase": P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE,
        "p26_operator_runtime_activation_request_template_sha256": template_hash,
        "request_is_runtime_authority": False,
        "request_executes_runtime": False,
        "activation_request_executes_runtime": False,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p26_skeleton = {
        "skeleton_type": "final_operator_runtime_activation_gate_skeleton_review_only",
        "p26_final_activation_gate_skeleton_sha256": skeleton_hash,
        "activation_gate_is_runtime_authority": False,
        "activation_gate_executes_runtime": False,
        "separate_filled_operator_activation_request_required": True,
        "gate_controls": {field: True for field in sorted(_REQUIRED_SKELETON_CONTROLS)},
        "runtime_activation_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    intake = build_operator_runtime_activation_request_intake_template(
        p26_gate_report_sha256=gate_hash,
        p26_template_sha256=template_hash,
        p26_skeleton_sha256=skeleton_hash,
    )
    intake.update({"operator_id": "operator-thomas", "ticket_or_signature": "TICKET-P27-VALID-001", "requested_at_utc": "2026-07-08T00:00:00Z"})
    return p26_summary, p26_report, p26_template, p26_skeleton, intake


def build_p27_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    p26_summary, p26_report, p26_template, p26_skeleton, intake = _valid_p26_fixture()
    base = {"p26_summary": p26_summary, "p26_report": p26_report, "p26_template": p26_template, "p26_skeleton": p26_skeleton, "p27_intake": intake}
    cases = {
        "p26_not_ready": {**base, "p26_summary": {**p26_summary, "p26_operator_runtime_activation_gate_ready_review_only": False}},
        "missing_intake": {**base, "p27_intake": {}},
        "missing_operator_identity": {**base, "p27_intake": {**intake, "operator_id": ""}},
        "missing_ticket_signature": {**base, "p27_intake": {**intake, "ticket_or_signature": ""}},
        "missing_exact_phrase": {**base, "p27_intake": {**intake, "exact_operator_runtime_activation_request_phrase": "WRONG"}},
        "p26_gate_hash_mismatch": {**base, "p27_intake": {**intake, "source_p26_operator_runtime_activation_request_template_gate_report_sha256": "d" * 64}},
        "p26_template_hash_mismatch": {**base, "p27_intake": {**intake, "source_p26_operator_runtime_activation_request_template_sha256": "e" * 64}},
        "p26_skeleton_hash_mismatch": {**base, "p27_intake": {**intake, "source_p26_final_activation_gate_skeleton_sha256": "f" * 64}},
        "auto_generated_activation_request": {**base, "p27_intake": {**intake, "auto_generated_runtime_activation_request": True}},
        "runtime_authority_claimed": {**base, "p27_intake": {**intake, "intake_is_runtime_authority": True}},
        "request_executes_runtime": {**base, "p27_intake": {**intake, "request_executes_runtime": True}},
        "missing_caps_acknowledgement": {**base, "p27_intake": {**intake, "caps_acknowledged": False}},
        "missing_kill_switch_acknowledgement": {**base, "p27_intake": {**intake, "kill_switch_acknowledged": False}},
        "cap_detail_missing": {**base, "p27_intake": {**intake, "cap_acknowledgements": {**intake["cap_acknowledgements"], "max_leverage_acknowledged": False}}},
        "skeleton_control_missing": {**base, "p27_intake": {**intake, "skeleton_control_acknowledgements": {**intake["skeleton_control_acknowledgements"], "hot_path_preorder_risk_gate_required": False}}},
        "scheduler_enablement_requested": {**base, "p27_intake": {**intake, "runtime_scheduler_enabled": True}},
        "order_submission_requested": {**base, "p27_intake": {**intake, "live_order_submission_allowed": True}},
        "endpoint_called": {**base, "p27_intake": {**intake, "order_endpoint_called": True}},
        "secret_pattern_found": {**base, "p27_intake": {**intake, "operator_note": "BINANCE_API_SECRET=leaked"}},
        "runtime_mutation_requested": {**base, "p27_intake": {**intake, "runtime_settings_mutated": True}},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_operator_runtime_activation_request_intake_validator_report(root=root, **kwargs)
        blocked_or_waiting = report["blocked"] or report["waiting"]
        results[name] = {
            "blocked_or_waiting": blocked_or_waiting,
            "blocked": report["blocked"],
            "waiting": report["waiting"],
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "live_order_submission_allowed": report["live_order_submission_allowed"],
            "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    return {
        "p27_operator_runtime_activation_request_intake_validator_version": P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_VERSION,
        "status": "P27_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_operator_runtime_activation_request_intake_validator(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p27_operator_runtime_activation_request_intake_validator")
    p26_summary = _read_latest_json(cfg, _P26_SUMMARY_FILENAME)
    p26_report = _read_latest_json(cfg, _P26_REPORT_FILENAME)
    p26_template = _read_latest_json(cfg, _P26_TEMPLATE_FILENAME)
    p26_skeleton = _read_latest_json(cfg, _P26_SKELETON_FILENAME)
    p27_intake = _read_latest_json(cfg, _P27_INTAKE_FILENAME)
    report = build_operator_runtime_activation_request_intake_validator_report(
        root=cfg.root,
        p26_summary=p26_summary,
        p26_report=p26_report,
        p26_template=p26_template,
        p26_skeleton=p26_skeleton,
        p27_intake=p27_intake,
    )
    negative_results = build_p27_negative_fixture_results(root=cfg.root)
    atomic_write_json(latest / "p27_operator_runtime_activation_request_intake_validator_report.json", report)
    atomic_write_json(storage / "p27_operator_runtime_activation_request_intake_validator_report.json", report)
    atomic_write_json(latest / "p27_operator_runtime_activation_request_intake_TEMPLATE.json", report["operator_runtime_activation_request_intake_template"])
    atomic_write_json(latest / "p27_operator_runtime_activation_request_intake_validator_negative_fixture_results.json", negative_results)
    summary = {
        "status": report["status"],
        "p27_operator_runtime_activation_request_intake_validator_sha256": report["p27_operator_runtime_activation_request_intake_validator_sha256"],
        "p27_operator_runtime_activation_request_intake_valid_review_only": report["p27_operator_runtime_activation_request_intake_valid_review_only"],
        "operator_runtime_activation_request_validated_review_only": report["operator_runtime_activation_request_validated_review_only"],
        "operator_runtime_activation_request_is_runtime_authority": False,
        "separate_final_operator_runtime_activation_gate_required": True,
        "fresh_validation_required_before_activation": True,
        "source_p26_operator_runtime_activation_request_template_gate_report_sha256": report["source_p26_operator_runtime_activation_request_template_gate_report_sha256"],
        "source_p26_operator_runtime_activation_request_template_sha256": report["source_p26_operator_runtime_activation_request_template_sha256"],
        "source_p26_final_activation_gate_skeleton_sha256": report["source_p26_final_activation_gate_skeleton_sha256"],
        "p27_operator_runtime_activation_request_intake_sha256": report["p27_operator_runtime_activation_request_intake_sha256"],
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
    summary["p27_operator_runtime_activation_request_intake_validator_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p27_operator_runtime_activation_request_intake_validator_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_REGISTRY_NAME),
        report,
        registry_name=P27_OPERATOR_RUNTIME_ACTIVATION_REQUEST_INTAKE_VALIDATOR_REGISTRY_NAME,
        id_field="p27_operator_runtime_activation_request_intake_validator_registry_id",
        hash_field="p27_operator_runtime_activation_request_intake_validator_registry_sha256",
        id_prefix="p27_operator_runtime_activation_request_intake_validator",
    )
    atomic_write_json(latest / "p27_operator_runtime_activation_request_intake_validator_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_operator_runtime_activation_request_intake_validator()
    print(result["status"])
    print(result["p27_operator_runtime_activation_request_intake_validator_sha256"])
