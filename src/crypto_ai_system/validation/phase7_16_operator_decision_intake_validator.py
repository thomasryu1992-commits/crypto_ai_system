from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase7_15_operator_decision_intake_template import (
    ALLOWED_DECISION_OPTIONS,
    OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS,
    persist_phase7_15_operator_decision_intake_template_report,
    validate_operator_decision_intake_template,
)

PHASE7_16_VERSION = "phase7_16_operator_decision_intake_validator_v2_revised_boundary"
PHASE7_16_REGISTRY_NAME = "phase7_16_operator_decision_intake_validator_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_16_OPERATOR_DECISION_INTAKE_VALIDATOR_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_16_OPERATOR_DECISION_INTAKE_VALIDATOR_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_15_report": "phase7_15_operator_decision_intake_template_report.json",
    "operator_decision_intake_template": "operator_decision_intake_TEMPLATE_REVIEW_ONLY.json",
    "operator_decision_intake_template_guard": "operator_decision_intake_template_guard_report.json",
    "phase7_15_template_validation": "phase7_15_operator_decision_intake_template_validation_report.json",
    "phase7_15_negative_fixture_results": "phase7_15_negative_fixture_results.json",
    "phase7_15_package_boundary_scan": "phase7_15_package_boundary_scan.json",
}

REQUIRED_PHASE7_15_NEGATIVE_FIXTURES = [
    "missing_source_hash.json",
    "mismatched_source_packet_id.json",
    "unsafe_execution_flag_true.json",
    "missing_operator_acknowledgement.json",
    "stale_decision_timestamp.json",
    "missing_execution_disabled_ack.json",
    "missing_operator_signature_placeholder.json",
    "approval_intake_misused_as_operator_decision_intake.json",
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
    "api_key_value_access_allowed",
    "api_secret_value_access_allowed",
    "secret_file_access_allowed",
    "secret_file_creation_allowed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "settings_write_preview_applied",
    "live_trading_allowed",
    "auto_promotion_allowed",
]

