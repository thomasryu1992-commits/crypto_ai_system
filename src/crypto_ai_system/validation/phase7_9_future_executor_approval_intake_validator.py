from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase7_8_future_executor_approval_packet_template import (
    OPERATOR_REQUIRED_FIELDS,
    persist_phase7_8_future_executor_approval_packet_template_report,
)

PHASE7_9_VERSION = "phase7_9_future_executor_approval_intake_validator_v1"
PHASE7_9_REGISTRY_NAME = "phase7_9_future_executor_approval_intake_validator_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_9_FUTURE_EXECUTOR_APPROVAL_INTAKE_VALIDATOR_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_9_FUTURE_EXECUTOR_APPROVAL_INTAKE_VALIDATOR_BLOCKED_REVIEW_ONLY"

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_8_template_report": "phase7_8_future_executor_approval_packet_template_report.json",
    "future_executor_approval_template": "future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY.json",
    "future_executor_approval_template_guard": "future_signed_testnet_executor_approval_template_guard_report.json",
    "future_executor_prerequisite_packet": "future_signed_testnet_executor_review_prerequisite_packet_review_only.json",
}

UNSAFE_TRUTHY_FIELDS = [
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
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

FRESH_RECHECK_FIELDS = [
    "kill_switch_rechecked",
    "hard_caps_rechecked",
    "pre_order_risk_gate_rechecked",
    "fresh_pre_submit_payload_validation_required",
    "fresh_pre_order_risk_gate_recheck_required",
    "reconciliation_required_after_any_session",
    "session_close_report_required",
]

SUBMISSION_TEMPLATE_NAME = "future_executor_approval_packet_submission_TEMPLATE_REVIEW_ONLY.json"
ACTUAL_SUBMISSION_NAME = "future_executor_approval_packet_submission.json"


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


def _read_signed_testnet_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    payload = read_json(cfg.root / "storage" / "signed_testnet" / name, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _as_positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _as_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _looks_like_placeholder(value: Any) -> bool:
    return _safe_text(value).startswith("MANUAL_REQUIRED")


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
        "phase7_9_report_sha256",
        "phase7_8_report_sha256",
        "future_executor_approval_template_sha256",
        "future_executor_approval_template_guard_report_sha256",
        "future_executor_prerequisite_packet_sha256",
        "future_executor_approval_intake_validation_record_sha256",
        "future_executor_approval_intake_guard_report_sha256",
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


def _build_submission_template(*, template: Mapping[str, Any], created_at_utc: str) -> dict[str, Any]:
    payload = dict(template or {})
    payload.pop("future_executor_approval_template_sha256", None)
    payload.update(
        {
            "template_type": "future_signed_testnet_executor_approval_packet_submission_TEMPLATE_REVIEW_ONLY",
            "phase7_9_version": PHASE7_9_VERSION,
            "review_only": True,
            "template_only": True,
            "submission_template_only": True,
            "not_runtime_authority": True,
            "write_target_when_manually_completed": "storage/signed_testnet/future_executor_approval_packet_submission.json",
            "actual_executor_approval_created": False,
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
    )
    payload["future_executor_approval_packet_submission_template_sha256"] = sha256_json(payload)
    return payload


def _fill_if_placeholder(value: Any, replacement: str) -> Any:
    return replacement if _looks_like_placeholder(value) or not _safe_text(value) else value


def _build_valid_submission_fixture(*, template: Mapping[str, Any], created_at_utc: str) -> dict[str, Any]:
    seed = {
        "template_hash": sha256_json(dict(template or {})),
        "created_at_utc": created_at_utc,
    }
    prerequisite_hash = _safe_text(template.get("prerequisite_packet_hash") or template.get("source_prerequisite_packet_hash"))
    fixture = dict(template or {})
    fixture.pop("future_executor_approval_template_sha256", None)
    fixture.pop("future_executor_approval_packet_submission_template_sha256", None)
    fixture.update(
        {
            "fixture_type": "future_signed_testnet_executor_approval_packet_valid_submission_fixture_review_only",
            "phase7_9_version": PHASE7_9_VERSION,
            "review_only": True,
            "submission_fixture_only": True,
            "not_runtime_authority": True,
            "executor_approval_packet_id": stable_id("future_executor_approval_packet_fixture", seed, 24),
            "operator_id": "fixture_operator_review_only",
            "operator_ticket_or_signature": "fixture_operator_ticket_or_signature_review_only",
            "canonical_utc_timestamp": created_at_utc,
            "approved_profile_id": _fill_if_placeholder(template.get("approved_profile_id"), "fixture_approved_profile_review_only"),
            "approved_profile_hash": _fill_if_placeholder(template.get("approved_profile_hash"), "fixture_approved_profile_hash_review_only"),
            "approval_intake_id": _fill_if_placeholder(template.get("approval_intake_id"), "fixture_approval_intake_review_only"),
            "approval_packet_id": _fill_if_placeholder(template.get("approval_packet_id"), "fixture_approval_packet_review_only"),
            "prerequisite_packet_hash": prerequisite_hash,
            "metadata_only_key_reference_id": "metadata_only_key_reference_fixture_review_only",
            "metadata_only_key_fingerprint": "metadata_only_key_fingerprint_fixture_review_only",
            "max_testnet_notional_usd": 25.0,
            "max_testnet_order_count": 1,
            "max_testnet_daily_loss_usd": 10.0,
            "kill_switch_rechecked": True,
            "hard_caps_rechecked": True,
            "pre_order_risk_gate_rechecked": True,
            "fresh_pre_submit_payload_validation_required": True,
            "fresh_pre_order_risk_gate_recheck_required": True,
            "reconciliation_required_after_any_session": True,
            "session_close_report_required": True,
            "actual_executor_approval_created": False,
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
    )
    fixture["future_executor_approval_packet_submission_fixture_sha256"] = sha256_json(fixture)
    return fixture


def _clone_with_modification(
    base: Mapping[str, Any], *, fixture_type: str, modifications: Mapping[str, Any] | None = None, drop_fields: list[str] | None = None
) -> dict[str, Any]:
    payload = dict(base)
    payload.pop("future_executor_approval_packet_submission_fixture_sha256", None)
    for field in drop_fields or []:
        payload.pop(field, None)
    payload.update(dict(modifications or {}))
    payload["fixture_type"] = fixture_type
    payload["future_executor_approval_packet_submission_fixture_sha256"] = sha256_json(payload)
    return payload


def _build_invalid_fixtures(valid: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "missing_metadata_fingerprint": _clone_with_modification(
            valid,
            fixture_type="future_executor_approval_invalid_missing_metadata_fingerprint_fixture_review_only",
            drop_fields=["metadata_only_key_fingerprint"],
        ),
        "prerequisite_hash_mismatch": _clone_with_modification(
            valid,
            fixture_type="future_executor_approval_invalid_prerequisite_hash_mismatch_fixture_review_only",
            modifications={"prerequisite_packet_hash": "invalid_prerequisite_hash_review_only"},
        ),
        "hard_cap_exceeded": _clone_with_modification(
            valid,
            fixture_type="future_executor_approval_invalid_hard_cap_exceeded_fixture_review_only",
            modifications={"max_testnet_notional_usd": 250000.0},
        ),
        "kill_switch_not_rechecked": _clone_with_modification(
            valid,
            fixture_type="future_executor_approval_invalid_kill_switch_not_rechecked_fixture_review_only",
            modifications={"kill_switch_rechecked": False},
        ),
        "unsafe_executor_flag": _clone_with_modification(
            valid,
            fixture_type="future_executor_approval_invalid_unsafe_executor_flag_fixture_review_only",
            modifications={"signed_order_executor_enabled": True, "testnet_order_submission_allowed": True},
        ),
    }


def validate_future_executor_approval_submission(
    submission: Mapping[str, Any], *, template: Mapping[str, Any], prerequisite_packet: Mapping[str, Any]
) -> dict[str, Any]:
    payload = dict(submission or {})
    required_missing = [field for field in OPERATOR_REQUIRED_FIELDS if not _safe_text(payload.get(field))]
    placeholder_fields = [field for field in OPERATOR_REQUIRED_FIELDS if _looks_like_placeholder(payload.get(field))]
    unsafe = _unsafe_fields(payload)
    blockers: list[str] = []
    if not payload:
        blockers.append("FUTURE_EXECUTOR_APPROVAL_SUBMISSION_MISSING")
    if required_missing:
        blockers.append(f"MISSING_REQUIRED_FIELDS:{','.join(required_missing)}")
    if placeholder_fields:
        blockers.append(f"PLACEHOLDER_FIELDS_NOT_FILLED:{','.join(placeholder_fields)}")
    timestamp = payload.get("canonical_utc_timestamp")
    if timestamp and not is_canonical_utc_timestamp(str(timestamp)):
        blockers.append("CANONICAL_UTC_TIMESTAMP_INVALID")
    expected_prereq_hash = sha256_json(dict(prerequisite_packet or {})) if prerequisite_packet else template.get("prerequisite_packet_hash")
    if _safe_text(payload.get("prerequisite_packet_hash")) != _safe_text(expected_prereq_hash):
        blockers.append("PREREQUISITE_PACKET_HASH_MISMATCH")
    if not _safe_text(payload.get("metadata_only_key_reference_id")):
        blockers.append("METADATA_ONLY_KEY_REFERENCE_ID_MISSING")
    if not _safe_text(payload.get("metadata_only_key_fingerprint")):
        blockers.append("METADATA_ONLY_KEY_FINGERPRINT_MISSING")
    for field in ("metadata_only_key_reference_id", "metadata_only_key_fingerprint"):
        value = _safe_text(payload.get(field)).lower()
        if any(term in value for term in ("api_secret", "private_key", "passphrase", "secret_value")):
            blockers.append(f"METADATA_ONLY_KEY_FIELD_LOOKS_LIKE_SECRET_VALUE:{field}")
    notional = _as_positive_float(payload.get("max_testnet_notional_usd"))
    order_count = _as_positive_int(payload.get("max_testnet_order_count"))
    daily_loss = _as_positive_float(payload.get("max_testnet_daily_loss_usd"))
    if notional is None:
        blockers.append("MAX_TESTNET_NOTIONAL_INVALID")
    elif notional > 25.0:
        blockers.append("MAX_TESTNET_NOTIONAL_EXCEEDS_REVIEW_CAP")
    if order_count is None:
        blockers.append("MAX_TESTNET_ORDER_COUNT_INVALID")
    elif order_count > 1:
        blockers.append("MAX_TESTNET_ORDER_COUNT_EXCEEDS_REVIEW_CAP")
    if daily_loss is None:
        blockers.append("MAX_TESTNET_DAILY_LOSS_INVALID")
    elif daily_loss > 10.0:
        blockers.append("MAX_TESTNET_DAILY_LOSS_EXCEEDS_REVIEW_CAP")
    missing_rechecks = [field for field in FRESH_RECHECK_FIELDS if payload.get(field) is not True]
    if missing_rechecks:
        blockers.append(f"REQUIRED_FRESH_RECHECK_FIELDS_NOT_TRUE:{','.join(missing_rechecks)}")
    if unsafe:
        blockers.append(f"UNSAFE_FUTURE_EXECUTOR_APPROVAL_FIELDS_TRUE:{','.join(unsafe)}")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    valid = not blockers
    return {
        "submission_valid_review_only": valid,
        "submission_blocked_fail_closed": not valid,
        "required_missing_fields": required_missing,
        "placeholder_fields_not_filled": placeholder_fields,
        "unsafe_truthy_fields": unsafe,
        "submission_blockers": blockers,
        "metadata_only_key_reference_present": bool(_safe_text(payload.get("metadata_only_key_reference_id"))),
        "metadata_only_key_fingerprint_present": bool(_safe_text(payload.get("metadata_only_key_fingerprint"))),
        "prerequisite_packet_hash_matches": "PREREQUISITE_PACKET_HASH_MISMATCH" not in blockers,
        "hard_caps_numeric": notional is not None and order_count is not None and daily_loss is not None,
        "fresh_rechecks_true": not missing_rechecks,
    }


def _build_guard_report(*, report_id: str, validation: Mapping[str, Any], invalid_results: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    invalid_blocked = all(result.get("submission_blocked_fail_closed") is True for result in invalid_results.values())
    guard_passed = validation.get("submission_valid_review_only") is True and invalid_blocked
    return {
        "guard_type": "future_signed_testnet_executor_approval_intake_guard_review_only",
        "source_phase7_9_report_id": report_id,
        "review_only": True,
        "intake_validation_only": True,
        "guard_passed": guard_passed,
        "valid_submission_fixture_passed_review_only_validation": validation.get("submission_valid_review_only") is True,
        "invalid_submission_fixtures_blocked_fail_closed": invalid_blocked,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 7.9 Future Executor Approval Intake Validator — Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase validates a review-only future executor approval intake fixture/submission against the Phase 7.8 template and Phase 7.7 prerequisite hash. It does not approve an executor, enable execution, submit orders, read secrets, mutate settings, or promote to testnet/live.",
            "",
            "## Result",
            "",
            f"- Intake validation ready: `{report.get('phase7_9_intake_validation_ready')}`",
            f"- Validation record created: `{report.get('future_executor_approval_intake_validation_record_created')}`",
            f"- Intake guard passed: `{report.get('intake_guard_passed')}`",
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
            f"`{report.get('phase7_9_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_9_future_executor_approval_intake_validator_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_8_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_8_first:
        persist_phase7_8_future_executor_approval_packet_template_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    phase7_8 = artifacts.get("phase7_8_template_report", {})
    template = artifacts.get("future_executor_approval_template", {})
    template_guard = artifacts.get("future_executor_approval_template_guard", {})
    prerequisite_packet = artifacts.get("future_executor_prerequisite_packet", {})

    report_seed = {"source_summary": source_summary, "created_at_utc": created}
    preliminary_id = stable_id("phase7_9_future_executor_approval_intake_validator", report_seed, 24)
    submission_template = _build_submission_template(template=template, created_at_utc=created)
    valid_fixture = _build_valid_submission_fixture(template=template, created_at_utc=created)
    invalid_fixtures = _build_invalid_fixtures(valid_fixture)
    actual_submission = _read_signed_testnet_json(cfg, ACTUAL_SUBMISSION_NAME)
    submission_to_validate = actual_submission or valid_fixture
    validation = validate_future_executor_approval_submission(submission_to_validate, template=template, prerequisite_packet=prerequisite_packet)
    invalid_results = {
        name: validate_future_executor_approval_submission(payload, template=template, prerequisite_packet=prerequisite_packet)
        for name, payload in invalid_fixtures.items()
    }
    guard = _build_guard_report(report_id=preliminary_id, validation=validation, invalid_results=invalid_results, created_at_utc=created)

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_9_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_9_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_8.get("status") != "PHASE7_8_FUTURE_EXECUTOR_APPROVAL_PACKET_TEMPLATE_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE7_8_TEMPLATE_REPORT_NOT_READY")
    if phase7_8.get("phase7_8_template_ready") is not True:
        blockers.append("PHASE7_8_TEMPLATE_NOT_READY")
    if template.get("template_type") != "future_signed_testnet_executor_approval_packet_TEMPLATE_REVIEW_ONLY":
        blockers.append("FUTURE_EXECUTOR_APPROVAL_TEMPLATE_INVALID")
    if template_guard.get("guard_type") != "future_signed_testnet_executor_approval_template_guard_review_only":
        blockers.append("FUTURE_EXECUTOR_APPROVAL_TEMPLATE_GUARD_INVALID")
    if template_guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_APPROVAL_TEMPLATE_GUARD_NOT_PASSED")
    if prerequisite_packet.get("packet_type") != "future_signed_testnet_executor_review_prerequisite_packet_review_only":
        blockers.append("PREREQUISITE_PACKET_INVALID")
    if validation.get("submission_valid_review_only") is not True:
        blockers.extend([f"FUTURE_EXECUTOR_APPROVAL_SUBMISSION_INVALID:{item}" for item in validation.get("submission_blockers", [])])
    if guard.get("guard_passed") is not True:
        blockers.append("FUTURE_EXECUTOR_APPROVAL_INTAKE_GUARD_NOT_PASSED")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_9_future_executor_approval_intake_validator",
        {
            "source_summary": source_summary,
            "validation_hash": sha256_json(validation),
            "guard_hash": sha256_json(guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    guard = {**guard, "source_phase7_9_report_id": report_id}
    validation_record = {
        "record_type": "future_signed_testnet_executor_approval_intake_validation_record_review_only",
        "phase7_9_version": PHASE7_9_VERSION,
        "source_phase7_9_report_id": report_id,
        "review_only": True,
        "intake_validation_only": True,
        "actual_operator_submission_present": bool(actual_submission),
        "validated_submission_source": "actual_operator_submission" if actual_submission else "valid_review_only_fixture",
        "submission_valid_review_only": validation.get("submission_valid_review_only") is True,
        "submission_blocked_fail_closed": validation.get("submission_blocked_fail_closed") is True,
        "validation": validation,
        "invalid_fixture_validation": invalid_results,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "created_at_utc": created,
    }
    validation_record["future_executor_approval_intake_validation_record_sha256"] = sha256_json(validation_record)

    report: dict[str, Any] = {
        "phase7_9_future_executor_approval_intake_validator_id": report_id,
        "phase7_9_version": PHASE7_9_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "intake_validation_only": True,
        "phase7_9_intake_validation_ready": ready,
        "future_executor_approval_submission_template_created": True,
        "future_executor_approval_intake_validation_record_created": True,
        "future_executor_approval_intake_guard_created": True,
        "intake_guard_passed": guard.get("guard_passed") is True,
        "actual_operator_submission_present": bool(actual_submission),
        "validated_submission_source": "actual_operator_submission" if actual_submission else "valid_review_only_fixture",
        "valid_future_executor_approval_submission_passed_review_only_validation": validation.get("submission_valid_review_only") is True,
        "invalid_future_executor_approval_submission_fixture_count": len(invalid_fixtures),
        "invalid_future_executor_approval_submission_fixtures_blocked_fail_closed": all(
            result.get("submission_blocked_fail_closed") is True for result in invalid_results.values()
        ),
        "validation": validation,
        "invalid_fixture_validation": invalid_results,
        "actual_executor_approval_created": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_approval_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_promotion_authority": False,
        "metadata_only_key_reference_validated_review_only": validation.get("metadata_only_key_reference_present") is True
        and validation.get("metadata_only_key_fingerprint_present") is True,
        "fresh_pre_submit_payload_validation_required": True,
        "fresh_pre_order_risk_gate_recheck_required": True,
        "manual_kill_switch_confirmation_required": True,
        "reconciliation_required_after_any_session": True,
        "session_close_report_required": True,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_9_allowed_next_scope": "future_executor_approval_review_packet_still_disabled" if ready else "resolve_phase7_9_intake_blockers",
        "recommended_next_action": "prepare_phase7_10_future_executor_approval_review_packet_keep_execution_disabled" if ready else "inspect_phase7_9_blockers_and_rerun_phase7_8_phase7_9",
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
    report["future_executor_approval_submission_template_sha256"] = sha256_json(submission_template)
    report["valid_future_executor_approval_submission_fixture_sha256"] = sha256_json(valid_fixture)
    report["future_executor_approval_intake_validation_record_sha256"] = validation_record["future_executor_approval_intake_validation_record_sha256"]
    report["future_executor_approval_intake_guard_report_sha256"] = sha256_json(guard)
    report["phase7_9_report_sha256"] = sha256_json(report)
    return report, submission_template, validation_record, guard, {"valid": valid_fixture, **invalid_fixtures}


def persist_phase7_9_future_executor_approval_intake_validator_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_8_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_9_future_executor_approval_intake_validator")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    fixture_dir = _storage_dir(cfg, "storage/signed_testnet/fixtures")
    report, submission_template, validation_record, guard, fixtures = build_phase7_9_future_executor_approval_intake_validator_report(
        cfg=cfg, run_phase7_8_first=run_phase7_8_first
    )
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_9_future_executor_approval_intake_validator_report.json", report)
    atomic_write_json(latest / "future_signed_testnet_executor_approval_intake_validation_record_review_only.json", validation_record)
    atomic_write_json(latest / "future_signed_testnet_executor_approval_intake_guard_report.json", guard)
    (latest / "PHASE7_9_FUTURE_EXECUTOR_APPROVAL_INTAKE_VALIDATOR_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(signed_testnet_dir / SUBMISSION_TEMPLATE_NAME, submission_template)
    atomic_write_json(latest / "future_executor_approval_packet_submission_TEMPLATE_REVIEW_ONLY.json", submission_template)
    for name, payload in fixtures.items():
        atomic_write_json(fixture_dir / f"future_executor_approval_packet_{name}_submission_FIXTURE_REVIEW_ONLY.json", payload)

    atomic_write_json(phase_dir / "phase7_9_future_executor_approval_intake_validator_report.json", report)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_approval_intake_validation_record_review_only.json", validation_record)
    atomic_write_json(phase_dir / "future_signed_testnet_executor_approval_intake_guard_report.json", guard)
    atomic_write_json(phase_dir / SUBMISSION_TEMPLATE_NAME, submission_template)
    (phase_dir / "PHASE7_9_FUTURE_EXECUTOR_APPROVAL_INTAKE_VALIDATOR_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_9_REGISTRY_NAME),
        {
            "phase7_9_future_executor_approval_intake_validator_id": report.get("phase7_9_future_executor_approval_intake_validator_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_9_intake_validation_ready": report.get("phase7_9_intake_validation_ready"),
            "intake_guard_passed": report.get("intake_guard_passed"),
            "actual_executor_approval_created": False,
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
        registry_name=PHASE7_9_REGISTRY_NAME,
        id_field="phase7_9_future_executor_approval_intake_validator_registry_record_id",
        hash_field="phase7_9_future_executor_approval_intake_validator_registry_record_sha256",
        id_prefix="phase7_9_future_executor_approval_intake_validator_registry_record",
    )
    atomic_write_json(latest / "phase7_9_future_executor_approval_intake_validator_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_9_future_executor_approval_intake_validator_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_9_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "validate_future_executor_approval_submission",
    "build_phase7_9_future_executor_approval_intake_validator_report",
    "persist_phase7_9_future_executor_approval_intake_validator_report",
]
