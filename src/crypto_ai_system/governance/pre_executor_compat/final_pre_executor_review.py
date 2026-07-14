from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import unsafe_truthy_fields
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.governance.pre_executor_compat.operator_decision_validation import (
    persist_phase7_16_operator_decision_intake_validator_report,
)

PHASE7_17_VERSION = "phase7_17_final_pre_executor_review_packet_v2_reissued"
PHASE7_17_REGISTRY_NAME = "phase7_17_final_pre_executor_review_packet_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_17_FINAL_PRE_EXECUTOR_REVIEW_PACKET_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_17_FINAL_PRE_EXECUTOR_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"

REQUIRED_PHASE7_EVIDENCE = {
    "payload_guard": "phase7_1_signed_testnet_pre_submit_payload_guard_report.json",
    "disabled_executor_evidence": "phase7_3_disabled_signed_testnet_executor_review_report.json",
    "disabled_reconciliation_session_close": "phase7_4_disabled_execution_reconciliation_session_close_report.json",
    "reconciliation_session_close_review": "phase7_5_reconciliation_session_close_review_packet_report.json",
    "future_executor_approval_review": "phase7_10_future_executor_approval_review_packet_report.json",
    "enablement_design": "phase7_11_future_executor_enablement_design_review_report.json",
    "enablement_guard_fixture": "phase7_12_future_executor_enablement_guard_fixture_report.json",
    "enablement_review_packet": "phase7_13_future_executor_enablement_review_packet_report.json",
    "operator_decision_packet": "phase7_14_future_executor_operator_decision_packet_report.json",
    "operator_decision_intake_template": "phase7_15_operator_decision_intake_template_report.json",
    "operator_decision_intake_validator": "phase7_16_operator_decision_intake_validator_report.json",
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

FINAL_PACKET_REQUIRED_FIELDS = [
    "packet_type",
    "phase7_17_version",
    "source_phase7_17_report_id",
    "review_only",
    "final_pre_executor_review_only",
    "phase7_completion_review_only",
    "not_runtime_authority",
    "required_evidence_status",
    "required_evidence_hash_summary",
    "phase7_final_pre_executor_review_ready",
    "phase8_preparation_review_may_begin",
    "phase8_execution_authority",
    "blocks_signed_testnet_execution",
    "blocks_order_submission",
    "ready_for_signed_testnet_execution",
    "testnet_order_submission_allowed",
    "place_order_enabled",
    "cancel_order_enabled",
    "signed_order_executor_enabled",
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
        "phase7_17_report_sha256",
        "phase7_16_report_sha256",
        "phase7_15_report_sha256",
        "phase7_14_report_sha256",
        "phase7_13_report_sha256",
        "phase7_12_report_sha256",
        "phase7_11_report_sha256",
        "phase7_10_report_sha256",
        "phase7_5_report_sha256",
        "phase7_4_report_sha256",
        "phase7_3_report_sha256",
        "phase7_1_report_sha256",
        "final_pre_executor_review_packet_sha256",
        "final_pre_executor_review_guard_report_sha256",
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
        "status": data.get("status") or data.get("packet_type") or data.get("guard_type") or data.get("validation_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _evidence_ready(name: str, payload: Mapping[str, Any]) -> bool:
    data = dict(payload or {})
    if not data:
        return False
    if data.get("blocked") is True or data.get("fail_closed") is True:
        return False
    status = str(data.get("status") or "")
    if status and "RECORDED_REVIEW_ONLY" not in status:
        return False
    if name == "operator_decision_intake_template" and data.get("phase7_15_intake_template_ready") is not True:
        return False
    if name == "operator_decision_intake_validator" and data.get("phase7_16_intake_validation_ready") is not True:
        return False
    if name == "operator_decision_packet" and data.get("phase7_14_operator_decision_packet_ready") is not True:
        return False
    if name == "enablement_review_packet" and data.get("phase7_13_enablement_review_packet_ready") is False:
        return False
    return True


def validate_final_pre_executor_review_packet(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    missing = [field for field in FINAL_PACKET_REQUIRED_FIELDS if field not in data or data.get(field) in (None, "")]
    unsafe = _unsafe_fields(data)
    blockers: list[str] = []
    if missing:
        blockers.append("MISSING_REQUIRED_FINAL_PRE_EXECUTOR_REVIEW_PACKET_FIELDS:" + ",".join(missing))
    if unsafe:
        blockers.append("UNSAFE_FINAL_PRE_EXECUTOR_REVIEW_PACKET_FLAGS:" + ",".join(unsafe))
    if data.get("packet_type") != "phase7_17_final_pre_executor_review_packet_review_only":
        blockers.append("INVALID_FINAL_PRE_EXECUTOR_REVIEW_PACKET_TYPE")
    if data.get("review_only") is not True:
        blockers.append("FINAL_PRE_EXECUTOR_REVIEW_PACKET_NOT_REVIEW_ONLY")
    if data.get("final_pre_executor_review_only") is not True:
        blockers.append("FINAL_PRE_EXECUTOR_REVIEW_PACKET_SCOPE_INVALID")
    if data.get("not_runtime_authority") is not True:
        blockers.append("FINAL_PRE_EXECUTOR_REVIEW_PACKET_RUNTIME_AUTHORITY_NOT_BLOCKED")
    for field in (
        "blocks_signed_testnet_execution",
        "blocks_order_submission",
        "phase8_secret_key_design_required",
        "phase8_write_path_dry_validation_required",
        "phase8_hot_path_risk_gate_required",
        "phase8_final_guard_required",
    ):
        if data.get(field) is not True:
            blockers.append(f"REQUIRED_FINAL_PRE_EXECUTOR_REVIEW_CONFIRMATION_NOT_TRUE:{field}")
    for field in (
        "phase8_execution_authority",
        "signed_testnet_execution_authority",
        "signed_testnet_order_submission_authority",
        "actual_executor_enablement_performed",
        "actual_order_submission_performed",
        "ready_for_signed_testnet_execution",
        "testnet_order_submission_allowed",
        "place_order_enabled",
        "cancel_order_enabled",
        "signed_order_executor_enabled",
    ):
        if data.get(field) is not False:
            blockers.append(f"REQUIRED_FINAL_PRE_EXECUTOR_REVIEW_FALSE_FLAG_NOT_FALSE:{field}")
    ready_map = data.get("required_evidence_status") or {}
    if isinstance(ready_map, Mapping):
        not_ready = [name for name, summary in ready_map.items() if not isinstance(summary, Mapping) or summary.get("ready") is not True]
        if not_ready:
            blockers.append("FINAL_PRE_EXECUTOR_REVIEW_EVIDENCE_NOT_READY:" + ",".join(sorted(not_ready)))
    else:
        blockers.append("FINAL_PRE_EXECUTOR_REVIEW_EVIDENCE_STATUS_INVALID")
    valid = not blockers
    return {
        "final_packet_valid_review_only": valid,
        "final_packet_blocked_fail_closed": not valid,
        "missing_required_fields": missing,
        "unsafe_truthy_fields": unsafe,
        "final_packet_blockers": sorted(dict.fromkeys(blockers)),
    }


def _build_final_packet(
    *,
    report_id: str,
    artifacts: Mapping[str, Mapping[str, Any]],
    source_summary: Mapping[str, Mapping[str, Any]],
    ready: bool,
    created_at_utc: str,
    phase7_15_boundary_reconciled: bool = False,
    phase7_16_negative_fixtures_passed: bool = False,
    revised_source_summary: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence_status = {
        name: {
            "ready": _evidence_ready(name, payload),
            "status": source_summary.get(name, {}).get("status"),
            "blocked": source_summary.get(name, {}).get("blocked"),
            "fail_closed": source_summary.get(name, {}).get("fail_closed"),
            "sha256": source_summary.get(name, {}).get("sha256"),
        }
        for name, payload in artifacts.items()
    }
    packet: dict[str, Any] = {
        "packet_type": "phase7_17_final_pre_executor_review_packet_review_only",
        "phase7_17_version": PHASE7_17_VERSION,
        "source_phase7_17_report_id": report_id,
        "review_only": True,
        "final_pre_executor_review_only": True,
        "phase7_completion_review_only": True,
        "phase7_17_final_packet_reissued": True,
        "not_runtime_authority": True,
        "required_evidence_status": evidence_status,
        "required_evidence_hash_summary": dict(source_summary),
        "revised_boundary_evidence_hash_summary": dict(revised_source_summary or {}),
        "phase7_15_boundary_reconciled": phase7_15_boundary_reconciled,
        "phase7_16_negative_fixtures_passed": phase7_16_negative_fixtures_passed,
        "phase7_final_pre_executor_review_ready": ready,
        "phase7_review_chain_complete": ready,
        "phase8_preparation_review_may_begin": ready,
        "phase8_preparation_review_may_continue": ready,
        "phase8_execution_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "signed_testnet_unlock_authority": False,
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "phase8_secret_key_design_required": True,
        "phase8_write_path_dry_validation_required": True,
        "phase8_hot_path_risk_gate_required": True,
        "phase8_final_guard_required": True,
        "remaining_before_any_signed_testnet_order": [
            "phase8_1_secret_manager_key_handling_design_metadata_only_no_secret_values",
            "phase8_2_exchange_adapter_write_path_dry_validation_no_order_endpoint_calls",
            "phase8_3_fresh_hot_path_pre_order_risk_gate_recheck",
            "phase8_4_signed_testnet_executor_enablement_final_guard_still_disabled",
            "phase9_explicit_single_order_operator_intake_required_before_any_actual_testnet_order",
        ],
        "acceptance_criteria": {
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
        },
        "actual_operator_decision_recorded": False,
        "actual_phase8_approval_granted": False,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "external_order_submission_performed": False,
        "exchange_endpoint_called": False,
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
        "created_at_utc": created_at_utc,
    }
    packet["final_pre_executor_review_packet_sha256"] = sha256_json(packet)
    return packet


def _build_guard(*, report_id: str, packet: Mapping[str, Any], packet_validation: Mapping[str, Any], created_at_utc: str) -> dict[str, Any]:
    guard_passed = packet_validation.get("final_packet_valid_review_only") is True
    guard = {
        "guard_type": "phase7_17_final_pre_executor_review_guard_review_only",
        "phase7_17_version": PHASE7_17_VERSION,
        "source_phase7_17_report_id": report_id,
        "review_only": True,
        "final_pre_executor_review_guard_only": True,
        "guard_passed": guard_passed,
        "packet_validation": dict(packet_validation),
        "blocks_signed_testnet_execution": True,
        "blocks_order_submission": True,
        "phase8_preparation_review_may_begin": packet.get("phase8_preparation_review_may_begin") is True and guard_passed,
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
    guard["final_pre_executor_review_guard_report_sha256"] = sha256_json(guard)
    return guard


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 7.17 Final Pre-Executor Review Packet - Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase closes the Phase 7 review-only chain. It confirms review evidence consistency before Phase 8 preparation, but it does not enable signed testnet execution or order submission.",
            "",
            "## Result",
            "",
            f"- Final pre-executor review ready: `{report.get('phase7_final_pre_executor_review_ready')}`",
            f"- Final guard passed: `{report.get('final_pre_executor_review_guard_passed')}`",
            f"- Phase 8 preparation review may begin: `{report.get('phase8_preparation_review_may_begin')}`",
            "",
            "## Safety Flags",
            "",
            "- `ready_for_signed_testnet_execution=false`",
            "- `testnet_order_submission_allowed=false`",
            "- `place_order_enabled=false`",
            "- `cancel_order_enabled=false`",
            "- `signed_order_executor_enabled=false`",
            "- `actual_order_submission_performed=false`",
            "",
            "## Blockers",
            "",
            blocker_lines,
            "",
            "## Next Allowed Scope",
            "",
            f"`{report.get('phase7_17_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_17_final_pre_executor_review_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_16_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_16_first:
        persist_phase7_16_operator_decision_intake_validator_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_PHASE7_EVIDENCE.items()}
    revised_artifacts = {
        "phase7_15_template_validation": _read_latest_json(cfg, "phase7_15_operator_decision_intake_template_validation_report.json"),
        "phase7_15_negative_fixture_results": _read_latest_json(cfg, "phase7_15_negative_fixture_results.json"),
        "phase7_15_package_boundary_scan": _read_latest_json(cfg, "phase7_15_package_boundary_scan.json"),
        "phase7_16_validator_hardening": _read_latest_json(cfg, "phase7_16_operator_decision_intake_validator_hardening_report.json"),
        "phase7_16_negative_fixture_results_revised": _read_latest_json(cfg, "phase7_16_negative_fixture_results_REVISED.json"),
    }
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}
    revised_source_summary = {name: _source_summary(name, payload) for name, payload in revised_artifacts.items()}
    evidence_not_ready = [name for name, payload in artifacts.items() if not _evidence_ready(name, payload)]

    phase7_15_boundary_reconciled = (
        revised_artifacts["phase7_15_template_validation"].get("passed_review_only") is True
        and revised_artifacts["phase7_15_template_validation"].get("approval_intake_validator_reused") is False
        and revised_artifacts["phase7_15_negative_fixture_results"].get("all_negative_fixtures_blocked") is True
        and revised_artifacts["phase7_15_package_boundary_scan"].get("blocked") is not True
        and not revised_artifacts["phase7_15_package_boundary_scan"].get("forbidden_artifacts_found")
    )
    phase7_16_report_for_reissue = artifacts.get("operator_decision_intake_validator", {})
    phase7_16_negative_fixtures_passed = (
        (
            revised_artifacts["phase7_16_validator_hardening"].get("all_required_negative_fixtures_blocked_fail_closed") is True
            and revised_artifacts["phase7_16_validator_hardening"].get("approval_intake_validator_reused") is False
            and revised_artifacts["phase7_16_negative_fixture_results_revised"].get("all_required_negative_fixtures_blocked_fail_closed") is True
        )
        or (
            phase7_16_report_for_reissue.get("phase7_16_validator_hardened_revised") is True
            and phase7_16_report_for_reissue.get("all_required_negative_fixtures_blocked_fail_closed") is True
            and phase7_16_report_for_reissue.get("approval_intake_validator_reused") is False
        )
    )

    preliminary_blockers: list[str] = []
    preliminary_blockers.extend([f"MISSING_PHASE7_17_REQUIRED_EVIDENCE:{name}" for name in missing])
    if unsafe:
        preliminary_blockers.extend([f"UNSAFE_PHASE7_17_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    preliminary_blockers.extend([f"PHASE7_17_REQUIRED_EVIDENCE_NOT_READY:{name}" for name in evidence_not_ready])
    if not phase7_15_boundary_reconciled:
        preliminary_blockers.append("PHASE7_15_BOUNDARY_RECONCILIATION_NOT_CONFIRMED_FOR_REISSUE")
    if not phase7_16_negative_fixtures_passed:
        preliminary_blockers.append("PHASE7_16_NEGATIVE_FIXTURE_HARDENING_NOT_CONFIRMED_FOR_REISSUE")
    preliminary_blockers = sorted(dict.fromkeys(str(item) for item in preliminary_blockers if item))
    preliminary_ready = not preliminary_blockers

    preliminary_id = stable_id("phase7_17_final_pre_executor_review_packet", {"source_summary": source_summary, "created_at_utc": created}, 24)
    packet = _build_final_packet(
        report_id=preliminary_id,
        artifacts=artifacts,
        source_summary=source_summary,
        ready=preliminary_ready,
        created_at_utc=created,
        phase7_15_boundary_reconciled=phase7_15_boundary_reconciled,
        phase7_16_negative_fixtures_passed=phase7_16_negative_fixtures_passed,
        revised_source_summary=revised_source_summary,
    )
    packet_validation = validate_final_pre_executor_review_packet(packet)
    guard = _build_guard(report_id=preliminary_id, packet=packet, packet_validation=packet_validation, created_at_utc=created)

    blockers = list(preliminary_blockers)
    if packet_validation.get("final_packet_valid_review_only") is not True:
        blockers.extend(packet_validation.get("final_packet_blockers") or ["FINAL_PRE_EXECUTOR_REVIEW_PACKET_INVALID"])
    if guard.get("guard_passed") is not True:
        blockers.append("FINAL_PRE_EXECUTOR_REVIEW_GUARD_NOT_PASSED")
    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY

    report_id = stable_id(
        "phase7_17_final_pre_executor_review_packet",
        {
            "source_summary": source_summary,
            "packet_hash": sha256_json(packet),
            "guard_hash": sha256_json(guard),
            "blockers": blockers,
            "created_at_utc": created,
        },
        24,
    )
    packet["source_phase7_17_report_id"] = report_id
    packet["phase7_final_pre_executor_review_ready"] = ready
    packet["phase7_review_chain_complete"] = ready
    packet["phase8_preparation_review_may_begin"] = ready
    packet["final_pre_executor_review_packet_sha256"] = sha256_json(packet)
    packet_validation = validate_final_pre_executor_review_packet(packet)
    guard = _build_guard(report_id=report_id, packet=packet, packet_validation=packet_validation, created_at_utc=created)

    report: dict[str, Any] = {
        "phase7_17_final_pre_executor_review_packet_id": report_id,
        "phase7_17_version": PHASE7_17_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "final_pre_executor_review_only": True,
        "phase7_final_pre_executor_review_ready": ready,
        "phase7_review_chain_complete": ready,
        "phase7_17_final_packet_reissued": True,
        "phase7_15_boundary_reconciled": phase7_15_boundary_reconciled,
        "phase7_16_negative_fixtures_passed": phase7_16_negative_fixtures_passed,
        "phase8_preparation_review_may_continue": ready,
        "final_pre_executor_review_packet_created": True,
        "final_pre_executor_review_guard_created": True,
        "final_pre_executor_review_guard_passed": guard.get("guard_passed") is True,
        "phase8_preparation_review_may_begin": ready,
        "phase8_execution_authority": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "required_evidence_hash_summary": source_summary,
        "revised_boundary_evidence_hash_summary": revised_source_summary,
        "required_evidence_not_ready": evidence_not_ready,
        "missing_required_evidence": missing,
        "unsafe_flags_by_artifact": unsafe,
        "packet_validation": packet_validation,
        "block_reasons": blockers,
        "phase7_17_allowed_next_scope": "phase8_1_secret_manager_key_handling_design_still_no_order_endpoints" if ready else "resolve_phase7_17_final_pre_executor_review_blockers",
        "recommended_next_action": "start_phase8_1_secret_manager_key_handling_design_keep_executor_disabled" if ready else "inspect_phase7_17_blockers_and_rerun_phase7_review_chain",
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "secret_value_accessed": False,
        "secret_file_read": False,
        "secret_file_created": False,
        "api_key_value_access_allowed": False,
        "api_secret_value_access_allowed": False,
        "secret_file_access_allowed": False,
        "secret_file_creation_allowed": False,
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
        "candidate_profile_applied": False,
        "settings_write_preview_applied": False,
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    report["final_pre_executor_review_packet_sha256"] = packet["final_pre_executor_review_packet_sha256"]
    report["final_pre_executor_review_guard_report_sha256"] = guard["final_pre_executor_review_guard_report_sha256"]
    report["phase7_17_report_sha256"] = sha256_json(report)
    return report, packet, guard


def persist_phase7_17_final_pre_executor_review_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_16_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_17_final_pre_executor_review_packet")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report, packet, guard = build_phase7_17_final_pre_executor_review_packet_report(cfg=cfg, run_phase7_16_first=run_phase7_16_first)
    handoff = _build_handoff_markdown(report)

    atomic_write_json(latest / "phase7_17_final_pre_executor_review_packet_report.json", report)
    atomic_write_json(latest / "phase7_final_pre_executor_review_packet_review_only.json", packet)
    atomic_write_json(latest / "final_pre_executor_review_packet_REISSUED.json", packet)
    atomic_write_json(latest / "phase7_final_pre_executor_review_guard_report.json", guard)
    atomic_write_json(latest / "phase_7_completion_guard_report_REVISED.json", guard)
    still_disabled = {
        "report_type": "still_disabled_execution_flags_REVISED",
        "phase7_17_version": PHASE7_17_VERSION,
        "review_only": True,
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
        "actual_order_submission_performed": False,
        "created_at_utc": report.get("created_at_utc"),
    }
    still_disabled["still_disabled_execution_flags_sha256"] = sha256_json(still_disabled)
    atomic_write_json(latest / "still_disabled_execution_flags_REVISED.json", still_disabled)
    (latest / "PHASE7_17_FINAL_PRE_EXECUTOR_REVIEW_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    (latest / "final_pre_executor_review_summary_REISSUED.md").write_text(handoff, encoding="utf-8")

    atomic_write_json(signed_testnet_dir / "phase7_final_pre_executor_review_packet_review_only.json", packet)

    atomic_write_json(phase_dir / "phase7_17_final_pre_executor_review_packet_report.json", report)
    atomic_write_json(phase_dir / "phase7_final_pre_executor_review_packet_review_only.json", packet)
    atomic_write_json(phase_dir / "final_pre_executor_review_packet_REISSUED.json", packet)
    atomic_write_json(phase_dir / "phase7_final_pre_executor_review_guard_report.json", guard)
    atomic_write_json(phase_dir / "phase_7_completion_guard_report_REVISED.json", guard)
    atomic_write_json(phase_dir / "still_disabled_execution_flags_REVISED.json", still_disabled)
    (phase_dir / "PHASE7_17_FINAL_PRE_EXECUTOR_REVIEW_PACKET_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    (phase_dir / "final_pre_executor_review_summary_REISSUED.md").write_text(handoff, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_17_REGISTRY_NAME),
        {
            "phase7_17_final_pre_executor_review_packet_id": report.get("phase7_17_final_pre_executor_review_packet_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_final_pre_executor_review_ready": report.get("phase7_final_pre_executor_review_ready"),
            "phase7_review_chain_complete": report.get("phase7_review_chain_complete"),
            "phase7_17_final_packet_reissued": report.get("phase7_17_final_packet_reissued"),
            "phase7_15_boundary_reconciled": report.get("phase7_15_boundary_reconciled"),
            "phase7_16_negative_fixtures_passed": report.get("phase7_16_negative_fixtures_passed"),
            "phase8_preparation_review_may_begin": report.get("phase8_preparation_review_may_begin"),
            "phase8_preparation_review_may_continue": report.get("phase8_preparation_review_may_continue"),
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
        registry_name=PHASE7_17_REGISTRY_NAME,
        id_field="phase7_17_final_pre_executor_review_packet_registry_record_id",
        hash_field="phase7_17_final_pre_executor_review_packet_registry_record_sha256",
        id_prefix="phase7_17_final_pre_executor_review_packet_registry_record",
    )
    atomic_write_json(latest / "phase7_17_final_pre_executor_review_packet_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_17_final_pre_executor_review_packet_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_17_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "validate_final_pre_executor_review_packet",
    "build_phase7_17_final_pre_executor_review_packet_report",
    "persist_phase7_17_final_pre_executor_review_packet_report",
]
