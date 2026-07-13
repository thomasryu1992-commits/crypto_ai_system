from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import FALSE_FLAGS
from crypto_ai_system.validation.phase9_2_runtime_submit_action_boundary import (
    STATUS_RUNTIME_SUBMIT_ACTION_BOUNDARY_RECORDED_BLOCKED,
    persist_phase9_2_runtime_submit_action_boundary_report,
)
from crypto_ai_system.validation.phase10_signed_testnet_session_validation_blocked_design import (
    SESSION_METRICS_REQUIRED,
    SESSION_SCENARIOS_REQUIRED,
)

PHASE9_10_EVIDENCE_INTAKE_VERSION = "phase9_10_signed_testnet_evidence_intake_v1"
PHASE9_10_EVIDENCE_INTAKE_REGISTRY_NAME = "phase9_10_signed_testnet_evidence_intake_registry"
STATUS_PHASE9_10_EVIDENCE_INTAKE_RECORDED_REVIEW_ONLY = "PHASE9_10_SIGNED_TESTNET_EVIDENCE_INTAKE_RECORDED_REVIEW_ONLY"

REQUIRED_SOURCE_FILES = {
    "runtime_submit_action_boundary": "phase9_2_runtime_submit_action_boundary_report.json",
    "manual_final_confirmation": "phase9_2_manual_final_confirmation_report.json",
    "final_approval_package": "phase9_2_final_approval_package_report.json",
    "submit_guard_recheck": "phase9_2_submit_guard_recheck_after_operator_fixture_report.json",
}

UNSAFE_TRUE_FIELDS = list(FALSE_FLAGS) + [
    "runtime_submit_action_approved",
    "runtime_submit_action_executed",
    "runtime_submit_action_performed",
    "runtime_authority_granted",
    "phase9_2_real_submit_authorized",
    "phase9_2_order_submission_authorized",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "phase10_signed_testnet_session_validation_may_begin",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
    "reconciliation_started",
    "phase10_session_validation_started",
    "live_canary_preparation_may_begin",
]

EVIDENCE_TEMPLATE_FILES = {
    "phase9_2_execution": "phase9_2_single_testnet_order_execution_EVIDENCE_TEMPLATE_REVIEW_ONLY.json",
    "phase9_3_status_cancel": "phase9_3_status_cancel_session_EVIDENCE_TEMPLATE_REVIEW_ONLY.json",
    "phase9_4_reconciliation": "phase9_4_testnet_reconciliation_EVIDENCE_TEMPLATE_REVIEW_ONLY.json",
    "phase10_session_validation": "phase10_signed_testnet_session_validation_EVIDENCE_TEMPLATE_REVIEW_ONLY.json",
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


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / name, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _flag_false_payload() -> dict[str, bool]:
    return {field: False for field in FALSE_FLAGS}


def _unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in UNSAFE_TRUE_FIELDS if _safe_bool(data.get(field))]
    for field in unsafe_truthy_fields(data):
        if field not in fields:
            fields.append(field)
    return sorted(dict.fromkeys(fields))


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase9_2_runtime_submit_action_boundary_report_sha256",
        "phase9_2_manual_final_confirmation_report_sha256",
        "phase9_2_final_approval_package_report_sha256",
        "phase9_2_submit_guard_recheck_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _source_summary(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "artifact_name": name,
        "present": bool(data),
        "status": data.get("status") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data or _unsafe_fields(data):
        return False
    if name == "runtime_submit_action_boundary":
        return (
            data.get("status") == STATUS_RUNTIME_SUBMIT_ACTION_BOUNDARY_RECORDED_BLOCKED
            and data.get("runtime_submit_action_ready_for_explicit_submit_approval_review_only") is True
            and data.get("runtime_submit_action_approved") is False
            and data.get("runtime_submit_action_executed") is False
            and data.get("actual_order_submission_performed") is False
        )
    if name == "manual_final_confirmation":
        return (
            data.get("manual_final_confirmation_valid") is True
            and data.get("phase9_2_order_submission_authorized") is False
            and data.get("actual_order_submission_performed") is False
        )
    if name == "final_approval_package":
        return (
            data.get("final_approval_packet_valid") is True
            and data.get("phase9_2_ready_for_manual_final_confirmation") is True
            and data.get("phase9_2_order_submission_authorized") is False
        )
    if name == "submit_guard_recheck":
        return (
            data.get("phase9_2_submit_guard_recheck_ready") is True
            and data.get("phase9_2_order_submission_authorized") is False
            and data.get("phase9_3_status_polling_may_begin") is False
        )
    return True


