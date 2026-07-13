from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_VERSION = "phase9_2_final_pre_submit_checklist_v1"
PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_REGISTRY_NAME = "phase9_2_final_pre_submit_checklist_registry"
STATUS_BLOCKED = "PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_BLOCKED_NO_ORDER_SUBMIT_REVIEW_ONLY"
STATUS_READY_FOR_SEPARATE_APPROVAL = "PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_READY_FOR_SEPARATE_ONE_ORDER_APPROVAL_REVIEW_ONLY"

EXECUTION_FALSE_FLAGS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "external_order_submission_performed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "runtime_authority_granted",
    "runtime_submit_action_approved",
    "runtime_submit_action_executed",
    "runtime_submit_action_performed",
    "phase9_2_real_submit_authorized",
    "phase9_2_order_submission_authorized",
    "phase9_3_status_polling_may_begin",
    "phase9_4_testnet_reconciliation_may_begin",
    "phase10_signed_testnet_session_validation_may_begin",
    "live_canary_preparation_may_begin",
    "order_endpoint_called",
    "order_status_endpoint_called",
    "cancel_endpoint_called",
    "cancel_request_sent",
    "private_account_endpoint_called",
    "balance_endpoint_called",
    "position_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "actual_order_submission_performed",
    "real_exchange_endpoint_call_performed",
    "real_testnet_order_endpoint_called",
    "api_key_value_logged",
    "api_secret_value_logged",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
    "executor_enable_performed",
    "runtime_settings_mutated",
    "score_weights_mutated",
]

REQUIRED_REPORTS = {
    "manual_final_confirmation": "phase9_2_manual_final_confirmation_report.json",
    "runtime_submit_boundary": "phase9_2_runtime_submit_action_boundary_report.json",
    "real_submit_enablement_gate": "phase9_2_real_submit_enablement_gate_report.json",
    "endpoint_time_risk_refresh": "phase9_2_endpoint_time_risk_refresh_report.json",
    "secret_manager_runtime_binding": "phase9_2_secret_manager_runtime_binding_report.json",
    "executor_endpoint_policy_readiness": "phase9_2_executor_endpoint_policy_readiness_report.json",
    "runtime_submit_wrapper": "phase9_2_single_testnet_runtime_submit_wrapper_report.json",
    "mock_submit_evidence_flow": "phase9_2_mock_submit_evidence_flow_report.json",
    "real_testnet_endpoint_preflight": "phase9_2_real_testnet_endpoint_adapter_preflight_report.json",
    "real_testnet_network_dry_probe": "phase9_2_real_testnet_network_dry_probe_report.json",
    "public_metadata_result_intake": "phase9_2_public_metadata_network_dry_probe_result_intake_report.json",
    "public_metadata_filled_validation": "phase9_2_public_metadata_probe_result_filled_validation_report.json",
    "real_public_metadata_probe_command": "phase9_2_real_public_metadata_probe_command_report.json",
    "public_metadata_probe_bridge": "phase9_2_public_metadata_probe_bridge_report.json",
}

PHASE9_2_CLOSE_CRITERIA = [
    "Phase 9.2 public metadata probe command exists and is no-order-submit scoped.",
    "Phase 9.2 public metadata probe bridge exists and keeps real_testnet_submit_may_begin=false.",
    "A real operator-run public metadata probe result validates successfully, not sample/synthetic/mock data.",
    "Final pre-submit checklist records all remaining blockers and does not unlock order submission.",
    "Separate explicit one-order runtime submit approval is collected outside this review-only checklist.",
    "Fresh endpoint-time hot-path risk refresh is required immediately before any real submit action.",
    "Runtime secret binding remains metadata-only in artifacts; secret values are never stored or logged.",
    "One-order-only duplicate submit lock and post-submit relock are required by the runtime submit wrapper.",
]


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


def _disabled_payload() -> dict[str, bool]:
    return {field: False for field in EXECUTION_FALSE_FLAGS}


