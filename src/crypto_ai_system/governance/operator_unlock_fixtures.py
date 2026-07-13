from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.governance.readiness_common import (
    positive_float as _as_positive_float,
    positive_int as _as_positive_int,
    latest_dir as _latest_dir,
    read_latest_json as _read_latest_json,
    bool_value as _safe_bool,
    safe_text as _safe_text,
    storage_dir as _storage_dir,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

PHASE6_2_VERSION = "phase6_2_operator_unlock_request_fixture_validator_v1"
PHASE6_2_REGISTRY_NAME = "phase6_2_operator_unlock_request_fixture_validator_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE6_2_OPERATOR_UNLOCK_REQUEST_FIXTURE_VALIDATOR_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE6_2_OPERATOR_UNLOCK_REQUEST_FIXTURE_VALIDATOR_BLOCKED_REVIEW_ONLY"

REQUIRED_UNLOCK_FIELDS = [
    "operator_unlock_request_id",
    "operator_id",
    "operator_ticket_or_signature",
    "canonical_utc_timestamp",
    "approval_intake_id",
    "approval_packet_id",
    "phase6_preparation_preview_hash",
    "pre_submit_validation_hash",
    "venue_probe_hash",
    "enablement_packet_hash",
    "max_testnet_notional_usd",
    "max_testnet_order_count",
    "max_testnet_daily_loss_usd",
    "kill_switch_rechecked",
    "hard_caps_rechecked",
    "pre_order_risk_gate_rechecked",
]

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
    "live_trading_allowed",
    "auto_promotion_allowed",
]

MANUAL_PLACEHOLDER_PREFIX = "MANUAL_REQUIRED"


def _source_blockers(phase6_1: Mapping[str, Any], template: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if phase6_1.get("status") != "PHASE6_1_SIGNED_TESTNET_OPERATOR_UNLOCK_REQUEST_TEMPLATE_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE6_1_OPERATOR_UNLOCK_TEMPLATE_NOT_READY")
    if not template:
        blockers.append("OPERATOR_UNLOCK_TEMPLATE_MISSING")
    if template and template.get("do_not_write_automatically") is not True:
        blockers.append("OPERATOR_UNLOCK_TEMPLATE_AUTO_WRITE_GUARD_MISSING")
    if template and template.get("write_target_when_manually_approved") != "storage/latest/operator_unlock_request.json":
        blockers.append("OPERATOR_UNLOCK_TEMPLATE_TARGET_INVALID")
    return sorted(dict.fromkeys(blockers))


def _build_valid_fixture(template: Mapping[str, Any], created: str) -> dict[str, Any]:
    seed = {
        "template_id": template.get("operator_unlock_request_id"),
        "phase6_hash": template.get("phase6_preparation_preview_hash"),
        "pre_submit_hash": template.get("pre_submit_validation_hash"),
        "venue_probe_hash": template.get("venue_probe_hash"),
        "enablement_hash": template.get("enablement_packet_hash"),
        "created_at_utc": created,
    }
    fixture = dict(template)
    fixture.pop("operator_unlock_request_template_sha256", None)
    fixture.update(
        {
            "fixture_type": "operator_unlock_request_valid_fixture",
            "fixture_version": PHASE6_2_VERSION,
            "review_only_fixture": True,
            "do_not_copy_to_runtime_without_human_review": True,
            "operator_unlock_request_id": stable_id("operator_unlock_request_fixture", seed, 24),
            "operator_id": "fixture_operator_review_only",
            "operator_ticket_or_signature": "fixture_operator_ticket_or_signature_review_only",
            "canonical_utc_timestamp": created,
            "approval_intake_id": "fixture_validated_approval_intake_review_only",
            "approval_packet_id": "fixture_validated_approval_packet_review_only",
            "requested_stage": "signed_testnet_preparation_fixture_review_only",
            "requested_action": "operator_unlock_request_fixture_validation_only",
            "max_testnet_notional_usd": 25.0,
            "max_testnet_order_count": 1,
            "max_testnet_daily_loss_usd": 10.0,
            "kill_switch_rechecked": True,
            "hard_caps_rechecked": True,
            "pre_order_risk_gate_rechecked": True,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "signed_testnet_promotion_allowed": False,
            "external_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "api_key_value_access_allowed": False,
            "api_secret_value_access_allowed": False,
            "secret_file_access_allowed": False,
            "secret_file_creation_allowed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "live_trading_allowed": False,
            "auto_promotion_allowed": False,
            "created_at_utc": created,
        }
    )
    fixture["operator_unlock_request_fixture_sha256"] = sha256_json(fixture)
    return fixture


