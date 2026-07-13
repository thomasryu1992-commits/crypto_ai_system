from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_VERSION = "p25_final_runtime_enablement_boundary_review_packet_v1"
P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_REGISTRY_NAME = "p25_final_runtime_enablement_boundary_review_packet_registry"

STATUS_WAITING_REVIEW_ONLY = "P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY = "P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_READY_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_BLOCKED_FAIL_CLOSED"

P25_FINAL_RUNTIME_REVIEW_EXACT_PHRASE = (
    "I REQUEST FINAL REVIEW OF THE LIMITED LIVE SCALED RUNTIME ENABLEMENT BOUNDARY "
    "AND ACKNOWLEDGE THIS PACKET DOES NOT ENABLE RUNTIME"
)

_P24_SUMMARY_FILENAME = "p24_runtime_enablement_request_intake_validator_summary.json"
_P24_REPORT_FILENAME = "p24_runtime_enablement_request_intake_validator_report.json"
_P24_TEMPLATE_FILENAME = "p24_runtime_enablement_request_intake_TEMPLATE.json"
_P24_INTAKE_FILENAME = "p24_runtime_enablement_request_intake.json"
_P25_CONTROLS_FILENAME = "p25_final_runtime_enablement_boundary_review_controls.json"

_EXECUTION_FIELDS_FOR_P25 = {
    "limited_live_scaled_auto_trading_allowed",
    "live_scaled_runtime_enablement_allowed",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "runtime_scheduler_enabled",
    "runtime_loop_started",
    "runtime_enablement_performed",
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
    "scheduler_start_requested",
    "order_submission_requested",
    "endpoint_call_allowed",
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

_REQUIRED_FRESH_VALIDATION = {
    "fresh_stage_policy_loaded",
    "fresh_market_data_required",
    "hard_required_price_source_required",
    "source_qa_required",
    "data_snapshot_required",
    "feature_lineage_required",
    "research_signal_v2_required",
    "signal_qa_required",
    "trading_decision_required",
    "hot_path_preorder_risk_gate_required",
    "hot_path_preorder_risk_gate_freshness_required",
    "clock_sync_required",
}

_REQUIRED_KILL_SWITCHES = {
    "config_global_kill_switch_required",
    "operator_manual_kill_switch_required",
    "daily_loss_kill_switch_required",
    "consecutive_loss_kill_switch_required",
    "api_error_kill_switch_required",
    "reconciliation_mismatch_kill_switch_required",
    "stale_data_kill_switch_required",
    "missing_hard_required_source_kill_switch_required",
    "duplicate_submit_lock_required",
}

_REQUIRED_RUNTIME_CONTROLS = {
    "scheduler_dry_run_review_required",
    "scheduler_must_remain_disabled_by_this_packet",
    "idempotency_required",
    "post_submit_relock_required",
    "status_polling_required",
    "reconciliation_required",
    "outcome_feedback_required",
    "daily_report_required",
    "incident_report_required",
    "monitoring_alerting_required",
    "rollback_required",
    "full_shutdown_required",
    "canonical_id_chain_required",
    "all_orders_must_reconcile",
    "no_secret_value_access_required",
    "no_endpoint_call_required_by_this_packet",
}

_REQUIRED_CAPS = {
    "symbol_scope_btcusdt_only",
    "fixed_max_notional_cap_present",
    "daily_loss_cap_present",
    "max_daily_order_count_present",
    "max_consecutive_loss_present",
    "max_open_position_count_present",
    "max_leverage_present",
    "max_slippage_present",
    "max_api_error_rate_present",
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
                if key in _EXECUTION_FIELDS_FOR_P25 and _bool(value):
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


def build_final_runtime_enablement_review_controls_template(
    *,
    p24_validator_sha256: str | None = None,
    p24_intake_sha256: str | None = None,
) -> dict[str, Any]:
    template: dict[str, Any] = {
        "request_type": "final_runtime_enablement_boundary_review_controls_review_only",
        "stage": "final_runtime_enablement_boundary_review_packet",
        "operator_id": "OPERATOR_ID_REQUIRED",
        "ticket_or_signature": "TICKET_OR_SIGNATURE_REQUIRED",
        "requested_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
        "exact_final_runtime_review_phrase": P25_FINAL_RUNTIME_REVIEW_EXACT_PHRASE,
        "source_p24_runtime_enablement_request_intake_validator_sha256": p24_validator_sha256 or "P24_VALIDATOR_SHA256_REQUIRED",
        "source_p24_runtime_enablement_request_intake_sha256": p24_intake_sha256 or "P24_INTAKE_SHA256_REQUIRED",
        "manual_operator_submission": True,
        "auto_generated_runtime_enablement": False,
        "packet_is_runtime_authority": False,
        "request_executes_runtime": False,
        "fresh_validation_checklist": {field: True for field in sorted(_REQUIRED_FRESH_VALIDATION)},
        "kill_switch_checklist": {field: True for field in sorted(_REQUIRED_KILL_SWITCHES)},
        "runtime_control_checklist": {field: True for field in sorted(_REQUIRED_RUNTIME_CONTROLS)},
        "cap_policy": {
            "symbol_scope_btcusdt_only": True,
            "fixed_max_notional_cap_present": True,
            "fixed_max_notional_usdt": 5.0,
            "daily_loss_cap_present": True,
            "daily_loss_cap_usdt": 5.0,
            "max_daily_order_count_present": True,
            "max_daily_order_count": 3,
            "max_consecutive_loss_present": True,
            "max_consecutive_loss_count": 2,
            "max_open_position_count_present": True,
            "max_open_position_count": 1,
            "max_leverage_present": True,
            "max_leverage": 1.0,
            "max_slippage_present": True,
            "max_slippage_bps": 25.0,
            "max_api_error_rate_present": True,
            "max_api_error_rate": 0.01,
        },
        "separate_operator_runtime_activation_required_after_this_packet": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "runtime_enablement_performed": False,
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
    template["p25_final_runtime_enablement_review_controls_template_sha256"] = sha256_json(template)
    return template


def _validate_p24_source(p24_summary: Mapping[str, Any], p24_report: Mapping[str, Any], p24_template: Mapping[str, Any], p24_intake: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not p24_summary:
        waiting.append("P25_SOURCE_P24_SUMMARY_MISSING")
    if not p24_report:
        waiting.append("P25_SOURCE_P24_REPORT_MISSING")
    if not p24_template:
        waiting.append("P25_SOURCE_P24_TEMPLATE_MISSING")
    if not p24_intake:
        waiting.append("P25_SOURCE_P24_INTAKE_MISSING")
    if p24_summary and p24_summary.get("status") == "P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_BLOCKED_FAIL_CLOSED":
        blocked.append("P25_SOURCE_P24_SUMMARY_BLOCKED")
    if p24_report and p24_report.get("status") == "P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_BLOCKED_FAIL_CLOSED":
        blocked.append("P25_SOURCE_P24_REPORT_BLOCKED")
    if p24_summary and p24_summary.get("p24_runtime_enablement_request_intake_valid_review_only") is not True:
        waiting.append("P25_SOURCE_P24_INTAKE_NOT_VALID")
    if p24_summary and p24_summary.get("runtime_enablement_request_validated_review_only") is not True:
        waiting.append("P25_SOURCE_P24_REQUEST_NOT_VALIDATED")
    if p24_report and p24_report.get("p24_runtime_enablement_request_intake_valid_review_only") is not True:
        waiting.append("P25_SOURCE_P24_REPORT_INTAKE_NOT_VALID")
    if p24_report and p24_report.get("runtime_enablement_request_validated_review_only") is not True:
        waiting.append("P25_SOURCE_P24_REPORT_REQUEST_NOT_VALIDATED")
    summary_hash = p24_summary.get("p24_runtime_enablement_request_intake_validator_sha256")
    report_hash = p24_report.get("p24_runtime_enablement_request_intake_validator_sha256")
    if p24_summary and not _is_sha256(summary_hash):
        waiting.append("P25_SOURCE_P24_SUMMARY_HASH_MISSING_OR_INVALID")
    if p24_report and not _is_sha256(report_hash):
        waiting.append("P25_SOURCE_P24_REPORT_HASH_MISSING_OR_INVALID")
    if _is_sha256(summary_hash) and _is_sha256(report_hash) and summary_hash != report_hash:
        blocked.append("P25_SOURCE_P24_SUMMARY_REPORT_HASH_MISMATCH")
    if p24_report and p24_report.get("runtime_enablement_request_is_runtime_authority") is not False:
        blocked.append("P25_SOURCE_P24_RUNTIME_AUTHORITY_CLAIMED")
    if p24_report and p24_report.get("separate_final_runtime_boundary_required") is not True:
        blocked.append("P25_SOURCE_P24_FINAL_BOUNDARY_NOT_REQUIRED")
    p24_template_hash = p24_template.get("p24_runtime_enablement_request_intake_template_sha256")
    if p24_template and not _is_sha256(p24_template_hash):
        waiting.append("P25_SOURCE_P24_TEMPLATE_HASH_MISSING_OR_INVALID")
    p24_intake_hash = p24_report.get("p24_runtime_enablement_request_intake_sha256") or p24_summary.get("p24_runtime_enablement_request_intake_sha256")
    if p24_intake and _is_sha256(p24_intake_hash):
        calculated = sha256_json(p24_intake)
        if calculated != p24_intake_hash:
            blocked.append("P25_SOURCE_P24_INTAKE_HASH_MISMATCH")
    if p24_intake and p24_intake.get("request_executes_runtime") is not False:
        blocked.append("P25_SOURCE_P24_INTAKE_EXECUTES_RUNTIME")
    return waiting, blocked


def _validate_controls(controls: Mapping[str, Any], *, p24_validator_hash: Any, p24_intake_hash: Any) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not controls:
        waiting.append("P25_FINAL_RUNTIME_REVIEW_CONTROLS_MISSING")
        return waiting, blocked
    if controls.get("request_type") != "final_runtime_enablement_boundary_review_controls_review_only":
        blocked.append("P25_CONTROLS_REQUEST_TYPE_INVALID")
    if not str(controls.get("operator_id") or "").strip() or str(controls.get("operator_id")).endswith("REQUIRED"):
        waiting.append("P25_OPERATOR_ID_MISSING")
    if not str(controls.get("ticket_or_signature") or "").strip() or str(controls.get("ticket_or_signature")).endswith("REQUIRED"):
        waiting.append("P25_TICKET_OR_SIGNATURE_MISSING")
    if controls.get("exact_final_runtime_review_phrase") != P25_FINAL_RUNTIME_REVIEW_EXACT_PHRASE:
        blocked.append("P25_CONTROLS_EXACT_FINAL_RUNTIME_REVIEW_PHRASE_INVALID")
    if controls.get("source_p24_runtime_enablement_request_intake_validator_sha256") != p24_validator_hash:
        blocked.append("P25_CONTROLS_P24_VALIDATOR_HASH_MISMATCH")
    if controls.get("source_p24_runtime_enablement_request_intake_sha256") != p24_intake_hash:
        blocked.append("P25_CONTROLS_P24_INTAKE_HASH_MISMATCH")
    if controls.get("manual_operator_submission") is not True:
        blocked.append("P25_CONTROLS_MANUAL_OPERATOR_SUBMISSION_REQUIRED")
    if controls.get("auto_generated_runtime_enablement") is not False:
        blocked.append("P25_CONTROLS_AUTO_GENERATED_RUNTIME_ENABLEMENT_BLOCKED")
    if controls.get("packet_is_runtime_authority") is not False:
        blocked.append("P25_CONTROLS_RUNTIME_AUTHORITY_CLAIMED")
    if controls.get("request_executes_runtime") is not False:
        blocked.append("P25_CONTROLS_EXECUTES_RUNTIME_BLOCKED")
    fresh = controls.get("fresh_validation_checklist")
    if not isinstance(fresh, Mapping):
        blocked.append("P25_FRESH_VALIDATION_CHECKLIST_MISSING")
    else:
        for field in sorted(_REQUIRED_FRESH_VALIDATION):
            if fresh.get(field) is not True:
                blocked.append(f"P25_REQUIRED_FRESH_VALIDATION_MISSING_{field.upper()}")
    kill = controls.get("kill_switch_checklist")
    if not isinstance(kill, Mapping):
        blocked.append("P25_KILL_SWITCH_CHECKLIST_MISSING")
    else:
        for field in sorted(_REQUIRED_KILL_SWITCHES):
            if kill.get(field) is not True:
                blocked.append(f"P25_REQUIRED_KILL_SWITCH_MISSING_{field.upper()}")
    runtime_controls = controls.get("runtime_control_checklist")
    if not isinstance(runtime_controls, Mapping):
        blocked.append("P25_RUNTIME_CONTROL_CHECKLIST_MISSING")
    else:
        for field in sorted(_REQUIRED_RUNTIME_CONTROLS):
            if runtime_controls.get(field) is not True:
                blocked.append(f"P25_REQUIRED_RUNTIME_CONTROL_MISSING_{field.upper()}")
    caps = controls.get("cap_policy")
    if not isinstance(caps, Mapping):
        blocked.append("P25_CAP_POLICY_MISSING")
    else:
        for field in sorted(_REQUIRED_CAPS):
            if caps.get(field) is not True:
                blocked.append(f"P25_REQUIRED_CAP_POLICY_MISSING_{field.upper()}")
        if float(caps.get("fixed_max_notional_usdt", 999999)) > 10:
            blocked.append("P25_FIXED_MAX_NOTIONAL_CAP_TOO_HIGH")
        if float(caps.get("daily_loss_cap_usdt", 999999)) > 10:
            blocked.append("P25_DAILY_LOSS_CAP_TOO_HIGH")
        if int(caps.get("max_daily_order_count", 999999)) > 5:
            blocked.append("P25_MAX_DAILY_ORDER_COUNT_TOO_HIGH")
        if float(caps.get("max_leverage", 999999)) > 1:
            blocked.append("P25_MAX_LEVERAGE_TOO_HIGH")
        if float(caps.get("max_slippage_bps", 999999)) > 50:
            blocked.append("P25_MAX_SLIPPAGE_TOO_HIGH")
        if float(caps.get("max_api_error_rate", 1)) > 0.02:
            blocked.append("P25_MAX_API_ERROR_RATE_TOO_HIGH")
    if controls.get("separate_operator_runtime_activation_required_after_this_packet") is not True:
        blocked.append("P25_SEPARATE_OPERATOR_RUNTIME_ACTIVATION_NOT_REQUIRED")
    return waiting, blocked


def build_final_runtime_enablement_boundary_review_packet_report(
    *,
    root: Path,
    p24_summary: Mapping[str, Any] | None = None,
    p24_report: Mapping[str, Any] | None = None,
    p24_template: Mapping[str, Any] | None = None,
    p24_intake: Mapping[str, Any] | None = None,
    p25_controls: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    del root
    p24_summary = dict(p24_summary or {})
    p24_report = dict(p24_report or {})
    p24_template = dict(p24_template or {})
    p24_intake = dict(p24_intake or {})
    p25_controls = dict(p25_controls or {})
    p24_validator_hash = p24_summary.get("p24_runtime_enablement_request_intake_validator_sha256") or p24_report.get("p24_runtime_enablement_request_intake_validator_sha256")
    p24_intake_hash = p24_summary.get("p24_runtime_enablement_request_intake_sha256") or p24_report.get("p24_runtime_enablement_request_intake_sha256")
    controls_template = build_final_runtime_enablement_review_controls_template(
        p24_validator_sha256=str(p24_validator_hash) if p24_validator_hash else None,
        p24_intake_sha256=str(p24_intake_hash) if p24_intake_hash else None,
    )
    named_payloads: list[tuple[str, Mapping[str, Any]]] = [
        ("p24_summary", p24_summary),
        ("p24_report", p24_report),
        ("p24_runtime_enablement_request_intake_template", p24_template),
        ("p24_runtime_enablement_request_intake", p24_intake),
        ("p25_final_runtime_enablement_review_controls", p25_controls),
        ("p25_final_runtime_enablement_review_controls_template", controls_template),
    ]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)
    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P25})
    truthy_disabled = truthy_execution_flags(disabled_state)

    waiting_reasons, block_reasons = _validate_p24_source(p24_summary, p24_report, p24_template, p24_intake)
    control_waiting, control_blocked = _validate_controls(p25_controls, p24_validator_hash=p24_validator_hash, p24_intake_hash=p24_intake_hash)
    waiting_reasons.extend(control_waiting)
    block_reasons.extend(control_blocked)
    if unsafe_hits:
        block_reasons.append("P25_UNSAFE_TRUTHY_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P25_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P25_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    valid = not blocked and not waiting_reasons
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else (STATUS_VALID_REVIEW_ONLY if valid else STATUS_WAITING_REVIEW_ONLY)
    controls_sha = sha256_json(p25_controls) if p25_controls else None
    final_review_packet = {
        "packet_type": "final_runtime_enablement_boundary_review_packet_review_only",
        "status": "ready_review_only" if valid else "waiting_or_blocked_review_only",
        "source_p24_runtime_enablement_request_intake_validator_sha256": p24_validator_hash,
        "source_p24_runtime_enablement_request_intake_sha256": p24_intake_hash,
        "source_p25_final_runtime_enablement_review_controls_sha256": controls_sha,
        "fresh_validation_required_before_any_runtime": True,
        "all_kill_switch_layers_required": True,
        "caps_required": True,
        "scheduler_dry_run_required": True,
        "no_secret_value_access_required": True,
        "no_endpoint_call_allowed_by_this_packet": True,
        "rollback_and_full_shutdown_required": True,
        "daily_report_required": True,
        "incident_report_required": True,
        "separate_operator_runtime_activation_required_after_this_packet": True,
        "packet_is_runtime_authority": False,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
    }
    final_review_packet["p25_final_runtime_enablement_boundary_review_packet_sha256"] = sha256_json(final_review_packet)
    report: dict[str, Any] = {
        "p25_final_runtime_enablement_boundary_review_packet_version": P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": valid,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p24_runtime_enablement_request_intake_validator_sha256": p24_validator_hash,
        "source_p24_runtime_enablement_request_intake_sha256": p24_intake_hash,
        "p25_final_runtime_enablement_review_controls_sha256": controls_sha,
        "final_runtime_enablement_review_controls_template": controls_template,
        "final_runtime_enablement_boundary_review_packet": final_review_packet,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "p25_final_runtime_enablement_boundary_review_packet_valid_review_only": valid,
        "p25_final_runtime_enablement_boundary_review_packet_ready_review_only": valid,
        "fresh_validation_requirements_bound_review_only": valid,
        "kill_switch_requirements_bound_review_only": valid,
        "caps_requirements_bound_review_only": valid,
        "scheduler_dry_run_requirements_bound_review_only": valid,
        "daily_incident_reporting_requirements_bound_review_only": valid,
        "final_review_packet_is_runtime_authority": False,
        "separate_operator_runtime_activation_required_after_this_packet": True,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "runtime_enablement_performed": False,
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
    report["p25_final_runtime_enablement_boundary_review_packet_id"] = stable_id("p25_final_runtime_enablement_boundary_review_packet", report, 25)
    report["p25_final_runtime_enablement_boundary_review_packet_report_sha256"] = sha256_json(report)
    return report


def _valid_p24_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    p24_hash = "a" * 64
    intake_hash = "b" * 64
    template_hash = "c" * 64
    p24_summary = {
        "status": "P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_VALID_REVIEW_ONLY",
        "p24_runtime_enablement_request_intake_validator_sha256": p24_hash,
        "p24_runtime_enablement_request_intake_sha256": intake_hash,
        "p24_runtime_enablement_request_intake_valid_review_only": True,
        "runtime_enablement_request_validated_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p24_report = {
        "status": "P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_VALID_REVIEW_ONLY",
        "p24_runtime_enablement_request_intake_validator_sha256": p24_hash,
        "p24_runtime_enablement_request_intake_sha256": intake_hash,
        "p24_runtime_enablement_request_intake_valid_review_only": True,
        "runtime_enablement_request_validated_review_only": True,
        "runtime_enablement_request_is_runtime_authority": False,
        "separate_final_runtime_boundary_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p24_template = {
        "request_type": "limited_live_scaled_runtime_enablement_request_intake_review_only",
        "p24_runtime_enablement_request_intake_template_sha256": template_hash,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p24_intake = {
        "request_type": "limited_live_scaled_runtime_enablement_request_intake_review_only",
        "operator_id": "operator-thomas",
        "ticket_or_signature": "TICKET-P24-VALID-001",
        "request_executes_runtime": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    # Align fixture hash with actual intake payload so hash-chain tests can pass.
    intake_hash = sha256_json(p24_intake)
    p24_summary["p24_runtime_enablement_request_intake_sha256"] = intake_hash
    p24_report["p24_runtime_enablement_request_intake_sha256"] = intake_hash
    controls = build_final_runtime_enablement_review_controls_template(p24_validator_sha256=p24_hash, p24_intake_sha256=intake_hash)
    controls.update({"operator_id": "operator-thomas", "ticket_or_signature": "TICKET-P25-VALID-001", "requested_at_utc": "2026-07-08T00:00:00Z"})
    return p24_summary, p24_report, p24_template, p24_intake, controls


def build_p25_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    p24_summary, p24_report, p24_template, p24_intake, controls = _valid_p24_fixture()
    base = {"p24_summary": p24_summary, "p24_report": p24_report, "p24_template": p24_template, "p24_intake": p24_intake, "p25_controls": controls}
    cases = {
        "p24_not_valid": {**base, "p24_summary": {**p24_summary, "p24_runtime_enablement_request_intake_valid_review_only": False}},
        "missing_controls": {**base, "p25_controls": {}},
        "missing_exact_phrase": {**base, "p25_controls": {**controls, "exact_final_runtime_review_phrase": "WRONG"}},
        "p24_validator_hash_mismatch": {**base, "p25_controls": {**controls, "source_p24_runtime_enablement_request_intake_validator_sha256": "d" * 64}},
        "fresh_validation_missing": {**base, "p25_controls": {**controls, "fresh_validation_checklist": {**controls["fresh_validation_checklist"], "signal_qa_required": False}}},
        "kill_switch_missing": {**base, "p25_controls": {**controls, "kill_switch_checklist": {**controls["kill_switch_checklist"], "operator_manual_kill_switch_required": False}}},
        "cap_too_high": {**base, "p25_controls": {**controls, "cap_policy": {**controls["cap_policy"], "fixed_max_notional_usdt": 1000.0}}},
        "scheduler_dry_run_missing": {**base, "p25_controls": {**controls, "runtime_control_checklist": {**controls["runtime_control_checklist"], "scheduler_dry_run_review_required": False}}},
        "scheduler_enabled": {**base, "p25_controls": {**controls, "runtime_scheduler_enabled": True}},
        "endpoint_called": {**base, "p25_controls": {**controls, "order_endpoint_called": True}},
        "secret_pattern_found": {**base, "p25_controls": {**controls, "operator_note": "BINANCE_API_SECRET=leaked"}},
        "rollback_missing": {**base, "p25_controls": {**controls, "runtime_control_checklist": {**controls["runtime_control_checklist"], "rollback_required": False}}},
        "daily_report_missing": {**base, "p25_controls": {**controls, "runtime_control_checklist": {**controls["runtime_control_checklist"], "daily_report_required": False}}},
        "runtime_authority_claimed": {**base, "p25_controls": {**controls, "packet_is_runtime_authority": True}},
        "runtime_mutation_requested": {**base, "p25_controls": {**controls, "runtime_settings_mutated": True}},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_final_runtime_enablement_boundary_review_packet_report(root=root, **kwargs)
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
        "p25_final_runtime_enablement_boundary_review_packet_version": P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_VERSION,
        "status": "P25_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_final_runtime_enablement_boundary_review_packet(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p25_final_runtime_enablement_boundary_review_packet")
    p24_summary = _read_latest_json(cfg, _P24_SUMMARY_FILENAME)
    p24_report = _read_latest_json(cfg, _P24_REPORT_FILENAME)
    p24_template = _read_latest_json(cfg, _P24_TEMPLATE_FILENAME)
    p24_intake = _read_latest_json(cfg, _P24_INTAKE_FILENAME)
    p25_controls = _read_latest_json(cfg, _P25_CONTROLS_FILENAME)
    report = build_final_runtime_enablement_boundary_review_packet_report(
        root=cfg.root,
        p24_summary=p24_summary,
        p24_report=p24_report,
        p24_template=p24_template,
        p24_intake=p24_intake,
        p25_controls=p25_controls,
    )
    negative_results = build_p25_negative_fixture_results(root=cfg.root)
    atomic_write_json(latest / "p25_final_runtime_enablement_boundary_review_packet_report.json", report)
    atomic_write_json(storage / "p25_final_runtime_enablement_boundary_review_packet_report.json", report)
    atomic_write_json(latest / "p25_final_runtime_enablement_boundary_review_controls_TEMPLATE.json", report["final_runtime_enablement_review_controls_template"])
    atomic_write_json(latest / "p25_final_runtime_enablement_boundary_review_packet.json", report["final_runtime_enablement_boundary_review_packet"])
    atomic_write_json(latest / "p25_final_runtime_enablement_boundary_review_packet_negative_fixture_results.json", negative_results)
    summary = {
        "status": report["status"],
        "p25_final_runtime_enablement_boundary_review_packet_report_sha256": report["p25_final_runtime_enablement_boundary_review_packet_report_sha256"],
        "p25_final_runtime_enablement_boundary_review_packet_valid_review_only": report["p25_final_runtime_enablement_boundary_review_packet_valid_review_only"],
        "p25_final_runtime_enablement_boundary_review_packet_ready_review_only": report["p25_final_runtime_enablement_boundary_review_packet_ready_review_only"],
        "fresh_validation_requirements_bound_review_only": report["fresh_validation_requirements_bound_review_only"],
        "kill_switch_requirements_bound_review_only": report["kill_switch_requirements_bound_review_only"],
        "caps_requirements_bound_review_only": report["caps_requirements_bound_review_only"],
        "scheduler_dry_run_requirements_bound_review_only": report["scheduler_dry_run_requirements_bound_review_only"],
        "daily_incident_reporting_requirements_bound_review_only": report["daily_incident_reporting_requirements_bound_review_only"],
        "final_review_packet_is_runtime_authority": False,
        "separate_operator_runtime_activation_required_after_this_packet": True,
        "source_p24_runtime_enablement_request_intake_validator_sha256": report["source_p24_runtime_enablement_request_intake_validator_sha256"],
        "p25_final_runtime_enablement_review_controls_sha256": report["p25_final_runtime_enablement_review_controls_sha256"],
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
        "actual_live_order_submitted": False,
        "actual_testnet_order_submitted": False,
        "live_order_endpoint_called": False,
        "order_endpoint_called": False,
        "secret_value_accessed": False,
    }
    summary["p25_final_runtime_enablement_boundary_review_packet_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p25_final_runtime_enablement_boundary_review_packet_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_REGISTRY_NAME),
        report,
        registry_name=P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_REGISTRY_NAME,
        id_field="p25_final_runtime_enablement_boundary_review_packet_registry_id",
        hash_field="p25_final_runtime_enablement_boundary_review_packet_registry_sha256",
        id_prefix="p25_final_runtime_enablement_boundary_review_packet",
    )
    atomic_write_json(latest / "p25_final_runtime_enablement_boundary_review_packet_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_final_runtime_enablement_boundary_review_packet()
    print(result["status"])
    print(result["p25_final_runtime_enablement_boundary_review_packet_report_sha256"])
