from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase7_14_future_executor_operator_decision_packet import (
    persist_phase7_14_future_executor_operator_decision_packet_report,
)

PHASE7_15_VERSION = "phase7_15_operator_decision_intake_template_v1"
PHASE7_15_REGISTRY_NAME = "phase7_15_operator_decision_intake_template_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_15_OPERATOR_DECISION_INTAKE_TEMPLATE_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_15_OPERATOR_DECISION_INTAKE_TEMPLATE_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_14_operator_decision_packet_report": "phase7_14_future_executor_operator_decision_packet_report.json",
    "future_executor_operator_decision_packet": "future_signed_testnet_executor_operator_decision_packet_review_only.json",
    "future_executor_operator_decision_guard": "future_signed_testnet_executor_operator_decision_guard_report.json",
}

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

OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS = [
    "operator_decision_intake_id",
    "operator_decision_id",
    "operator_id",
    "operator_ticket_or_signature",
    "canonical_utc_timestamp",
    "decision_option",
    "decision_scope",
    "source_phase7_14_report_hash",
    "source_operator_decision_packet_hash",
    "source_operator_decision_guard_hash",
    "metadata_only_key_reference_id",
    "metadata_only_key_fingerprint",
    "max_testnet_notional_usd",
    "max_testnet_order_count",
    "max_testnet_daily_loss_usd",
    "manual_kill_switch_confirmation",
    "hard_caps_rechecked",
    "pre_order_risk_gate_rechecked",
    "fresh_pre_submit_payload_validation_required",
    "fresh_pre_order_risk_gate_recheck_required",
    "reconciliation_required_after_any_session",
    "session_close_report_required",
    "phase7_16_intake_validation_required",
    "phase7_17_final_pre_executor_review_required",
]

REQUIRED_TEMPLATE_FIELDS = [
    "template_type",
    "template_id",
    "phase",
    "phase7_15_version",
    "source_phase",
    "source_phase7_15_report_id",
    "source_phase7_14_report_id",
    "source_phase7_14_packet_id",
    "source_phase7_14_packet_hash",
    "source_artifact_path",
    "source_ref",
    "source_hash",
    "derived_template_hash",
    "operator_decision",
    "risk_ack",
    "execution_disabled_ack",
    "approval_scope",
    "timestamp_utc",
    "operator_signature_placeholder",
    "review_only",
    "template_only",
    "intake_template_only",
    "not_runtime_authority",
    "operator_decision_intake_required_fields",
    "operator_fill_instructions",
    "forbidden_scope",
    *OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS,
]

ALLOWED_DECISION_OPTIONS = [
    "APPROVE_PHASE8_PREPARATION_REVIEW_ONLY_NOT_EXECUTION",
    "DEFER_PHASE8_PREPARATION",
    "REJECT_PHASE8_PREPARATION",
]

PHASE7_15_APPROVAL_SCOPE = "review_only_signed_testnet_preparation"
PHASE7_15_OPERATOR_DECISION_PENDING = "PENDING_OPERATOR_DECISION_REVIEW_ONLY"
PHASE7_15_OPERATOR_SIGNATURE_PLACEHOLDER = "MANUAL_REQUIRED_OPERATOR_SIGNATURE_REVIEW_ONLY"
PHASE7_15_REVIEW_WINDOW_DAYS = 30

FORBIDDEN_PHASE7_15_PACKAGE_TOKENS = [
    "signed_testnet_order_executor",
    "live_canary",
    "live_scaled",
    "deployment_runbook",
    "canary_outcome_report",
    "real_order_endpoint",
    "real_exchange_order",
    "runtime_execution",
    "session_artifact",
]

