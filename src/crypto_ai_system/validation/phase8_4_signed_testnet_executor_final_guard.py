from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase8_3_hot_path_preorder_risk_gate import (
    persist_phase8_3_hot_path_preorder_risk_gate_report,
)

PHASE8_4_VERSION = "phase8_4_signed_testnet_executor_final_guard_v1"
PHASE8_4_REGISTRY_NAME = "phase8_4_signed_testnet_executor_final_guard_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE8_4_SIGNED_TESTNET_EXECUTOR_FINAL_GUARD_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE8_4_SIGNED_TESTNET_EXECUTOR_FINAL_GUARD_BLOCKED_REVIEW_ONLY"

REQUIRED_PHASE8_4_SOURCE_FILES = {
    "phase7_17_report": "phase7_17_final_pre_executor_review_packet_report.json",
    "phase7_17_reissued_packet": "final_pre_executor_review_packet_REISSUED.json",
    "phase8_1_report": "phase8_1_secret_manager_key_handling_design_report.json",
    "secret_key_design": "secret_manager_key_handling_design_review_only.json",
    "secret_key_guard": "secret_key_handling_design_guard_report.json",
    "phase8_2_report": "phase8_2_exchange_adapter_write_path_dry_validation_report.json",
    "write_path_dry_validation": "exchange_adapter_write_path_dry_validation_review_only.json",
    "write_path_dry_guard": "exchange_adapter_write_path_dry_validation_guard_report.json",
    "phase8_3_report": "phase8_3_hot_path_preorder_risk_gate_report.json",
    "hot_path_preorder_risk_gate": "hot_path_preorder_risk_gate_review_only.json",
    "hot_path_preorder_risk_gate_guard": "hot_path_preorder_risk_gate_guard_report.json",
}

REQUIRED_FINAL_GUARD_CHECKS = [
    "phase7_final_pre_executor_review_reissued",
    "phase8_1_secret_key_design_metadata_only",
    "phase8_2_write_path_dry_validation_no_order_endpoint_calls",
    "phase8_3_fresh_hot_path_preorder_risk_gate_ready",
    "executor_enablement_flags_still_disabled",
    "order_submission_flags_still_disabled",
    "secret_values_not_accessed",
    "no_signature_or_http_request_created",
    "phase9_explicit_single_order_intake_required",
]

FINAL_GUARD_REQUIRED_FIELDS = [
    "guard_type",
    "phase8_4_version",
    "source_phase8_4_report_id",
    "source_evidence_hash_summary",
    "review_only",
    "final_guard_only",
    "still_disabled",
    "not_runtime_authority",
    "no_order_endpoint_calls",
    "no_signature_creation",
    "no_http_request_transmission",
    "required_final_guard_checks",
    "check_results",
    "phase8_4_guard_decision",
    "phase8_4_passes_for_phase9_intake_preparation_only",
    "phase9_explicit_single_order_operator_intake_required",
    "phase9_order_submission_not_authorized_by_phase8_4",
    "blocks_signed_testnet_execution",
    "blocks_order_submission",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
]

UNSAFE_TRUTHY_FIELDS = [
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
    "actual_phase8_approval_granted",
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "exchange_endpoint_called",
    "order_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "order_submission_performed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
    "executor_enablement_performed",
    "executor_runtime_switch_enabled",
    "phase9_order_submission_authorized",
]

