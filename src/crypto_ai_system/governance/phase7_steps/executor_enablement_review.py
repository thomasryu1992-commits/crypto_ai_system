from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.governance.phase7_steps.review_chain_doctor import persist_phase7_1_review_chain_state_doctor_report

PHASE7_2_VERSION = "phase7_2_executor_enablement_review_packet_v1"
PHASE7_2_REGISTRY_NAME = "phase7_2_executor_enablement_review_packet_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_2_EXECUTOR_ENABLEMENT_REVIEW_PACKET_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_2_EXECUTOR_ENABLEMENT_REVIEW_PACKET_BLOCKED_REVIEW_ONLY"

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

REQUIRED_SOURCE_ARTIFACTS = {
    "phase7_1_1_review_chain_state_doctor": "phase7_1_1_review_chain_state_doctor_report.json",
    "phase7_1_signed_testnet_pre_submit_payload_guard": "phase7_1_signed_testnet_pre_submit_payload_guard_report.json",
    "signed_testnet_would_submit_payload_fixture": "signed_testnet_would_submit_payload_FIXTURE_REVIEW_ONLY.json",
    "signed_testnet_disabled_executor_fixture_guard": "signed_testnet_disabled_executor_fixture_guard_report.json",
    "signed_testnet_validation_design_packet": "signed_testnet_validation_design_packet_review_only.json",
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


def _unsafe_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    return [field for field in UNSAFE_TRUTHY_FIELDS if _safe_bool(data.get(field))]


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
        "phase7_2_report_sha256",
        "phase7_1_1_report_sha256",
        "phase7_1_report_sha256",
        "signed_testnet_validation_design_packet_sha256",
        "valid_would_submit_payload_fixture_sha256",
        "disabled_executor_fixture_guard_report_sha256",
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
        "status": data.get("status") or data.get("packet_type") or data.get("guard_type") or data.get("fixture_type"),
        "blocked": data.get("blocked"),
        "fail_closed": data.get("fail_closed"),
        "sha256": _artifact_hash(data),
    }