PHASE7_15_ALLOWED_PACKAGE_ARTIFACTS = [
    "operator_decision_intake_TEMPLATE_REVIEW_ONLY.json",
    "operator_decision_intake_template_guard_report.json",
    "operator_decision_intake_template_registry.jsonl",
    "phase7_15_operator_decision_intake_handoff.md",
    "phase7_15_operator_decision_intake_template_validation_report.json",
    "negative_fixture_results.json",
    "phase7_15_package_boundary_scan.json",
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


def _is_nonempty(value: Any) -> bool:
    return value not in (None, "")


def _canonical_timestamp_to_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _timestamp_is_fresh_for_review(value: Any, *, now: datetime | None = None) -> bool:
    parsed = _canonical_timestamp_to_datetime(value)
    if parsed is None:
        return False
    now_dt = now or datetime.now(timezone.utc)
    age = now_dt - parsed.astimezone(timezone.utc)
    return age.total_seconds() >= 0 and age.days <= PHASE7_15_REVIEW_WINDOW_DAYS


def _is_forbidden_phase7_15_package_name(path_text: str) -> bool:
    normalized = str(path_text).replace("\\", "/").lower()
    return any(token in normalized for token in FORBIDDEN_PHASE7_15_PACKAGE_TOKENS)


def scan_phase7_15_package_boundary(package_root: str | Path) -> dict[str, Any]:
    root = Path(package_root)
    files = []
    forbidden = []
    if root.exists():
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = path.relative_to(root).as_posix()
            files.append(rel)
            if _is_forbidden_phase7_15_package_name(rel):
                forbidden.append(rel)
    allowed_present = sorted(name for name in PHASE7_15_ALLOWED_PACKAGE_ARTIFACTS if (root / name).exists())
    blocked = bool(forbidden)
    result = {
        "scan_type": "phase7_15_operator_decision_intake_package_boundary_scan",
        "phase7_15_version": PHASE7_15_VERSION,
        "package_root": str(root),
        "review_only": True,
        "package_boundary_only": True,
        "allowed_artifacts_present": allowed_present,
        "forbidden_tokens": FORBIDDEN_PHASE7_15_PACKAGE_TOKENS,
        "forbidden_artifacts_found": forbidden,
        "scanned_file_count": len(files),
        "blocked": blocked,
        "fail_closed": blocked,
        "execution_scope_excluded": not blocked,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_order_executor_enabled": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    result["phase7_15_package_boundary_scan_sha256"] = sha256_json(result)
    return result


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase7_15_report_sha256",
        "phase7_14_report_sha256",
        "future_executor_operator_decision_packet_sha256",
        "future_executor_operator_decision_guard_report_sha256",
        "operator_decision_intake_template_sha256",
        "operator_decision_intake_template_guard_report_sha256",
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
        "status": data.get("status") or data.get("template_type") or data.get("guard_type") or data.get("packet_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def validate_operator_decision_intake_template(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in REQUIRED_TEMPLATE_FIELDS if not _is_nonempty(data.get(field))]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_OPERATOR_DECISION_INTAKE_TEMPLATE_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_OPERATOR_DECISION_INTAKE_TEMPLATE_FLAGS:" + ",".join(unsafe))
    if data.get("template_type") != "operator_decision_intake_TEMPLATE_REVIEW_ONLY":
        blockers.append("INVALID_OPERATOR_DECISION_INTAKE_TEMPLATE_TYPE")
    if data.get("template_id") != data.get("operator_decision_intake_id"):
        blockers.append("TEMPLATE_ID_MUST_MATCH_OPERATOR_DECISION_INTAKE_ID")
    if data.get("phase") != "7.15":
        blockers.append("INVALID_OPERATOR_DECISION_INTAKE_TEMPLATE_PHASE")
    if data.get("source_phase") != "7.14":
        blockers.append("INVALID_OPERATOR_DECISION_INTAKE_TEMPLATE_SOURCE_PHASE")
    if data.get("review_only") is not True:
        blockers.append("OPERATOR_DECISION_INTAKE_TEMPLATE_NOT_REVIEW_ONLY")
    if data.get("template_only") is not True:
        blockers.append("OPERATOR_DECISION_INTAKE_TEMPLATE_NOT_TEMPLATE_ONLY")
    if data.get("intake_template_only") is not True:
        blockers.append("OPERATOR_DECISION_INTAKE_TEMPLATE_NOT_INTAKE_TEMPLATE_ONLY")
    if data.get("not_runtime_authority") is not True:
        blockers.append("OPERATOR_DECISION_INTAKE_TEMPLATE_RUNTIME_AUTHORITY_NOT_BLOCKED")
    if data.get("operator_decision") != PHASE7_15_OPERATOR_DECISION_PENDING:
        blockers.append("OPERATOR_DECISION_MUST_REMAIN_PENDING_REVIEW_ONLY")
    risk_ack = data.get("risk_ack")
    if not isinstance(risk_ack, Mapping) or risk_ack.get("operator_acknowledgement_required") is not True:
        blockers.append("OPERATOR_RISK_ACKNOWLEDGEMENT_REQUIRED")
    if data.get("execution_disabled_ack") is not True:
        blockers.append("EXECUTION_DISABLED_ACK_MUST_BE_TRUE")
    if data.get("approval_scope") != PHASE7_15_APPROVAL_SCOPE:
        blockers.append("OPERATOR_DECISION_APPROVAL_SCOPE_NOT_REVIEW_ONLY_SIGNED_TESTNET_PREPARATION")
    if data.get("operator_signature_placeholder") != PHASE7_15_OPERATOR_SIGNATURE_PLACEHOLDER:
        blockers.append("OPERATOR_SIGNATURE_PLACEHOLDER_INVALID")
    if not _timestamp_is_fresh_for_review(data.get("timestamp_utc")):
        blockers.append("OPERATOR_DECISION_INTAKE_TEMPLATE_TIMESTAMP_STALE_OR_INVALID")
    source_ref = data.get("source_ref") if isinstance(data.get("source_ref"), Mapping) else {}
    if source_ref.get("source_phase") != "7.14":
        blockers.append("SOURCE_REF_PHASE_MISMATCH")
    if source_ref.get("source_phase7_14_packet_id") != data.get("source_phase7_14_packet_id"):
        blockers.append("SOURCE_REF_PACKET_ID_MISMATCH")
    if source_ref.get("source_phase7_14_packet_hash") != data.get("source_phase7_14_packet_hash"):
        blockers.append("SOURCE_REF_PACKET_HASH_MISMATCH")
    if data.get("source_hash") != data.get("source_phase7_14_packet_hash"):
        blockers.append("SOURCE_HASH_MUST_MATCH_SOURCE_PHASE7_14_PACKET_HASH")
    if data.get("source_phase7_14_packet_id") != data.get("source_phase7_14_report_id"):
        blockers.append("SOURCE_PHASE7_14_PACKET_ID_MUST_MATCH_SOURCE_PHASE7_14_REPORT_ID")
    if _is_forbidden_phase7_15_package_name(str(data.get("source_artifact_path") or "")):
        blockers.append("SOURCE_ARTIFACT_PATH_CONTAINS_FORBIDDEN_PHASE7_15_SCOPE")
    if "approval_intake_id" in data:
        blockers.append("APPROVAL_INTAKE_ID_MISUSED_AS_OPERATOR_DECISION_INTAKE_ID")
    if "approval_intake_validator" in str(data.get("validator_name") or ""):
        blockers.append("APPROVAL_INTAKE_VALIDATOR_MISUSED_FOR_OPERATOR_DECISION_INTAKE")
    options = data.get("allowed_decision_options")
    if options != ALLOWED_DECISION_OPTIONS:
        blockers.append("OPERATOR_DECISION_INTAKE_TEMPLATE_ALLOWED_OPTIONS_INVALID")
    required_fields = data.get("operator_decision_intake_required_fields")
    if required_fields != OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS:
        blockers.append("OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS_INVALID")
    if data.get("write_target_when_manually_completed") != "storage/signed_testnet/operator_decision_intake_submission.json":
        blockers.append("OPERATOR_DECISION_INTAKE_WRITE_TARGET_INVALID")
    for field in (
        "fresh_pre_submit_payload_validation_required",
        "fresh_pre_order_risk_gate_recheck_required",
        "reconciliation_required_after_any_session",
        "session_close_report_required",
        "phase7_16_intake_validation_required",
        "phase7_17_final_pre_executor_review_required",
        "final_pre_executor_review_required",
        "no_order_submission_authorized_by_template",
    ):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_TEMPLATE_CONFIRMATION_NOT_TRUE:{field}")
    valid = not blockers
    return {
        "template_valid_review_only": valid,
        "template_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "source_ref_valid": "SOURCE_REF_PACKET_ID_MISMATCH" not in blockers
        and "SOURCE_REF_PACKET_HASH_MISMATCH" not in blockers
        and "SOURCE_HASH_MUST_MATCH_SOURCE_PHASE7_14_PACKET_HASH" not in blockers,
        "approval_intake_separation_valid": not any("APPROVAL_INTAKE" in item for item in blockers),
        "template_blockers": sorted(dict.fromkeys(blockers)),
    }

def build_phase7_15_negative_fixtures(template: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    base = dict(template or {})
    fixtures: dict[str, dict[str, Any]] = {}

    missing_source_hash = dict(base)
    missing_source_hash.pop("source_phase7_14_packet_hash", None)
    missing_source_hash.pop("source_hash", None)
    source_ref = dict(missing_source_hash.get("source_ref") or {})
    source_ref.pop("source_phase7_14_packet_hash", None)
    missing_source_hash["source_ref"] = source_ref
    fixtures["missing_source_hash.json"] = missing_source_hash

    mismatched_source_packet_id = dict(base)
    mismatched_source_packet_id["source_phase7_14_packet_id"] = "MISMATCHED_PHASE7_14_PACKET_ID"
    fixtures["mismatched_source_packet_id.json"] = mismatched_source_packet_id

    unsafe_execution_flag_true = dict(base)
    unsafe_execution_flag_true["signed_order_executor_enabled"] = True
    unsafe_execution_flag_true["testnet_order_submission_allowed"] = True
    fixtures["unsafe_execution_flag_true.json"] = unsafe_execution_flag_true

    missing_operator_acknowledgement = dict(base)
    missing_operator_acknowledgement.pop("risk_ack", None)
    fixtures["missing_operator_acknowledgement.json"] = missing_operator_acknowledgement

    stale_decision_timestamp = dict(base)
    stale_decision_timestamp["timestamp_utc"] = "2000-01-01T00:00:00Z"
    fixtures["stale_decision_timestamp.json"] = stale_decision_timestamp

    missing_execution_disabled_ack = dict(base)
    missing_execution_disabled_ack.pop("execution_disabled_ack", None)
    fixtures["missing_execution_disabled_ack.json"] = missing_execution_disabled_ack

    missing_operator_signature_placeholder = dict(base)
    missing_operator_signature_placeholder.pop("operator_signature_placeholder", None)
    fixtures["missing_operator_signature_placeholder.json"] = missing_operator_signature_placeholder

    approval_intake_misused = dict(base)
    approval_intake_misused["approval_intake_id"] = approval_intake_misused.get("operator_decision_intake_id")
    approval_intake_misused["validator_name"] = "approval_intake_validator"
    fixtures["approval_intake_misused_as_operator_decision_intake.json"] = approval_intake_misused
    return fixtures


def validate_phase7_15_negative_fixtures(template: Mapping[str, Any]) -> dict[str, Any]:
    fixtures = build_phase7_15_negative_fixtures(template)
    results: dict[str, Any] = {}
    all_blocked = True
    for name, payload in fixtures.items():
        validation = validate_operator_decision_intake_template(payload)
        blocked = validation.get("template_blocked_fail_closed") is True
        all_blocked = all_blocked and blocked
        results[name] = {
            "fixture_name": name,
            "expected_blocked": True,
            "blocked": blocked,
            "fail_closed": validation.get("template_blocked_fail_closed") is True,
            "block_reasons": validation.get("template_blockers") or [],
        }
    report = {
        "validation_type": "phase7_15_operator_decision_intake_template_negative_fixture_results",
        "phase7_15_version": PHASE7_15_VERSION,
        "review_only": True,
        "negative_fixture_count": len(fixtures),
        "all_negative_fixtures_blocked": all_blocked,
        "results": results,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    report["negative_fixture_results_sha256"] = sha256_json(report)
    return report


def build_phase7_15_template_validation_report(template: Mapping[str, Any], *, package_boundary_scan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    validation = validate_operator_decision_intake_template(template)
    fixture_results = validate_phase7_15_negative_fixtures(template)
    package_scan = dict(package_boundary_scan or {})
    package_ok = package_scan.get("blocked") is not True
    passed = validation.get("template_valid_review_only") is True and fixture_results.get("all_negative_fixtures_blocked") is True and package_ok
    report = {
        "validation_type": "phase7_15_operator_decision_intake_template_validation_report",
        "phase7_15_version": PHASE7_15_VERSION,
        "review_only": True,
        "validator_only": True,
        "dedicated_operator_decision_intake_validator": True,
        "approval_intake_validator_reused": False,
        "passed_review_only": passed,
        "blocked": not passed,
        "fail_closed": not passed,
        "template_validation": validation,
        "negative_fixture_results_sha256": fixture_results.get("negative_fixture_results_sha256"),
        "all_negative_fixtures_blocked": fixture_results.get("all_negative_fixtures_blocked") is True,
        "package_boundary_scan_sha256": package_scan.get("phase7_15_package_boundary_scan_sha256"),
        "package_boundary_passed": package_ok,
        "source_phase7_14_packet_id": template.get("source_phase7_14_packet_id"),
        "source_phase7_14_packet_hash": template.get("source_phase7_14_packet_hash"),
        "source_ref": template.get("source_ref"),
        "source_hash": template.get("source_hash"),
        "derived_template_hash": template.get("derived_template_hash") or template.get("operator_decision_intake_template_sha256"),
        "final_evidence_statement": "Phase 7.15 converted the Phase 7.14 future executor operator decision packet into a review-only operator decision intake template. The conversion preserved the source packet id and hash lineage. No execution permission was granted. All signed testnet, live canary, live scaled, place_order, cancel_order, and external order submission flags remain disabled.",
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
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
    }
    report["phase7_15_operator_decision_intake_template_validation_report_sha256"] = sha256_json(report)
    return report


def _build_operator_decision_intake_template(*, report_id: str, artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    phase7_14 = artifacts.get("phase7_14_operator_decision_packet_report", {})
    operator_packet = artifacts.get("future_executor_operator_decision_packet", {})
    operator_guard = artifacts.get("future_executor_operator_decision_guard", {})
    source_phase7_14_packet_id = str(phase7_14.get("phase7_14_future_executor_operator_decision_packet_id") or "MANUAL_REQUIRED_PHASE7_14_PACKET_ID")
    source_phase7_14_hash = _artifact_hash(phase7_14) or "MANUAL_REQUIRED_PHASE7_14_REPORT_HASH"
    source_packet_hash = _artifact_hash(operator_packet) or "MANUAL_REQUIRED_OPERATOR_DECISION_PACKET_HASH"
    source_guard_hash = _artifact_hash(operator_guard) or "MANUAL_REQUIRED_OPERATOR_DECISION_GUARD_HASH"
    source_artifact_path = "storage/latest/phase7_14_future_executor_operator_decision_packet_report.json"
    template_id = stable_id(
        "phase7_15_operator_decision_intake_template_boundary",
        {
            "source_phase7_14_packet_id": source_phase7_14_packet_id,
            "source_phase7_14_packet_hash": source_phase7_14_hash,
            "report_id": report_id,
        },
        24,
    )
    template: dict[str, Any] = {
        "template_type": "operator_decision_intake_TEMPLATE_REVIEW_ONLY",
        "template_id": template_id,
        "phase": "7.15",
        "phase7_15_version": PHASE7_15_VERSION,
        "source_phase": "7.14",
        "source_phase7_15_report_id": report_id,
        "source_phase7_14_report_id": source_phase7_14_packet_id,
        "source_phase7_14_packet_id": source_phase7_14_packet_id,
        "source_phase7_14_packet_hash": source_phase7_14_hash,
        "source_artifact_path": source_artifact_path,
        "source_ref": {
            "source_phase": "7.14",
            "source_phase7_14_packet_id": source_phase7_14_packet_id,
            "source_phase7_14_packet_hash": source_phase7_14_hash,
            "source_artifact_path": source_artifact_path,
            "converted_to_phase7_15_template": True,
        },
        "source_hash": source_phase7_14_hash,
        "operator_decision": PHASE7_15_OPERATOR_DECISION_PENDING,
        "risk_ack": {
            "operator_acknowledgement_required": True,
            "acknowledgement_scope": "risk_ack_review_only_no_execution_permission",
            "acknowledgement_placeholder": "MANUAL_REQUIRED_RISK_ACK_REVIEW_ONLY",
        },
        "execution_disabled_ack": True,
        "approval_scope": PHASE7_15_APPROVAL_SCOPE,
        "timestamp_utc": created_at_utc,
        "operator_signature_placeholder": PHASE7_15_OPERATOR_SIGNATURE_PLACEHOLDER,
        "source_operator_decision_packet_type": operator_packet.get("packet_type"),
        "source_operator_decision_guard_type": operator_guard.get("guard_type"),
        "source_phase7_14_report_hash": source_phase7_14_hash,
        "source_operator_decision_packet_hash": source_packet_hash,
        "source_operator_decision_guard_hash": source_guard_hash,
        "review_only": True,
        "template_only": True,
        "intake_template_only": True,
        "not_runtime_authority": True,
        "write_target_when_manually_completed": "storage/signed_testnet/operator_decision_intake_submission.json",
        "allowed_decision_options": ALLOWED_DECISION_OPTIONS,
        "operator_decision_intake_required_fields": OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS,
        "operator_decision_intake_id": template_id,
        "operator_decision_id": "MANUAL_REQUIRED_OPERATOR_DECISION_ID",
        "operator_id": "MANUAL_REQUIRED_OPERATOR_ID",
        "operator_ticket_or_signature": "MANUAL_REQUIRED_OPERATOR_TICKET_OR_SIGNATURE",
        "canonical_utc_timestamp": "MANUAL_REQUIRED_CANONICAL_UTC_TIMESTAMP",
        "decision_option": "MANUAL_REQUIRED_ONE_OF_ALLOWED_DECISION_OPTIONS",
        "decision_scope": "MANUAL_REQUIRED_PHASE8_PREPARATION_SCOPE_REVIEW_ONLY_NOT_EXECUTION",
        "phase8_transition_scope": [
            "phase8_1_secret_manager_key_handling_design",
            "phase8_2_exchange_adapter_write_path_dry_validation",
            "phase8_3_fresh_hot_path_pre_order_risk_gate",
            "phase8_4_executor_enablement_final_guard_still_disabled",
        ],
        "metadata_only_key_reference_id": "MANUAL_REQUIRED_METADATA_ONLY_KEY_REFERENCE_ID",
        "metadata_only_key_fingerprint": "MANUAL_REQUIRED_METADATA_ONLY_KEY_FINGERPRINT",
        "max_testnet_notional_usd": "MANUAL_REQUIRED_NUMERIC_MAX_TESTNET_NOTIONAL_USD",
        "max_testnet_order_count": "MANUAL_REQUIRED_INTEGER_MAX_TESTNET_ORDER_COUNT",
        "max_testnet_daily_loss_usd": "MANUAL_REQUIRED_NUMERIC_MAX_TESTNET_DAILY_LOSS_USD",
        "manual_kill_switch_confirmation": "MANUAL_REQUIRED_BOOLEAN_TRUE",
        "hard_caps_rechecked": "MANUAL_REQUIRED_BOOLEAN_TRUE",
        "pre_order_risk_gate_rechecked": "MANUAL_REQUIRED_BOOLEAN_TRUE",
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "phase7_16_intake_validation_required": True,
        "phase7_17_final_pre_executor_review_required": True,
        "final_pre_executor_review_required": True,
        "no_order_submission_authorized_by_template": True,
        "operator_fill_instructions": [
            "Fill only MANUAL_REQUIRED_* values before Phase 7.16 validation.",
            "Select exactly one allowed_decision_options value; approval may only target Phase 8 preparation, not execution.",
            "Use metadata-only key reference and fingerprint; never paste API key values, API secret values, passphrases, or secret file contents.",
            "Do not set executor, order, promotion, live, runtime, settings, or score-weight flags to true.",
            "Phase 7.16 must validate this intake; Phase 7.17 must create a final pre-executor review packet before Phase 8 begins.",
        ],
        "forbidden_scope": [
            "actual_signed_testnet_order_submission",
            "actual_executor_enablement",
            "place_order_enablement",
            "cancel_order_enablement",
            "signed_executor_enablement",
            "api_key_value_access",
            "api_secret_value_access",
            "secret_file_read_or_creation",
            "settings_yaml_mutation",
            "runtime_score_weights_mutation",
            "automatic_promotion_to_signed_testnet_or_live",
            "live_canary_or_live_scaled_execution",
        ],
        "actual_operator_decision_recorded": False,
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
        "created_at_utc": created_at_utc,
    }
    template["operator_decision_intake_template_sha256"] = sha256_json(template)
    template["derived_template_hash"] = template["operator_decision_intake_template_sha256"]
    return template


def _build_template_guard(*, report_id: str, template: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    validation = validate_operator_decision_intake_template(template)
    source_flags = _unsafe_flags_by_artifact(artifacts)
    unsafe: dict[str, list[str]] = dict(source_flags)
    if validation.get("unsafe_truthy_fields"):
        unsafe["operator_decision_intake_template"] = list(validation.get("unsafe_truthy_fields") or [])
    guard_passed = validation.get("template_valid_review_only") is True and not source_flags
    guard = {
        "guard_type": "operator_decision_intake_template_guard_review_only",
        "phase7_15_version": PHASE7_15_VERSION,
        "source_phase7_15_report_id": report_id,
        "source_phase7_14_packet_id": template.get("source_phase7_14_packet_id"),
        "source_phase7_14_packet_hash": template.get("source_phase7_14_packet_hash"),
        "source_ref": template.get("source_ref"),
        "source_hash": template.get("source_hash"),
        "derived_template_hash": template.get("derived_template_hash") or template.get("operator_decision_intake_template_sha256"),
        "review_only": True,
        "template_guard_only": True,
        "guard_passed": guard_passed,
        "template_validation": validation,
        "unsafe_flags_by_artifact": unsafe,
        "source_phase7_14_ready": artifacts.get("phase7_14_operator_decision_packet_report", {}).get("phase7_14_operator_decision_packet_ready") is True,
        "source_operator_decision_guard_passed": artifacts.get("future_executor_operator_decision_guard", {}).get("guard_passed") is True,
        "blocks_executor_enablement": True,
        "blocks_order_submission": True,
        "actual_operator_decision_recorded": False,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
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
    guard["operator_decision_intake_template_guard_report_sha256"] = sha256_json(guard)
    return guard


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    required_lines = "\n".join(f"- `{item}`" for item in OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS)
    return "\n".join(
        [
            "# Phase 7.15 Operator Decision Intake Template - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase creates a manual operator decision intake template for a later Phase 7.16 validator. It does not record an actual operator decision, authorize Phase 8, enable a signed executor, or submit orders.",
            "",
            "## Result",
            "",
            f"- Intake template created: `{report.get('operator_decision_intake_template_created')}`",
            f"- Intake template guard passed: `{report.get('operator_decision_intake_template_guard_passed')}`",
            f"- Phase 7.15 ready: `{report.get('phase7_15_intake_template_ready')}`",
            "",
            "## Required Manual Fields",
            "",
            required_lines,
            "",
            "## Phase 7.14 -> 7.15 Lineage",
            "",
            f"- Source Phase 7.14 packet id: `{report.get('source_phase7_14_packet_id')}`",
            f"- Source Phase 7.14 packet hash: `{report.get('source_phase7_14_packet_hash')}`",
            f"- Derived Phase 7.15 template hash: `{report.get('derived_template_hash')}`",
            "- Approval intake and operator decision intake remain separate.",
            "",
            "## Safety Flags",
            "",
            "- `ready_for_signed_testnet_execution=false`",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `external_order_submission_performed=false`",
            "",
            "## Blockers",
            "",
            blocker_lines,
            "",
            "## Next Allowed Scope",
            "",
            f"`{report.get('phase7_15_allowed_next_scope')}`",
            "",
            "## Final Evidence Statement",
            "",
            str(report.get("final_evidence_statement") or ""),
            "",
        ]
    )


def build_phase7_15_operator_decision_intake_template_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_14_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_14_first:
        persist_phase7_14_future_executor_operator_decision_packet_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    phase7_14 = artifacts.get("phase7_14_operator_decision_packet_report", {})
    operator_packet = artifacts.get("future_executor_operator_decision_packet", {})
    operator_guard = artifacts.get("future_executor_operator_decision_guard", {})

    preliminary_id = stable_id("phase7_15_operator_decision_intake_template", {"source_summary": source_summary, "created_at_utc": created}, 24)
    template = _build_operator_decision_intake_template(report_id=preliminary_id, artifacts=artifacts, created_at_utc=created)
    guard = _build_template_guard(report_id=preliminary_id, template=template, artifacts=artifacts, created_at_utc=created)

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_15_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_15_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_14.get("status") != "PHASE7_14_FUTURE_EXECUTOR_OPERATOR_DECISION_PACKET_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE7_14_OPERATOR_DECISION_PACKET_NOT_READY")
    if phase7_14.get("phase7_14_operator_decision_packet_ready") is not True:
        blockers.append("PHASE7_14_OPERATOR_DECISION_PACKET_READY_FALSE")
    if operator_packet.get("packet_type") != "future_signed_testnet_executor_operator_decision_packet_review_only":
        blockers.append("FUTURE_EXECUTOR_OPERATOR_DECISION_PACKET_INVALID")
    if operator_packet.get("not_runtime_authority") is not True:
        blockers.append("FUTURE_EXECUTOR_OPERATOR_DECISION_PACKET_RUNTIME_AUTHORITY_NOT_BLOCKED")
    if operator_guard.get("guard_type") != "future_signed_testnet_executor_operator_decision_guard_review_only":
        blockers.append("FUTURE_EXECUTOR_OPERATOR_DECISION_GUARD_INVALID")
    if operator_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_OPERATOR_DECISION_GUARD_NOT_PASSED")
    template_validation = validate_operator_decision_intake_template(template)
    if template_validation.get("template_valid_review_only") is not True:
        blockers.extend(template_validation.get("template_blockers") or ["OPERATOR_DECISION_INTAKE_TEMPLATE_INVALID"])
    if guard.get("guard_passed") is not True:
        blockers.append("OPERATOR_DECISION_INTAKE_TEMPLATE_GUARD_NOT_PASSED")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_15_operator_decision_intake_template",
        {
            "source_summary": source_summary,
            "template_hash": sha256_json(template),
            "guard_hash": sha256_json(guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    template["source_phase7_15_report_id"] = report_id
    guard["source_phase7_15_report_id"] = report_id
    template["operator_decision_intake_template_sha256"] = sha256_json(template)
    template["derived_template_hash"] = template["operator_decision_intake_template_sha256"]
    guard["operator_decision_intake_template_guard_report_sha256"] = sha256_json(guard)

    report: dict[str, Any] = {
        "phase7_15_operator_decision_intake_template_id": report_id,
        "phase7_15_version": PHASE7_15_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "template_only": True,
        "phase7_15_intake_template_ready": ready,
        "operator_decision_intake_template_created": True,
        "operator_decision_intake_template_guard_created": True,
        "operator_decision_intake_template_guard_passed": guard.get("guard_passed") is True,
        "actual_operator_decision_recorded": False,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "source_phase7_14_ready": phase7_14.get("phase7_14_operator_decision_packet_ready") is True,
        "source_operator_decision_guard_passed": operator_guard.get("guard_passed") is True,
        "operator_decision_intake_registry_separate_from_approval_intake": True,
        "approval_intake_validator_reused": False,
        "source_phase7_14_packet_id": template.get("source_phase7_14_packet_id"),
        "source_phase7_14_packet_hash": template.get("source_phase7_14_packet_hash"),
        "source_artifact_path": template.get("source_artifact_path"),
        "source_ref": template.get("source_ref"),
        "source_hash": template.get("source_hash"),
        "derived_template_hash": template.get("derived_template_hash"),
        "phase7_14_to_7_15_lineage_preserved": True,
        "operator_decision_intake_required_fields": OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS,
        "phase7_16_intake_validation_required": True,
        "phase7_17_final_pre_executor_review_required": True,
        "final_pre_executor_review_required": True,
        "metadata_only_key_reference_required": True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "phase8_execution_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_15_allowed_next_scope": "phase7_16_operator_decision_intake_validator_still_disabled" if ready else "resolve_phase7_15_operator_decision_intake_template_blockers",
        "recommended_next_action": "prepare_phase7_16_operator_decision_intake_validator_keep_execution_disabled" if ready else "inspect_phase7_15_blockers_and_rerun_phase7_14_phase7_15",
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
        "final_evidence_statement": "Phase 7.15 converted the Phase 7.14 future executor operator decision packet into a review-only operator decision intake template. The conversion preserved the source packet id and hash lineage. No execution permission was granted. All signed testnet, live canary, live scaled, place_order, cancel_order, and external order submission flags remain disabled.",
    }
    report["operator_decision_intake_template_sha256"] = template["operator_decision_intake_template_sha256"]
    report["operator_decision_intake_template_guard_report_sha256"] = guard["operator_decision_intake_template_guard_report_sha256"]
    report["phase7_15_report_sha256"] = sha256_json(report)
    return report, template, guard


def persist_phase7_15_operator_decision_intake_template_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_14_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_15_operator_decision_intake_template")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, template, guard = build_phase7_15_operator_decision_intake_template_report(cfg=cfg, run_phase7_14_first=run_phase7_14_first)
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_15_operator_decision_intake_template_report.json", report)
    atomic_write_json(latest / "operator_decision_intake_TEMPLATE_REVIEW_ONLY.json", template)
    atomic_write_json(latest / "operator_decision_intake_template_guard_report.json", guard)
    (latest / "PHASE7_15_OPERATOR_DECISION_INTAKE_TEMPLATE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(signed_testnet_dir / "operator_decision_intake_TEMPLATE_REVIEW_ONLY.json", template)

    atomic_write_json(phase_dir / "phase7_15_operator_decision_intake_template_report.json", report)
    atomic_write_json(phase_dir / "operator_decision_intake_TEMPLATE_REVIEW_ONLY.json", template)
    atomic_write_json(phase_dir / "operator_decision_intake_template_guard_report.json", guard)
    (phase_dir / "phase7_15_operator_decision_intake_handoff.md").write_text(handoff, encoding="utf-8")
    (phase_dir / "PHASE7_15_OPERATOR_DECISION_INTAKE_TEMPLATE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    negative_fixtures = build_phase7_15_negative_fixtures(template)
    negative_dir = phase_dir / "negative_fixtures"
    negative_dir.mkdir(parents=True, exist_ok=True)
    for fixture_name, fixture_payload in negative_fixtures.items():
        atomic_write_json(negative_dir / fixture_name, fixture_payload)
    negative_results = validate_phase7_15_negative_fixtures(template)
    atomic_write_json(phase_dir / "negative_fixture_results.json", negative_results)
    atomic_write_json(latest / "phase7_15_negative_fixture_results.json", negative_results)

    package_boundary_scan = scan_phase7_15_package_boundary(phase_dir)
    atomic_write_json(phase_dir / "phase7_15_package_boundary_scan.json", package_boundary_scan)
    atomic_write_json(latest / "phase7_15_package_boundary_scan.json", package_boundary_scan)

    validation_report = build_phase7_15_template_validation_report(template, package_boundary_scan=package_boundary_scan)
    atomic_write_json(phase_dir / "phase7_15_operator_decision_intake_template_validation_report.json", validation_report)
    atomic_write_json(latest / "phase7_15_operator_decision_intake_template_validation_report.json", validation_report)

    operator_boundary_registry_record = append_registry_record(
        registry_path(cfg, "operator_decision_intake_template_registry"),
        {
            "operator_decision_intake_registry_id": stable_id(
                "operator_decision_intake_registry",
                {
                    "template_id": template.get("template_id"),
                    "source_phase7_14_packet_id": template.get("source_phase7_14_packet_id"),
                    "source_phase7_14_packet_hash": template.get("source_phase7_14_packet_hash"),
                },
                24,
            ),
            "phase": "7.15",
            "template_id": template.get("template_id"),
            "template_version": PHASE7_15_VERSION,
            "source_phase7_14_packet_id": template.get("source_phase7_14_packet_id"),
            "source_phase7_14_packet_hash": template.get("source_phase7_14_packet_hash"),
            "source_artifact_path": template.get("source_artifact_path"),
            "derived_template_hash": template.get("derived_template_hash"),
            "operator_decision": template.get("operator_decision"),
            "approval_scope": template.get("approval_scope"),
            "risk_ack": template.get("risk_ack"),
            "execution_disabled_ack": template.get("execution_disabled_ack"),
            "operator_signature_placeholder": template.get("operator_signature_placeholder"),
            "timestamp_utc": template.get("timestamp_utc"),
            "validation_status": "PASS_REVIEW_ONLY" if validation_report.get("passed_review_only") is True else "BLOCK_REVIEW_ONLY",
            "guard_report_path": "storage/phase7_15_operator_decision_intake_template/operator_decision_intake_template_guard_report.json",
            "blocked_reason": validation_report.get("template_validation", {}).get("template_blockers") or [],
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name="operator_decision_intake_template_registry",
        id_field="operator_decision_intake_template_registry_record_id",
        hash_field="operator_decision_intake_template_registry_record_sha256",
        id_prefix="operator_decision_intake_template_registry_record",
    )
    atomic_write_json(latest / "operator_decision_intake_template_registry_record.json", operator_boundary_registry_record)
    atomic_write_json(phase_dir / "operator_decision_intake_template_registry_record.json", operator_boundary_registry_record)
    with (phase_dir / "operator_decision_intake_template_registry.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(operator_boundary_registry_record, ensure_ascii=False, sort_keys=True, default=str) + "\n")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_15_REGISTRY_NAME),
        {
            "phase7_15_operator_decision_intake_template_id": report.get("phase7_15_operator_decision_intake_template_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_15_intake_template_ready": report.get("phase7_15_intake_template_ready"),
            "operator_decision_intake_template_created": report.get("operator_decision_intake_template_created"),
            "operator_decision_intake_template_guard_passed": report.get("operator_decision_intake_template_guard_passed"),
            "operator_decision_intake_registry_id": operator_boundary_registry_record.get("operator_decision_intake_registry_id"),
            "template_id": template.get("template_id"),
            "source_phase7_14_packet_id": template.get("source_phase7_14_packet_id"),
            "source_phase7_14_packet_hash": template.get("source_phase7_14_packet_hash"),
            "source_ref": template.get("source_ref"),
            "source_hash": template.get("source_hash"),
            "derived_template_hash": template.get("derived_template_hash"),
            "phase7_15_template_validation_report_sha256": validation_report.get("phase7_15_operator_decision_intake_template_validation_report_sha256"),
            "negative_fixture_results_sha256": negative_results.get("negative_fixture_results_sha256"),
            "phase7_15_package_boundary_scan_sha256": package_boundary_scan.get("phase7_15_package_boundary_scan_sha256"),
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
        registry_name=PHASE7_15_REGISTRY_NAME,
        id_field="phase7_15_operator_decision_intake_template_registry_record_id",
        hash_field="phase7_15_operator_decision_intake_template_registry_record_sha256",
        id_prefix="phase7_15_operator_decision_intake_template_registry_record",
    )
    atomic_write_json(latest / "phase7_15_operator_decision_intake_template_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_15_operator_decision_intake_template_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_15_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "OPERATOR_DECISION_INTAKE_REQUIRED_FIELDS",
    "ALLOWED_DECISION_OPTIONS",
    "validate_operator_decision_intake_template",
    "build_phase7_15_negative_fixtures",
    "validate_phase7_15_negative_fixtures",
    "build_phase7_15_template_validation_report",
    "scan_phase7_15_package_boundary",
    "build_phase7_15_operator_decision_intake_template_report",
    "persist_phase7_15_operator_decision_intake_template_report",
]