REQUIRED_VALIDATION_RESULT_FIELDS = [
    "validation_type",
    "phase7_16_version",
    "review_only",
    "validator_only",
    "not_runtime_authority",
    "source_phase7_16_report_id",
    "source_phase7_15_report_id",
    "source_phase7_15_report_hash",
    "source_operator_decision_intake_template_hash",
    "source_operator_decision_intake_template_guard_hash",
    "validated_submission_hash",
    "submission_validation_passed",
    "submission_blocked_fail_closed",
    "operator_decision_intake_validated",
    "operator_decision_scope_review_only",
    "phase7_17_final_pre_executor_review_required",
    "blocks_executor_enablement",
    "blocks_order_submission",
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


def _unsafe_flags_by_artifact(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    unsafe: dict[str, list[str]] = {}
    for name, payload in artifacts.items():
        flags = _unsafe_fields(payload)
        if flags:
            unsafe[name] = flags
    return unsafe


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase7_16_report_sha256",
        "phase7_15_report_sha256",
        "operator_decision_intake_template_sha256",
        "operator_decision_intake_template_guard_report_sha256",
        "operator_decision_intake_submission_fixture_sha256",
        "operator_decision_intake_validation_report_sha256",
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
        "status": data.get("status") or data.get("template_type") or data.get("guard_type") or data.get("validation_type") or data.get("submission_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _phase7_15_negative_fixture_names_from_report(report: Mapping[str, Any]) -> list[str]:
    results = report.get("results")
    if not isinstance(results, Mapping):
        return []
    return sorted(str(name) for name in results.keys())


def _phase7_15_negative_fixture_revised_check(report: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(report or {})
    results = data.get("results") if isinstance(data.get("results"), Mapping) else {}
    fixture_names = _phase7_15_negative_fixture_names_from_report(data)
    missing = [name for name in REQUIRED_PHASE7_15_NEGATIVE_FIXTURES if name not in fixture_names]
    not_blocked: list[str] = []
    missing_reasons: list[str] = []
    approval_misuse_blocked = False
    stale_timestamp_blocked = False
    for name in fixture_names:
        item = results.get(name) if isinstance(results, Mapping) else {}
        if not isinstance(item, Mapping):
            not_blocked.append(name)
            missing_reasons.append(name)
            continue
        block_reasons = item.get("block_reasons") or []
        if item.get("blocked") is not True or item.get("fail_closed") is not True:
            not_blocked.append(name)
        if not block_reasons:
            missing_reasons.append(name)
        joined = " ".join(str(reason) for reason in block_reasons)
        if name == "approval_intake_misused_as_operator_decision_intake.json" and "APPROVAL_INTAKE" in joined:
            approval_misuse_blocked = True
        if name == "stale_decision_timestamp.json" and ("STALE" in joined or "TIMESTAMP" in joined):
            stale_timestamp_blocked = True
    passed = (
        data.get("all_negative_fixtures_blocked") is True
        and not missing
        and not not_blocked
        and not missing_reasons
        and approval_misuse_blocked
        and stale_timestamp_blocked
    )
    blockers: list[str] = []
    if data.get("all_negative_fixtures_blocked") is not True:
        blockers.append("PHASE7_15_NEGATIVE_FIXTURES_NOT_ALL_BLOCKED")
    if missing:
        blockers.append("PHASE7_15_NEGATIVE_FIXTURES_MISSING:" + ",".join(missing))
    if not_blocked:
        blockers.append("PHASE7_15_NEGATIVE_FIXTURES_DID_NOT_BLOCK:" + ",".join(sorted(not_blocked)))
    if missing_reasons:
        blockers.append("PHASE7_15_NEGATIVE_FIXTURES_MISSING_BLOCK_REASONS:" + ",".join(sorted(missing_reasons)))
    if not approval_misuse_blocked:
        blockers.append("PHASE7_15_APPROVAL_INTAKE_MISUSE_FIXTURE_NOT_BLOCKED")
    if not stale_timestamp_blocked:
        blockers.append("PHASE7_15_STALE_TIMESTAMP_FIXTURE_NOT_BLOCKED")
    return {
        "required_fixture_names": REQUIRED_PHASE7_15_NEGATIVE_FIXTURES,
        "observed_fixture_names": fixture_names,
        "missing_fixture_names": missing,
        "not_blocked_fixture_names": sorted(not_blocked),
        "missing_block_reason_fixture_names": sorted(missing_reasons),
        "approval_intake_misuse_blocked": approval_misuse_blocked,
        "stale_timestamp_blocked": stale_timestamp_blocked,
        "all_required_negative_fixtures_blocked_fail_closed": passed,
        "block_reasons": sorted(dict.fromkeys(blockers)),
    }


def _phase7_15_boundary_artifact_check(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    validation = dict(artifacts.get("phase7_15_template_validation") or {})
    package_scan = dict(artifacts.get("phase7_15_package_boundary_scan") or {})
    negative_report = dict(artifacts.get("phase7_15_negative_fixture_results") or {})
    negative_check = _phase7_15_negative_fixture_revised_check(negative_report)
    blockers: list[str] = []
    if validation.get("passed_review_only") is not True:
        blockers.append("PHASE7_15_TEMPLATE_VALIDATION_NOT_PASSED_REVIEW_ONLY")
    if validation.get("approval_intake_validator_reused") is not False:
        blockers.append("PHASE7_15_APPROVAL_INTAKE_VALIDATOR_REUSED")
    if package_scan.get("blocked") is True or package_scan.get("fail_closed") is True:
        blockers.append("PHASE7_15_PACKAGE_BOUNDARY_SCAN_BLOCKED")
    if package_scan.get("forbidden_artifacts_found"):
        blockers.append("PHASE7_15_PACKAGE_BOUNDARY_FORBIDDEN_ARTIFACTS_FOUND")
    blockers.extend(negative_check.get("block_reasons") or [])
    passed = not blockers
    return {
        "phase7_15_boundary_validation_consumed": bool(validation),
        "phase7_15_negative_fixture_results_consumed": bool(negative_report),
        "phase7_15_package_boundary_scan_consumed": bool(package_scan),
        "template_validation_passed_review_only": validation.get("passed_review_only") is True,
        "approval_intake_validator_reused": validation.get("approval_intake_validator_reused"),
        "package_boundary_passed": package_scan.get("blocked") is not True and not package_scan.get("forbidden_artifacts_found"),
        "negative_fixture_revised_check": negative_check,
        "boundary_hardening_passed": passed,
        "block_reasons": sorted(dict.fromkeys(str(item) for item in blockers if item)),
    }


def _is_manual_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("MANUAL_REQUIRED")


def build_operator_decision_intake_submission_fixture(template: Mapping[str, Any], *, created_at_utc: str | None = None) -> dict[str, Any]:
    created = created_at_utc or utc_now_canonical()
    payload: dict[str, Any] = {
        "submission_type": "operator_decision_intake_submission_FIXTURE_REVIEW_ONLY",
        "phase7_16_version": PHASE7_16_VERSION,
        "review_only": True,
        "fixture_only": True,
        "validator_fixture_only": True,
        "not_runtime_authority": True,
        "operator_decision_intake_id": stable_id("operator_decision_intake_fixture", {"created_at_utc": created}, 24),
        "operator_decision_id": stable_id("operator_decision_fixture", {"created_at_utc": created}, 24),
        "operator_id": "fixture_operator_review_only",
        "operator_ticket_or_signature": "fixture_ticket_review_only_no_runtime_authority",
        "canonical_utc_timestamp": created,
        "decision_option": "APPROVE_PHASE8_PREPARATION_REVIEW_ONLY_NOT_EXECUTION",
        "decision_scope": "phase8_preparation_review_only_no_executor_enablement_no_order_submission",
        "source_phase7_14_report_hash": template.get("source_phase7_14_report_hash"),
        "source_operator_decision_packet_hash": template.get("source_operator_decision_packet_hash"),
        "source_operator_decision_guard_hash": template.get("source_operator_decision_guard_hash"),
        "metadata_only_key_reference_id": "fixture_metadata_key_ref_review_only_no_secret_value",
        "metadata_only_key_fingerprint": "fixture_key_fingerprint_review_only_no_secret_value",
        "max_testnet_notional_usd": 0,
        "max_testnet_order_count": 0,
        "max_testnet_daily_loss_usd": 0,
        "manual_kill_switch_confirmation": True,
        "hard_caps_rechecked": True,
        "pre_order_risk_gate_rechecked": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "phase7_16_intake_validation_required": True,
        "phase7_17_final_pre_executor_review_required": True,
        "final_pre_executor_review_required": True,
        "no_order_submission_authorized_by_submission": True,
        "phase8_preparation_review_may_be_considered": True,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
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
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    payload["operator_decision_intake_submission_fixture_sha256"] = sha256_json(payload)
    return payload


def validate_operator_decision_intake_submission(
    submission: Mapping[str, Any], *, template: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    data = dict(submission or {})
    template_data = dict(template or {})
    missing = [field for field in OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS if field not in data or data.get(field) in (None, "")]
    placeholders = [field for field in OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS if _is_manual_placeholder(data.get(field))]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_OPERATOR_DECISION_INTAKE_FIELDS:" + ",".join(missing))
    if placeholders:
        blockers.append("UNFILLED_OPERATOR_DECISION_INTAKE_PLACEHOLDERS:" + ",".join(placeholders))
    if unsafe:
        blockers.append("UNSAFE_OPERATOR_DECISION_INTAKE_FLAGS:" + ",".join(unsafe))
    if data.get("decision_option") not in ALLOWED_DECISION_OPTIONS:
        blockers.append("OPERATOR_DECISION_INTAKE_DECISION_OPTION_INVALID")
    if data.get("decision_option") == "APPROVE_PHASE8_PREPARATION_REVIEW_ONLY_NOT_EXECUTION":
        scope = str(data.get("decision_scope") or "").lower()
        if "execution" in scope and "no" not in scope:
            blockers.append("OPERATOR_DECISION_SCOPE_MAY_AUTHORIZE_EXECUTION")
    if not is_canonical_utc_timestamp(data.get("canonical_utc_timestamp")):
        blockers.append("OPERATOR_DECISION_INTAKE_TIMESTAMP_NOT_CANONICAL_UTC")
    for field in (
        "manual_kill_switch_confirmation",
        "hard_caps_rechecked",
        "pre_order_risk_gate_rechecked",
        "fresh_pre_submit_payload_validation_required",
        "fresh_pre_order_risk_gate_recheck_required",
        "reconciliation_required_after_any_session",
        "session_close_report_required",
        "phase7_16_intake_validation_required",
        "phase7_17_final_pre_executor_review_required",
    ):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_OPERATOR_DECISION_INTAKE_CONFIRMATION_NOT_TRUE:{field}")
    for field in ("max_testnet_notional_usd", "max_testnet_order_count", "max_testnet_daily_loss_usd"):
        value = data.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            blockers.append(f"OPERATOR_DECISION_INTAKE_NUMERIC_CAP_INVALID:{field}")
    if template_data:
        for field in ("source_phase7_14_report_hash", "source_operator_decision_packet_hash", "source_operator_decision_guard_hash"):
            if data.get(field) != template_data.get(field):
                blockers.append(f"OPERATOR_DECISION_INTAKE_SOURCE_HASH_MISMATCH:{field}")
    if data.get("metadata_only_key_reference_id") in (None, "") or _is_manual_placeholder(data.get("metadata_only_key_reference_id")):
        blockers.append("METADATA_ONLY_KEY_REFERENCE_ID_MISSING_OR_PLACEHOLDER")
    if data.get("metadata_only_key_fingerprint") in (None, "") or _is_manual_placeholder(data.get("metadata_only_key_fingerprint")):
        blockers.append("METADATA_ONLY_KEY_FINGERPRINT_MISSING_OR_PLACEHOLDER")
    valid = not blockers
    return {
        "submission_validation_passed": valid,
        "submission_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unfilled_placeholders": placeholders,
        "unsafe_truthy_fields": unsafe,
        "submission_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_validation_report_artifact(
    *,
    report_id: str,
    artifacts: Mapping[str, Mapping[str, Any]],
    submission: Mapping[str, Any],
    submission_validation: Mapping[str, Any],
    created_at_utc: str,
) -> dict[str, Any]:
    phase7_15 = artifacts.get("phase7_15_report", {})
    template = artifacts.get("operator_decision_intake_template", {})
    guard = artifacts.get("operator_decision_intake_template_guard", {})
    payload: dict[str, Any] = {
        "validation_type": "operator_decision_intake_validation_report_review_only",
        "phase7_16_version": PHASE7_16_VERSION,
        "review_only": True,
        "validator_only": True,
        "not_runtime_authority": True,
        "source_phase7_16_report_id": report_id,
        "source_phase7_15_report_id": phase7_15.get("phase7_15_operator_decision_intake_template_id"),
        "source_phase7_15_report_hash": _artifact_hash(phase7_15),
        "source_operator_decision_intake_template_hash": _artifact_hash(template),
        "source_operator_decision_intake_template_guard_hash": _artifact_hash(guard),
        "validated_submission_hash": _artifact_hash(submission),
        "submission_validation": dict(submission_validation),
        "submission_validation_passed": submission_validation.get("submission_validation_passed") is True,
        "submission_blocked_fail_closed": submission_validation.get("submission_blocked_fail_closed") is True,
        "operator_decision_intake_validated": submission_validation.get("submission_validation_passed") is True,
        "operator_decision_scope_review_only": True,
        "phase7_17_final_pre_executor_review_required": True,
        "blocks_executor_enablement": True,
        "blocks_order_submission": True,
        "phase7_15_negative_fixtures_validated_by_7_16": True,
        "phase7_15_package_boundary_checked_by_7_16": True,
        "approval_intake_misuse_blocked_by_7_16": True,
        "actual_operator_decision_recorded": False,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }
    payload["operator_decision_intake_validation_report_sha256"] = sha256_json(payload)
    return payload


def validate_operator_decision_intake_validation_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in REQUIRED_VALIDATION_RESULT_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_PHASE7_16_VALIDATION_REPORT_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_PHASE7_16_VALIDATION_REPORT_FLAGS:" + ",".join(unsafe))
    if data.get("validation_type") != "operator_decision_intake_validation_report_review_only":
        blockers.append("INVALID_PHASE7_16_VALIDATION_REPORT_TYPE")
    if data.get("review_only") is not True:
        blockers.append("PHASE7_16_VALIDATION_REPORT_NOT_REVIEW_ONLY")
    if data.get("validator_only") is not True:
        blockers.append("PHASE7_16_VALIDATION_REPORT_NOT_VALIDATOR_ONLY")
    if data.get("not_runtime_authority") is not True:
        blockers.append("PHASE7_16_VALIDATION_REPORT_RUNTIME_AUTHORITY_NOT_BLOCKED")
    for field in ("phase7_17_final_pre_executor_review_required", "blocks_executor_enablement", "blocks_order_submission"):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_PHASE7_16_CONFIRMATION_NOT_TRUE:{field}")
    valid = not blockers
    return {
        "validation_report_valid_review_only": valid,
        "validation_report_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "validation_report_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 7.16 Operator Decision Intake Validator - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase validates the Phase 7.15 operator decision intake structure. It does not grant Phase 8 authority, enable executors, or submit signed testnet orders.",
            "",
            "## Result",
            "",
            f"- Intake validation passed: `{report.get('operator_decision_intake_validation_passed')}`",
            f"- Fixture-only validation: `{report.get('validated_fixture_only')}`",
            f"- Phase 7.17 required: `{report.get('phase7_17_final_pre_executor_review_required')}`",
            "",
            "## Safety Flags",
            "",
            "- `ready_for_signed_testnet_execution=false`",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `actual_phase8_approval_granted=false`",
            "",
            "## Blockers",
            "",
            blocker_lines,
            "",
            "## Next Allowed Scope",
            "",
            f"`{report.get('phase7_16_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_16_operator_decision_intake_validator_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_15_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_15_first:
        persist_phase7_15_operator_decision_intake_template_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    phase7_15 = artifacts.get("phase7_15_report", {})
    template = artifacts.get("operator_decision_intake_template", {})
    template_guard = artifacts.get("operator_decision_intake_template_guard", {})
    boundary_hardening = _phase7_15_boundary_artifact_check(artifacts)

    submission = build_operator_decision_intake_submission_fixture(template, created_at_utc=created)
    submission_validation = validate_operator_decision_intake_submission(submission, template=template)
    preliminary_id = stable_id("phase7_16_operator_decision_intake_validator", {"source_summary": source_summary, "created_at_utc": created}, 24)
    validation_report = _build_validation_report_artifact(
        report_id=preliminary_id,
        artifacts=artifacts,
        submission=submission,
        submission_validation=submission_validation,
        created_at_utc=created,
    )
    validation_report_check = validate_operator_decision_intake_validation_report(validation_report)

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_16_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_16_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_15.get("status") != "PHASE7_15_OPERATOR_DECISION_INTAKE_TEMPLATE_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE7_15_OPERATOR_DECISION_INTAKE_TEMPLATE_NOT_READY")
    if phase7_15.get("phase7_15_intake_template_ready") is not True:
        blockers.append("PHASE7_15_INTAKE_TEMPLATE_READY_FALSE")
    template_validation = validate_operator_decision_intake_template(template)
    if template_validation.get("template_valid_review_only") is not True:
        blockers.extend(template_validation.get("template_blockers") or ["OPERATOR_DECISION_INTAKE_TEMPLATE_INVALID"])
    if template_guard.get("guard_passed") is not True:
        blockers.append("OPERATOR_DECISION_INTAKE_TEMPLATE_GUARD_NOT_PASSED")
    if boundary_hardening.get("boundary_hardening_passed") is not True:
        blockers.extend(boundary_hardening.get("block_reasons") or ["PHASE7_15_BOUNDARY_HARDENING_NOT_PASSED"])
    if submission_validation.get("submission_validation_passed") is not True:
        blockers.extend(submission_validation.get("submission_blockers") or ["OPERATOR_DECISION_INTAKE_SUBMISSION_INVALID"])
    if validation_report_check.get("validation_report_valid_review_only") is not True:
        blockers.extend(validation_report_check.get("validation_report_blockers") or ["PHASE7_16_VALIDATION_REPORT_INVALID"])

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_16_operator_decision_intake_validator",
        {
            "source_summary": source_summary,
            "submission_hash": sha256_json(submission),
            "validation_report_hash": sha256_json(validation_report),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    validation_report["source_phase7_16_report_id"] = report_id
    validation_report["operator_decision_intake_validation_report_sha256"] = sha256_json(validation_report)

    report: dict[str, Any] = {
        "phase7_16_operator_decision_intake_validator_id": report_id,
        "phase7_16_version": PHASE7_16_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "validator_only": True,
        "phase7_16_intake_validation_ready": ready,
        "operator_decision_intake_validation_passed": ready and submission_validation.get("submission_validation_passed") is True,
        "operator_decision_intake_validation_report_created": True,
        "operator_decision_intake_submission_fixture_created": True,
        "validated_fixture_only": True,
        "actual_operator_decision_recorded": False,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "source_phase7_15_ready": phase7_15.get("phase7_15_intake_template_ready") is True,
        "source_template_guard_passed": template_guard.get("guard_passed") is True,
        "submission_validation": submission_validation,
        "validation_report_check": validation_report_check,
        "phase7_16_validator_hardened_revised": True,
        "dedicated_operator_decision_intake_validator": True,
        "approval_intake_validator_reused": False,
        "phase7_15_boundary_hardening": boundary_hardening,
        "phase7_15_boundary_validation_consumed": boundary_hardening.get("phase7_15_boundary_validation_consumed") is True,
        "phase7_15_negative_fixture_results_consumed": boundary_hardening.get("phase7_15_negative_fixture_results_consumed") is True,
        "phase7_15_package_boundary_scan_consumed": boundary_hardening.get("phase7_15_package_boundary_scan_consumed") is True,
        "all_required_negative_fixtures_blocked_fail_closed": boundary_hardening.get("negative_fixture_revised_check", {}).get("all_required_negative_fixtures_blocked_fail_closed") is True,
        "package_boundary_passed": boundary_hardening.get("package_boundary_passed") is True,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_17_final_pre_executor_review_required": True,
        "phase7_16_allowed_next_scope": "phase7_17_final_pre_executor_review_packet_still_disabled" if ready else "resolve_phase7_16_operator_decision_intake_validator_blockers",
        "recommended_next_action": "prepare_phase7_17_final_pre_executor_review_packet_keep_execution_disabled" if ready else "inspect_phase7_16_blockers_and_rerun_phase7_15_phase7_16",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
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
        "created_at_utc": created,
    }
    report["operator_decision_intake_submission_fixture_sha256"] = submission["operator_decision_intake_submission_fixture_sha256"]
    report["operator_decision_intake_validation_report_sha256"] = validation_report["operator_decision_intake_validation_report_sha256"]
    report["phase7_16_report_sha256"] = sha256_json(report)
    return report, submission, validation_report


def persist_phase7_16_operator_decision_intake_validator_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_15_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_16_operator_decision_intake_validator")
    signed_fixtures_dir = _storage_dir(cfg, "storage/signed_testnet/fixtures")
    report, submission, validation_report = build_phase7_16_operator_decision_intake_validator_report(
        cfg=cfg, run_phase7_15_first=run_phase7_15_first
    )
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_16_operator_decision_intake_validator_report.json", report)
    atomic_write_json(latest / "operator_decision_intake_valid_submission_FIXTURE_REVIEW_ONLY.json", submission)
    atomic_write_json(latest / "operator_decision_intake_validation_report_review_only.json", validation_report)
    (latest / "PHASE7_16_OPERATOR_DECISION_INTAKE_VALIDATOR_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(signed_fixtures_dir / "operator_decision_intake_valid_submission_FIXTURE_REVIEW_ONLY.json", submission)

    atomic_write_json(phase_dir / "phase7_16_operator_decision_intake_validator_report.json", report)
    atomic_write_json(phase_dir / "operator_decision_intake_valid_submission_FIXTURE_REVIEW_ONLY.json", submission)
    atomic_write_json(phase_dir / "operator_decision_intake_validation_report_review_only.json", validation_report)
    hardening_report = {
        "report_type": "phase7_16_operator_decision_intake_validator_hardening_report",
        "phase7_16_version": PHASE7_16_VERSION,
        "status": "PHASE7_16_OPERATOR_DECISION_INTAKE_VALIDATOR_HARDENED_REVIEW_ONLY" if report.get("phase7_16_intake_validation_ready") else "PHASE7_16_OPERATOR_DECISION_INTAKE_VALIDATOR_HARDENING_BLOCKED_REVIEW_ONLY",
        "blocked": report.get("blocked"),
        "fail_closed": report.get("fail_closed"),
        "review_only": True,
        "validator_only": True,
        "dedicated_operator_decision_intake_validator": True,
        "approval_intake_validator_reused": False,
        "phase7_15_boundary_hardening": report.get("phase7_15_boundary_hardening"),
        "all_required_negative_fixtures_blocked_fail_closed": report.get("all_required_negative_fixtures_blocked_fail_closed"),
        "package_boundary_passed": report.get("package_boundary_passed"),
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "actual_order_submission_performed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "created_at_utc": report.get("created_at_utc"),
    }
    hardening_report["phase7_16_hardening_report_sha256"] = sha256_json(hardening_report)
    negative_revised = {
        "report_type": "phase7_16_negative_fixture_results_REVISED",
        "phase7_16_version": PHASE7_16_VERSION,
        "status": hardening_report["status"],
        "blocked": report.get("blocked"),
        "fail_closed": report.get("fail_closed"),
        "review_only": True,
        "validator_only": True,
        **dict(report.get("phase7_15_boundary_hardening", {}).get("negative_fixture_revised_check") or {}),
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "created_at_utc": report.get("created_at_utc"),
    }
    negative_revised["phase7_16_negative_fixture_results_revised_sha256"] = sha256_json(negative_revised)
    atomic_write_json(latest / "phase7_16_operator_decision_intake_validator_hardening_report.json", hardening_report)
    atomic_write_json(latest / "phase7_16_negative_fixture_results_REVISED.json", negative_revised)
    atomic_write_json(phase_dir / "phase7_16_operator_decision_intake_validator_hardening_report.json", hardening_report)
    atomic_write_json(phase_dir / "phase7_16_negative_fixture_results_REVISED.json", negative_revised)
    (phase_dir / "PHASE7_16_OPERATOR_DECISION_INTAKE_VALIDATOR_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_16_REGISTRY_NAME),
        {
            "phase7_16_operator_decision_intake_validator_id": report.get("phase7_16_operator_decision_intake_validator_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_16_intake_validation_ready": report.get("phase7_16_intake_validation_ready"),
            "operator_decision_intake_validation_passed": report.get("operator_decision_intake_validation_passed"),
            "phase7_16_validator_hardened_revised": report.get("phase7_16_validator_hardened_revised"),
            "all_required_negative_fixtures_blocked_fail_closed": report.get("all_required_negative_fixtures_blocked_fail_closed"),
            "package_boundary_passed": report.get("package_boundary_passed"),
            "validated_fixture_only": True,
            "actual_operator_decision_recorded": False,
            "actual_phase8_approval_granted": False,
            "actual_executor_enablement_performed": False,
            "actual_order_submission_performed": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "external_order_submission_performed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE7_16_REGISTRY_NAME,
        id_field="phase7_16_operator_decision_intake_validator_registry_record_id",
        hash_field="phase7_16_operator_decision_intake_validator_registry_record_sha256",
        id_prefix="phase7_16_operator_decision_intake_validator_registry_record",
    )
    atomic_write_json(latest / "phase7_16_operator_decision_intake_validator_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_16_operator_decision_intake_validator_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_16_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_operator_decision_intake_submission_fixture",
    "validate_operator_decision_intake_submission",
    "validate_operator_decision_intake_validation_report",
    "build_phase7_16_operator_decision_intake_validator_report",
    "persist_phase7_16_operator_decision_intake_validator_report",
]