def _is_true(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _report_summary(cfg: AppConfig) -> dict[str, Any]:
    latest = _latest_dir(cfg)
    summaries: dict[str, Any] = {}
    for key, filename in REQUIRED_REPORTS.items():
        path = latest / filename
        data = _read_latest_json(cfg, filename)
        summaries[key] = {
            "filename": filename,
            "exists": path.exists(),
            "status": data.get("status"),
            "blocked": data.get("blocked"),
            "fail_closed": data.get("fail_closed"),
            "review_only": data.get("review_only"),
            "no_order_submit": data.get("no_order_submit"),
            "real_testnet_submit_may_begin": data.get("real_testnet_submit_may_begin"),
            "real_testnet_metadata_conditions_ready_for_submit_review_only": data.get("real_testnet_metadata_conditions_ready_for_submit_review_only"),
            "block_reasons": data.get("block_reasons", []),
        }
    return summaries


def _unsafe_true_fields(reports: Mapping[str, Any]) -> list[str]:
    unsafe: list[str] = []
    for _name, summary in reports.items():
        filename = summary.get("filename")
        data = summary if isinstance(summary, Mapping) else {}
        for field in EXECUTION_FALSE_FLAGS:
            if _is_true(data.get(field)):
                unsafe.append(f"{filename}:{field}")
    return sorted(set(unsafe))


def build_phase9_2_final_pre_submit_checklist(*, cfg: AppConfig | None = None, created_at_utc: str | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    created_at_utc = created_at_utc or utc_now_canonical()
    reports = _report_summary(cfg)
    missing = [name for name, summary in reports.items() if not summary.get("exists")]
    unsafe_true_fields = _unsafe_true_fields(reports)

    bridge = reports.get("public_metadata_probe_bridge", {})
    filled = reports.get("public_metadata_filled_validation", {})
    metadata_ready = bool(
        bridge.get("real_testnet_metadata_conditions_ready_for_submit_review_only") is True
        and filled.get("real_testnet_metadata_conditions_ready_for_submit_review_only") is True
    )
    bridge_validated = bool(bridge.get("real_testnet_metadata_conditions_ready_for_submit_review_only") is True)
    filled_validated = bool(filled.get("real_testnet_metadata_conditions_ready_for_submit_review_only") is True)

    blockers: list[str] = []
    if missing:
        blockers.append("PHASE9_2_FINAL_PRE_SUBMIT_MISSING_REQUIRED_REPORTS:" + ",".join(sorted(missing)))
    if unsafe_true_fields:
        blockers.append("PHASE9_2_FINAL_PRE_SUBMIT_UNSAFE_TRUE_FLAGS:" + ",".join(unsafe_true_fields))
    if not bridge_validated:
        blockers.append("PHASE9_2_FINAL_PRE_SUBMIT_PUBLIC_METADATA_BRIDGE_NOT_VALIDATED")
    if not filled_validated:
        blockers.append("PHASE9_2_FINAL_PRE_SUBMIT_OPERATOR_FILLED_METADATA_RESULT_NOT_VALIDATED")
    if not metadata_ready:
        blockers.append("PHASE9_2_FINAL_PRE_SUBMIT_REAL_PUBLIC_METADATA_CONDITIONS_NOT_READY")

    # These are deliberate blockers/reminders. This checklist never grants submit authority.
    blockers.extend([
        "PHASE9_2_FINAL_PRE_SUBMIT_SEPARATE_EXPLICIT_ONE_ORDER_RUNTIME_APPROVAL_REQUIRED",
        "PHASE9_2_FINAL_PRE_SUBMIT_FRESH_HOT_PATH_RISK_REFRESH_REQUIRED_AT_ACTION_TIME",
        "PHASE9_2_FINAL_PRE_SUBMIT_RUNTIME_SECRET_BINDING_REQUIRED_AT_ACTION_TIME_METADATA_ONLY_IN_ARTIFACTS",
        "PHASE9_2_FINAL_PRE_SUBMIT_OPERATOR_LOCAL_EXECUTION_REQUIRED_FOR_ANY_REAL_TESTNET_SUBMIT",
    ])

    ready_for_separate_approval_review_only = bool(metadata_ready and not missing and not unsafe_true_fields)
    report_id = stable_id("phase9_2_final_pre_submit_checklist", {
        "reports": reports,
        "metadata_ready": metadata_ready,
        "version": PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_VERSION,
    }, 24)
    report: dict[str, Any] = {
        "artifact_type": "phase9_2_final_pre_submit_checklist_report",
        "phase9_2_final_pre_submit_checklist_id": report_id,
        "phase9_2_final_pre_submit_checklist_version": PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_VERSION,
        "status": STATUS_READY_FOR_SEPARATE_APPROVAL if ready_for_separate_approval_review_only else STATUS_BLOCKED,
        "blocked": True,
        "fail_closed": True,
        "review_only": True,
        "no_order_submit": True,
        "phase": "9.2",
        "phase9_2_close_recommendation": "close_phase9_2_after_real_public_metadata_probe_success_and_final_checklist_review_then_move_to_separate_one_order_submit_approval",
        "phase9_2_should_continue_count_estimate": "1_to_2_more_packages_before_actual_single_testnet_submit_decision",
        "phase9_2_close_criteria": PHASE9_2_CLOSE_CRITERIA,
        "required_report_summaries": reports,
        "missing_required_reports": missing,
        "unsafe_true_fields": unsafe_true_fields,
        "public_metadata_bridge_validated": bridge_validated,
        "operator_filled_metadata_result_validated": filled_validated,
        "real_testnet_metadata_conditions_ready_for_submit_review_only": metadata_ready,
        "ready_for_separate_one_order_runtime_approval_review_only": ready_for_separate_approval_review_only,
        "real_testnet_submit_may_begin": False,
        "phase9_2_order_submission_authorized": False,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "order_status_endpoint_called": False,
        "cancel_endpoint_called": False,
        "private_account_endpoint_called": False,
        "balance_endpoint_called": False,
        "position_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "secret_value_accessed": False,
        "executor_enable_performed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "next_action": "operator_runs_real_public_metadata_probe_locally_or_prepare_separate_one_order_runtime_submit_runbook_after_valid_probe",
        "block_reasons": blockers,
        **_disabled_payload(),
        "created_at_utc": created_at_utc,
    }
    report["phase9_2_final_pre_submit_checklist_report_sha256"] = sha256_json(report)
    return report


def persist_phase9_2_final_pre_submit_checklist(*, cfg: AppConfig | None = None, created_at_utc: str | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_phase9_2_final_pre_submit_checklist(cfg=cfg, created_at_utc=created_at_utc)
    latest = _latest_dir(cfg)
    signed_testnet = _storage_dir(cfg, "storage/signed_testnet")
    for directory in (latest, signed_testnet):
        atomic_write_json(directory / "phase9_2_final_pre_submit_checklist_report.json", report)
        handoff = "\n".join([
            "# Phase 9.2 Final Pre-Submit Checklist / No Order Submit",
            "",
            "This checklist summarizes Phase 9.2 completion status and remaining blockers before any separate one-order signed testnet submit action.",
            "It never submits orders, calls order/private endpoints, creates signatures, reads secrets, enables executors, or mutates runtime settings.",
            "A valid public metadata probe is evidence only. It does not automatically unlock testnet submit.",
        ])
        (directory / "PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_HANDOFF_NO_ORDER_SUBMIT_REVIEW_ONLY.md").write_text(handoff + "\n", encoding="utf-8")
    record = append_registry_record(
        registry_path(cfg, PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_REGISTRY_NAME),
        {
            "artifact_type": report["artifact_type"],
            "artifact_id": report["phase9_2_final_pre_submit_checklist_id"],
            "status": report["status"],
            "blocked": report["blocked"],
            "fail_closed": report["fail_closed"],
            "review_only": True,
            "no_order_submit": True,
            "sha256": report["phase9_2_final_pre_submit_checklist_report_sha256"],
            "created_at_utc": report["created_at_utc"],
        },
        registry_name=PHASE9_2_FINAL_PRE_SUBMIT_CHECKLIST_REGISTRY_NAME,
        id_field="phase9_2_final_pre_submit_checklist_registry_id",
        hash_field="phase9_2_final_pre_submit_checklist_registry_record_sha256",
        id_prefix="phase9_2_final_pre_submit_checklist_registry",
    )
    atomic_write_json(latest / "phase9_2_final_pre_submit_checklist_registry_record.json", record)
    return report


def build_negative_fixture_results() -> dict[str, Any]:
    fixtures = {
        "metadata_not_validated": {"metadata_ready": False, "unsafe_true_fields": []},
        "order_endpoint_called_true": {"metadata_ready": True, "unsafe_true_fields": ["order_endpoint_called"]},
        "signature_created_true": {"metadata_ready": True, "unsafe_true_fields": ["signature_created"]},
        "submit_allowed_true": {"metadata_ready": True, "unsafe_true_fields": ["real_testnet_submit_may_begin"]},
    }
    results = {}
    for name, payload in fixtures.items():
        reasons = []
        if not payload["metadata_ready"]:
            reasons.append("PHASE9_2_FINAL_PRE_SUBMIT_REAL_PUBLIC_METADATA_CONDITIONS_NOT_READY")
        if payload["unsafe_true_fields"]:
            reasons.append("PHASE9_2_FINAL_PRE_SUBMIT_UNSAFE_TRUE_FLAGS:" + ",".join(payload["unsafe_true_fields"]))
        results[name] = {"fixture_name": name, "blocked": bool(reasons), "fail_closed": bool(reasons), "block_reasons": reasons}
    output = {
        "artifact_type": "phase9_2_final_pre_submit_checklist_negative_fixture_results",
        "review_only": True,
        "no_order_submit": True,
        "all_negative_fixtures_blocked_fail_closed": all(v["blocked"] and v["fail_closed"] for v in results.values()),
        "fixture_results": results,
        "real_testnet_submit_may_begin": False,
        **_disabled_payload(),
        "created_at_utc": utc_now_canonical(),
    }
    output["phase9_2_final_pre_submit_checklist_negative_fixture_results_sha256"] = sha256_json(output)
    return output
