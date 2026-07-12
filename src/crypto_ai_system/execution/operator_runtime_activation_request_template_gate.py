from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_VERSION = "p26_operator_runtime_activation_request_template_gate_v1"
P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_REGISTRY_NAME = "p26_operator_runtime_activation_request_template_gate_registry"

STATUS_WAITING_REVIEW_ONLY = "P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_WAITING_REVIEW_ONLY"
STATUS_GENERATED_REVIEW_ONLY = "P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_GENERATED_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_BLOCKED_FAIL_CLOSED"

P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE = (
    "I REQUEST REVIEW OF A SEPARATE OPERATOR RUNTIME ACTIVATION GATE "
    "AND ACKNOWLEDGE THIS REQUEST DOES NOT ENABLE RUNTIME"
)

_P25_SUMMARY_FILENAME = "p25_final_runtime_enablement_boundary_review_packet_summary.json"
_P25_REPORT_FILENAME = "p25_final_runtime_enablement_boundary_review_packet_report.json"
_P25_PACKET_FILENAME = "p25_final_runtime_enablement_boundary_review_packet.json"

_EXECUTION_FIELDS_FOR_P26 = {
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

_REQUIRED_ACTIVATION_ACKS = {
    "p25_final_review_packet_valid_acknowledged",
    "this_request_is_not_runtime_authority_acknowledged",
    "separate_activation_gate_required_acknowledged",
    "fresh_validation_required_acknowledged",
    "all_kill_switches_required_acknowledged",
    "caps_required_acknowledged",
    "scheduler_must_remain_disabled_by_this_template_acknowledged",
    "no_order_submission_allowed_by_this_template_acknowledged",
    "no_endpoint_call_allowed_by_this_template_acknowledged",
    "no_secret_value_access_acknowledged",
    "rollback_full_shutdown_required_acknowledged",
    "daily_incident_reports_required_acknowledged",
    "all_orders_must_reconcile_acknowledged",
    "idempotency_required_acknowledged",
    "post_submit_relock_required_acknowledged",
    "canonical_id_chain_required_acknowledged",
}

_REQUIRED_GATE_SKELETON_CONTROLS = {
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
                if key in _EXECUTION_FIELDS_FOR_P26 and _bool(value):
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


def build_operator_runtime_activation_request_template(
    *,
    p25_review_packet_sha256: str | None = None,
    p25_review_report_sha256: str | None = None,
) -> dict[str, Any]:
    template: dict[str, Any] = {
        "request_type": "operator_runtime_activation_request_template_review_only",
        "stage": "operator_runtime_activation_request_template",
        "operator_id": "OPERATOR_ID_REQUIRED",
        "ticket_or_signature": "TICKET_OR_SIGNATURE_REQUIRED",
        "requested_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
        "exact_operator_runtime_activation_request_phrase": P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_EXACT_PHRASE,
        "source_p25_final_runtime_enablement_boundary_review_packet_sha256": p25_review_packet_sha256 or "P25_REVIEW_PACKET_SHA256_REQUIRED",
        "source_p25_final_runtime_enablement_boundary_review_report_sha256": p25_review_report_sha256 or "P25_REVIEW_REPORT_SHA256_REQUIRED",
        "manual_operator_submission_required": True,
        "auto_generated_runtime_activation": False,
        "request_is_runtime_authority": False,
        "request_executes_runtime": False,
        "activation_request_executes_runtime": False,
        "acknowledgements": {field: True for field in sorted(_REQUIRED_ACTIVATION_ACKS)},
        "caps_acknowledgement": {
            "symbol_scope_btcusdt_only": True,
            "fixed_max_notional_usdt": 5.0,
            "daily_loss_cap_usdt": 5.0,
            "max_daily_order_count": 3,
            "max_consecutive_loss_count": 2,
            "max_open_position_count": 1,
            "max_leverage": 1.0,
            "max_slippage_bps": 25.0,
            "max_api_error_rate": 0.01,
        },
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
        "actual_live_order_submitted": False,
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
    template["p26_operator_runtime_activation_request_template_sha256"] = sha256_json(template)
    return template


def build_final_activation_gate_skeleton(
    *,
    p25_review_packet_sha256: str | None = None,
    p25_review_report_sha256: str | None = None,
) -> dict[str, Any]:
    skeleton: dict[str, Any] = {
        "skeleton_type": "final_operator_runtime_activation_gate_skeleton_review_only",
        "stage": "final_runtime_activation_gate_skeleton",
        "source_p25_final_runtime_enablement_boundary_review_packet_sha256": p25_review_packet_sha256,
        "source_p25_final_runtime_enablement_boundary_review_report_sha256": p25_review_report_sha256,
        "activation_gate_is_runtime_authority": False,
        "activation_gate_executes_runtime": False,
        "separate_filled_operator_activation_request_required": True,
        "separate_fresh_validation_required": True,
        "runtime_activation_performed": False,
        "scheduler_start_performed": False,
        "order_submission_performed": False,
        "gate_controls": {field: True for field in sorted(_REQUIRED_GATE_SKELETON_CONTROLS)},
        "gate_must_recheck": {
            "p25_hash_chain": True,
            "p26_activation_request_hash_chain": True,
            "fresh_data_snapshot": True,
            "source_qa": True,
            "research_signal_v2": True,
            "signal_qa": True,
            "trading_decision": True,
            "hot_path_preorder_risk_gate": True,
            "all_caps": True,
            "all_kill_switches": True,
            "duplicate_submit_lock": True,
            "idempotency_key_uniqueness": True,
            "monitoring_alerting": True,
            "rollback_full_shutdown": True,
            "daily_incident_reporting": True,
            "no_secret_value_leak": True,
        },
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "actual_live_order_submitted": False,
        "live_order_endpoint_called": False,
        "http_request_sent": False,
        "secret_value_accessed": False,
    }
    skeleton["p26_final_activation_gate_skeleton_sha256"] = sha256_json(skeleton)
    return skeleton


def _p25_source_valid(p25_summary: Mapping[str, Any], p25_report: Mapping[str, Any], p25_packet: Mapping[str, Any]) -> tuple[bool, list[str], list[str]]:
    waiting: list[str] = []
    blocks: list[str] = []
    if not p25_summary:
        waiting.append("P26_SOURCE_P25_SUMMARY_MISSING")
    if not p25_report:
        waiting.append("P26_SOURCE_P25_REPORT_MISSING")
    if not p25_packet:
        waiting.append("P26_SOURCE_P25_PACKET_MISSING")
    if waiting:
        return False, waiting, blocks

    if not _bool(p25_summary.get("p25_final_runtime_enablement_boundary_review_packet_valid_review_only")):
        waiting.append("P26_SOURCE_P25_FINAL_REVIEW_PACKET_NOT_VALID")
    if not _bool(p25_summary.get("p25_final_runtime_enablement_boundary_review_packet_ready_review_only")):
        waiting.append("P26_SOURCE_P25_FINAL_REVIEW_PACKET_NOT_READY")
    if not _bool(p25_report.get("p25_final_runtime_enablement_boundary_review_packet_valid_review_only")):
        waiting.append("P26_SOURCE_P25_REPORT_NOT_VALID")
    if _bool(p25_report.get("final_review_packet_is_runtime_authority")) or _bool(p25_packet.get("packet_is_runtime_authority")):
        blocks.append("P26_SOURCE_P25_RUNTIME_AUTHORITY_CLAIMED")
    if _bool(p25_report.get("runtime_enablement_performed")) or _bool(p25_packet.get("runtime_enablement_performed")):
        blocks.append("P26_SOURCE_P25_RUNTIME_ENABLEMENT_ALREADY_PERFORMED")
    if not _bool(p25_report.get("separate_operator_runtime_activation_required_after_this_packet")):
        blocks.append("P26_SOURCE_P25_SEPARATE_OPERATOR_ACTIVATION_NOT_REQUIRED")

    packet_hash = p25_packet.get("p25_final_runtime_enablement_boundary_review_packet_sha256")
    if packet_hash is not None and not _is_sha256(packet_hash):
        blocks.append("P26_SOURCE_P25_PACKET_HASH_INVALID")
    return not waiting and not blocks, waiting, blocks


def build_operator_runtime_activation_request_template_gate_report(
    *,
    root: Path | str | None = None,
    p25_summary: Mapping[str, Any] | None = None,
    p25_report: Mapping[str, Any] | None = None,
    p25_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_config(Path(root) if root is not None else None)
    if p25_summary is None:
        p25_summary = _read_latest_json(cfg, _P25_SUMMARY_FILENAME)
    if p25_report is None:
        p25_report = _read_latest_json(cfg, _P25_REPORT_FILENAME)
    if p25_packet is None:
        p25_packet = _read_latest_json(cfg, _P25_PACKET_FILENAME)

    p25_summary = dict(p25_summary or {})
    p25_report = dict(p25_report or {})
    p25_packet = dict(p25_packet or {})

    waiting_reasons: list[str] = []
    block_reasons: list[str] = []
    source_valid, source_waiting, source_blocks = _p25_source_valid(p25_summary, p25_report, p25_packet)
    waiting_reasons.extend(source_waiting)
    block_reasons.extend(source_blocks)

    payloads: list[tuple[str, Mapping[str, Any]]] = [
        (_P25_SUMMARY_FILENAME, p25_summary),
        (_P25_REPORT_FILENAME, p25_report),
        (_P25_PACKET_FILENAME, p25_packet),
    ]
    unsafe_hits = _scan_truthy_execution_fields(payloads)
    secret_hits = _scan_secret_value_patterns(payloads)
    internal_truthy = truthy_execution_flags(default_execution_flag_state())

    if unsafe_hits:
        block_reasons.append("P26_UNSAFE_TRUTHY_EXECUTION_FLAG_FOUND_IN_SOURCE")
    if secret_hits:
        block_reasons.append("P26_SECRET_VALUE_PATTERN_FOUND_IN_SOURCE")
    if internal_truthy:
        block_reasons.append("P26_INTERNAL_DISABLED_FLAGS_NOT_ALL_FALSE")

    p25_report_sha256 = p25_summary.get("p25_final_runtime_enablement_boundary_review_packet_report_sha256")
    if not _is_sha256(p25_report_sha256):
        p25_report_sha256 = sha256_json(p25_report) if p25_report else None
    p25_packet_sha256 = p25_packet.get("p25_final_runtime_enablement_boundary_review_packet_sha256")
    if not _is_sha256(p25_packet_sha256):
        p25_packet_sha256 = sha256_json(p25_packet) if p25_packet else None

    activation_request_template = build_operator_runtime_activation_request_template(
        p25_review_packet_sha256=p25_packet_sha256,
        p25_review_report_sha256=p25_report_sha256,
    )
    final_activation_gate_skeleton = build_final_activation_gate_skeleton(
        p25_review_packet_sha256=p25_packet_sha256,
        p25_review_report_sha256=p25_report_sha256,
    )

    if block_reasons:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif waiting_reasons:
        status = STATUS_WAITING_REVIEW_ONLY
    elif source_valid:
        status = STATUS_GENERATED_REVIEW_ONLY
    else:
        status = STATUS_WAITING_REVIEW_ONLY

    generated = status == STATUS_GENERATED_REVIEW_ONLY
    created_at = utc_now_canonical()
    report: dict[str, Any] = {
        "p26_operator_runtime_activation_request_template_gate_version": P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "waiting": status == STATUS_WAITING_REVIEW_ONLY,
        "valid_review_only": generated,
        "created_at_utc": created_at,
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p25_final_runtime_enablement_boundary_review_packet_sha256": p25_packet_sha256,
        "source_p25_final_runtime_enablement_boundary_review_report_sha256": p25_report_sha256,
        "operator_runtime_activation_request_template": activation_request_template,
        "final_activation_gate_skeleton": final_activation_gate_skeleton,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": internal_truthy,
        "p26_operator_runtime_activation_request_template_generated_review_only": generated,
        "p26_final_activation_gate_skeleton_generated_review_only": generated,
        "p26_operator_runtime_activation_gate_ready_review_only": generated,
        "activation_request_template_is_runtime_authority": False,
        "final_activation_gate_skeleton_is_runtime_authority": False,
        "separate_filled_operator_activation_request_required_after_this_template": True,
        "separate_runtime_activation_validator_required_after_this_template": True,
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
    report["p26_operator_runtime_activation_request_template_gate_report_sha256"] = sha256_json(report)
    return report


def summarize_p26_report(report: Mapping[str, Any]) -> dict[str, Any]:
    summary_keys = [
        "status",
        "p26_operator_runtime_activation_request_template_gate_report_sha256",
        "p26_operator_runtime_activation_request_template_generated_review_only",
        "p26_final_activation_gate_skeleton_generated_review_only",
        "p26_operator_runtime_activation_gate_ready_review_only",
        "activation_request_template_is_runtime_authority",
        "final_activation_gate_skeleton_is_runtime_authority",
        "separate_filled_operator_activation_request_required_after_this_template",
        "separate_runtime_activation_validator_required_after_this_template",
        "source_p25_final_runtime_enablement_boundary_review_packet_sha256",
        "source_p25_final_runtime_enablement_boundary_review_report_sha256",
        "waiting_reasons",
        "block_reasons",
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
        "actual_live_order_submitted",
        "live_order_endpoint_called",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "secret_value_accessed",
        "secret_value_logged",
        "runtime_settings_mutated",
        "score_weights_mutated",
        "auto_promotion_allowed",
    ]
    summary = {key: report.get(key) for key in summary_keys if key in report}
    summary["p26_operator_runtime_activation_request_template_gate_summary_sha256"] = sha256_json(summary)
    return summary


def build_p26_negative_fixture_results() -> dict[str, Any]:
    valid_summary = {
        "status": "P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_READY_REVIEW_ONLY",
        "p25_final_runtime_enablement_boundary_review_packet_report_sha256": "a" * 64,
        "p25_final_runtime_enablement_boundary_review_packet_valid_review_only": True,
        "p25_final_runtime_enablement_boundary_review_packet_ready_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    valid_report = {
        "status": "P25_FINAL_RUNTIME_ENABLEMENT_BOUNDARY_REVIEW_PACKET_READY_REVIEW_ONLY",
        "p25_final_runtime_enablement_boundary_review_packet_valid_review_only": True,
        "final_review_packet_is_runtime_authority": False,
        "separate_operator_runtime_activation_required_after_this_packet": True,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    valid_packet = {
        "packet_type": "final_runtime_enablement_boundary_review_packet_review_only",
        "p25_final_runtime_enablement_boundary_review_packet_sha256": "b" * 64,
        "packet_is_runtime_authority": False,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
    }

    fixtures: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {
        "p25_not_valid": ({**valid_summary, "p25_final_runtime_enablement_boundary_review_packet_valid_review_only": False}, valid_report, valid_packet),
        "p25_runtime_authority_claimed": (valid_summary, {**valid_report, "final_review_packet_is_runtime_authority": True}, valid_packet),
        "p25_runtime_already_enabled": (valid_summary, {**valid_report, "runtime_enablement_performed": True}, valid_packet),
        "p25_separate_activation_missing": (valid_summary, {**valid_report, "separate_operator_runtime_activation_required_after_this_packet": False}, valid_packet),
        "unsafe_live_scaled_enabled": ({**valid_summary, "live_scaled_execution_enabled": True}, valid_report, valid_packet),
        "scheduler_enabled": ({**valid_summary, "runtime_scheduler_enabled": True}, valid_report, valid_packet),
        "endpoint_called": (valid_summary, {**valid_report, "order_endpoint_called": True}, valid_packet),
        "secret_pattern_found": (valid_summary, {**valid_report, "diagnostic": "api_secret_value: SHOULD_NOT_EXIST"}, valid_packet),
    }
    results: list[dict[str, Any]] = []
    for name, (summary, report, packet) in fixtures.items():
        built = build_operator_runtime_activation_request_template_gate_report(
            p25_summary=summary,
            p25_report=report,
            p25_packet=packet,
        )
        results.append({
            "fixture": name,
            "status": built["status"],
            "blocked_or_waiting_fail_closed": built["status"] in {STATUS_BLOCKED_FAIL_CLOSED, STATUS_WAITING_REVIEW_ONLY},
            "block_reasons": built.get("block_reasons", []),
            "waiting_reasons": built.get("waiting_reasons", []),
            "live_scaled_execution_enabled": built["live_scaled_execution_enabled"],
            "runtime_scheduler_enabled": built["runtime_scheduler_enabled"],
            "secret_value_accessed": built["secret_value_accessed"],
        })
    return {
        "p26_negative_fixture_results_version": "p26_negative_fixture_results_v1",
        "created_at_utc": utc_now_canonical(),
        "results": results,
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting_fail_closed"] for item in results),
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }


def persist_operator_runtime_activation_request_template_gate(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    report = build_operator_runtime_activation_request_template_gate_report(root=cfg.root)
    summary = summarize_p26_report(report)
    template = report["operator_runtime_activation_request_template"]
    skeleton = report["final_activation_gate_skeleton"]
    negative = build_p26_negative_fixture_results()

    atomic_write_json(latest / "p26_operator_runtime_activation_request_template_gate_report.json", report)
    atomic_write_json(latest / "p26_operator_runtime_activation_request_template_gate_summary.json", summary)
    atomic_write_json(latest / "p26_operator_runtime_activation_request_TEMPLATE.json", template)
    atomic_write_json(latest / "p26_final_activation_gate_skeleton.json", skeleton)
    atomic_write_json(latest / "p26_operator_runtime_activation_request_template_gate_negative_fixture_results.json", negative)

    store = _storage_dir(cfg, "storage/p26_operator_runtime_activation_request_template_gate")
    atomic_write_json(store / "p26_operator_runtime_activation_request_template_gate_report.json", report)

    registry_record = {
        "record_id": stable_id("p26_operator_runtime_activation_request_template_gate", {"created_at_utc": report.get("created_at_utc"), "status": report.get("status")}),
        "registry_name": P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_REGISTRY_NAME,
        "created_at_utc": utc_now_canonical(),
        "status": report["status"],
        "report_sha256": report["p26_operator_runtime_activation_request_template_gate_report_sha256"],
        "summary_sha256": summary["p26_operator_runtime_activation_request_template_gate_summary_sha256"],
        "activation_request_template_sha256": template["p26_operator_runtime_activation_request_template_sha256"],
        "final_activation_gate_skeleton_sha256": skeleton["p26_final_activation_gate_skeleton_sha256"],
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
    }
    atomic_write_json(latest / "p26_operator_runtime_activation_request_template_gate_registry_record.json", registry_record)
    append_registry_record(registry_path(cfg, P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_REGISTRY_NAME), registry_record, registry_name=P26_OPERATOR_RUNTIME_ACTIVATION_REQUEST_TEMPLATE_GATE_REGISTRY_NAME)
    return report
