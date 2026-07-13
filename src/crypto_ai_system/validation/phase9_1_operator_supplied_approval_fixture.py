from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase9_1_single_signed_testnet_enablement_intake import (
    FALSE_FLAGS,
    persist_phase9_1_actual_operator_approval_intake_hardening_report,
    validate_phase9_1_actual_operator_approval_intake_template,
)

PHASE9_1_APPROVAL_FIXTURE_VERSION = "phase9_1_operator_supplied_approval_fixture_v1"
PHASE9_1_APPROVAL_FIXTURE_REGISTRY_NAME = "phase9_1_operator_supplied_approval_fixture_registry"
STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY = "PHASE9_1_OPERATOR_SUPPLIED_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY"
STATUS_APPROVAL_FIXTURE_BLOCKED_REVIEW_ONLY = "PHASE9_1_OPERATOR_SUPPLIED_APPROVAL_FIXTURE_BLOCKED_REVIEW_ONLY"

UNSAFE_TRUTHY_FIELDS = list(FALSE_FLAGS) + [
    "phase9_2_order_submission_authorized",
    "phase9_order_submission_authorized",
    "actual_order_submission_authorized",
    "order_submission_authorized",
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
    return sorted(dict.fromkeys(fields))


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase9_1_actual_operator_approval_intake_template_sha256",
        "phase9_1_actual_operator_approval_hardening_report_sha256",
        "phase9_1_operator_supplied_approval_fixture_sha256",
        "phase9_1_operator_supplied_approval_fixture_validation_report_sha256",
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
        "status": data.get("status") or data.get("actual_approval_intake_type") or data.get("artifact_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _base_template_ready(template: Mapping[str, Any], hardening_report: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if not hardening_report:
        blockers.append("PHASE9_1_APPROVAL_FIXTURE_HARDENING_REPORT_MISSING")
    elif hardening_report.get("phase9_1_actual_operator_approval_template_ready") is not True:
        blockers.append("PHASE9_1_APPROVAL_FIXTURE_HARDENING_REPORT_NOT_READY")
    if not template:
        blockers.append("PHASE9_1_APPROVAL_FIXTURE_TEMPLATE_MISSING")
    elif template.get("actual_approval_intake_type") != "phase9_1_actual_operator_approval_intake_template_review_only":
        blockers.append("PHASE9_1_APPROVAL_FIXTURE_TEMPLATE_TYPE_INVALID")
    for name, payload in {"hardening_report": hardening_report, "template": template}.items():
        unsafe = _unsafe_fields(payload)
        if unsafe:
            blockers.append(f"PHASE9_1_APPROVAL_FIXTURE_SOURCE_UNSAFE_FLAGS:{name}:{','.join(unsafe)}")
    return not blockers, sorted(dict.fromkeys(blockers))


def build_phase9_1_operator_supplied_approval_fixture_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_1_hardening_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase9_1_hardening_first:
        persist_phase9_1_actual_operator_approval_intake_hardening_report(cfg=cfg, run_phase9_1_first=True)

    hardening_report = _read_latest_json(cfg, "phase9_1_actual_operator_approval_hardening_report.json")
    template = _read_latest_json(cfg, "phase9_1_actual_operator_approval_intake_TEMPLATE_REVIEW_ONLY.json")
    source_ready, source_blockers = _base_template_ready(template, hardening_report)

    fixture = dict(template)
    fixture.update(
        {
            "artifact_type": "phase9_1_operator_supplied_approval_fixture_review_only",
            "phase9_1_operator_supplied_approval_fixture_version": PHASE9_1_APPROVAL_FIXTURE_VERSION,
            "source_phase9_1_actual_operator_approval_hardening_id": hardening_report.get("phase9_1_actual_operator_approval_hardening_id"),
            "source_phase9_1_actual_operator_approval_template_hash": template.get("phase9_1_actual_operator_approval_intake_template_sha256") or _artifact_hash(template),
            "operator_decision": "approve_single_signed_testnet_order",
            "operator_signature": "operator_signature_fixture_review_only_metadata",
            "operator_signature_placeholder": "FILLED_BY_REVIEW_ONLY_FIXTURE_NOT_REAL_RUNTIME_SIGNATURE",
            "operator_signature_hash_sha256": "b" * 64,
            "actual_operator_approval_recorded": True,
            "operator_approval_ticket_or_record_id": "fixture-phase9-1-single-testnet-order-approval",
            "operator_approval_timestamp_utc": created,
            "kill_switch_confirmed_for_actual_approval": True,
            "kill_switch_confirmation_timestamp_utc": created,
            "testnet_key_fingerprint_sha256": "a" * 64,
            "operator_supplied_fixture_only": True,
            "fixture_not_actual_runtime_approval": True,
            "fixture_must_not_submit_orders": True,
            "phase9_1_actual_enablement_approval_complete": True,
            "phase9_1_actual_approval_complete_for_fixture_only": True,
            "phase9_2_submit_guard_recheck_may_begin": True,
            "phase9_2_single_testnet_order_submit_may_begin": False,
            "phase9_2_order_submission_authorized": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "actual_order_submission_performed": False,
            "order_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "created_at_utc": created,
        }
    )
    for field in FALSE_FLAGS:
        fixture[field] = False
    fixture["phase9_1_operator_supplied_approval_fixture_sha256"] = sha256_json(fixture)

    validation_report = validate_phase9_1_actual_operator_approval_intake_template(fixture, require_complete_approval=True)
    fixture_valid = source_ready and validation_report.get("phase9_1_actual_operator_approval_template_valid_review_only") is True
    fixture_complete = validation_report.get("phase9_1_actual_operator_approval_values_complete") is True
    blockers = list(source_blockers)
    if not fixture_valid:
        blockers.extend(validation_report.get("phase9_1_actual_operator_approval_validation_blockers") or ["PHASE9_1_APPROVAL_FIXTURE_VALIDATION_FAILED"])
    if not fixture_complete:
        blockers.extend(validation_report.get("phase9_1_actual_operator_approval_blockers") or ["PHASE9_1_APPROVAL_FIXTURE_VALUES_INCOMPLETE"])
    if _unsafe_fields(fixture):
        blockers.append("PHASE9_1_APPROVAL_FIXTURE_UNSAFE_FLAGS:" + ",".join(_unsafe_fields(fixture)))
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    passed = not blockers

    validation_artifact = {
        "artifact_type": "phase9_1_operator_supplied_approval_fixture_validation_report",
        "phase9_1_operator_supplied_approval_fixture_version": PHASE9_1_APPROVAL_FIXTURE_VERSION,
        "review_only": True,
        "fixture_only": True,
        "fixture_valid_review_only": passed,
        "fixture_values_complete_review_only": fixture_complete and not blockers,
        "source_template_ready": source_ready,
        "source_blockers": source_blockers,
        "validator_result": validation_report,
        "block_reasons": blockers,
        "phase9_2_submit_guard_recheck_may_begin": passed,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_2_order_submission_authorized": False,
        **{field: False for field in FALSE_FLAGS},
        "created_at_utc": created,
    }
    validation_artifact["phase9_1_operator_supplied_approval_fixture_validation_report_sha256"] = sha256_json(validation_artifact)

    negative_fixture_results = _build_negative_fixture_results(fixture)
    status = STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY if passed and negative_fixture_results["all_negative_fixtures_blocked_fail_closed"] else STATUS_APPROVAL_FIXTURE_BLOCKED_REVIEW_ONLY
    report = {
        "phase9_1_operator_supplied_approval_fixture_id": stable_id(
            "phase9_1_operator_supplied_approval_fixture",
            {"fixture_hash": sha256_json(fixture), "validation_hash": sha256_json(validation_artifact), "created_at_utc": created},
            24,
        ),
        "phase9_1_operator_supplied_approval_fixture_version": PHASE9_1_APPROVAL_FIXTURE_VERSION,
        "status": status,
        "blocked": status != STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY,
        "fail_closed": status != STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY,
        "review_only": True,
        "fixture_only": True,
        "fixture_not_actual_runtime_approval": True,
        "phase9_1_operator_supplied_approval_fixture_validated": status == STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY,
        "phase9_1_actual_approval_complete_for_fixture_only": status == STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY,
        "phase9_2_submit_guard_recheck_may_begin": status == STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY,
        "phase9_2_single_testnet_order_submit_may_begin": False,
        "phase9_2_order_submission_authorized": False,
        "required_evidence_hash_summary": {
            "phase9_1_actual_operator_approval_hardening_report": _source_summary("phase9_1_actual_operator_approval_hardening_report", hardening_report),
            "phase9_1_actual_operator_approval_intake_template": _source_summary("phase9_1_actual_operator_approval_intake_template", template),
            "phase9_1_operator_supplied_approval_fixture": _source_summary("phase9_1_operator_supplied_approval_fixture", fixture),
        },
        "validation_report": validation_artifact,
        "negative_fixture_results": negative_fixture_results,
        "block_reasons": blockers,
        "recommended_next_action": "rerun_phase9_2_submit_guard_recheck_with_fixture_only_keep_order_endpoints_disabled",
        **{field: False for field in FALSE_FLAGS},
        "created_at_utc": created,
    }
    report["phase9_1_operator_supplied_approval_fixture_report_sha256"] = sha256_json(report)
    return report, fixture, validation_artifact, negative_fixture_results


def _build_negative_fixture_results(fixture: Mapping[str, Any]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {
        "missing_operator_signature": {"operator_signature": None},
        "missing_ticket_or_record_id": {"operator_approval_ticket_or_record_id": None},
        "missing_key_fingerprint": {"testnet_key_fingerprint_sha256": "REQUIRED_OPERATOR_SUPPLIED_METADATA_ONLY_TESTNET_KEY_FINGERPRINT_SHA256"},
        "kill_switch_not_confirmed": {"kill_switch_confirmed_for_actual_approval": False},
        "unsafe_submit_permission_true": {"testnet_order_submission_allowed": True},
        "order_endpoint_called_true": {"order_endpoint_called": True},
        "raw_secret_value_present": {"api_secret_value": "raw-secret-value-must-not-appear"},
    }
    results: dict[str, dict[str, Any]] = {}
    for name, patch in cases.items():
        payload = dict(fixture)
        payload.update(patch)
        result = validate_phase9_1_actual_operator_approval_intake_template(payload, require_complete_approval=True)
        reasons = list(result.get("phase9_1_actual_operator_approval_validation_blockers") or []) + list(result.get("phase9_1_actual_operator_approval_blockers") or [])
        results[name] = {
            "fixture_name": name,
            "blocked": bool(reasons),
            "fail_closed": bool(reasons),
            "block_reasons": sorted(dict.fromkeys(str(item) for item in reasons if item)),
        }
    all_blocked = all(item["blocked"] and item["fail_closed"] for item in results.values())
    return {
        "artifact_type": "phase9_1_operator_supplied_approval_fixture_negative_results",
        "review_only": True,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "fixture_results": results,
        **{field: False for field in FALSE_FLAGS},
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 9.1 Operator-Supplied Approval Fixture - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact validates a review-only operator-supplied approval fixture. It is not a live runtime approval and does not enable Phase 9.2 order submission.",
            "",
            "## Result",
            "",
            f"- Fixture validated: `{report.get('phase9_1_operator_supplied_approval_fixture_validated')}`",
            f"- Fixture-only approval complete: `{report.get('phase9_1_actual_approval_complete_for_fixture_only')}`",
            f"- Phase 9.2 submit guard recheck may begin: `{report.get('phase9_2_submit_guard_recheck_may_begin')}`",
            "",
            "## Still Disabled",
            "",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `actual_order_submission_performed=false`",
            "- `order_endpoint_called=false`",
            "- `http_request_sent=false`",
            "- `signature_created=false`",
            "",
        ]
    )


def persist_phase9_1_operator_supplied_approval_fixture_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase9_1_hardening_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase9_1_single_signed_testnet_enablement_intake")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, fixture, validation_report, negative_fixture_results = build_phase9_1_operator_supplied_approval_fixture_report(
        cfg=cfg,
        run_phase9_1_hardening_first=run_phase9_1_hardening_first,
    )
    handoff = _build_handoff_markdown(report)
    atomic_write_json(latest / "phase9_1_operator_supplied_approval_fixture_report.json", report)
    atomic_write_json(latest / "phase9_1_operator_supplied_approval_FIXTURE_REVIEW_ONLY.json", fixture)
    atomic_write_json(latest / "phase9_1_operator_supplied_approval_fixture_validation_report.json", validation_report)
    atomic_write_json(latest / "phase9_1_operator_supplied_approval_fixture_negative_results.json", negative_fixture_results)
    (latest / "PHASE9_1_OPERATOR_SUPPLIED_APPROVAL_FIXTURE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(phase_dir / "phase9_1_operator_supplied_approval_fixture_report.json", report)
    atomic_write_json(phase_dir / "phase9_1_operator_supplied_approval_FIXTURE_REVIEW_ONLY.json", fixture)
    atomic_write_json(phase_dir / "phase9_1_operator_supplied_approval_fixture_validation_report.json", validation_report)
    atomic_write_json(phase_dir / "phase9_1_operator_supplied_approval_fixture_negative_results.json", negative_fixture_results)
    (phase_dir / "PHASE9_1_OPERATOR_SUPPLIED_APPROVAL_FIXTURE_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(signed_testnet_dir / "phase9_1_operator_supplied_approval_fixture_report.json", report)
    atomic_write_json(signed_testnet_dir / "phase9_1_operator_supplied_approval_FIXTURE_REVIEW_ONLY.json", fixture)
    registry_record = append_registry_record(
        registry_path(cfg, PHASE9_1_APPROVAL_FIXTURE_REGISTRY_NAME),
        {
            "phase9_1_operator_supplied_approval_fixture_id": report.get("phase9_1_operator_supplied_approval_fixture_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "fixture_only": True,
            "phase9_1_operator_supplied_approval_fixture_validated": report.get("phase9_1_operator_supplied_approval_fixture_validated"),
            "phase9_2_submit_guard_recheck_may_begin": report.get("phase9_2_submit_guard_recheck_may_begin"),
            "phase9_2_order_submission_authorized": False,
            "actual_order_submission_performed": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE9_1_APPROVAL_FIXTURE_REGISTRY_NAME,
        id_field="phase9_1_operator_supplied_approval_fixture_registry_record_id",
        hash_field="phase9_1_operator_supplied_approval_fixture_registry_record_sha256",
        id_prefix="phase9_1_operator_supplied_approval_fixture_registry_record",
    )
    atomic_write_json(latest / "phase9_1_operator_supplied_approval_fixture_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase9_1_operator_supplied_approval_fixture_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE9_1_APPROVAL_FIXTURE_VERSION",
    "STATUS_APPROVAL_FIXTURE_VALIDATED_REVIEW_ONLY",
    "STATUS_APPROVAL_FIXTURE_BLOCKED_REVIEW_ONLY",
    "build_phase9_1_operator_supplied_approval_fixture_report",
    "persist_phase9_1_operator_supplied_approval_fixture_report",
]
