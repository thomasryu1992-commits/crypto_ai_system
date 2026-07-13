from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.governance.common import (
    latest_dir as _latest_dir,
    read_latest_json as _read_latest_json,
    safe_text as _safe_text,
    storage_dir as _storage_dir,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, stable_id, utc_now_canonical

PHASE5_2_VERSION = "phase5_2_manual_approval_submission_fixture_validator_v1"
PHASE5_2_REGISTRY_NAME = "phase5_2_manual_approval_submission_fixture_validator_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE5_2_MANUAL_APPROVAL_SUBMISSION_FIXTURE_VALIDATOR_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE5_2_MANUAL_APPROVAL_SUBMISSION_FIXTURE_VALIDATOR_BLOCKED_REVIEW_ONLY"

RUNTIME_SETTINGS_MUTATED_BY_THIS_MODULE = False
SCORE_WEIGHTS_MUTATED_BY_THIS_MODULE = False
CANDIDATE_PROFILE_APPLIED_BY_THIS_MODULE = False
APPROVAL_PACKET_CREATED_BY_THIS_MODULE = False
APPROVAL_INTAKE_SUBMITTED_BY_THIS_MODULE = False
APPROVAL_INTAKE_VALIDATED_BY_THIS_MODULE = False
SIGNED_TESTNET_UNLOCK_ALLOWED_BY_THIS_MODULE = False
TESTNET_ORDER_SUBMISSION_ALLOWED_BY_THIS_MODULE = False
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED_BY_THIS_MODULE = False
AUTO_PROMOTION_ALLOWED_BY_THIS_MODULE = False

REQUIRED_SUBMISSION_FIELDS = [
    "approval_packet_id",
    "approval_intake_id",
    "approver_info",
    "ticket_or_signature",
    "source_report_hash",
    "approval_packet_hash",
    "feature_matrix_hash",
    "profile_candidate_hash",
    "canonical_utc_timestamp",
]

UNSAFE_TRUTHY_FIELDS = [
    "signed_testnet_unlock_allowed",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "signed_testnet_promotion_allowed",
    "live_trading_allowed",
    "runtime_settings_mutated",
    "score_weights_mutated",
    "candidate_profile_applied",
    "external_order_submission_performed",
    "auto_promotion_allowed",
]


def _source_blockers(phase5_1: Mapping[str, Any], approval_draft: Mapping[str, Any], template: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if phase5_1.get("status") != "PHASE5_1_MANUAL_APPROVAL_OPERATOR_HANDOFF_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE5_1_OPERATOR_HANDOFF_NOT_READY")
    if not approval_draft:
        blockers.append("APPROVAL_PACKET_DRAFT_MISSING")
    if not template:
        blockers.append("MANUAL_APPROVAL_TEMPLATE_MISSING")
    if template and template.get("do_not_write_automatically") is not True:
        blockers.append("MANUAL_APPROVAL_TEMPLATE_AUTO_WRITE_GUARD_MISSING")
    if template and template.get("write_target_when_manually_approved") != "storage/manual_approval/approval_intake_submission.json":
        blockers.append("MANUAL_APPROVAL_TEMPLATE_TARGET_INVALID")
    return blockers


def _build_valid_fixture(approval_draft: Mapping[str, Any], created: str) -> dict[str, Any]:
    seed = {
        "approval_packet_draft_id": approval_draft.get("approval_packet_draft_id"),
        "profile_candidate_hash": approval_draft.get("profile_candidate_hash"),
        "created_at_utc": created,
    }
    fixture = {
        "fixture_type": "manual_approval_intake_submission_valid_fixture",
        "fixture_version": PHASE5_2_VERSION,
        "review_only_fixture": True,
        "do_not_copy_to_runtime_without_human_review": True,
        "approval_packet_id": stable_id("manual_fixture_approval_packet", seed, 24),
        "approval_intake_id": stable_id("manual_fixture_approval_intake", seed, 24),
        "approver_info": "fixture_operator_review_only",
        "ticket_or_signature": "fixture_ticket_or_signature_review_only",
        "source_report_hash": approval_draft.get("source_report_hash"),
        "approval_packet_hash": approval_draft.get("approval_packet_draft_sha256"),
        "feature_matrix_hash": approval_draft.get("feature_matrix_sha256"),
        "profile_candidate_hash": approval_draft.get("profile_candidate_hash"),
        "canonical_utc_timestamp": created,
        "approval_scope": "signed_testnet_preparation_review_only_fixture",
        "signed_testnet_unlock_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_trading_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    fixture["fixture_sha256"] = sha256_json(fixture)
    return fixture


def _clone_with_modification(base: Mapping[str, Any], *, fixture_type: str, modifications: Mapping[str, Any], drop_fields: list[str] | None = None) -> dict[str, Any]:
    payload = dict(base)
    payload["fixture_type"] = fixture_type
    payload.pop("fixture_sha256", None)
    for field in drop_fields or []:
        payload.pop(field, None)
    payload.update(dict(modifications))
    payload["fixture_sha256"] = sha256_json(payload)
    return payload


def _build_invalid_fixtures(valid_fixture: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "missing_signature": _clone_with_modification(
            valid_fixture,
            fixture_type="manual_approval_intake_submission_invalid_missing_signature_fixture",
            modifications={},
            drop_fields=["ticket_or_signature"],
        ),
        "hash_mismatch": _clone_with_modification(
            valid_fixture,
            fixture_type="manual_approval_intake_submission_invalid_hash_mismatch_fixture",
            modifications={"profile_candidate_hash": "fixture_invalid_profile_candidate_hash"},
        ),
        "unsafe_unlock_flag": _clone_with_modification(
            valid_fixture,
            fixture_type="manual_approval_intake_submission_invalid_unsafe_unlock_flag_fixture",
            modifications={"signed_testnet_unlock_allowed": True},
        ),
    }


def _validate_fixture_submission(submission: Mapping[str, Any], approval_draft: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    for field in REQUIRED_SUBMISSION_FIELDS:
        if not _safe_text(submission.get(field)):
            blockers.append(f"MANUAL_APPROVAL_FIELD_MISSING:{field}")
    timestamp = submission.get("canonical_utc_timestamp")
    if timestamp and not is_canonical_utc_timestamp(str(timestamp)):
        blockers.append("MANUAL_APPROVAL_TIMESTAMP_NOT_CANONICAL_UTC")
    for field in UNSAFE_TRUTHY_FIELDS:
        if bool(submission.get(field)):
            blockers.append(f"UNSAFE_MANUAL_APPROVAL_FIELD_TRUE:{field}")

    expected_pairs = {
        "source_report_hash": approval_draft.get("source_report_hash"),
        "approval_packet_hash": approval_draft.get("approval_packet_draft_sha256"),
        "feature_matrix_hash": approval_draft.get("feature_matrix_sha256"),
        "profile_candidate_hash": approval_draft.get("profile_candidate_hash"),
    }
    for field, expected in expected_pairs.items():
        if _safe_text(submission.get(field)) != _safe_text(expected):
            blockers.append(f"MANUAL_APPROVAL_HASH_CHAIN_MISMATCH:{field}")

    blocked = bool(blockers)
    return {
        "blocked": blocked,
        "fail_closed": blocked,
        "passed_review_only": not blocked,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "signed_testnet_unlock_allowed": False,
        "testnet_order_submission_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
    }


def build_phase5_2_manual_approval_submission_fixture_validator_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    phase5_1 = _read_latest_json(cfg, "phase5_1_manual_approval_operator_handoff_report.json")
    approval_draft = _read_latest_json(cfg, "approval_packet_draft_review_only.json")
    template = _read_latest_json(cfg, "manual_approval_submission_template_review_only.json")
    source_blockers = _source_blockers(phase5_1, approval_draft, template)

    valid_fixture = _build_valid_fixture(approval_draft, created) if approval_draft else {}
    invalid_fixtures = _build_invalid_fixtures(valid_fixture) if valid_fixture else {}
    valid_result = _validate_fixture_submission(valid_fixture, approval_draft) if valid_fixture and approval_draft else {
        "blocked": True,
        "fail_closed": True,
        "passed_review_only": False,
        "block_reasons": ["VALID_FIXTURE_NOT_BUILT"],
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "signed_testnet_unlock_allowed": False,
        "testnet_order_submission_allowed": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
    }
    invalid_results = {
        name: _validate_fixture_submission(payload, approval_draft)
        for name, payload in invalid_fixtures.items()
    }
    invalid_all_blocked = bool(invalid_results) and all(result["blocked"] and result["fail_closed"] for result in invalid_results.values())
    valid_passed = bool(valid_result.get("passed_review_only")) and not bool(valid_result.get("blocked"))

    blockers = list(source_blockers)
    if not valid_passed:
        blockers.append("VALID_FIXTURE_DID_NOT_PASS_REVIEW_ONLY_VALIDATION")
    if not invalid_all_blocked:
        blockers.append("INVALID_FIXTURE_NOT_BLOCKED_FAIL_CLOSED")
    blockers = sorted(dict.fromkeys(blockers))
    blocked = bool(blockers)
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY

    seed = {
        "approval_packet_draft_id": approval_draft.get("approval_packet_draft_id"),
        "manual_template_sha256": template.get("manual_approval_submission_template_sha256"),
        "valid_fixture_sha256": valid_fixture.get("fixture_sha256"),
        "created_at_utc": created,
        "blocked": blocked,
    }
    phase5_2_id = stable_id("phase5_2_manual_approval_submission_fixture_validator", seed, 24)

    report: dict[str, Any] = {
        "phase5_2_manual_approval_submission_fixture_validator_id": phase5_2_id,
        "phase5_2_version": PHASE5_2_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "fixture_only": True,
        "manual_approval_submission_created": False,
        "actual_manual_approval_submission_path_created": False,
        "approval_intake_submitted": False,
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "valid_fixture_created": bool(valid_fixture),
        "valid_fixture_passed_review_only_validation": valid_passed,
        "invalid_fixture_count": len(invalid_results),
        "invalid_fixtures_blocked_fail_closed": invalid_all_blocked,
        "valid_fixture_result": valid_result,
        "invalid_fixture_results": invalid_results,
        "valid_fixture_path": "storage/manual_approval/fixtures/valid_approval_intake_submission_FIXTURE_REVIEW_ONLY.json",
        "invalid_fixture_paths": {
            name: f"storage/manual_approval/fixtures/invalid_{name}_approval_intake_submission_FIXTURE_REVIEW_ONLY.json"
            for name in invalid_fixtures
        },
        "approval_packet_draft_id": approval_draft.get("approval_packet_draft_id"),
        "approval_packet_draft_sha256": approval_draft.get("approval_packet_draft_sha256"),
        "manual_template_sha256": template.get("manual_approval_submission_template_sha256"),
        "source_report_hash": approval_draft.get("source_report_hash"),
        "feature_matrix_hash": approval_draft.get("feature_matrix_sha256"),
        "profile_candidate_hash": approval_draft.get("profile_candidate_hash"),
        "block_reasons": blockers,
        "recommended_next_action": "operator_may_use_template_for_real_manual_submission_after_human_review" if not blocked else "repair_manual_approval_fixture_validation",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "signed_testnet_unlock_allowed": False,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "signed_testnet_promotion_allowed": False,
        "live_execution_unlock_authority": False,
        "live_trading_allowed_by_this_module": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "external_order_submission_performed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    report["phase5_2_report_sha256"] = sha256_json(report)
    return report


def persist_phase5_2_manual_approval_submission_fixture_validator_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase5_2_manual_approval_submission_fixture_validator")
    fixture_dir = _storage_dir(cfg, "storage/manual_approval/fixtures")
    approval_draft = _read_latest_json(cfg, "approval_packet_draft_review_only.json")
    created_report = build_phase5_2_manual_approval_submission_fixture_validator_report(cfg=cfg)
    report = created_report

    # Rebuild fixtures with the same timestamp used in the report so hashes remain traceable.
    created = str(report["created_at_utc"])
    valid_fixture = _build_valid_fixture(approval_draft, created) if approval_draft else {}
    invalid_fixtures = _build_invalid_fixtures(valid_fixture) if valid_fixture else {}

    atomic_write_json(latest / "phase5_2_manual_approval_submission_fixture_validator_report.json", report)
    atomic_write_json(phase_dir / "phase5_2_manual_approval_submission_fixture_validator_report.json", report)
    if valid_fixture:
        atomic_write_json(fixture_dir / "valid_approval_intake_submission_FIXTURE_REVIEW_ONLY.json", valid_fixture)
        atomic_write_json(phase_dir / "valid_approval_intake_submission_FIXTURE_REVIEW_ONLY.json", valid_fixture)
    for name, payload in invalid_fixtures.items():
        fixture_name = f"invalid_{name}_approval_intake_submission_FIXTURE_REVIEW_ONLY.json"
        atomic_write_json(fixture_dir / fixture_name, payload)
        atomic_write_json(phase_dir / fixture_name, payload)

    registry_record = append_registry_record(
        registry_path(cfg, PHASE5_2_REGISTRY_NAME),
        {
            "phase5_2_manual_approval_submission_fixture_validator_id": report.get("phase5_2_manual_approval_submission_fixture_validator_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "valid_fixture_passed_review_only_validation": report.get("valid_fixture_passed_review_only_validation"),
            "invalid_fixtures_blocked_fail_closed": report.get("invalid_fixtures_blocked_fail_closed"),
            "manual_approval_submission_created": False,
            "approval_intake_submitted": False,
            "approval_intake_validated": False,
            "approval_packet_created": False,
            "signed_testnet_unlock_allowed": False,
            "testnet_order_submission_allowed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE5_2_REGISTRY_NAME,
        id_field="phase5_2_manual_approval_submission_fixture_validator_registry_record_id",
        hash_field="phase5_2_manual_approval_submission_fixture_validator_registry_record_sha256",
        id_prefix="phase5_2_manual_approval_submission_fixture_validator_registry_record",
    )
    atomic_write_json(latest / "phase5_2_manual_approval_submission_fixture_validator_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase5_2_manual_approval_submission_fixture_validator_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE5_2_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase5_2_manual_approval_submission_fixture_validator_report",
    "persist_phase5_2_manual_approval_submission_fixture_validator_report",
]
