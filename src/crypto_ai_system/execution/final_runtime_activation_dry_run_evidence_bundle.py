from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_BUNDLE_VERSION = "p29_final_runtime_activation_dry_run_evidence_bundle_v1"
P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_BUNDLE_REGISTRY_NAME = "p29_final_runtime_activation_dry_run_evidence_bundle_registry"

P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_EXACT_PHRASE = (
    "I REQUEST FINAL RUNTIME ACTIVATION DRY-RUN EVIDENCE REVIEW AND ACKNOWLEDGE THIS BUNDLE DOES NOT ENABLE RUNTIME"
)

STATUS_WAITING_REVIEW_ONLY = "P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_BUNDLE_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY = "P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_BUNDLE_VALID_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_BUNDLE_BLOCKED_FAIL_CLOSED"

_P28_SUMMARY_FILENAME = "p28_final_operator_runtime_activation_gate_review_summary.json"
_P28_REPORT_FILENAME = "p28_final_operator_runtime_activation_gate_review_report.json"
_P28_PACKET_FILENAME = "p28_final_operator_runtime_activation_gate_review_packet.json"
_P29_DRY_RUN_EVIDENCE_FILENAME = "p29_final_runtime_activation_dry_run_evidence.json"

_EXECUTION_FIELDS_FOR_P29 = {
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
    "final_runtime_activation_dry_run_performed",
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
    "bundle_is_runtime_authority",
    "bundle_executes_runtime",
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
    "activation_still_requires_separate_execution_step_acknowledged",
    "no_execution_flags_modified_acknowledged",
    "no_order_submission_acknowledged",
    "no_scheduler_enablement_acknowledged",
    "no_secret_values_acknowledged",
    "no_endpoint_call_acknowledged",
    "fresh_validation_acknowledged",
    "kill_switch_acknowledged",
    "caps_acknowledged",
    "rollback_and_full_shutdown_acknowledged",
    "monitoring_alerting_acknowledged",
    "daily_report_acknowledged",
    "incident_report_acknowledged",
    "all_orders_must_reconcile_acknowledged",
    "idempotency_required_acknowledged",
    "post_submit_relock_required_acknowledged",
    "canonical_id_chain_required_acknowledged",
}

_REQUIRED_TICK_FIELDS_TRUE = {
    "current_stage_policy_loaded",
    "fresh_market_data_loaded",
    "source_qa_passed",
    "data_snapshot_created",
    "feature_lineage_created",
    "research_signal_v2_created",
    "signal_qa_passed",
    "trading_decision_created",
    "hot_path_preorder_risk_gate_refreshed",
    "hot_path_preorder_risk_gate_passed",
    "hot_path_preorder_risk_gate_fresh",
    "order_intent_after_risk_gate_only",
    "hard_caps_checked",
    "hard_caps_passed",
    "duplicate_submit_lock_engaged",
    "idempotency_key_created",
    "idempotency_key_unique",
    "would_submit_evidence_created",
    "would_submit_only",
    "runtime_activation_dry_run_only",
    "post_submit_relock_required",
    "post_submit_relock_confirmed_review_only",
    "status_polling_required",
    "reconciliation_required",
    "outcome_feedback_required",
    "daily_report_required",
    "incident_report_required",
    "monitoring_alerting_required",
    "rollback_available",
    "full_shutdown_available",
    "kill_switch_ready",
    "canonical_id_chain_present_review_only",
    "all_orders_must_reconcile",
}

_REQUIRED_TICK_FIELDS_FALSE = {
    "live_order_submission_allowed",
    "runtime_scheduler_enabled",
    "runtime_loop_started",
    "order_endpoint_called",
    "live_order_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "secret_value_accessed",
    "secret_value_logged",
}

_REQUIRED_RISK_REFRESH_EVIDENCE = {
    "fresh_data_snapshot_confirmed",
    "source_qa_confirmed",
    "research_signal_v2_confirmed",
    "signal_qa_confirmed",
    "trading_decision_confirmed",
    "hot_path_preorder_risk_gate_fresh_confirmed",
    "hard_caps_confirmed",
}