def _build_enablement_review_packet(*, report_id: str, sources: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    payload = dict(sources.get("signed_testnet_would_submit_payload_fixture") or {})
    design = dict(sources.get("signed_testnet_validation_design_packet") or {})
    return {
        "packet_type": "signed_testnet_executor_enablement_review_packet_review_only",
        "phase7_2_version": PHASE7_2_VERSION,
        "source_phase7_2_report_id": report_id,
        "review_only": True,
        "executor_enablement_review_only": True,
        "actual_executor_enablement_performed": False,
        "signed_testnet_execution_authority": False,
        "signed_testnet_order_submission_authority": False,
        "allowed_scope": [
            "executor_enablement_design_review",
            "disabled_executor_guard_review",
            "would_submit_payload_reference_review",
            "operator_handoff_for_later_explicit_executor_approval",
        ],
        "forbidden_scope": [
            "actual_signed_testnet_order_submission",
            "place_order_enablement",
            "cancel_order_enablement",
            "signed_executor_enablement",
            "api_key_value_access",
            "api_secret_value_access",
            "secret_file_read_or_creation",
            "settings_yaml_mutation",
            "runtime_score_weights_mutation",
            "automatic_promotion_to_live",
        ],
        "would_submit_payload_reference": {
            "fixture_type": payload.get("fixture_type"),
            "symbol": payload.get("symbol"),
            "side": payload.get("side"),
            "order_type": payload.get("order_type"),
            "quantity": payload.get("quantity"),
            "notional": payload.get("notional"),
            "idempotency_key": payload.get("idempotency_key"),
            "canonical_id_chain": payload.get("canonical_id_chain"),
        },
        "future_executor_stage_prerequisites": [
            "Separate explicit signed testnet executor approval packet is required.",
            "Fresh pre-submit validation must be generated after later approval and operator unlock.",
            "Metadata-only key reference validation is allowed; key value reads remain forbidden.",
            "Manual kill switch confirmation must be recorded immediately before any future enablement review.",
            "PreOrderRiskGate must be rerun immediately before any future executor review.",
            "Reconciliation and session close evidence are required after any future testnet session.",
        ],
        "design_packet_ready_review_only": design.get("phase7_design_ready_review_only") is True,
        "ready_for_signed_testnet_execution": False,
        "testnet_order_submission_allowed": False,
        "external_order_submission_performed": False,
        "place_order_enabled": False,
        "cancel_order_enabled": False,
        "signed_order_executor_enabled": False,
        "runtime_settings_mutated": False,
        "score_weights_mutated": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created_at_utc,
    }


def _build_disabled_executor_enablement_guard(*, report_id: str, sources: Mapping[str, Mapping[str, Any]], created_at_utc: str) -> dict[str, Any]:
    payload_guard = dict(sources.get("phase7_1_signed_testnet_pre_submit_payload_guard") or {})
    disabled_fixture_guard = dict(sources.get("signed_testnet_disabled_executor_fixture_guard") or {})
    passed = (
        payload_guard.get("disabled_executor_guard_passed") is True
        and disabled_fixture_guard.get("guard_passed") is True
        and payload_guard.get("actual_order_submission_performed") is False
        and disabled_fixture_guard.get("external_order_submission_performed") is False
        and not _unsafe_fields(payload_guard)
        and not _unsafe_fields(disabled_fixture_guard)
    )
    return {
        "guard_type": "signed_testnet_executor_enablement_disabled_guard_review_only",
        "source_phase7_2_report_id": report_id,
        "guard_passed": passed,
        "guard_scope": "prove_executor_enablement_is_not_performed_during_phase7_2_review",
        "payload_guard_disabled_executor_passed": payload_guard.get("disabled_executor_guard_passed") is True,
        "fixture_guard_passed": disabled_fixture_guard.get("guard_passed") is True,
        "actual_executor_enablement_performed": False,
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
            "# Phase 7.2 Executor Enablement Review Packet — Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This artifact prepares a review-only executor enablement packet. It does not enable the signed executor, does not read secret values, and does not submit orders.",
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
            f"`{report.get('phase7_2_allowed_next_scope')}`",
            "",
        ]
    )