def _clone_with_modification(
    base: Mapping[str, Any],
    *,
    fixture_type: str,
    modifications: Mapping[str, Any] | None = None,
    drop_fields: list[str] | None = None,
) -> dict[str, Any]:
    payload = dict(base)
    payload.pop("operator_unlock_request_fixture_sha256", None)
    for field in drop_fields or []:
        payload.pop(field, None)
    payload.update(dict(modifications or {}))
    payload["fixture_type"] = fixture_type
    payload["operator_unlock_request_fixture_sha256"] = sha256_json(payload)
    return payload


def _build_invalid_fixtures(valid_fixture: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "missing_operator_signature": _clone_with_modification(
            valid_fixture,
            fixture_type="operator_unlock_request_invalid_missing_operator_signature_fixture",
            drop_fields=["operator_ticket_or_signature"],
        ),
        "hash_mismatch": _clone_with_modification(
            valid_fixture,
            fixture_type="operator_unlock_request_invalid_hash_mismatch_fixture",
            modifications={"pre_submit_validation_hash": "fixture_invalid_pre_submit_validation_hash"},
        ),
        "missing_hard_cap": _clone_with_modification(
            valid_fixture,
            fixture_type="operator_unlock_request_invalid_missing_hard_cap_fixture",
            drop_fields=["max_testnet_notional_usd"],
        ),
        "kill_switch_not_rechecked": _clone_with_modification(
            valid_fixture,
            fixture_type="operator_unlock_request_invalid_kill_switch_not_rechecked_fixture",
            modifications={"kill_switch_rechecked": False},
        ),
        "unsafe_unlock_flag": _clone_with_modification(
            valid_fixture,
            fixture_type="operator_unlock_request_invalid_unsafe_unlock_flag_fixture",
            modifications={"testnet_order_submission_allowed": True, "place_order_enabled": True},
        ),
    }


