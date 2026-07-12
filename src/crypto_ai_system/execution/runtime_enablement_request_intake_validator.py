from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_accepted_release_candidate_handoff import P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_VERSION = "p24_runtime_enablement_request_intake_validator_v1"
P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_REGISTRY_NAME = "p24_runtime_enablement_request_intake_validator_registry"

STATUS_WAITING_REVIEW_ONLY = "P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY = "P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_VALID_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_BLOCKED_FAIL_CLOSED"

_P23_SUMMARY_FILENAME = "p23_operator_accepted_release_candidate_handoff_summary.json"
_P23_REPORT_FILENAME = "p23_operator_accepted_release_candidate_handoff_report.json"
_P23_TEMPLATE_FILENAME = "p23_runtime_enablement_request_TEMPLATE.json"
_P24_INTAKE_FILENAME = "p24_runtime_enablement_request_intake.json"

_EXECUTION_FIELDS_FOR_P24 = {
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
    "runtime_enablement_requested_as_authority",
    "scheduler_start_requested",
    "order_submission_requested",
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
    "separate_runtime_enablement_boundary_required_acknowledged",
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
                if key in _EXECUTION_FIELDS_FOR_P24 and _bool(value):
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


def build_runtime_enablement_request_intake_template(
    *,
    p23_handoff_sha256: str | None = None,
    p23_template_sha256: str | None = None,
) -> dict[str, Any]:
    template: dict[str, Any] = {
        "request_type": "limited_live_scaled_runtime_enablement_request_intake_review_only",
        "stage": "runtime_enablement_request_intake_validation",
        "operator_id": "OPERATOR_ID_REQUIRED",
        "ticket_or_signature": "TICKET_OR_SIGNATURE_REQUIRED",
        "requested_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
        "exact_runtime_enablement_request_phrase": P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE,
        "source_p23_operator_accepted_release_candidate_handoff_sha256": p23_handoff_sha256 or "P23_HANDOFF_SHA256_REQUIRED",
        "source_p23_runtime_enablement_request_template_sha256": p23_template_sha256 or "P23_RUNTIME_ENABLEMENT_REQUEST_TEMPLATE_SHA256_REQUIRED",
        "manual_operator_submission": True,
        "auto_generated_runtime_approval": False,
        "intake_is_runtime_authority": False,
        "request_executes_runtime": False,
        "no_runtime_authority_acknowledged": True,
        "separate_runtime_enablement_boundary_required_acknowledged": True,
        "fresh_validation_required_acknowledged": True,
        "no_execution_flags_modified_acknowledged": True,
        "no_order_submission_allowed_acknowledged": True,
        "no_scheduler_enablement_allowed_acknowledged": True,
        "no_secret_values_inserted_acknowledged": True,
        "no_endpoint_call_allowed_by_this_intake_acknowledged": True,
        "caps_acknowledged": True,
        "cap_acknowledgements": {
            "symbol_scope_btcusdt_only": True,
            "fixed_max_notional_cap_acknowledged": True,
            "daily_loss_cap_acknowledged": True,
            "max_daily_order_count_acknowledged": True,
            "max_consecutive_loss_acknowledged": True,
            "max_open_position_count_acknowledged": True,
            "max_leverage_acknowledged": True,
            "max_slippage_acknowledged": True,
            "max_api_error_rate_acknowledged": True,
        },
        "kill_switch_acknowledged": True,
        "rollback_and_full_shutdown_acknowledged": True,
        "monitoring_alerting_acknowledged": True,
        "daily_report_acknowledged": True,
        "incident_report_acknowledged": True,
        "all_orders_must_reconcile_acknowledged": True,
        "idempotency_required_acknowledged": True,
        "post_submit_relock_required_acknowledged": True,
        "canonical_id_chain_required_acknowledged": True,
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
    }
    template["p24_runtime_enablement_request_intake_template_sha256"] = sha256_json(template)
    return template


def _validate_p23_source(p23_summary: Mapping[str, Any], p23_report: Mapping[str, Any], p23_template: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not p23_summary:
        waiting.append("P24_SOURCE_P23_SUMMARY_MISSING")
    if not p23_report:
        waiting.append("P24_SOURCE_P23_REPORT_MISSING")
    if not p23_template:
        waiting.append("P24_SOURCE_P23_TEMPLATE_MISSING")
    if p23_summary and p23_summary.get("status") == "P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_BLOCKED_FAIL_CLOSED":
        blocked.append("P24_SOURCE_P23_BLOCKED")
    if p23_report and p23_report.get("status") == "P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_BLOCKED_FAIL_CLOSED":
        blocked.append("P24_SOURCE_P23_REPORT_BLOCKED")
    if p23_summary and p23_summary.get("p23_operator_accepted_release_candidate_handoff_valid_review_only") is not True:
        waiting.append("P24_SOURCE_P23_HANDOFF_NOT_VALID")
    if p23_summary and p23_summary.get("operator_release_candidate_handoff_ready_review_only") is not True:
        waiting.append("P24_SOURCE_P23_HANDOFF_NOT_READY")
    if p23_report and p23_report.get("p23_operator_accepted_release_candidate_handoff_valid_review_only") is not True:
        waiting.append("P24_SOURCE_P23_REPORT_NOT_VALID")
    if p23_report and p23_report.get("operator_release_candidate_handoff_ready_review_only") is not True:
        waiting.append("P24_SOURCE_P23_REPORT_NOT_READY")
    summary_hash = p23_summary.get("p23_operator_accepted_release_candidate_handoff_sha256")
    report_hash = p23_report.get("p23_operator_accepted_release_candidate_handoff_sha256")
    if p23_summary and not _is_sha256(summary_hash):
        waiting.append("P24_SOURCE_P23_SUMMARY_HASH_MISSING_OR_INVALID")
    if p23_report and not _is_sha256(report_hash):
        waiting.append("P24_SOURCE_P23_REPORT_HASH_MISSING_OR_INVALID")
    if _is_sha256(summary_hash) and _is_sha256(report_hash) and summary_hash != report_hash:
        blocked.append("P24_SOURCE_P23_SUMMARY_REPORT_HASH_MISMATCH")
    template_hash = p23_template.get("p23_runtime_enablement_request_template_sha256")
    if p23_template and not _is_sha256(template_hash):
        waiting.append("P24_SOURCE_P23_TEMPLATE_HASH_MISSING_OR_INVALID")
    if p23_template and p23_template.get("exact_runtime_enablement_request_phrase") != P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE:
        blocked.append("P24_SOURCE_P23_TEMPLATE_EXACT_PHRASE_INVALID")
    if p23_template and p23_template.get("template_only") is not True:
        blocked.append("P24_SOURCE_P23_TEMPLATE_NOT_TEMPLATE_ONLY")
    if p23_template and p23_template.get("runtime_enablement_performed") is not False:
        blocked.append("P24_SOURCE_P23_TEMPLATE_RUNTIME_ENABLEMENT_PERFORMED")
    return waiting, blocked


def _validate_intake(
    intake: Mapping[str, Any],
    *,
    p23_handoff_hash: Any,
    p23_template_hash: Any,
) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not intake:
        waiting.append("P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_MISSING")
        return waiting, blocked
    if intake.get("request_type") != "limited_live_scaled_runtime_enablement_request_intake_review_only":
        blocked.append("P24_INTAKE_REQUEST_TYPE_INVALID")
    if not str(intake.get("operator_id") or "").strip() or str(intake.get("operator_id")).endswith("REQUIRED"):
        waiting.append("P24_OPERATOR_ID_MISSING")
    if not str(intake.get("ticket_or_signature") or "").strip() or str(intake.get("ticket_or_signature")).endswith("REQUIRED"):
        waiting.append("P24_TICKET_OR_SIGNATURE_MISSING")
    if intake.get("exact_runtime_enablement_request_phrase") != P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE:
        blocked.append("P24_INTAKE_EXACT_RUNTIME_ENABLEMENT_REQUEST_PHRASE_INVALID")
    if intake.get("source_p23_operator_accepted_release_candidate_handoff_sha256") != p23_handoff_hash:
        blocked.append("P24_INTAKE_P23_HANDOFF_HASH_MISMATCH")
    if intake.get("source_p23_runtime_enablement_request_template_sha256") != p23_template_hash:
        blocked.append("P24_INTAKE_P23_TEMPLATE_HASH_MISMATCH")
    if intake.get("manual_operator_submission") is not True:
        blocked.append("P24_INTAKE_MANUAL_OPERATOR_SUBMISSION_REQUIRED")
    if intake.get("auto_generated_runtime_approval") is not False:
        blocked.append("P24_INTAKE_AUTO_GENERATED_RUNTIME_APPROVAL_BLOCKED")
    if intake.get("intake_is_runtime_authority") is not False:
        blocked.append("P24_INTAKE_RUNTIME_AUTHORITY_CLAIMED")
    if intake.get("request_executes_runtime") is not False:
        blocked.append("P24_INTAKE_EXECUTES_RUNTIME_BLOCKED")
    for ack in sorted(_REQUIRED_ACKS):
        if intake.get(ack) is not True:
            blocked.append(f"P24_REQUIRED_ACK_MISSING_{ack.upper()}")
    cap_ack = intake.get("cap_acknowledgements")
    if not isinstance(cap_ack, Mapping):
        blocked.append("P24_CAP_ACKNOWLEDGEMENTS_MISSING")
    else:
        for cap_field in sorted(_REQUIRED_CAP_FIELDS):
            if cap_ack.get(cap_field) is not True:
                blocked.append(f"P24_REQUIRED_CAP_ACK_MISSING_{cap_field.upper()}")
    return waiting, blocked


def build_runtime_enablement_request_intake_validator_report(
    *,
    root: Path,
    p23_summary: Mapping[str, Any] | None = None,
    p23_report: Mapping[str, Any] | None = None,
    p23_template: Mapping[str, Any] | None = None,
    p24_intake: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    del root
    p23_summary = dict(p23_summary or {})
    p23_report = dict(p23_report or {})
    p23_template = dict(p23_template or {})
    p24_intake = dict(p24_intake or {})
    p23_handoff_hash = p23_summary.get("p23_operator_accepted_release_candidate_handoff_sha256") or p23_report.get("p23_operator_accepted_release_candidate_handoff_sha256")
    p23_template_hash = p23_template.get("p23_runtime_enablement_request_template_sha256")
    intake_template = build_runtime_enablement_request_intake_template(
        p23_handoff_sha256=str(p23_handoff_hash) if p23_handoff_hash else None,
        p23_template_sha256=str(p23_template_hash) if p23_template_hash else None,
    )

    named_payloads: list[tuple[str, Mapping[str, Any]]] = [
        ("p23_summary", p23_summary),
        ("p23_report", p23_report),
        ("p23_runtime_enablement_request_template", p23_template),
        ("p24_runtime_enablement_request_intake", p24_intake),
        ("p24_runtime_enablement_request_intake_template", intake_template),
    ]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)
    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P24})
    truthy_disabled = truthy_execution_flags(disabled_state)

    waiting_reasons, block_reasons = _validate_p23_source(p23_summary, p23_report, p23_template)
    intake_waiting, intake_blocked = _validate_intake(p24_intake, p23_handoff_hash=p23_handoff_hash, p23_template_hash=p23_template_hash)
    waiting_reasons.extend(intake_waiting)
    block_reasons.extend(intake_blocked)
    if unsafe_hits:
        block_reasons.append("P24_UNSAFE_TRUTHY_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P24_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P24_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    valid = not blocked and not waiting_reasons
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else (STATUS_VALID_REVIEW_ONLY if valid else STATUS_WAITING_REVIEW_ONLY)
    intake_sha = sha256_json(p24_intake) if p24_intake else None
    report: dict[str, Any] = {
        "p24_runtime_enablement_request_intake_validator_version": P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": valid,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p23_operator_accepted_release_candidate_handoff_sha256": p23_handoff_hash,
        "source_p23_runtime_enablement_request_template_sha256": p23_template_hash,
        "p24_runtime_enablement_request_intake_sha256": intake_sha,
        "runtime_enablement_request_intake_template": intake_template,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "p24_runtime_enablement_request_intake_valid_review_only": valid,
        "runtime_enablement_request_validated_review_only": valid,
        "runtime_enablement_request_is_runtime_authority": False,
        "separate_final_runtime_boundary_required": True,
        "fresh_validation_required_before_runtime": True,
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
    report["p24_runtime_enablement_request_intake_validator_id"] = stable_id("p24_runtime_enablement_request_intake_validator", report, 24)
    report["p24_runtime_enablement_request_intake_validator_sha256"] = sha256_json(report)
    return report


def _valid_p23_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    p23_hash = "a" * 64
    p23_template_hash = "b" * 64
    p23_summary = {
        "status": "P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_READY_REVIEW_ONLY",
        "p23_operator_accepted_release_candidate_handoff_sha256": p23_hash,
        "p23_operator_accepted_release_candidate_handoff_valid_review_only": True,
        "operator_release_candidate_handoff_ready_review_only": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p23_report = {
        "status": "P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_READY_REVIEW_ONLY",
        "p23_operator_accepted_release_candidate_handoff_sha256": p23_hash,
        "p23_operator_accepted_release_candidate_handoff_valid_review_only": True,
        "operator_release_candidate_handoff_ready_review_only": True,
        "handoff_is_runtime_authority": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p23_template = {
        "request_type": "limited_live_scaled_runtime_enablement_request_template_review_only",
        "exact_runtime_enablement_request_phrase": P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE,
        "p23_runtime_enablement_request_template_sha256": p23_template_hash,
        "template_only": True,
        "review_only": True,
        "runtime_enablement_performed": False,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    intake = build_runtime_enablement_request_intake_template(p23_handoff_sha256=p23_hash, p23_template_sha256=p23_template_hash)
    intake.update({"operator_id": "operator-thomas", "ticket_or_signature": "TICKET-P24-VALID-001", "requested_at_utc": "2026-07-08T00:00:00Z"})
    return p23_summary, p23_report, p23_template, intake


def build_p24_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    p23_summary, p23_report, p23_template, intake = _valid_p23_fixture()
    base = {"p23_summary": p23_summary, "p23_report": p23_report, "p23_template": p23_template, "p24_intake": intake}
    cases = {
        "p23_not_valid": {**base, "p23_summary": {**p23_summary, "p23_operator_accepted_release_candidate_handoff_valid_review_only": False}},
        "missing_intake": {**base, "p24_intake": {}},
        "missing_operator_identity": {**base, "p24_intake": {**intake, "operator_id": ""}},
        "missing_ticket_signature": {**base, "p24_intake": {**intake, "ticket_or_signature": ""}},
        "missing_exact_phrase": {**base, "p24_intake": {**intake, "exact_runtime_enablement_request_phrase": "WRONG"}},
        "p23_handoff_hash_mismatch": {**base, "p24_intake": {**intake, "source_p23_operator_accepted_release_candidate_handoff_sha256": "c" * 64}},
        "p23_template_hash_mismatch": {**base, "p24_intake": {**intake, "source_p23_runtime_enablement_request_template_sha256": "d" * 64}},
        "auto_generated_runtime_approval": {**base, "p24_intake": {**intake, "auto_generated_runtime_approval": True}},
        "runtime_authority_claimed": {**base, "p24_intake": {**intake, "intake_is_runtime_authority": True}},
        "request_executes_runtime": {**base, "p24_intake": {**intake, "request_executes_runtime": True}},
        "missing_caps_acknowledgement": {**base, "p24_intake": {**intake, "caps_acknowledged": False}},
        "missing_kill_switch_acknowledgement": {**base, "p24_intake": {**intake, "kill_switch_acknowledged": False}},
        "cap_detail_missing": {**base, "p24_intake": {**intake, "cap_acknowledgements": {**intake["cap_acknowledgements"], "max_leverage_acknowledged": False}}},
        "scheduler_enablement_requested": {**base, "p24_intake": {**intake, "runtime_scheduler_enabled": True}},
        "order_submission_requested": {**base, "p24_intake": {**intake, "live_order_submission_allowed": True}},
        "endpoint_called": {**base, "p24_intake": {**intake, "order_endpoint_called": True}},
        "secret_pattern_found": {**base, "p24_intake": {**intake, "operator_note": "BINANCE_API_SECRET=leaked"}},
        "runtime_mutation_requested": {**base, "p24_intake": {**intake, "runtime_settings_mutated": True}},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_runtime_enablement_request_intake_validator_report(root=root, **kwargs)
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
        "p24_runtime_enablement_request_intake_validator_version": P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_VERSION,
        "status": "P24_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_runtime_enablement_request_intake_validator(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p24_runtime_enablement_request_intake_validator")
    p23_summary = _read_latest_json(cfg, _P23_SUMMARY_FILENAME)
    p23_report = _read_latest_json(cfg, _P23_REPORT_FILENAME)
    p23_template = _read_latest_json(cfg, _P23_TEMPLATE_FILENAME)
    p24_intake = _read_latest_json(cfg, _P24_INTAKE_FILENAME)
    report = build_runtime_enablement_request_intake_validator_report(
        root=cfg.root,
        p23_summary=p23_summary,
        p23_report=p23_report,
        p23_template=p23_template,
        p24_intake=p24_intake,
    )
    negative_results = build_p24_negative_fixture_results(root=cfg.root)
    atomic_write_json(latest / "p24_runtime_enablement_request_intake_validator_report.json", report)
    atomic_write_json(storage / "p24_runtime_enablement_request_intake_validator_report.json", report)
    atomic_write_json(latest / "p24_runtime_enablement_request_intake_TEMPLATE.json", report["runtime_enablement_request_intake_template"])
    atomic_write_json(latest / "p24_runtime_enablement_request_intake_validator_negative_fixture_results.json", negative_results)
    summary = {
        "status": report["status"],
        "p24_runtime_enablement_request_intake_validator_sha256": report["p24_runtime_enablement_request_intake_validator_sha256"],
        "p24_runtime_enablement_request_intake_valid_review_only": report["p24_runtime_enablement_request_intake_valid_review_only"],
        "runtime_enablement_request_validated_review_only": report["runtime_enablement_request_validated_review_only"],
        "runtime_enablement_request_is_runtime_authority": False,
        "separate_final_runtime_boundary_required": True,
        "fresh_validation_required_before_runtime": True,
        "source_p23_operator_accepted_release_candidate_handoff_sha256": report["source_p23_operator_accepted_release_candidate_handoff_sha256"],
        "p24_runtime_enablement_request_intake_sha256": report["p24_runtime_enablement_request_intake_sha256"],
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
    summary["p24_runtime_enablement_request_intake_validator_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p24_runtime_enablement_request_intake_validator_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_REGISTRY_NAME),
        report,
        registry_name=P24_RUNTIME_ENABLEMENT_REQUEST_INTAKE_VALIDATOR_REGISTRY_NAME,
        id_field="p24_runtime_enablement_request_intake_validator_registry_id",
        hash_field="p24_runtime_enablement_request_intake_validator_registry_sha256",
        id_prefix="p24_runtime_enablement_request_intake_validator",
    )
    atomic_write_json(latest / "p24_runtime_enablement_request_intake_validator_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_runtime_enablement_request_intake_validator()
    print(result["status"])
    print(result["p24_runtime_enablement_request_intake_validator_sha256"])