_REQUIRED_IDEMPOTENCY_EVIDENCE = {
    "idempotency_keys_unique",
    "duplicate_submit_lock_confirmed",
    "duplicate_submit_rejected",
}

_REQUIRED_RECONCILIATION_EVIDENCE = {
    "reconciliation_required_for_every_would_submit",
    "status_polling_required_for_every_would_submit",
    "outcome_feedback_required_for_every_would_submit",
    "all_orders_must_reconcile",
}

_REQUIRED_KILL_SWITCH_EVIDENCE = {
    "global_kill_switch_ready",
    "operator_manual_kill_switch_ready",
    "daily_loss_kill_switch_ready",
    "consecutive_loss_kill_switch_ready",
    "api_error_kill_switch_ready",
    "reconciliation_mismatch_kill_switch_ready",
    "stale_data_kill_switch_ready",
    "hard_required_source_kill_switch_ready",
}

_REQUIRED_REPORTING_EVIDENCE = {
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
                if key in _EXECUTION_FIELDS_FOR_P29 and _bool(value):
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


def _bool_map(fields: set[str]) -> dict[str, bool]:
    return {field: True for field in sorted(fields)}


def _dry_run_tick(index: int) -> dict[str, Any]:
    tick = {field: True for field in sorted(_REQUIRED_TICK_FIELDS_TRUE)}
    tick.update({field: False for field in sorted(_REQUIRED_TICK_FIELDS_FALSE)})
    tick.update({
        "tick_index": index,
        "scheduler_tick_id": f"p29_tick_{index:02d}",
        "stage": "limited_live_scaled_dry_run_review_only",
        "symbol": "BTCUSDT",
        "idempotency_key": f"p29-dry-run-idempotency-{index:02d}",
        "would_submit_evidence_id": f"p29_would_submit_{index:02d}",
        "risk_gate_id": f"p29_hot_path_risk_gate_{index:02d}",
        "order_intent_id": f"p29_order_intent_review_only_{index:02d}",
        "reconciliation_id": f"p29_reconciliation_required_{index:02d}",
        "endpoint_called": False,
        "secret_value_accessed": False,
    })
    return tick


def build_final_runtime_activation_dry_run_evidence_template(
    *,
    p28_final_operator_runtime_activation_gate_review_report_sha256: str | None = None,
    p28_final_operator_runtime_activation_gate_review_packet_sha256: str | None = None,
) -> dict[str, Any]:
    template: dict[str, Any] = {
        "request_type": "final_runtime_activation_dry_run_evidence_bundle_review_only",
        "stage": "final_runtime_activation_dry_run_evidence_bundle",
        "operator_id": "OPERATOR_ID_REQUIRED",
        "ticket_or_signature": "TICKET_OR_SIGNATURE_REQUIRED",
        "reviewed_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
        "exact_final_runtime_activation_dry_run_evidence_phrase": P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_EXACT_PHRASE,
        "source_p28_final_operator_runtime_activation_gate_review_report_sha256": p28_final_operator_runtime_activation_gate_review_report_sha256 or "P28_REPORT_SHA256_REQUIRED",
        "source_p28_final_operator_runtime_activation_gate_review_packet_sha256": p28_final_operator_runtime_activation_gate_review_packet_sha256 or "P28_PACKET_SHA256_REQUIRED",
        "manual_operator_submission": True,
        "auto_generated_dry_run_evidence": False,
        "bundle_is_runtime_authority": False,
        "bundle_executes_runtime": False,
        "request_executes_runtime": False,
        "no_runtime_authority_acknowledged": True,
        "activation_still_requires_separate_execution_step_acknowledged": True,
        "no_execution_flags_modified_acknowledged": True,
        "no_order_submission_acknowledged": True,
        "no_scheduler_enablement_acknowledged": True,
        "no_secret_values_acknowledged": True,
        "no_endpoint_call_acknowledged": True,
        "fresh_validation_acknowledged": True,
        "kill_switch_acknowledged": True,
        "caps_acknowledged": True,
        "rollback_and_full_shutdown_acknowledged": True,
        "monitoring_alerting_acknowledged": True,
        "daily_report_acknowledged": True,
        "incident_report_acknowledged": True,
        "all_orders_must_reconcile_acknowledged": True,
        "idempotency_required_acknowledged": True,
        "post_submit_relock_required_acknowledged": True,
        "canonical_id_chain_required_acknowledged": True,
        "minimum_scheduler_dry_run_tick_count": 3,
        "scheduler_dry_run_ticks": [_dry_run_tick(1), _dry_run_tick(2), _dry_run_tick(3)],
        "risk_refresh_evidence": _bool_map(_REQUIRED_RISK_REFRESH_EVIDENCE),
        "idempotency_evidence": _bool_map(_REQUIRED_IDEMPOTENCY_EVIDENCE),
        "reconciliation_required_evidence": _bool_map(_REQUIRED_RECONCILIATION_EVIDENCE),
        "kill_switch_ready_evidence": _bool_map(_REQUIRED_KILL_SWITCH_EVIDENCE),
        "daily_incident_reporting_evidence": _bool_map(_REQUIRED_REPORTING_EVIDENCE),
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
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    template["p29_final_runtime_activation_dry_run_evidence_template_sha256"] = sha256_json(template)
    return template


def _validate_p28_source(p28_summary: Mapping[str, Any], p28_report: Mapping[str, Any], p28_packet: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not p28_summary:
        waiting.append("P29_SOURCE_P28_SUMMARY_MISSING")
    if not p28_report:
        waiting.append("P29_SOURCE_P28_REPORT_MISSING")
    if not p28_packet:
        waiting.append("P29_SOURCE_P28_PACKET_MISSING")
    if waiting:
        return waiting, blocked

    if p28_summary.get("status") == "P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_BLOCKED_FAIL_CLOSED":
        blocked.append("P29_SOURCE_P28_SUMMARY_BLOCKED")
    if p28_report.get("status") == "P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_BLOCKED_FAIL_CLOSED":
        blocked.append("P29_SOURCE_P28_REPORT_BLOCKED")
    if p28_summary.get("p28_final_operator_runtime_activation_gate_review_valid_review_only") is not True:
        waiting.append("P29_SOURCE_P28_FINAL_GATE_REVIEW_NOT_VALID")
    if p28_summary.get("final_operator_runtime_activation_gate_ready_review_only") is not True:
        waiting.append("P29_SOURCE_P28_FINAL_GATE_NOT_READY")
    if p28_report.get("p28_final_operator_runtime_activation_gate_review_valid_review_only") is not True:
        waiting.append("P29_SOURCE_P28_REPORT_FINAL_GATE_REVIEW_NOT_VALID")
    if p28_report.get("final_operator_runtime_activation_gate_ready_review_only") is not True:
        waiting.append("P29_SOURCE_P28_REPORT_FINAL_GATE_NOT_READY")
    if p28_report.get("final_operator_runtime_activation_gate_review_is_runtime_authority") is not False:
        blocked.append("P29_SOURCE_P28_RUNTIME_AUTHORITY_CLAIMED")
    if p28_report.get("separate_operator_runtime_activation_execution_required_after_this_review") is not True:
        blocked.append("P29_SOURCE_P28_SEPARATE_ACTIVATION_NOT_REQUIRED")
    if p28_packet.get("runtime_authority") is not False:
        blocked.append("P29_SOURCE_P28_PACKET_RUNTIME_AUTHORITY_CLAIMED")
    if p28_packet.get("runtime_activation_performed") is not False:
        blocked.append("P29_SOURCE_P28_PACKET_RUNTIME_ALREADY_ACTIVATED")

    report_hash_summary = p28_summary.get("p28_final_operator_runtime_activation_gate_review_sha256")
    report_hash_report = p28_report.get("p28_final_operator_runtime_activation_gate_review_sha256")
    if not _is_sha256(report_hash_summary):
        waiting.append("P29_SOURCE_P28_SUMMARY_REPORT_HASH_MISSING_OR_INVALID")
    if not _is_sha256(report_hash_report):
        waiting.append("P29_SOURCE_P28_REPORT_HASH_MISSING_OR_INVALID")
    if _is_sha256(report_hash_summary) and _is_sha256(report_hash_report) and report_hash_summary != report_hash_report:
        blocked.append("P29_SOURCE_P28_REPORT_HASH_MISMATCH")
    packet_hash = p28_packet.get("p28_final_operator_runtime_activation_gate_review_packet_sha256")
    if not _is_sha256(packet_hash):
        waiting.append("P29_SOURCE_P28_PACKET_HASH_MISSING_OR_INVALID")
    return waiting, blocked


def _validate_bool_map(payload: Mapping[str, Any], field_name: str, required: set[str], prefix: str) -> list[str]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        return [f"{prefix}_{field_name.upper()}_MISSING"]
    return [f"{prefix}_{field_name.upper()}_MISSING_{field.upper()}" for field in sorted(required) if value.get(field) is not True]


def _validate_dry_run_evidence(
    evidence: Mapping[str, Any],
    *,
    p28_report_hash: Any,
    p28_packet_hash: Any,
) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not evidence:
        waiting.append("P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_MISSING")
        return waiting, blocked
    if evidence.get("request_type") != "final_runtime_activation_dry_run_evidence_bundle_review_only":
        blocked.append("P29_DRY_RUN_EVIDENCE_REQUEST_TYPE_INVALID")
    if not str(evidence.get("operator_id") or "").strip() or str(evidence.get("operator_id")).endswith("REQUIRED"):
        waiting.append("P29_OPERATOR_ID_MISSING")
    if not str(evidence.get("ticket_or_signature") or "").strip() or str(evidence.get("ticket_or_signature")).endswith("REQUIRED"):
        waiting.append("P29_TICKET_OR_SIGNATURE_MISSING")
    if evidence.get("exact_final_runtime_activation_dry_run_evidence_phrase") != P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_EXACT_PHRASE:
        blocked.append("P29_DRY_RUN_EVIDENCE_EXACT_PHRASE_INVALID")
    if evidence.get("source_p28_final_operator_runtime_activation_gate_review_report_sha256") != p28_report_hash:
        blocked.append("P29_DRY_RUN_EVIDENCE_P28_REPORT_HASH_MISMATCH")
    if evidence.get("source_p28_final_operator_runtime_activation_gate_review_packet_sha256") != p28_packet_hash:
        blocked.append("P29_DRY_RUN_EVIDENCE_P28_PACKET_HASH_MISMATCH")
    if evidence.get("auto_generated_dry_run_evidence") is not False:
        blocked.append("P29_DRY_RUN_EVIDENCE_AUTO_GENERATED_BLOCKED")
    if evidence.get("bundle_is_runtime_authority") is not False:
        blocked.append("P29_DRY_RUN_EVIDENCE_RUNTIME_AUTHORITY_CLAIMED")
    if evidence.get("bundle_executes_runtime") is not False:
        blocked.append("P29_DRY_RUN_EVIDENCE_EXECUTES_RUNTIME_BLOCKED")
    if evidence.get("request_executes_runtime") is not False:
        blocked.append("P29_DRY_RUN_EVIDENCE_REQUEST_EXECUTES_RUNTIME_BLOCKED")
    for ack in sorted(_REQUIRED_TOP_LEVEL_ACKS):
        if evidence.get(ack) is not True:
            blocked.append(f"P29_REQUIRED_ACK_MISSING_{ack.upper()}")

    ticks = evidence.get("scheduler_dry_run_ticks")
    if not isinstance(ticks, list) or len(ticks) < 3:
        blocked.append("P29_SCHEDULER_DRY_RUN_MIN_TICK_COUNT_MISSING")
    else:
        idempotency_keys: list[str] = []
        for idx, tick in enumerate(ticks, start=1):
            if not isinstance(tick, Mapping):
                blocked.append(f"P29_TICK_{idx}_INVALID")
                continue
            for field in sorted(_REQUIRED_TICK_FIELDS_TRUE):
                if tick.get(field) is not True:
                    blocked.append(f"P29_TICK_{idx}_MISSING_TRUE_{field.upper()}")
            for field in sorted(_REQUIRED_TICK_FIELDS_FALSE):
                if tick.get(field) is not False:
                    blocked.append(f"P29_TICK_{idx}_UNSAFE_TRUE_{field.upper()}")
            key = tick.get("idempotency_key")
            if not isinstance(key, str) or not key.strip():
                blocked.append(f"P29_TICK_{idx}_IDEMPOTENCY_KEY_MISSING")
            else:
                idempotency_keys.append(key)
        if len(idempotency_keys) != len(set(idempotency_keys)):
            blocked.append("P29_DRY_RUN_DUPLICATE_IDEMPOTENCY_KEY")

    blocked.extend(_validate_bool_map(evidence, "risk_refresh_evidence", _REQUIRED_RISK_REFRESH_EVIDENCE, "P29"))
    blocked.extend(_validate_bool_map(evidence, "idempotency_evidence", _REQUIRED_IDEMPOTENCY_EVIDENCE, "P29"))
    blocked.extend(_validate_bool_map(evidence, "reconciliation_required_evidence", _REQUIRED_RECONCILIATION_EVIDENCE, "P29"))
    blocked.extend(_validate_bool_map(evidence, "kill_switch_ready_evidence", _REQUIRED_KILL_SWITCH_EVIDENCE, "P29"))
    blocked.extend(_validate_bool_map(evidence, "daily_incident_reporting_evidence", _REQUIRED_REPORTING_EVIDENCE, "P29"))
    return waiting, blocked


def build_final_runtime_activation_dry_run_evidence_bundle_report(
    *,
    root: Path | None = None,
    p28_summary: Mapping[str, Any] | None = None,
    p28_report: Mapping[str, Any] | None = None,
    p28_packet: Mapping[str, Any] | None = None,
    p29_dry_run_evidence: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    root = root or Path.cwd()
    p28_summary = dict(p28_summary or {})
    p28_report = dict(p28_report or {})
    p28_packet = dict(p28_packet or {})
    p29_dry_run_evidence = dict(p29_dry_run_evidence or {})
    p28_report_hash = p28_summary.get("p28_final_operator_runtime_activation_gate_review_sha256") or p28_report.get("p28_final_operator_runtime_activation_gate_review_sha256")
    p28_packet_hash = p28_packet.get("p28_final_operator_runtime_activation_gate_review_packet_sha256")
    evidence_template = build_final_runtime_activation_dry_run_evidence_template(
        p28_final_operator_runtime_activation_gate_review_report_sha256=str(p28_report_hash) if p28_report_hash else None,
        p28_final_operator_runtime_activation_gate_review_packet_sha256=str(p28_packet_hash) if p28_packet_hash else None,
    )

    named_payloads: list[tuple[str, Mapping[str, Any]]] = [
        ("p28_summary", p28_summary),
        ("p28_report", p28_report),
        ("p28_packet", p28_packet),
        ("p29_dry_run_evidence", p29_dry_run_evidence),
        ("p29_dry_run_evidence_template", evidence_template),
    ]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)
    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P29})
    truthy_disabled = truthy_execution_flags(disabled_state)

    waiting_reasons, block_reasons = _validate_p28_source(p28_summary, p28_report, p28_packet)
    evidence_waiting, evidence_blocked = _validate_dry_run_evidence(
        p29_dry_run_evidence,
        p28_report_hash=p28_report_hash,
        p28_packet_hash=p28_packet_hash,
    )
    waiting_reasons.extend(evidence_waiting)
    block_reasons.extend(evidence_blocked)
    if unsafe_hits:
        block_reasons.append("P29_UNSAFE_TRUTHY_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P29_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P29_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    valid = not blocked and not waiting_reasons
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else (STATUS_VALID_REVIEW_ONLY if valid else STATUS_WAITING_REVIEW_ONLY)
    evidence_hash = sha256_json(p29_dry_run_evidence) if p29_dry_run_evidence else None
    dry_run_bundle_packet = {
        "packet_type": "p29_final_runtime_activation_dry_run_evidence_bundle_packet_review_only",
        "status": status,
        "valid_review_only": valid,
        "source_p28_final_operator_runtime_activation_gate_review_report_sha256": p28_report_hash,
        "source_p28_final_operator_runtime_activation_gate_review_packet_sha256": p28_packet_hash,
        "p29_final_runtime_activation_dry_run_evidence_sha256": evidence_hash,
        "runtime_authority": False,
        "runtime_activation_performed": False,
        "scheduler_enabled": False,
        "order_submission_allowed": False,
        "secret_value_accessed": False,
        "endpoint_called": False,
    }
    dry_run_bundle_packet["p29_final_runtime_activation_dry_run_evidence_bundle_packet_sha256"] = sha256_json(dry_run_bundle_packet)

    report: dict[str, Any] = {
        "p29_final_runtime_activation_dry_run_evidence_bundle_version": P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_BUNDLE_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": valid,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p28_final_operator_runtime_activation_gate_review_report_sha256": p28_report_hash,
        "source_p28_final_operator_runtime_activation_gate_review_packet_sha256": p28_packet_hash,
        "p29_final_runtime_activation_dry_run_evidence_sha256": evidence_hash,
        "p29_final_runtime_activation_dry_run_evidence_template": evidence_template,
        "p29_final_runtime_activation_dry_run_evidence_bundle_packet": dry_run_bundle_packet,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "p29_final_runtime_activation_dry_run_evidence_bundle_valid_review_only": valid,
        "final_runtime_activation_dry_run_evidence_bundle_ready_review_only": valid,
        "final_runtime_activation_dry_run_evidence_bundle_is_runtime_authority": False,
        "separate_operator_runtime_activation_execution_required_after_this_bundle": True,
        "fresh_validation_required_before_runtime_activation": True,
        "scheduler_tick_dry_run_evidence_valid_review_only": valid,
        "risk_refresh_evidence_valid_review_only": valid,
        "idempotency_evidence_valid_review_only": valid,
        "reconciliation_required_evidence_valid_review_only": valid,
        "kill_switch_ready_evidence_valid_review_only": valid,
        "daily_incident_reporting_evidence_valid_review_only": valid,
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
        "final_runtime_activation_dry_run_performed": False,
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
    report["p29_final_runtime_activation_dry_run_evidence_bundle_id"] = stable_id("p29_final_runtime_activation_dry_run_evidence_bundle", report, 24)
    report["p29_final_runtime_activation_dry_run_evidence_bundle_sha256"] = sha256_json(report)
    return report


def _valid_p28_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    report_hash = "a" * 64
    packet = {
        "packet_type": "p28_final_operator_runtime_activation_gate_review_packet_review_only",
        "valid_review_only": True,
        "runtime_authority": False,
        "runtime_activation_performed": False,
        "scheduler_enabled": False,
        "order_submission_allowed": False,
        "secret_value_accessed": False,
        "endpoint_called": False,
    }
    packet["p28_final_operator_runtime_activation_gate_review_packet_sha256"] = sha256_json(packet)
    p28_summary = {
        "status": "P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_VALID_REVIEW_ONLY",
        "p28_final_operator_runtime_activation_gate_review_sha256": report_hash,
        "p28_final_operator_runtime_activation_gate_review_valid_review_only": True,
        "final_operator_runtime_activation_gate_ready_review_only": True,
        "final_operator_runtime_activation_gate_review_is_runtime_authority": False,
        "separate_operator_runtime_activation_execution_required_after_this_review": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p28_report = {
        "status": "P28_FINAL_OPERATOR_RUNTIME_ACTIVATION_GATE_REVIEW_VALID_REVIEW_ONLY",
        "p28_final_operator_runtime_activation_gate_review_sha256": report_hash,
        "p28_final_operator_runtime_activation_gate_review_valid_review_only": True,
        "final_operator_runtime_activation_gate_ready_review_only": True,
        "final_operator_runtime_activation_gate_review_is_runtime_authority": False,
        "separate_operator_runtime_activation_execution_required_after_this_review": True,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    evidence = build_final_runtime_activation_dry_run_evidence_template(
        p28_final_operator_runtime_activation_gate_review_report_sha256=report_hash,
        p28_final_operator_runtime_activation_gate_review_packet_sha256=packet["p28_final_operator_runtime_activation_gate_review_packet_sha256"],
    )
    evidence.update({"operator_id": "operator-thomas", "ticket_or_signature": "TICKET-P29-VALID-001", "reviewed_at_utc": "2026-07-08T00:00:00Z"})
    return p28_summary, p28_report, packet, evidence


def build_p29_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    p28_summary, p28_report, p28_packet, evidence = _valid_p28_fixture()
    base = {"p28_summary": p28_summary, "p28_report": p28_report, "p28_packet": p28_packet, "p29_dry_run_evidence": evidence}
    duplicate_ticks = [dict(item) for item in evidence["scheduler_dry_run_ticks"]]
    duplicate_ticks[1]["idempotency_key"] = duplicate_ticks[0]["idempotency_key"]
    cases = {
        "p28_not_valid": {**base, "p28_summary": {**p28_summary, "p28_final_operator_runtime_activation_gate_review_valid_review_only": False}},
        "missing_dry_run_evidence": {**base, "p29_dry_run_evidence": {}},
        "missing_exact_phrase": {**base, "p29_dry_run_evidence": {**evidence, "exact_final_runtime_activation_dry_run_evidence_phrase": "WRONG"}},
        "p28_report_hash_mismatch": {**base, "p29_dry_run_evidence": {**evidence, "source_p28_final_operator_runtime_activation_gate_review_report_sha256": "c" * 64}},
        "tick_missing_fresh_data": {**base, "p29_dry_run_evidence": {**evidence, "scheduler_dry_run_ticks": [{**evidence["scheduler_dry_run_ticks"][0], "fresh_market_data_loaded": False}, *evidence["scheduler_dry_run_ticks"][1:]]}},
        "risk_gate_failed": {**base, "p29_dry_run_evidence": {**evidence, "scheduler_dry_run_ticks": [{**evidence["scheduler_dry_run_ticks"][0], "hot_path_preorder_risk_gate_passed": False}, *evidence["scheduler_dry_run_ticks"][1:]]}},
        "duplicate_idempotency": {**base, "p29_dry_run_evidence": {**evidence, "scheduler_dry_run_ticks": duplicate_ticks}},
        "endpoint_called": {**base, "p29_dry_run_evidence": {**evidence, "scheduler_dry_run_ticks": [{**evidence["scheduler_dry_run_ticks"][0], "order_endpoint_called": True}, *evidence["scheduler_dry_run_ticks"][1:]]}},
        "scheduler_enabled": {**base, "p29_dry_run_evidence": {**evidence, "runtime_scheduler_enabled": True}},
        "secret_pattern_found": {**base, "p29_dry_run_evidence": {**evidence, "operator_note": "BINANCE_API_SECRET=leaked"}},
        "kill_switch_missing": {**base, "p29_dry_run_evidence": {**evidence, "kill_switch_ready_evidence": {**evidence["kill_switch_ready_evidence"], "operator_manual_kill_switch_ready": False}}},
        "reconciliation_not_required": {**base, "p29_dry_run_evidence": {**evidence, "reconciliation_required_evidence": {**evidence["reconciliation_required_evidence"], "reconciliation_required_for_every_would_submit": False}}},
        "daily_report_missing": {**base, "p29_dry_run_evidence": {**evidence, "daily_incident_reporting_evidence": {**evidence["daily_incident_reporting_evidence"], "daily_report_required": False}}},
        "runtime_authority_claimed": {**base, "p29_dry_run_evidence": {**evidence, "bundle_is_runtime_authority": True}},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_final_runtime_activation_dry_run_evidence_bundle_report(root=root, **kwargs)
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
        "p29_final_runtime_activation_dry_run_evidence_bundle_version": P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_BUNDLE_VERSION,
        "status": "P29_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_final_runtime_activation_dry_run_evidence_bundle(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p29_final_runtime_activation_dry_run_evidence_bundle")
    p28_summary = _read_latest_json(cfg, _P28_SUMMARY_FILENAME)
    p28_report = _read_latest_json(cfg, _P28_REPORT_FILENAME)
    p28_packet = _read_latest_json(cfg, _P28_PACKET_FILENAME)
    p29_dry_run_evidence = _read_latest_json(cfg, _P29_DRY_RUN_EVIDENCE_FILENAME)
    report = build_final_runtime_activation_dry_run_evidence_bundle_report(
        root=cfg.root,
        p28_summary=p28_summary,
        p28_report=p28_report,
        p28_packet=p28_packet,
        p29_dry_run_evidence=p29_dry_run_evidence,
    )
    negative_results = build_p29_negative_fixture_results(root=cfg.root)
    atomic_write_json(latest / "p29_final_runtime_activation_dry_run_evidence_bundle_report.json", report)
    atomic_write_json(storage / "p29_final_runtime_activation_dry_run_evidence_bundle_report.json", report)
    atomic_write_json(latest / "p29_final_runtime_activation_dry_run_evidence_TEMPLATE.json", report["p29_final_runtime_activation_dry_run_evidence_template"])
    atomic_write_json(latest / "p29_final_runtime_activation_dry_run_evidence_bundle_packet.json", report["p29_final_runtime_activation_dry_run_evidence_bundle_packet"])
    atomic_write_json(latest / "p29_final_runtime_activation_dry_run_evidence_bundle_negative_fixture_results.json", negative_results)
    summary = {
        "status": report["status"],
        "p29_final_runtime_activation_dry_run_evidence_bundle_sha256": report["p29_final_runtime_activation_dry_run_evidence_bundle_sha256"],
        "p29_final_runtime_activation_dry_run_evidence_bundle_valid_review_only": report["p29_final_runtime_activation_dry_run_evidence_bundle_valid_review_only"],
        "final_runtime_activation_dry_run_evidence_bundle_ready_review_only": report["final_runtime_activation_dry_run_evidence_bundle_ready_review_only"],
        "final_runtime_activation_dry_run_evidence_bundle_is_runtime_authority": False,
        "separate_operator_runtime_activation_execution_required_after_this_bundle": True,
        "fresh_validation_required_before_runtime_activation": True,
        "source_p28_final_operator_runtime_activation_gate_review_report_sha256": report["source_p28_final_operator_runtime_activation_gate_review_report_sha256"],
        "source_p28_final_operator_runtime_activation_gate_review_packet_sha256": report["source_p28_final_operator_runtime_activation_gate_review_packet_sha256"],
        "p29_final_runtime_activation_dry_run_evidence_sha256": report["p29_final_runtime_activation_dry_run_evidence_sha256"],
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
    summary["p29_final_runtime_activation_dry_run_evidence_bundle_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p29_final_runtime_activation_dry_run_evidence_bundle_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_BUNDLE_REGISTRY_NAME),
        report,
        registry_name=P29_FINAL_RUNTIME_ACTIVATION_DRY_RUN_EVIDENCE_BUNDLE_REGISTRY_NAME,
        id_field="p29_final_runtime_activation_dry_run_evidence_bundle_registry_id",
        hash_field="p29_final_runtime_activation_dry_run_evidence_bundle_registry_sha256",
        id_prefix="p29_final_runtime_activation_dry_run_evidence_bundle",
    )
    atomic_write_json(latest / "p29_final_runtime_activation_dry_run_evidence_bundle_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_final_runtime_activation_dry_run_evidence_bundle()
    print(result["status"])
    print(result["p29_final_runtime_activation_dry_run_evidence_bundle_sha256"])