def _validate_unlock_fixture(submission: Mapping[str, Any], template: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    for field in REQUIRED_UNLOCK_FIELDS:
        if not _safe_text(submission.get(field)):
            blockers.append(f"OPERATOR_UNLOCK_FIELD_MISSING:{field}")
    for field in ("operator_id", "operator_ticket_or_signature", "approval_intake_id", "approval_packet_id"):
        value = _safe_text(submission.get(field))
        if value.startswith(MANUAL_PLACEHOLDER_PREFIX):
            blockers.append(f"OPERATOR_UNLOCK_PLACEHOLDER_NOT_REPLACED:{field}")
    timestamp = submission.get("canonical_utc_timestamp")
    if timestamp and not is_canonical_utc_timestamp(str(timestamp)):
        blockers.append("OPERATOR_UNLOCK_TIMESTAMP_NOT_CANONICAL_UTC")
    expected_pairs = {
        "phase6_preparation_preview_hash": template.get("phase6_preparation_preview_hash"),
        "pre_submit_validation_hash": template.get("pre_submit_validation_hash"),
        "venue_probe_hash": template.get("venue_probe_hash"),
        "enablement_packet_hash": template.get("enablement_packet_hash"),
    }
    for field, expected in expected_pairs.items():
        if _safe_text(submission.get(field)) != _safe_text(expected):
            blockers.append(f"OPERATOR_UNLOCK_HASH_CHAIN_MISMATCH:{field}")
    notional = _as_positive_float(submission.get("max_testnet_notional_usd"))
    order_count = _as_positive_int(submission.get("max_testnet_order_count"))
    daily_loss = _as_positive_float(submission.get("max_testnet_daily_loss_usd"))
    if notional is None:
        blockers.append("OPERATOR_UNLOCK_HARD_CAP_INVALID:max_testnet_notional_usd")
    elif notional > 100.0:
        blockers.append("OPERATOR_UNLOCK_HARD_CAP_TOO_HIGH:max_testnet_notional_usd")
    if order_count is None:
        blockers.append("OPERATOR_UNLOCK_HARD_CAP_INVALID:max_testnet_order_count")
    elif order_count > 5:
        blockers.append("OPERATOR_UNLOCK_HARD_CAP_TOO_HIGH:max_testnet_order_count")
    if daily_loss is None:
        blockers.append("OPERATOR_UNLOCK_HARD_CAP_INVALID:max_testnet_daily_loss_usd")
    elif daily_loss > 50.0:
        blockers.append("OPERATOR_UNLOCK_HARD_CAP_TOO_HIGH:max_testnet_daily_loss_usd")
    for field in ("kill_switch_rechecked", "hard_caps_rechecked", "pre_order_risk_gate_rechecked"):
        if submission.get(field) is not True:
            blockers.append(f"OPERATOR_UNLOCK_REQUIRED_RECHECK_NOT_TRUE:{field}")
    for field in UNSAFE_TRUTHY_FIELDS:
        if _safe_bool(submission.get(field)):
            blockers.append(f"UNSAFE_OPERATOR_UNLOCK_FIELD_TRUE:{field}")
    blocked = bool(blockers)
    return {
        "blocked": blocked,
        "fail_closed": blocked,
        "passed_review_only_validation": not blocked,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "operator_unlock_request_validated": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "external_order_submission_performed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }


def build_phase6_2_operator_unlock_request_fixture_validator_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    phase6_1 = _read_latest_json(cfg, "phase6_1_signed_testnet_operator_unlock_request_template_report.json")
    template = _read_latest_json(cfg, "operator_unlock_request_template_review_only.json")
    actual_latest_path = _latest_dir(cfg) / "operator_unlock_request.json"
    actual_archive_path = cfg.root / "storage" / "signed_testnet" / "operator_unlock_request.json"
    source_blockers = _source_blockers(phase6_1, template)
    if actual_latest_path.exists() or actual_archive_path.exists():
        source_blockers.append("ACTUAL_OPERATOR_UNLOCK_REQUEST_PATH_PRESENT_UNEXPECTED")

    valid_fixture = _build_valid_fixture(template, created) if template else {}
    invalid_fixtures = _build_invalid_fixtures(valid_fixture) if valid_fixture else {}
    valid_result = _validate_unlock_fixture(valid_fixture, template) if valid_fixture and template else {
        "blocked": True,
        "fail_closed": True,
        "passed_review_only_validation": False,
        "block_reasons": ["VALID_OPERATOR_UNLOCK_FIXTURE_NOT_BUILT"],
        "operator_unlock_request_validated": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "external_order_submission_performed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
    }
    invalid_results = {
        name: _validate_unlock_fixture(payload, template)
        for name, payload in invalid_fixtures.items()
    }
    invalid_all_blocked = bool(invalid_results) and all(result.get("blocked") and result.get("fail_closed") for result in invalid_results.values())
    valid_passed = bool(valid_result.get("passed_review_only_validation")) and not bool(valid_result.get("blocked"))

    blockers = list(source_blockers)
    if not valid_passed:
        blockers.append("VALID_OPERATOR_UNLOCK_FIXTURE_DID_NOT_PASS_REVIEW_ONLY_VALIDATION")
    if not invalid_all_blocked:
        blockers.append("INVALID_OPERATOR_UNLOCK_FIXTURE_NOT_BLOCKED_FAIL_CLOSED")
    blockers = sorted(dict.fromkeys(blockers))
    blocked = bool(blockers)
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY
    phase6_2_id = stable_id(
        "phase6_2_operator_unlock_request_fixture_validator",
        {
            "phase6_1_id": phase6_1.get("phase6_1_signed_testnet_operator_unlock_request_template_id"),
            "template_sha256": template.get("operator_unlock_request_template_sha256"),
            "valid_fixture_sha256": valid_fixture.get("operator_unlock_request_fixture_sha256"),
            "created_at_utc": created,
            "blocked": blocked,
        },
        24,
    )
    report: dict[str, Any] = {
        "phase6_2_operator_unlock_request_fixture_validator_id": phase6_2_id,
        "phase6_2_version": PHASE6_2_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "fixture_only": True,
        "operator_unlock_request_fixture_validator_only": True,
        "valid_operator_unlock_fixture_created": bool(valid_fixture),
        "valid_operator_unlock_fixture_passed_review_only_validation": valid_passed,
        "invalid_operator_unlock_fixture_count": len(invalid_results),
        "invalid_operator_unlock_fixtures_blocked_fail_closed": invalid_all_blocked,
        "valid_operator_unlock_fixture_result": valid_result,
        "invalid_operator_unlock_fixture_results": invalid_results,
        "valid_operator_unlock_fixture_path": "storage/signed_testnet/fixtures/valid_operator_unlock_request_FIXTURE_REVIEW_ONLY.json",
        "invalid_operator_unlock_fixture_paths": {
            name: f"storage/signed_testnet/fixtures/invalid_{name}_operator_unlock_request_FIXTURE_REVIEW_ONLY.json"
            for name in invalid_fixtures
        },
        "operator_unlock_request_template_sha256": template.get("operator_unlock_request_template_sha256"),
        "phase6_1_status": phase6_1.get("status"),
        "manual_approval_fixture_validation_status": _read_latest_json(cfg, "phase5_2_manual_approval_submission_fixture_validator_report.json").get("status"),
        "operator_unlock_request_created": False,
        "actual_operator_unlock_request_path_created": False,
        "operator_unlock_request_present": False,
        "operator_unlock_request_validated": False,
        "approval_intake_validated": False,
        "signed_testnet_preparation_ready": False,
        "block_reasons": blockers,
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
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "recommended_next_action": "only_a_human_operator_may_create_operator_unlock_request_json_after_real_manual_approval_intake_passes" if not blocked else "repair_operator_unlock_fixture_validation",
        "created_at_utc": created,
    }
    report["phase6_2_report_sha256"] = sha256_json(report)
    return report


def persist_phase6_2_operator_unlock_request_fixture_validator_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase6_2_operator_unlock_request_fixture_validator")
    fixture_dir = _storage_dir(cfg, "storage/signed_testnet/fixtures")
    template = _read_latest_json(cfg, "operator_unlock_request_template_review_only.json")
    report = build_phase6_2_operator_unlock_request_fixture_validator_report(cfg=cfg)
    created = str(report["created_at_utc"])
    valid_fixture = _build_valid_fixture(template, created) if template else {}
    invalid_fixtures = _build_invalid_fixtures(valid_fixture) if valid_fixture else {}

    atomic_write_json(latest / "phase6_2_operator_unlock_request_fixture_validator_report.json", report)
    atomic_write_json(phase_dir / "phase6_2_operator_unlock_request_fixture_validator_report.json", report)
    if valid_fixture:
        atomic_write_json(fixture_dir / "valid_operator_unlock_request_FIXTURE_REVIEW_ONLY.json", valid_fixture)
        atomic_write_json(phase_dir / "valid_operator_unlock_request_FIXTURE_REVIEW_ONLY.json", valid_fixture)
    for name, payload in invalid_fixtures.items():
        filename = f"invalid_{name}_operator_unlock_request_FIXTURE_REVIEW_ONLY.json"
        atomic_write_json(fixture_dir / filename, payload)
        atomic_write_json(phase_dir / filename, payload)

    registry_record = append_registry_record(
        registry_path(cfg, PHASE6_2_REGISTRY_NAME),
        {
            "phase6_2_operator_unlock_request_fixture_validator_id": report.get("phase6_2_operator_unlock_request_fixture_validator_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "valid_operator_unlock_fixture_passed_review_only_validation": report.get("valid_operator_unlock_fixture_passed_review_only_validation"),
            "invalid_operator_unlock_fixtures_blocked_fail_closed": report.get("invalid_operator_unlock_fixtures_blocked_fail_closed"),
            "operator_unlock_request_created": False,
            "operator_unlock_request_validated": False,
            "approval_intake_validated": False,
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
        registry_name=PHASE6_2_REGISTRY_NAME,
        id_field="phase6_2_operator_unlock_request_fixture_validator_registry_record_id",
        hash_field="phase6_2_operator_unlock_request_fixture_validator_registry_record_sha256",
        id_prefix="phase6_2_operator_unlock_request_fixture_validator_registry_record",
    )
    atomic_write_json(latest / "phase6_2_operator_unlock_request_fixture_validator_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase6_2_operator_unlock_request_fixture_validator_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE6_2_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase6_2_operator_unlock_request_fixture_validator_report",
    "persist_phase6_2_operator_unlock_request_fixture_validator_report",
]