def build_phase9_2_execution_evidence_template(*, source_summary: Mapping[str, Any], created_at_utc: str) -> dict[str, Any]:
    payload = {
        "artifact_type": "phase9_2_single_testnet_order_execution_evidence_template_review_only",
        "phase9_10_signed_testnet_evidence_intake_version": PHASE9_10_EVIDENCE_INTAKE_VERSION,
        "review_only": True,
        "template_for_operator_supplied_evidence": True,
        "source_evidence_hash_summary": dict(source_summary),
        "instructions": [
            "Populate this template only after a separately approved real signed testnet single order is executed outside this review-only package.",
            "Do not include API key values, API secret values, private keys, passphrases, or raw signed payload secrets.",
            "Keep max_order_count=1 and testnet_only=true.",
        ],
        "phase": "9.2",
        "expected_scope": "single_signed_testnet_order_only",
        "testnet_only": True,
        "max_order_count": 1,
        "exchange": None,
        "symbol": None,
        "side": None,
        "order_type": None,
        "quantity": None,
        "price": None,
        "max_notional": None,
        "idempotency_key": None,
        "client_order_id": None,
        "exchange_order_id": None,
        "submit_timestamp_utc": None,
        "response_timestamp_utc": None,
        "exchange_order_status": None,
        "api_latency_ms": None,
        "api_error": None,
        "normalized_error_code": None,
        "fee_asset": None,
        "fee_amount": None,
        "raw_exchange_response_redacted_path": None,
        "secret_value_included": False,
        "api_key_value_included": False,
        "api_secret_value_included": False,
        "private_key_included": False,
        "passphrase_included": False,
        "withdrawal_permission_allowed": False,
        "mainnet_key_scope_allowed": False,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        **_flag_false_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase9_2_execution_evidence_template_sha256"] = sha256_json(payload)
    return payload


def build_phase9_3_status_cancel_evidence_template(*, phase9_2_template_hash: str, created_at_utc: str) -> dict[str, Any]:
    payload = {
        "artifact_type": "phase9_3_status_cancel_session_evidence_template_review_only",
        "phase9_10_signed_testnet_evidence_intake_version": PHASE9_10_EVIDENCE_INTAKE_VERSION,
        "review_only": True,
        "source_phase9_2_execution_evidence_template_sha256": phase9_2_template_hash,
        "phase": "9.3",
        "requires_real_phase9_2_exchange_order_id": True,
        "exchange_order_id": None,
        "client_order_id": None,
        "status_polling_events": [],
        "allowed_status_values": ["submitted", "accepted", "rejected", "partial_fill", "full_fill", "cancel_requested", "cancel_accepted", "cancel_rejected", "expired", "final"],
        "cancel_requested": False,
        "cancel_request_timestamp_utc": None,
        "cancel_response_timestamp_utc": None,
        "final_status": None,
        "session_closed_at_utc": None,
        "api_latency_ms_by_event": [],
        "api_errors": [],
        "rate_limit_events": [],
        "duplicate_cancel_prevented": True,
        "secret_value_included": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "cancel_request_sent": False,
        "phase9_4_testnet_reconciliation_may_begin": False,
        **_flag_false_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase9_3_status_cancel_evidence_template_sha256"] = sha256_json(payload)
    return payload


def build_phase9_4_reconciliation_evidence_template(*, phase9_3_template_hash: str, created_at_utc: str) -> dict[str, Any]:
    payload = {
        "artifact_type": "phase9_4_testnet_reconciliation_evidence_template_review_only",
        "phase9_10_signed_testnet_evidence_intake_version": PHASE9_10_EVIDENCE_INTAKE_VERSION,
        "review_only": True,
        "source_phase9_3_status_cancel_evidence_template_sha256": phase9_3_template_hash,
        "phase": "9.4",
        "requires_phase9_3_final_status": True,
        "exchange_order_status": None,
        "local_execution_record_id": None,
        "position_delta_expected": None,
        "position_delta_actual": None,
        "balance_delta_expected": None,
        "balance_delta_actual": None,
        "expected_fee": None,
        "actual_fee": None,
        "expected_slippage_bps": None,
        "actual_slippage_bps": None,
        "expected_fill_price": None,
        "actual_fill_price": None,
        "expected_notional": None,
        "actual_notional": None,
        "partial_fill_detected": False,
        "rejected_order_detected": False,
        "cancel_result_detected": False,
        "reconciliation_mismatch_detected": None,
        "unresolved_mismatch": None,
        "mismatch_blocks_promotion": True,
        "phase10_signed_testnet_session_validation_may_begin": False,
        "reconciliation_started": False,
        **_flag_false_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase9_4_reconciliation_evidence_template_sha256"] = sha256_json(payload)
    return payload


def build_phase10_session_validation_evidence_template(*, phase9_4_template_hash: str, created_at_utc: str) -> dict[str, Any]:
    payload = {
        "artifact_type": "phase10_signed_testnet_session_validation_evidence_template_review_only",
        "phase9_10_signed_testnet_evidence_intake_version": PHASE9_10_EVIDENCE_INTAKE_VERSION,
        "review_only": True,
        "source_phase9_4_reconciliation_evidence_template_sha256": phase9_4_template_hash,
        "phase": "10",
        "requires_multiple_clean_signed_testnet_sessions": True,
        "required_session_scenarios": SESSION_SCENARIOS_REQUIRED,
        "required_session_metrics": SESSION_METRICS_REQUIRED,
        "session_records": [],
        "minimum_session_count_required_before_live_canary_preparation": 6,
        "clean_session_count": 0,
        "unresolved_reconciliation_mismatch_count": None,
        "paper_testnet_gap_summary": None,
        "api_error_rate_summary": None,
        "promotion_review_packet_created": False,
        "live_canary_preparation_may_begin": False,
        "phase10_signed_testnet_session_validation_may_begin": False,
        "phase10_session_validation_started": False,
        **_flag_false_payload(),
        "created_at_utc": created_at_utc,
    }
    payload["phase10_session_validation_evidence_template_sha256"] = sha256_json(payload)
    return payload


def validate_phase9_10_evidence_templates(templates: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    blockers: list[str] = []
    unsafe: dict[str, list[str]] = {}
    required = set(EVIDENCE_TEMPLATE_FILES)
    missing = [name for name in required if not templates.get(name)]
    for name in missing:
        blockers.append(f"PHASE9_10_EVIDENCE_TEMPLATE_MISSING:{name}")
    for name, payload in templates.items():
        data = dict(payload or {})
        fields = _unsafe_fields(data)
        if fields:
            unsafe[name] = fields
            blockers.append(f"PHASE9_10_EVIDENCE_TEMPLATE_UNSAFE_FLAGS:{name}:{','.join(fields)}")
        if data.get("review_only") is not True:
            blockers.append(f"PHASE9_10_EVIDENCE_TEMPLATE_NOT_REVIEW_ONLY:{name}")
        if data.get("secret_value_included") is True or data.get("api_secret_value_included") is True:
            blockers.append(f"PHASE9_10_EVIDENCE_TEMPLATE_SECRET_INCLUDED:{name}")
    if templates.get("phase9_2_execution", {}).get("max_order_count") != 1:
        blockers.append("PHASE9_2_EXECUTION_EVIDENCE_TEMPLATE_MAX_ORDER_COUNT_NOT_ONE")
    valid = not blockers
    return {
        "artifact_type": "phase9_10_signed_testnet_evidence_intake_validation_report",
        "phase9_10_signed_testnet_evidence_templates_valid": valid,
        "blocked": not valid,
        "fail_closed": not valid,
        "missing_templates": missing,
        "unsafe_template_flags": unsafe,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "phase9_2_actual_submit_performed_by_this_package": False,
        "phase9_3_status_polling_started_by_this_package": False,
        "phase9_4_reconciliation_started_by_this_package": False,
        "phase10_session_validation_started_by_this_package": False,
        **_flag_false_payload(),
    }


def _build_negative_fixture_results(templates: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    cases: dict[str, tuple[str, dict[str, Any]]] = {
        "order_endpoint_called_true": ("phase9_2_execution", {"order_endpoint_called": True}),
        "http_request_sent_true": ("phase9_2_execution", {"http_request_sent": True}),
        "signature_created_true": ("phase9_2_execution", {"signature_created": True}),
        "secret_value_included_true": ("phase9_2_execution", {"secret_value_included": True}),
        "max_order_count_gt_one": ("phase9_2_execution", {"max_order_count": 2}),
        "status_polling_may_begin_true": ("phase9_3_status_cancel", {"phase9_3_status_polling_may_begin": True}),
        "reconciliation_may_begin_true": ("phase9_4_reconciliation", {"phase9_4_testnet_reconciliation_may_begin": True}),
        "phase10_may_begin_true": ("phase10_session_validation", {"phase10_signed_testnet_session_validation_may_begin": True}),
        "live_canary_preparation_true": ("phase10_session_validation", {"live_canary_preparation_may_begin": True}),
    }
    results: dict[str, dict[str, Any]] = {}
    for name, (template_name, patch) in cases.items():
        mutated = {k: dict(v) for k, v in templates.items()}
        mutated[template_name].update(patch)
        validation = validate_phase9_10_evidence_templates(mutated)
        results[name] = {
            "fixture_name": name,
            "blocked": validation["blocked"],
            "fail_closed": validation["fail_closed"],
            "block_reasons": validation["block_reasons"],
        }
    all_blocked = all(r["blocked"] and r["fail_closed"] for r in results.values())
    payload = {
        "artifact_type": "phase9_10_signed_testnet_evidence_intake_negative_fixture_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **_flag_false_payload(),
        "actual_order_submission_performed": False,
    }
    payload["phase9_10_signed_testnet_evidence_intake_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def build_phase9_10_signed_testnet_evidence_intake_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_runtime_boundary_first: bool = True
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    if run_runtime_boundary_first:
        persist_phase9_2_runtime_submit_action_boundary_report(cfg=cfg, run_manual_confirmation_first=True)
    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if payload and not _source_ready(name, payload)]
    unsafe_source_flags = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}
    created = utc_now_canonical()
    phase9_2 = build_phase9_2_execution_evidence_template(source_summary=source_summary, created_at_utc=created)
    phase9_3 = build_phase9_3_status_cancel_evidence_template(
        phase9_2_template_hash=phase9_2["phase9_2_execution_evidence_template_sha256"], created_at_utc=created
    )
    phase9_4 = build_phase9_4_reconciliation_evidence_template(
        phase9_3_template_hash=phase9_3["phase9_3_status_cancel_evidence_template_sha256"], created_at_utc=created
    )
    phase10 = build_phase10_session_validation_evidence_template(
        phase9_4_template_hash=phase9_4["phase9_4_reconciliation_evidence_template_sha256"], created_at_utc=created
    )
    templates = {
        "phase9_2_execution": phase9_2,
        "phase9_3_status_cancel": phase9_3,
        "phase9_4_reconciliation": phase9_4,
        "phase10_session_validation": phase10,
    }
    validation = validate_phase9_10_evidence_templates(templates)
    negative_fixture_results = _build_negative_fixture_results(templates)
    blockers: list[str] = []
    if missing:
        blockers.extend(f"PHASE9_10_REQUIRED_SOURCE_MISSING:{name}" for name in missing)
    if not_ready:
        blockers.extend(f"PHASE9_10_REQUIRED_SOURCE_NOT_READY:{name}" for name in not_ready)
    if validation["blocked"]:
        blockers.extend(validation["block_reasons"])
    if not negative_fixture_results["all_negative_fixtures_blocked_fail_closed"]:
        blockers.append("PHASE9_10_NEGATIVE_FIXTURES_DID_NOT_ALL_BLOCK_FAIL_CLOSED")
    blockers.append("PHASE9_10_EVIDENCE_INTAKE_DOES_NOT_EXECUTE_ORDERS_OR_POLL_ENDPOINTS")
    blockers.append("PHASE9_10_REAL_EVIDENCE_MUST_BE_SUPPLIED_AFTER_SEPARATE_RUNTIME_SUBMIT_ACTION")
    report = {
        "phase9_10_signed_testnet_evidence_intake_id": stable_id("phase9_10_signed_testnet_evidence_intake", source_summary),
        "phase9_10_signed_testnet_evidence_intake_version": PHASE9_10_EVIDENCE_INTAKE_VERSION,
        "status": STATUS_PHASE9_10_EVIDENCE_INTAKE_RECORDED_REVIEW_ONLY,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "phase9_10_evidence_intake_recorded": True,
        "phase9_2_execution_evidence_template_ready": True,
        "phase9_3_status_cancel_evidence_template_ready": True,
        "phase9_4_reconciliation_evidence_template_ready": True,
        "phase10_session_validation_evidence_template_ready": True,
        "phase9_10_evidence_templates_valid": validation["phase9_10_signed_testnet_evidence_templates_valid"],
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_source_flags": unsafe_source_flags,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "recommended_next_action": "run_separate_real_phase9_2_single_testnet_submit_only_after_explicit_runtime_approval_then_fill_evidence_templates",
        "phase9_2_actual_submit_performed_by_this_package": False,
        "phase9_3_status_polling_started_by_this_package": False,
        "phase9_4_reconciliation_started_by_this_package": False,
        "phase10_session_validation_started_by_this_package": False,
        "phase10_signed_testnet_session_validation_may_begin": False,
        "live_canary_preparation_may_begin": False,
        **_flag_false_payload(),
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "cancel_request_sent": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "actual_order_submission_performed": False,
        "created_at_utc": created,
    }
    report["phase9_10_signed_testnet_evidence_intake_report_sha256"] = sha256_json(report)
    return report, templates, validation, negative_fixture_results


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9-10 Signed Testnet Evidence Intake - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This package prepares the evidence templates needed to verify Phase 9.2/9.3/9.4/10 after a separately approved real signed testnet single-order action.",
            "",
            "## What this package does",
            "",
            "- Creates execution/status/reconciliation/session evidence templates.",
            "- Validates that evidence collection remains review-only.",
            "- Blocks any endpoint, signature, HTTP, secret, or order-submission flag.",
            "",
            "## What this package does not do",
            "",
            "- It does not submit orders.",
            "- It does not poll status endpoints.",
            "- It does not send cancel requests.",
            "- It does not reconcile a real order.",
            "- It does not start Phase 10 sessions.",
            "",
            "## Next required evidence",
            "",
            "- Real Phase 9.2 single signed testnet order evidence.",
            "- Phase 9.3 status/cancel session close evidence.",
            "- Phase 9.4 reconciliation evidence with no unresolved mismatch.",
            "- Multiple Phase 10 signed testnet session records before any live canary preparation.",
            "",
            "## Still Disabled",
            "",
            "- `actual_order_submission_performed=false`",
            "- `order_endpoint_called=false`",
            "- `order_status_endpoint_called=false`",
            "- `cancel_endpoint_called=false`",
            "- `signature_created=false`",
            "- `http_request_sent=false`",
            "",
        ]
    )


def persist_phase9_10_signed_testnet_evidence_intake_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_runtime_boundary_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_10_signed_testnet_evidence_intake")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, templates, validation, negative_fixture_results = build_phase9_10_signed_testnet_evidence_intake_report(
        cfg=cfg, run_runtime_boundary_first=run_runtime_boundary_first
    )
    handoff = _build_handoff_markdown(report)
    for base in (latest, phase_dir, signed_testnet_dir):
        atomic_write_json(base / "phase9_10_signed_testnet_evidence_intake_report.json", report)
        atomic_write_json(base / "phase9_10_signed_testnet_evidence_intake_validation_report.json", validation)
        atomic_write_json(base / "phase9_10_signed_testnet_evidence_intake_negative_fixture_results.json", negative_fixture_results)
        for key, filename in EVIDENCE_TEMPLATE_FILES.items():
            atomic_write_json(base / filename, templates[key])
        (base / "PHASE9_10_SIGNED_TESTNET_EVIDENCE_INTAKE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_10_EVIDENCE_INTAKE_REGISTRY_NAME),
        {
            "phase9_10_signed_testnet_evidence_intake_id": report.get("phase9_10_signed_testnet_evidence_intake_id"),
            "status": report.get("status"),
            "blocked": True,
            "fail_closed": True,
            "phase9_10_evidence_intake_recorded": True,
            "actual_order_submission_performed": False,
            "phase10_signed_testnet_session_validation_may_begin": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_10_EVIDENCE_INTAKE_REGISTRY_NAME,
        id_field="phase9_10_signed_testnet_evidence_intake_registry_record_id",
        hash_field="phase9_10_signed_testnet_evidence_intake_registry_record_sha256",
        id_prefix="phase9_10_signed_testnet_evidence_intake_registry_record",
    )
    atomic_write_json(latest / "phase9_10_signed_testnet_evidence_intake_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_10_signed_testnet_evidence_intake_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_10_EVIDENCE_INTAKE_VERSION",
    "STATUS_PHASE9_10_EVIDENCE_INTAKE_RECORDED_REVIEW_ONLY",
    "EVIDENCE_TEMPLATE_FILES",
    "build_phase9_10_signed_testnet_evidence_intake_report",
    "persist_phase9_10_signed_testnet_evidence_intake_report",
    "validate_phase9_10_evidence_templates",
]