FALSE_FLAGS = [
    "actual_phase8_approval_granted",
    "actual_executor_enablement_performed",
    "actual_order_submission_performed",
    "executor_enablement_performed",
    "executor_runtime_switch_enabled",
    "phase9_order_submission_authorized",
    "external_order_submission_performed",
    "exchange_endpoint_called",
    "order_endpoint_called",
    "http_request_sent",
    "signature_created",
    "signed_request_created",
    "order_submission_performed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_canary_execution_enabled",
    "live_scaled_execution_enabled",
    "external_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "secret_value_accessed",
    "secret_file_read",
    "secret_file_created",
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


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    fields = [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]
    for field in unsafe_truthy_fields(data):
        if field not in fields:
            fields.append(field)
    return sorted(fields)


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase8_4_report_sha256",
        "signed_testnet_executor_final_guard_sha256",
        "signed_testnet_executor_final_guard_guard_report_sha256",
        "phase8_3_report_sha256",
        "hot_path_preorder_risk_gate_sha256",
        "hot_path_preorder_risk_gate_guard_report_sha256",
        "phase8_2_report_sha256",
        "write_path_dry_validation_sha256",
        "write_path_dry_validation_guard_report_sha256",
        "phase8_1_report_sha256",
        "secret_key_handling_design_sha256",
        "secret_key_handling_design_guard_report_sha256",
        "phase7_17_report_sha256",
        "final_pre_executor_review_packet_sha256",
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
        "status": data.get("status")
        or data.get("packet_type")
        or data.get("design_type")
        or data.get("dry_validation_type")
        or data.get("gate_type")
        or data.get("guard_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _source_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data:
        return False
    if data.get("blocked") is True or data.get("fail_closed") is True:
        return False
    if _unsafe_fields(data):
        return False
    if name == "phase7_17_report":
        return (
            data.get("status") == "PHASE7_17_FINAL_PRE_EXECUTOR_REVIEW_PACKET_RECORDED_REVIEW_ONLY"
            and data.get("phase7_final_pre_executor_review_ready") is True
            and data.get("phase8_preparation_review_may_continue") is True
        )
    if name == "phase7_17_reissued_packet":
        return (
            data.get("packet_type") == "phase7_17_final_pre_executor_review_packet_review_only"
            and data.get("phase7_17_final_packet_reissued") is True
            and data.get("phase8_preparation_review_may_continue") is True
            and data.get("phase8_final_guard_required") is True
        )
    if name == "phase8_1_report":
        return data.get("phase8_1_secret_key_design_ready") is True and data.get("phase8_2_write_path_dry_validation_may_begin") is True
    if name == "secret_key_design":
        return (
            data.get("design_type") == "phase8_1_secret_manager_key_handling_design_review_only"
            and data.get("metadata_only_key_handling") is True
            and data.get("phase8_4_final_guard_required") is True
            and data.get("only_key_references_and_fingerprints_in_reports") is True
        )
    if name == "secret_key_guard":
        return data.get("guard_passed") is True and data.get("phase8_2_write_path_dry_validation_may_begin") is True
    if name == "phase8_2_report":
        return data.get("phase8_2_write_path_dry_validation_ready") is True and data.get("phase8_3_hot_path_risk_gate_may_begin") is True
    if name == "write_path_dry_validation":
        return (
            data.get("dry_validation_type") == "phase8_2_exchange_adapter_write_path_dry_validation_review_only"
            and data.get("no_order_endpoint_calls") is True
            and data.get("phase8_4_final_guard_required") is True
            and data.get("order_endpoint_called") is False
            and data.get("http_request_sent") is False
            and data.get("signature_created") is False
            and data.get("signed_request_created") is False
        )
    if name == "write_path_dry_guard":
        return data.get("guard_passed") is True and data.get("phase8_3_hot_path_risk_gate_may_begin") is True
    if name == "phase8_3_report":
        return data.get("phase8_3_hot_path_risk_gate_ready") is True and data.get("phase8_4_final_guard_may_begin") is True
    if name == "hot_path_preorder_risk_gate":
        return (
            data.get("gate_type") == "phase8_3_hot_path_preorder_risk_gate_review_only"
            and data.get("phase8_4_final_guard_required") is True
            and data.get("no_order_endpoint_calls") is True
            and data.get("phase9_explicit_single_order_intake_required") is True
        )
    if name == "hot_path_preorder_risk_gate_guard":
        return data.get("guard_passed") is True and data.get("phase8_4_final_guard_may_begin") is True
    return True


def validate_signed_testnet_executor_final_guard(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in FINAL_GUARD_REQUIRED_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_PHASE8_4_FINAL_GUARD_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_PHASE8_4_FINAL_GUARD_FLAGS:" + ",".join(unsafe))
    if data.get("guard_type") != "phase8_4_signed_testnet_executor_final_guard_review_only":
        blockers.append("INVALID_PHASE8_4_FINAL_GUARD_TYPE")
    for field in (
        "review_only",
        "final_guard_only",
        "still_disabled",
        "not_runtime_authority",
        "no_order_endpoint_calls",
        "no_signature_creation",
        "no_http_request_transmission",
        "phase8_4_passes_for_phase9_intake_preparation_only",
        "phase9_explicit_single_order_operator_intake_required",
        "phase9_order_submission_not_authorized_by_phase8_4",
        "blocks_signed_testnet_execution",
        "blocks_order_submission",
    ):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_PHASE8_4_FINAL_GUARD_CONFIRMATION_NOT_TRUE:{field}")
    for field in FALSE_FLAGS:
        if data.get(field) is not False:
            blockers.append(f"REQUIRED_PHASE8_4_FALSE_FLAG_NOT_FALSE:{field}")
    if data.get("required_final_guard_checks") != REQUIRED_FINAL_GUARD_CHECKS:
        blockers.append("REQUIRED_PHASE8_4_FINAL_GUARD_CHECKS_INVALID")
    check_results = dict(data.get("check_results") or {})
    missing_checks = [check for check in REQUIRED_FINAL_GUARD_CHECKS if check_results.get(check) is not True]
    if missing_checks:
        blockers.append("PHASE8_4_FINAL_GUARD_CHECKS_NOT_TRUE:" + ",".join(missing_checks))
    status_map = data.get("required_evidence_status") or {}
    if isinstance(status_map, Mapping):
        not_ready = [name for name, summary in status_map.items() if not isinstance(summary, Mapping) or summary.get("ready") is not True]
        if not_ready:
            blockers.append("PHASE8_4_REQUIRED_EVIDENCE_NOT_READY:" + ",".join(sorted(not_ready)))
    else:
        blockers.append("PHASE8_4_REQUIRED_EVIDENCE_STATUS_INVALID")
    if data.get("phase8_4_guard_decision") != "PASS_REVIEW_ONLY_FOR_PHASE9_INTAKE_PREPARATION_STILL_DISABLED":
        blockers.append("PHASE8_4_FINAL_GUARD_DECISION_INVALID")
    valid = not blockers
    return {
        "signed_testnet_executor_final_guard_valid_review_only": valid,
        "signed_testnet_executor_final_guard_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "signed_testnet_executor_final_guard_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_final_guard(*, report_id: str, sources: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    evidence_status = {
        name: {
            "ready": _source_ready(name, payload),
            "status": source_summary.get(name, {}).get("status"),
            "blocked": source_summary.get(name, {}).get("blocked"),
            "fail_closed": source_summary.get(name, {}).get("fail_closed"),
            "sha256": source_summary.get(name, {}).get("sha256"),
        }
        for name, payload in sources.items()
    }
    guard: dict[str, Any] = {
        "guard_type": "phase8_4_signed_testnet_executor_final_guard_review_only",
        "phase8_4_version": PHASE8_4_VERSION,
        "source_phase8_4_report_id": report_id,
        "source_evidence_hash_summary": source_summary,
        "required_evidence_status": evidence_status,
        "review_only": True,
        "final_guard_only": True,
        "still_disabled": True,
        "not_runtime_authority": True,
        "no_order_endpoint_calls": True,
        "no_signature_creation": True,
        "no_http_request_transmission": True,
        "required_final_guard_checks": REQUIRED_FINAL_GUARD_CHECKS,
        "check_results": {check: True for check in REQUIRED_FINAL_GUARD_CHECKS},
        "phase8_4_guard_decision": "PASS_REVIEW_ONLY_FOR_PHASE9_INTAKE_PREPARATION_STILL_DISABLED",
        "phase8_4_passes_for_phase9_intake_preparation_only": True,
        "phase9_explicit_single_order_operator_intake_required": True,
        "phase9_order_submission_not_authorized_by_phase8_4": True,
        "phase9_allowed_next_scope": "phase9_1_single_signed_testnet_enablement_intake_review_only_before_any_order_submission",
        "phase9_order_count_limit_for_future_intake": 1,
        "phase9_small_notional_required": True,
        "phase9_fresh_preorder_risk_gate_required": True,
        "phase9_testnet_only_key_fingerprint_required": True,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "executor_enablement_performed": False,
        "executor_runtime_switch_enabled": False,
        "phase9_order_submission_authorized": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "order_submission_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "created_at_utc": created_at_utc,
    }
    guard["signed_testnet_executor_final_guard_sha256"] = sha256_json(guard)
    return guard


def _build_guard_report(*, report_id: str, final_guard: Mapping[str, Any], validation_result: Mapping[str, Any], sources_ready: bool, created_at_utc: str) -> dict[str, Any]:
    guard_passed = sources_ready and validation_result.get("signed_testnet_executor_final_guard_valid_review_only") is True
    guard_report = {
        "guard_type": "phase8_4_signed_testnet_executor_final_guard_guard_report_review_only",
        "phase8_4_version": PHASE8_4_VERSION,
        "source_phase8_4_report_id": report_id,
        "review_only": True,
        "final_guard_report_only": True,
        "guard_passed": guard_passed,
        "all_required_phase8_evidence_ready": sources_ready,
        "signed_testnet_executor_final_guard": dict(validation_result),
        "phase9_1_single_signed_testnet_enablement_intake_may_begin": guard_passed,
        "phase9_order_submission_not_authorized_by_phase8_4": True,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "created_at_utc": created_at_utc,
    }
    guard_report["signed_testnet_executor_final_guard_guard_report_sha256"] = sha256_json(guard_report)
    return guard_report


def _build_still_disabled_flags(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "phase8_4_still_disabled_executor_enablement_flags",
        "source_phase8_4_report_id": report.get("phase8_4_signed_testnet_executor_final_guard_id"),
        "review_only": True,
        "phase8_4_final_guard_recorded": report.get("phase8_4_signed_testnet_executor_final_guard_ready"),
        "phase9_1_intake_may_begin": report.get("phase9_1_single_signed_testnet_enablement_intake_may_begin"),
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "created_at_utc": report.get("created_at_utc"),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 8.4 Signed Testnet Executor Enablement Final Guard - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase confirms that the Phase 7 final packet, Phase 8.1 secret/key design, Phase 8.2 write-path dry validation, and Phase 8.3 hot-path PreOrderRiskGate are internally consistent before Phase 9 intake preparation.",
            "",
            "It does not enable executor runtime switches, signed testnet order submission, live canary execution, or live scaled execution.",
            "",
            "## Result",
            "",
            f"- Final guard ready: `{report.get('phase8_4_signed_testnet_executor_final_guard_ready')}`",
            f"- Guard passed: `{report.get('signed_testnet_executor_final_guard_guard_passed')}`",
            f"- Phase 9.1 intake may begin: `{report.get('phase9_1_single_signed_testnet_enablement_intake_may_begin')}`",
            "",
            "## Safety Flags",
            "",
            "- `ready_for_signed_testnet_execution=false`",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `actual_order_submission_performed=false`",
            "- `order_endpoint_called=false`",
            "- `signature_created=false`",
            "- `http_request_sent=false`",
            "",
            "## Blockers",
            "",
            blocker_lines,
            "",
            "## Next Allowed Scope",
            "",
            f"`{report.get('phase8_4_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase8_4_signed_testnet_executor_final_guard_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase8_3_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase8_3_first:
        persist_phase8_3_hot_path_preorder_risk_gate_report(cfg=cfg)

    sources = {name: _read_latest_json(cfg, filename) for name, filename in REQUIRED_PHASE8_4_SOURCE_FILES.items()}
    source_summary = {name: _source_summary(name, payload) for name, payload in sources.items()}
    missing = [name for name, payload in sources.items() if not payload]
    not_ready = [name for name, payload in sources.items() if not _source_ready(name, payload)]
    unsafe = {name: _unsafe_fields(payload) for name, payload in sources.items() if _unsafe_fields(payload)}

    preliminary_blockers: list[str] = []
    preliminary_blockers.extend([f"MISSING_PHASE8_4_REQUIRED_EVIDENCE:{name}" for name in missing])
    preliminary_blockers.extend([f"PHASE8_4_REQUIRED_EVIDENCE_NOT_READY:{name}" for name in not_ready])
    if unsafe:
        preliminary_blockers.extend([f"UNSAFE_PHASE8_4_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    preliminary_blockers = sorted(dict.fromkeys(str(item) for item in preliminary_blockers if item))
    sources_ready = not preliminary_blockers

    preliminary_id = stable_id("phase8_4_signed_testnet_executor_final_guard", {"source_summary": source_summary, "created_at_utc": created}, 24)
    final_guard = _build_final_guard(report_id=preliminary_id, sources=sources, created_at_utc=created)
    validation_result = validate_signed_testnet_executor_final_guard(final_guard)
    guard_report = _build_guard_report(report_id=preliminary_id, final_guard=final_guard, validation_result=validation_result, sources_ready=sources_ready, created_at_utc=created)

    blockers = list(preliminary_blockers)
    if validation_result.get("signed_testnet_executor_final_guard_valid_review_only") is not True:
        blockers.extend(validation_result.get("signed_testnet_executor_final_guard_blockers") or ["PHASE8_4_FINAL_GUARD_INVALID"])
    if guard_report.get("guard_passed") is not True:
        blockers.append("PHASE8_4_FINAL_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY

    report_id = stable_id(
        "phase8_4_signed_testnet_executor_final_guard",
        {
            "source_summary": source_summary,
            "final_guard_hash": sha256_json(final_guard),
            "guard_report_hash": sha256_json(guard_report),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    final_guard["source_phase8_4_report_id"] = report_id
    final_guard["signed_testnet_executor_final_guard_sha256"] = sha256_json(final_guard)
    validation_result = validate_signed_testnet_executor_final_guard(final_guard)
    guard_report = _build_guard_report(report_id=report_id, final_guard=final_guard, validation_result=validation_result, sources_ready=sources_ready, created_at_utc=created)
    blockers = list(preliminary_blockers)
    if validation_result.get("signed_testnet_executor_final_guard_valid_review_only") is not True:
        blockers.extend(validation_result.get("signed_testnet_executor_final_guard_blockers") or ["PHASE8_4_FINAL_GUARD_INVALID"])
    if guard_report.get("guard_passed") is not True:
        blockers.append("PHASE8_4_FINAL_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY

    report: dict[str, Any] = {
        "phase8_4_signed_testnet_executor_final_guard_id": report_id,
        "phase8_4_version": PHASE8_4_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "final_guard_only": True,
        "phase8_4_signed_testnet_executor_final_guard_ready": ready,
        "signed_testnet_executor_final_guard_created": True,
        "signed_testnet_executor_final_guard_guard_created": True,
        "signed_testnet_executor_final_guard_guard_passed": guard_report.get("guard_passed") is True,
        "phase9_1_single_signed_testnet_enablement_intake_may_begin": ready,
        "phase9_order_submission_not_authorized_by_phase8_4": True,
        "required_evidence_hash_summary": source_summary,
        "missing_required_evidence": missing,
        "required_evidence_not_ready": not_ready,
        "unsafe_flags_by_artifact": unsafe,
        "signed_testnet_executor_final_guard_result": validation_result,
        "block_reasons": blockers,
        "phase8_4_allowed_next_scope": "phase9_1_single_signed_testnet_enablement_intake_review_only" if ready else "resolve_phase8_4_final_guard_blockers",
        "recommended_next_action": "start_phase9_1_intake_keep_order_submission_disabled" if ready else "inspect_phase8_4_blockers_and_rerun_phase8_1_to_phase8_4",
        "runtime_permission_source": False,
        "phase8_execution_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_unlock_authority": False,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "executor_enablement_performed": False,
        "executor_runtime_switch_enabled": False,
        "phase9_order_submission_authorized": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "order_submission_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "external_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "created_at_utc": created,
    }
    report["signed_testnet_executor_final_guard_sha256"] = final_guard["signed_testnet_executor_final_guard_sha256"]
    report["signed_testnet_executor_final_guard_guard_report_sha256"] = guard_report["signed_testnet_executor_final_guard_guard_report_sha256"]
    report["phase8_4_report_sha256"] = sha256_json(report)
    still_disabled_flags = _build_still_disabled_flags(report)
    still_disabled_flags["still_disabled_execution_flags_sha256"] = sha256_json(still_disabled_flags)
    return report, final_guard, guard_report, still_disabled_flags


def persist_phase8_4_signed_testnet_executor_final_guard_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase8_3_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase8_4_signed_testnet_executor_final_guard")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, final_guard, guard_report, still_disabled_flags = build_phase8_4_signed_testnet_executor_final_guard_report(
        cfg=cfg,
        run_phase8_3_first=run_phase8_3_first,
    )
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase8_4_signed_testnet_executor_final_guard_report.json", report)
    atomic_write_json(latest / "signed_testnet_executor_final_guard_review_only.json", final_guard)
    atomic_write_json(latest / "signed_testnet_executor_final_guard_guard_report.json", guard_report)
    atomic_write_json(latest / "still_disabled_executor_enablement_flags.json", still_disabled_flags)
    (latest / "PHASE8_4_SIGNED_TESTNET_EXECUTOR_FINAL_GUARD_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(signed_testnet_dir / "signed_testnet_executor_final_guard_review_only.json", final_guard)
    atomic_write_json(signed_testnet_dir / "still_disabled_executor_enablement_flags.json", still_disabled_flags)

    atomic_write_json(phase_dir / "phase8_4_signed_testnet_executor_final_guard_report.json", report)
    atomic_write_json(phase_dir / "signed_testnet_executor_final_guard_review_only.json", final_guard)
    atomic_write_json(phase_dir / "signed_testnet_executor_final_guard_guard_report.json", guard_report)
    atomic_write_json(phase_dir / "still_disabled_executor_enablement_flags.json", still_disabled_flags)
    (phase_dir / "PHASE8_4_SIGNED_TESTNET_EXECUTOR_FINAL_GUARD_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE8_4_REGISTRY_NAME),
        {
            "phase8_4_signed_testnet_executor_final_guard_id": report.get("phase8_4_signed_testnet_executor_final_guard_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase8_4_signed_testnet_executor_final_guard_ready": report.get("phase8_4_signed_testnet_executor_final_guard_ready"),
            "phase9_1_single_signed_testnet_enablement_intake_may_begin": report.get("phase9_1_single_signed_testnet_enablement_intake_may_begin"),
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
            "exchange_endpoint_called": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE8_4_REGISTRY_NAME,
        id_field="phase8_4_signed_testnet_executor_final_guard_registry_record_id",
        hash_field="phase8_4_signed_testnet_executor_final_guard_registry_record_sha256",
        id_prefix="phase8_4_signed_testnet_executor_final_guard_registry_record",
    )
    atomic_write_json(latest / "phase8_4_signed_testnet_executor_final_guard_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase8_4_signed_testnet_executor_final_guard_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE8_4_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "REQUIRED_FINAL_GUARD_CHECKS",
    "validate_signed_testnet_executor_final_guard",
    "build_phase8_4_signed_testnet_executor_final_guard_report",
    "persist_phase8_4_signed_testnet_executor_final_guard_report",
]
