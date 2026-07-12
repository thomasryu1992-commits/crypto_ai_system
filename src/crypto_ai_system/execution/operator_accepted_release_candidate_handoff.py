from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_VERSION = "p23_operator_accepted_release_candidate_handoff_v1"
P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_REGISTRY_NAME = "p23_operator_accepted_release_candidate_handoff_registry"

STATUS_WAITING_REVIEW_ONLY = "P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_WAITING_REVIEW_ONLY"
STATUS_VALID_REVIEW_ONLY = "P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_READY_REVIEW_ONLY"
STATUS_BLOCKED_FAIL_CLOSED = "P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_BLOCKED_FAIL_CLOSED"

_P22_SUMMARY_FILENAME = "p22_operator_release_candidate_acceptance_review_summary.json"
_P22_REPORT_FILENAME = "p22_operator_release_candidate_acceptance_review_report.json"

P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE = (
    "I REQUEST REVIEW OF A SEPARATE LIMITED LIVE SCALED RUNTIME ENABLEMENT BOUNDARY TEMPLATE AND ACKNOWLEDGE THIS IS NOT EXECUTION AUTHORITY"
)

_EXECUTION_FIELDS_FOR_P23 = {
    "limited_live_scaled_auto_trading_allowed",
    "live_scaled_runtime_enablement_allowed",
    "live_scaled_execution_enabled",
    "live_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "runtime_scheduler_enabled",
    "runtime_loop_started",
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
    "runtime_enablement_performed",
    "runtime_enablement_requested_as_authority",
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
                if key in _EXECUTION_FIELDS_FOR_P23 and _bool(value):
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


def build_runtime_enablement_request_template(
    *,
    p22_operator_acceptance_review_sha256: str | None = None,
    p22_operator_acceptance_intake_sha256: str | None = None,
) -> dict[str, Any]:
    template: dict[str, Any] = {
        "request_type": "limited_live_scaled_runtime_enablement_request_template_review_only",
        "stage": "runtime_enablement_request_template",
        "operator_id": "OPERATOR_ID_REQUIRED",
        "ticket_or_signature": "TICKET_OR_SIGNATURE_REQUIRED",
        "requested_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
        "exact_runtime_enablement_request_phrase": P23_RUNTIME_ENABLEMENT_REQUEST_EXACT_PHRASE,
        "source_p22_operator_release_candidate_acceptance_review_sha256": p22_operator_acceptance_review_sha256 or "P22_ACCEPTANCE_REVIEW_SHA256_REQUIRED",
        "source_p22_operator_acceptance_intake_sha256": p22_operator_acceptance_intake_sha256 or "P22_ACCEPTANCE_INTAKE_SHA256_REQUIRED",
        "template_only": True,
        "review_only": True,
        "manual_operator_submission_required": True,
        "separate_runtime_boundary_required": True,
        "separate_runtime_enablement_validation_required": True,
        "fresh_validation_required": True,
        "no_runtime_authority_acknowledged": True,
        "release_candidate_acceptance_is_not_execution_authority_acknowledged": True,
        "no_execution_flags_modified_acknowledged": True,
        "no_order_submission_allowed_acknowledged": True,
        "no_scheduler_enablement_allowed_acknowledged": True,
        "no_secret_values_inserted_acknowledged": True,
        "all_orders_must_reconcile_acknowledged": True,
        "daily_report_required_acknowledged": True,
        "incident_report_required_acknowledged": True,
        "rollback_and_full_shutdown_required_acknowledged": True,
        "kill_switch_required_acknowledged": True,
        "idempotency_required_acknowledged": True,
        "post_submit_relock_required_acknowledged": True,
        "canonical_id_chain_required_acknowledged": True,
        "auto_generated_runtime_approval": False,
        "runtime_enablement_performed": False,
        "runtime_scheduler_enabled": False,
        "runtime_loop_started": False,
        "limited_live_scaled_auto_trading_allowed": False,
        "live_scaled_runtime_enablement_allowed": False,
        "live_scaled_execution_enabled": False,
        "live_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "actual_live_order_submitted": False,
        "live_order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    template["p23_runtime_enablement_request_template_sha256"] = sha256_json(template)
    return template


def build_final_no_runtime_authority_handoff_checklist(
    *,
    p22_operator_acceptance_review_sha256: str | None = None,
) -> dict[str, Any]:
    checklist: dict[str, Any] = {
        "checklist_type": "final_no_runtime_authority_operator_handoff_checklist_review_only",
        "source_p22_operator_release_candidate_acceptance_review_sha256": p22_operator_acceptance_review_sha256,
        "items": [
            {"id": "confirm_release_candidate_acceptance_review_only", "required": True, "completed_by_this_module": True},
            {"id": "confirm_release_candidate_is_not_runtime_authority", "required": True, "completed_by_this_module": True},
            {"id": "confirm_separate_runtime_enablement_request_required", "required": True, "completed_by_this_module": True},
            {"id": "confirm_fresh_validation_required_before_runtime", "required": True, "completed_by_this_module": True},
            {"id": "confirm_no_execution_flags_modified", "required": True, "completed_by_this_module": True},
            {"id": "confirm_no_scheduler_enabled", "required": True, "completed_by_this_module": True},
            {"id": "confirm_no_order_endpoint_called", "required": True, "completed_by_this_module": True},
            {"id": "confirm_no_secret_value_inserted_or_accessed", "required": True, "completed_by_this_module": True},
            {"id": "confirm_kill_switch_rollback_reporting_required", "required": True, "completed_by_this_module": True},
            {"id": "confirm_reconciliation_required_for_every_future_order", "required": True, "completed_by_this_module": True},
        ],
        "all_items_required": True,
        "all_items_completed_by_this_module": True,
        "handoff_is_runtime_authority": False,
        "runtime_enablement_performed": False,
        "runtime_scheduler_enabled": False,
        "live_order_submission_allowed": False,
        "secret_value_accessed": False,
    }
    checklist["p23_final_no_runtime_authority_handoff_checklist_sha256"] = sha256_json(checklist)
    return checklist


def _validate_p22_source(p22_summary: Mapping[str, Any], p22_report: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    waiting: list[str] = []
    blocked: list[str] = []
    if not p22_summary:
        waiting.append("P23_SOURCE_P22_SUMMARY_MISSING")
    if not p22_report:
        waiting.append("P23_SOURCE_P22_REPORT_MISSING")
    if p22_summary and p22_summary.get("status") == "P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_BLOCKED_FAIL_CLOSED":
        blocked.append("P23_SOURCE_P22_BLOCKED")
    if p22_report and p22_report.get("status") == "P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_BLOCKED_FAIL_CLOSED":
        blocked.append("P23_SOURCE_P22_REPORT_BLOCKED")
    if p22_summary and p22_summary.get("p22_operator_release_candidate_acceptance_valid_review_only") is not True:
        waiting.append("P23_SOURCE_P22_ACCEPTANCE_NOT_VALID")
    if p22_summary and p22_summary.get("release_candidate_accepted_review_only") is not True:
        waiting.append("P23_SOURCE_P22_RELEASE_CANDIDATE_NOT_ACCEPTED")
    if p22_report and p22_report.get("p22_operator_release_candidate_acceptance_valid_review_only") is not True:
        waiting.append("P23_SOURCE_P22_REPORT_NOT_VALID_FOR_HANDOFF")
    if p22_report and p22_report.get("release_candidate_accepted_review_only") is not True:
        waiting.append("P23_SOURCE_P22_REPORT_RELEASE_CANDIDATE_NOT_ACCEPTED")
    summary_hash = p22_summary.get("p22_operator_release_candidate_acceptance_review_sha256")
    report_hash = p22_report.get("p22_operator_release_candidate_acceptance_review_sha256")
    if p22_summary and not _is_sha256(summary_hash):
        waiting.append("P23_SOURCE_P22_SUMMARY_HASH_MISSING_OR_INVALID")
    if p22_report and not _is_sha256(report_hash):
        waiting.append("P23_SOURCE_P22_REPORT_HASH_MISSING_OR_INVALID")
    if _is_sha256(summary_hash) and _is_sha256(report_hash) and summary_hash != report_hash:
        blocked.append("P23_SOURCE_P22_SUMMARY_REPORT_HASH_MISMATCH")
    if p22_report and p22_report.get("operator_acceptance_is_runtime_authority") is not False:
        blocked.append("P23_SOURCE_P22_RUNTIME_AUTHORITY_CLAIMED")
    if p22_summary and p22_summary.get("separate_runtime_enablement_required") is not True:
        blocked.append("P23_SOURCE_P22_SEPARATE_RUNTIME_ENABLEMENT_NOT_REQUIRED_INVALID")
    return waiting, blocked


def build_operator_accepted_release_candidate_handoff_report(
    *,
    root: Path,
    p22_summary: Mapping[str, Any] | None = None,
    p22_report: Mapping[str, Any] | None = None,
    extra_payloads_for_scan: Sequence[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    del root
    p22_summary = dict(p22_summary or {})
    p22_report = dict(p22_report or {})
    p22_hash = p22_summary.get("p22_operator_release_candidate_acceptance_review_sha256") or p22_report.get("p22_operator_release_candidate_acceptance_review_sha256")
    p22_intake_hash = p22_summary.get("operator_acceptance_intake_sha256") or p22_report.get("operator_acceptance_intake_sha256")
    runtime_request_template = build_runtime_enablement_request_template(
        p22_operator_acceptance_review_sha256=str(p22_hash) if p22_hash else None,
        p22_operator_acceptance_intake_sha256=str(p22_intake_hash) if p22_intake_hash else None,
    )
    handoff_checklist = build_final_no_runtime_authority_handoff_checklist(
        p22_operator_acceptance_review_sha256=str(p22_hash) if p22_hash else None,
    )
    named_payloads: list[tuple[str, Mapping[str, Any]]] = [
        ("p22_summary", p22_summary),
        ("p22_report", p22_report),
        ("runtime_request_template", runtime_request_template),
        ("handoff_checklist", handoff_checklist),
    ]
    named_payloads.extend(extra_payloads_for_scan or [])
    unsafe_hits = _scan_truthy_execution_fields(named_payloads)
    secret_hits = _scan_secret_value_patterns(named_payloads)
    disabled_state = default_execution_flag_state()
    disabled_state.update({field: False for field in _EXECUTION_FIELDS_FOR_P23})
    truthy_disabled = truthy_execution_flags(disabled_state)

    waiting_reasons, block_reasons = _validate_p22_source(p22_summary, p22_report)
    if unsafe_hits:
        block_reasons.append("P23_UNSAFE_TRUTHY_FLAG_FOUND")
    if secret_hits:
        block_reasons.append("P23_SECRET_VALUE_PATTERN_FOUND")
    if truthy_disabled:
        block_reasons.append("P23_INTERNAL_DISABLED_STATE_HAS_TRUTHY_EXECUTION_FLAG")

    blocked = bool(block_reasons)
    valid = not blocked and not waiting_reasons
    status = STATUS_BLOCKED_FAIL_CLOSED if blocked else (STATUS_VALID_REVIEW_ONLY if valid else STATUS_WAITING_REVIEW_ONLY)
    report: dict[str, Any] = {
        "p23_operator_accepted_release_candidate_handoff_version": P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_VERSION,
        "status": status,
        "blocked": blocked,
        "waiting": bool(waiting_reasons) and not blocked,
        "valid_review_only": valid,
        "created_at_utc": utc_now_canonical(),
        "block_reasons": sorted(set(block_reasons)),
        "waiting_reasons": sorted(set(waiting_reasons)),
        "source_p22_operator_release_candidate_acceptance_review_sha256": p22_hash,
        "source_p22_operator_acceptance_intake_sha256": p22_intake_hash,
        "runtime_enablement_request_template": runtime_request_template,
        "final_no_runtime_authority_handoff_checklist": handoff_checklist,
        "unsafe_truthy_execution_flag_hits": unsafe_hits,
        "secret_value_pattern_hits": secret_hits,
        "internal_disabled_state_truthy_flags": truthy_disabled,
        "p23_operator_accepted_release_candidate_handoff_valid_review_only": valid,
        "operator_release_candidate_handoff_ready_review_only": valid,
        "runtime_enablement_request_template_generated": True,
        "final_no_runtime_authority_handoff_checklist_generated": True,
        "handoff_is_runtime_authority": False,
        "runtime_enablement_request_template_is_runtime_authority": False,
        "separate_runtime_enablement_request_required": True,
        "separate_runtime_enablement_validation_required": True,
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
    report["p23_operator_accepted_release_candidate_handoff_id"] = stable_id("p23_operator_accepted_release_candidate_handoff", report, 24)
    report["p23_operator_accepted_release_candidate_handoff_sha256"] = sha256_json(report)
    return report


def build_p23_negative_fixture_results(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    p22_hash = "a" * 64
    intake_hash = "b" * 64
    p22_summary = {
        "status": "P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_VALID_REVIEW_ONLY",
        "p22_operator_release_candidate_acceptance_review_sha256": p22_hash,
        "p22_operator_release_candidate_acceptance_valid_review_only": True,
        "release_candidate_accepted_review_only": True,
        "operator_acceptance_intake_sha256": intake_hash,
        "separate_runtime_enablement_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    p22_report = {
        "status": "P22_OPERATOR_RELEASE_CANDIDATE_ACCEPTANCE_REVIEW_VALID_REVIEW_ONLY",
        "p22_operator_release_candidate_acceptance_review_sha256": p22_hash,
        "p22_operator_release_candidate_acceptance_valid_review_only": True,
        "release_candidate_accepted_review_only": True,
        "operator_acceptance_intake_sha256": intake_hash,
        "operator_acceptance_is_runtime_authority": False,
        "separate_runtime_enablement_required": True,
        "live_scaled_execution_enabled": False,
        "runtime_scheduler_enabled": False,
        "secret_value_accessed": False,
    }
    base = {"p22_summary": p22_summary, "p22_report": p22_report}
    cases = {
        "p22_not_valid": {**base, "p22_summary": {**p22_summary, "p22_operator_release_candidate_acceptance_valid_review_only": False}},
        "p22_not_accepted": {**base, "p22_summary": {**p22_summary, "release_candidate_accepted_review_only": False}},
        "p22_hash_mismatch": {**base, "p22_report": {**p22_report, "p22_operator_release_candidate_acceptance_review_sha256": "c" * 64}},
        "p22_runtime_authority_claimed": {**base, "p22_report": {**p22_report, "operator_acceptance_is_runtime_authority": True}},
        "missing_separate_runtime_enablement_required": {**base, "p22_summary": {**p22_summary, "separate_runtime_enablement_required": False}},
        "unsafe_runtime_flag": {**base, "p22_summary": {**p22_summary, "live_scaled_execution_enabled": True}},
        "runtime_scheduler_enabled": {**base, "p22_report": {**p22_report, "runtime_scheduler_enabled": True}},
        "secret_pattern_found": {**base, "p22_report": {**p22_report, "operator_note": "BINANCE_API_SECRET=leaked"}},
    }
    results: dict[str, Any] = {}
    for name, kwargs in cases.items():
        report = build_operator_accepted_release_candidate_handoff_report(root=root, **kwargs)
        blocked_or_waiting = report["blocked"] or report["waiting"]
        results[name] = {
            "blocked_or_waiting": blocked_or_waiting,
            "blocked": report["blocked"],
            "waiting": report["waiting"],
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "waiting_reasons": report["waiting_reasons"],
            "limited_live_scaled_auto_trading_allowed": report["limited_live_scaled_auto_trading_allowed"],
            "live_scaled_execution_enabled": report["live_scaled_execution_enabled"],
            "live_order_submission_allowed": report["live_order_submission_allowed"],
            "runtime_scheduler_enabled": report["runtime_scheduler_enabled"],
            "secret_value_accessed": report["secret_value_accessed"],
        }
    return {
        "p23_operator_accepted_release_candidate_handoff_version": P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_VERSION,
        "status": "P23_NEGATIVE_FIXTURES_RECORDED",
        "all_negative_fixtures_blocked_or_waiting_fail_closed": all(item["blocked_or_waiting"] for item in results.values()),
        "fixture_results": results,
        "created_at_utc": utc_now_canonical(),
    }


def persist_operator_accepted_release_candidate_handoff(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(Path.cwd())
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p23_operator_accepted_release_candidate_handoff")
    p22_summary = _read_latest_json(cfg, _P22_SUMMARY_FILENAME)
    p22_report = _read_latest_json(cfg, _P22_REPORT_FILENAME)
    report = build_operator_accepted_release_candidate_handoff_report(
        root=cfg.root,
        p22_summary=p22_summary,
        p22_report=p22_report,
    )
    negative_results = build_p23_negative_fixture_results(root=cfg.root)
    atomic_write_json(latest / "p23_operator_accepted_release_candidate_handoff_report.json", report)
    atomic_write_json(storage / "p23_operator_accepted_release_candidate_handoff_report.json", report)
    atomic_write_json(latest / "p23_runtime_enablement_request_TEMPLATE.json", report["runtime_enablement_request_template"])
    atomic_write_json(latest / "p23_final_no_runtime_authority_handoff_checklist.json", report["final_no_runtime_authority_handoff_checklist"])
    atomic_write_json(latest / "p23_operator_accepted_release_candidate_handoff_negative_fixture_results.json", negative_results)
    summary = {
        "status": report["status"],
        "p23_operator_accepted_release_candidate_handoff_sha256": report["p23_operator_accepted_release_candidate_handoff_sha256"],
        "p23_operator_accepted_release_candidate_handoff_valid_review_only": report["p23_operator_accepted_release_candidate_handoff_valid_review_only"],
        "operator_release_candidate_handoff_ready_review_only": report["operator_release_candidate_handoff_ready_review_only"],
        "runtime_enablement_request_template_generated": report["runtime_enablement_request_template_generated"],
        "final_no_runtime_authority_handoff_checklist_generated": report["final_no_runtime_authority_handoff_checklist_generated"],
        "source_p22_operator_release_candidate_acceptance_review_sha256": report["source_p22_operator_release_candidate_acceptance_review_sha256"],
        "waiting_reasons": report["waiting_reasons"],
        "block_reasons": report["block_reasons"],
        "separate_runtime_enablement_request_required": True,
        "separate_runtime_enablement_validation_required": True,
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
    summary["p23_operator_accepted_release_candidate_handoff_summary_sha256"] = sha256_json(summary)
    atomic_write_json(latest / "p23_operator_accepted_release_candidate_handoff_summary.json", summary)
    registry_record = append_registry_record(
        registry_path(cfg, P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_REGISTRY_NAME),
        report,
        registry_name=P23_OPERATOR_ACCEPTED_RELEASE_CANDIDATE_HANDOFF_REGISTRY_NAME,
        id_field="p23_operator_accepted_release_candidate_handoff_registry_id",
        hash_field="p23_operator_accepted_release_candidate_handoff_registry_sha256",
        id_prefix="p23_operator_accepted_release_candidate_handoff",
    )
    atomic_write_json(latest / "p23_operator_accepted_release_candidate_handoff_registry_record.json", registry_record)
    return report


if __name__ == "__main__":
    result = persist_operator_accepted_release_candidate_handoff()
    print(result["status"])
    print(result["p23_operator_accepted_release_candidate_handoff_sha256"])