def build_phase7_2_executor_enablement_review_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_review_chain_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_review_chain_first:
        persist_phase7_1_review_chain_state_doctor_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}

    doctor = artifacts.get("phase7_1_1_review_chain_state_doctor", {})
    phase7_1 = artifacts.get("phase7_1_signed_testnet_pre_submit_payload_guard", {})
    payload = artifacts.get("signed_testnet_would_submit_payload_fixture", {})
    fixture_guard = artifacts.get("signed_testnet_disabled_executor_fixture_guard", {})
    design = artifacts.get("signed_testnet_validation_design_packet", {})

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_2_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_2_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if doctor.get("status") != "PHASE7_1_1_REVIEW_CHAIN_STATE_DOCTOR_RECORDED_REVIEW_ONLY" or doctor.get("phase7_1_chain_ready_review_only") is not True:
        blockers.append("PHASE7_1_1_REVIEW_CHAIN_NOT_READY")
    if phase7_1.get("status") != "PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_RECORDED_REVIEW_ONLY" or phase7_1.get("phase7_1_payload_guard_ready_review_only") is not True:
        blockers.append("PHASE7_1_PAYLOAD_GUARD_NOT_READY")
    if phase7_1.get("valid_would_submit_payload_passed_review_only_validation") is not True:
        blockers.append("WOULD_SUBMIT_PAYLOAD_VALIDATION_NOT_PASSED")
    if phase7_1.get("invalid_payload_fixtures_blocked_fail_closed") is not True:
        blockers.append("INVALID_PAYLOAD_FIXTURES_NOT_BLOCKED_FAIL_CLOSED")
    if phase7_1.get("disabled_executor_guard_passed") is not True or fixture_guard.get("guard_passed") is not True:
        blockers.append("DISABLED_EXECUTOR_GUARD_NOT_PASSED")
    if payload.get("would_submit_only") is not True or payload.get("do_not_submit_order") is not True:
        blockers.append("WOULD_SUBMIT_PAYLOAD_NOT_REVIEW_ONLY")
    if design.get("phase7_design_ready_review_only") is not True:
        blockers.append("PHASE7_DESIGN_PACKET_NOT_READY")

    blockers = sorted(dict.fromkeys(blockers))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id("phase7_2_executor_enablement_review_packet", {"created_at_utc": created, "source_summary": source_summary, "blockers": blockers}, 24)

    enablement_packet = _build_enablement_review_packet(report_id=report_id, sources=artifacts, created_at_utc=created)
    disabled_guard = _build_disabled_executor_enablement_guard(report_id=report_id, sources=artifacts, created_at_utc=created)
    if not disabled_guard.get("guard_passed"):
        if "DISABLED_EXECUTOR_ENABLEMENT_GUARD_NOT_PASSED" not in blockers:
            blockers.append("DISABLED_EXECUTOR_ENABLEMENT_GUARD_NOT_PASSED")
        ready = False
        status = STATUS_BLOCKED_REVIEW_ONLY

    report: dict[str, Any] = {
        "phase7_2_executor_enablement_review_packet_id": report_id,
        "phase7_2_version": PHASE7_2_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "executor_enablement_review_only": True,
        "executor_enablement_review_packet_created": True,
        "disabled_executor_enablement_guard_created": True,
        "phase7_2_executor_enablement_review_ready": ready,
        "actual_executor_enablement_performed": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_enablement_authority": False,
        "signed_testnet_order_submission_authority": False,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "block_reasons": blockers,
        "phase7_2_allowed_next_scope": "future_disabled_executor_implementation_review_only" if ready else "resolve_phase7_2_review_packet_blockers",
        "recommended_next_action": "prepare_future_disabled_executor_implementation_review_keep_executor_disabled" if ready else "inspect_phase7_2_blockers_and_rerun_review_chain",
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
        "created_at_utc": created,
    }
    report["executor_enablement_review_packet_sha256"] = sha256_json(enablement_packet)
    report["disabled_executor_enablement_guard_sha256"] = sha256_json(disabled_guard)
    report["phase7_2_report_sha256"] = sha256_json(report)
    return report, enablement_packet, disabled_guard


def persist_phase7_2_executor_enablement_review_packet_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_review_chain_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_2_executor_enablement_review_packet")
    report, packet, guard = build_phase7_2_executor_enablement_review_packet_report(
        cfg=cfg, run_review_chain_first=run_review_chain_first
    )
    handoff = _build_handoff_markdown(report)
    atomic_write_json(latest / "phase7_2_executor_enablement_review_packet_report.json", report)
    atomic_write_json(latest / "signed_testnet_executor_enablement_review_packet_review_only.json", packet)
    atomic_write_json(latest / "signed_testnet_executor_enablement_disabled_guard_report.json", guard)
    (latest / "PHASE7_2_EXECUTOR_ENABLEMENT_REVIEW_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(phase_dir / "phase7_2_executor_enablement_review_packet_report.json", report)
    atomic_write_json(phase_dir / "signed_testnet_executor_enablement_review_packet_review_only.json", packet)
    atomic_write_json(phase_dir / "signed_testnet_executor_enablement_disabled_guard_report.json", guard)
    (phase_dir / "PHASE7_2_EXECUTOR_ENABLEMENT_REVIEW_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_2_REGISTRY_NAME),
        {
            "phase7_2_executor_enablement_review_packet_id": report.get("phase7_2_executor_enablement_review_packet_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_2_executor_enablement_review_ready": report.get("phase7_2_executor_enablement_review_ready"),
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
        registry_name=PHASE7_2_REGISTRY_NAME,
        id_field="phase7_2_executor_enablement_review_packet_registry_record_id",
        hash_field="phase7_2_executor_enablement_review_packet_registry_record_sha256",
        id_prefix="phase7_2_executor_enablement_review_packet_registry_record",
    )
    atomic_write_json(latest / "phase7_2_executor_enablement_review_packet_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_2_executor_enablement_review_packet_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_2_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase7_2_executor_enablement_review_packet_report",
    "persist_phase7_2_executor_enablement_review_packet_report",
]
