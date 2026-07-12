from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.paper_data_quality_gate import persist_paper_data_quality_gate_report
from crypto_ai_system.validation.paper_strategy_validation import persist_paper_strategy_validation_report
from crypto_ai_system.validation.phase4_1_paper_outcome_sample_accumulation import persist_phase4_1_paper_outcome_sample_accumulation_report
from crypto_ai_system.validation.phase4_2_signal_drift_candidate_readiness import persist_phase4_2_signal_drift_candidate_readiness_report
from crypto_ai_system.validation.phase4_3_research_signal_score_bucket_replay import persist_phase4_3_research_signal_score_bucket_replay_report
from crypto_ai_system.validation.phase4_4_candidate_profile_review_packet import persist_phase4_4_candidate_profile_review_packet_report
from crypto_ai_system.validation.phase5_1_manual_approval_operator_handoff import persist_phase5_1_manual_approval_operator_handoff_report
from crypto_ai_system.validation.phase5_2_manual_approval_submission_fixture_validator import persist_phase5_2_manual_approval_submission_fixture_validator_report
from crypto_ai_system.validation.phase5_manual_approval_intake_validation import persist_phase5_manual_approval_intake_validation_report
from crypto_ai_system.validation.phase6_1_signed_testnet_operator_unlock_request_template import persist_phase6_1_signed_testnet_operator_unlock_request_template_report
from crypto_ai_system.validation.phase6_2_operator_unlock_request_fixture_validator import persist_phase6_2_operator_unlock_request_fixture_validator_report
from crypto_ai_system.validation.phase6_3_signed_testnet_readiness_gate_review import persist_phase6_3_signed_testnet_readiness_gate_review_report
from crypto_ai_system.validation.phase6_4_signed_testnet_readiness_review_packet import persist_phase6_4_signed_testnet_readiness_review_packet_report
from crypto_ai_system.validation.phase6_5_actual_manual_approval_operator_unlock_intake_sandbox import persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report
from crypto_ai_system.validation.phase6_6_actual_intake_validation_bridge import persist_phase6_6_actual_intake_validation_bridge_report
from crypto_ai_system.validation.phase6_signed_testnet_preparation_preview import persist_phase6_signed_testnet_preparation_preview_report
from crypto_ai_system.validation.phase7_1_signed_testnet_pre_submit_payload_guard import persist_phase7_1_signed_testnet_pre_submit_payload_guard_report
from crypto_ai_system.validation.phase7_signed_testnet_validation_design_guard import persist_phase7_signed_testnet_validation_design_guard_report
from crypto_ai_system.validation.valid_price_lineage_artifacts import persist_valid_price_lineage_artifacts

PHASE7_1_1_VERSION = "phase7_1_1_review_chain_state_doctor_v1"
PHASE7_1_1_REGISTRY_NAME = "phase7_1_1_review_chain_state_doctor_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_1_1_REVIEW_CHAIN_STATE_DOCTOR_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_1_1_REVIEW_CHAIN_STATE_DOCTOR_BLOCKED_REVIEW_ONLY"

UNSAFE_FIELDS = [
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
    "live_trading_allowed_by_this_module",
    "auto_promotion_allowed",
]

CHAIN_SEQUENCE = [
    "phase2_1_valid_price_lineage",
    "phase2_paper_data_quality_gate",
    "phase3_paper_strategy_validation",
    "phase4_1_paper_outcome_sample_accumulation",
    "phase4_2_signal_drift_candidate_readiness",
    "phase4_3_research_signal_score_bucket_replay",
    "phase4_4_candidate_profile_review_packet",
    "phase5_1_manual_approval_operator_handoff",
    "phase5_2_manual_approval_submission_fixture_validator",
    "phase6_signed_testnet_preparation_preview",
    "phase6_1_signed_testnet_operator_unlock_request_template",
    "phase6_2_operator_unlock_request_fixture_validator",
    "phase5_manual_approval_intake_validation",
    "phase6_3_signed_testnet_readiness_gate_review",
    "phase6_4_signed_testnet_readiness_review_packet",
    "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox",
    "phase6_6_actual_intake_validation_bridge",
    "phase7_signed_testnet_validation_design_guard",
    "phase7_1_signed_testnet_pre_submit_payload_guard",
]

PERSISTERS: dict[str, Callable[..., dict[str, Any]]] = {
    "phase2_1_valid_price_lineage": persist_valid_price_lineage_artifacts,
    "phase2_paper_data_quality_gate": persist_paper_data_quality_gate_report,
    "phase3_paper_strategy_validation": persist_paper_strategy_validation_report,
    "phase4_1_paper_outcome_sample_accumulation": persist_phase4_1_paper_outcome_sample_accumulation_report,
    "phase4_2_signal_drift_candidate_readiness": persist_phase4_2_signal_drift_candidate_readiness_report,
    "phase4_3_research_signal_score_bucket_replay": persist_phase4_3_research_signal_score_bucket_replay_report,
    "phase4_4_candidate_profile_review_packet": persist_phase4_4_candidate_profile_review_packet_report,
    "phase5_1_manual_approval_operator_handoff": persist_phase5_1_manual_approval_operator_handoff_report,
    "phase5_2_manual_approval_submission_fixture_validator": persist_phase5_2_manual_approval_submission_fixture_validator_report,
    "phase6_signed_testnet_preparation_preview": persist_phase6_signed_testnet_preparation_preview_report,
    "phase6_1_signed_testnet_operator_unlock_request_template": persist_phase6_1_signed_testnet_operator_unlock_request_template_report,
    "phase6_2_operator_unlock_request_fixture_validator": persist_phase6_2_operator_unlock_request_fixture_validator_report,
    "phase5_manual_approval_intake_validation": persist_phase5_manual_approval_intake_validation_report,
    "phase6_3_signed_testnet_readiness_gate_review": persist_phase6_3_signed_testnet_readiness_gate_review_report,
    "phase6_4_signed_testnet_readiness_review_packet": persist_phase6_4_signed_testnet_readiness_review_packet_report,
    "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox": persist_phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report,
    "phase6_6_actual_intake_validation_bridge": persist_phase6_6_actual_intake_validation_bridge_report,
    "phase7_signed_testnet_validation_design_guard": persist_phase7_signed_testnet_validation_design_guard_report,
    "phase7_1_signed_testnet_pre_submit_payload_guard": persist_phase7_1_signed_testnet_pre_submit_payload_guard_report,
}

EXPECTED_READY = {
    "phase4_3_research_signal_score_bucket_replay": "PHASE4_3_RESEARCH_SIGNAL_SCORE_BUCKET_REPLAY_RECORDED_REVIEW_ONLY",
    "phase4_4_candidate_profile_review_packet": "PHASE4_4_CANDIDATE_PROFILE_REVIEW_PACKET_RECORDED_REVIEW_ONLY",
    "phase5_manual_approval_intake_validation": "PHASE5_MANUAL_APPROVAL_INTAKE_VALIDATION_RECORDED_REVIEW_ONLY",
    "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox": "PHASE6_5_ACTUAL_APPROVAL_OPERATOR_UNLOCK_INTAKE_SANDBOX_RECORDED_REVIEW_ONLY",
    "phase6_6_actual_intake_validation_bridge": "PHASE6_6_ACTUAL_INTAKE_VALIDATION_BRIDGE_RECORDED_REVIEW_ONLY",
    "phase7_signed_testnet_validation_design_guard": "PHASE7_SIGNED_TESTNET_VALIDATION_DESIGN_RECORDED_REVIEW_ONLY",
    "phase7_1_signed_testnet_pre_submit_payload_guard": "PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_RECORDED_REVIEW_ONLY",
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


def _read_json(path: Path) -> dict[str, Any]:
    payload = read_json(path, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _read_latest_json(cfg: AppConfig, name: str) -> dict[str, Any]:
    return _read_json(_latest_dir(cfg) / name)


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _unsafe_truthy_fields(payload: Mapping[str, Any]) -> list[str]:
    data = dict(payload or {})
    return sorted(field for field in UNSAFE_FIELDS if _safe_bool(data.get(field)))


def _artifact_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase7_1_report_sha256",
        "phase7_report_sha256",
        "phase6_6_report_sha256",
        "phase5_report_sha256",
        "phase4_4_report_sha256",
        "phase4_3_report_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _status_name(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    return data.get("status") or data.get("packet_type") or data.get("guard_type")


def _blocked(payload: Mapping[str, Any]) -> bool | None:
    data = dict(payload or {})
    if "blocked" in data:
        return bool(data.get("blocked"))
    if "passed" in data:
        return not bool(data.get("passed"))
    return None


def _step_summary(step: str, report: Mapping[str, Any] | None, *, exception: str | None = None) -> dict[str, Any]:
    data = dict(report or {})
    return {
        "step": step,
        "present": bool(data),
        "status": _status_name(data),
        "blocked": _blocked(data),
        "fail_closed": data.get("fail_closed"),
        "ready_like": data.get("phase7_1_payload_guard_ready_review_only")
        or data.get("phase7_design_ready_review_only")
        or data.get("phase7_entry_review_possible")
        or data.get("phase5_review_only_validation_ready")
        or data.get("candidate_profile_draft_created")
        or data.get("passed"),
        "block_reasons": data.get("block_reasons") or data.get("readiness_blockers") or [],
        "unsafe_truthy_fields": _unsafe_truthy_fields(data),
        "sha256": _artifact_hash(data),
        "exception": exception,
    }


def _latest_artifact_snapshot(cfg: AppConfig) -> dict[str, dict[str, Any]]:
    latest = _latest_dir(cfg)
    mapping = {
        "phase2_1_valid_price_lineage": "phase2_1_valid_price_lineage_artifacts_report.json",
        "phase3_paper_strategy_validation": "paper_strategy_validation_report.json",
        "phase4_1_paper_outcome_sample_accumulation": "phase4_1_paper_outcome_sample_accumulation_report.json",
        "phase4_2_signal_drift_candidate_readiness": "phase4_2_signal_drift_candidate_readiness_report.json",
        "phase4_3_research_signal_score_bucket_replay": "phase4_3_research_signal_score_bucket_replay_report.json",
        "phase4_4_candidate_profile_review_packet": "phase4_4_candidate_profile_review_packet_report.json",
        "phase5_2_manual_approval_submission_fixture_validator": "phase5_2_manual_approval_submission_fixture_validator_report.json",
        "phase5_manual_approval_intake_validation": "phase5_manual_approval_intake_validation_report.json",
        "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox": "phase6_5_actual_manual_approval_operator_unlock_intake_sandbox_report.json",
        "phase6_2_operator_unlock_request_fixture_validator": "phase6_2_operator_unlock_request_fixture_validator_report.json",
        "phase6_6_actual_intake_validation_bridge": "phase6_6_actual_intake_validation_bridge_report.json",
        "phase7_signed_testnet_validation_design_guard": "phase7_signed_testnet_validation_design_guard_report.json",
        "phase7_1_signed_testnet_pre_submit_payload_guard": "phase7_1_signed_testnet_pre_submit_payload_guard_report.json",
    }
    return {name: _step_summary(name, _read_json(latest / file_name)) for name, file_name in mapping.items()}


def _sync_review_only_actual_files(cfg: AppConfig) -> dict[str, Any]:
    """Create review-only approval/operator files from current templates.

    These files are convenience fixtures for the review chain runner. They are not
    runtime approvals and intentionally keep every execution flag disabled.
    """
    root = cfg.root
    approval_path = root / "storage" / "manual_approval" / "approval_intake_submission.json"
    unlock_path = _latest_dir(cfg) / "operator_unlock_request.json"
    approval_template_path = root / "storage" / "manual_approval" / "approval_intake_submission_TEMPLATE_REVIEW_ONLY.json"
    unlock_template_path = root / "storage" / "signed_testnet" / "operator_unlock_request_TEMPLATE_REVIEW_ONLY.json"
    approval_template = _read_json(approval_template_path)
    unlock_template = _read_json(unlock_template_path)
    created = utc_now_canonical()
    seed = {"version": PHASE7_1_1_VERSION, "created_at_utc": created, "approval_template": approval_template.get("approval_packet_hash") or approval_template.get("approval_packet_draft_sha256")}
    approval_id = stable_id("approval_packet_review_chain_fixture", seed, 18)
    intake_id = stable_id("approval_intake_review_chain_fixture", seed, 18)
    approval = dict(approval_template)
    approval.update(
        {
            "approval_packet_id": approval_id,
            "approval_intake_id": intake_id,
            "approver_info": "REVIEW_CHAIN_STATE_DOCTOR_FIXTURE_NOT_RUNTIME_APPROVAL",
            "ticket_or_signature": stable_id("review_chain_approval_fixture_signature", seed, 24),
            "canonical_utc_timestamp": created,
            "review_chain_fixture_created_by": "phase7_1_1_review_chain_state_doctor",
            "runtime_permission_source": False,
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
        }
    )
    unlock = dict(unlock_template)
    unlock.update(
        {
            "operator_id": "REVIEW_CHAIN_STATE_DOCTOR_FIXTURE_NOT_RUNTIME_OPERATOR",
            "operator_ticket_or_signature": stable_id("review_chain_operator_fixture_signature", seed, 24),
            "canonical_utc_timestamp": created,
            "approval_packet_id": approval_id,
            "approval_intake_id": intake_id,
            "max_testnet_notional_usd": 25.0,
            "max_testnet_order_count": 1,
            "max_testnet_daily_loss_usd": 10.0,
            "kill_switch_rechecked": True,
            "hard_caps_rechecked": True,
            "pre_order_risk_gate_rechecked": True,
            "review_chain_fixture_created_by": "phase7_1_1_review_chain_state_doctor",
            "runtime_permission_source": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "external_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
        }
    )
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    unlock_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(approval_path, approval)
    atomic_write_json(unlock_path, unlock)
    return {
        "approval_fixture_written": True,
        "operator_fixture_written": True,
        "approval_path": str(approval_path),
        "operator_unlock_request_path": str(unlock_path),
        "approval_packet_id": approval_id,
        "approval_intake_id": intake_id,
        "review_only_fixture_not_runtime_authority": True,
    }


def _diagnose_root_cause(step_summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    readiness_blocking: list[str] = []
    for name, expected_status in EXPECTED_READY.items():
        summary = step_summaries.get(name, {})
        if summary.get("status") != expected_status or summary.get("blocked") is True:
            readiness_blocking.append(name)
    first = readiness_blocking[0] if readiness_blocking else None
    reasons = list(step_summaries.get(first or "", {}).get("block_reasons") or [])
    diagnostic_blocked_steps = [name for name in CHAIN_SEQUENCE if step_summaries.get(name, {}).get("blocked") is True]
    phase4_3 = step_summaries.get("phase4_3_research_signal_score_bucket_replay", {})
    diagnosis: list[str] = []
    if first:
        diagnosis.append(f"FIRST_READINESS_BLOCKED_STEP:{first}")
    if "FEATURE_MATRIX_ROWS_MISSING_FOR_SCORE_BUCKET_REPLAY" in reasons:
        diagnosis.append("RUN_OR_REPAIR_PHASE2_1_VALID_PRICE_LINEAGE_AND_FEATURE_STORE_MANIFEST")
    if "PAPER_OUTCOME_SAMPLES_MISSING" in reasons:
        diagnosis.append("RUN_OR_REPAIR_PHASE3_AND_PHASE4_1_PAPER_OUTCOME_SAMPLE_CHAIN")
    if "SOURCE_REPORT_HASH_MISMATCH" in reasons:
        diagnosis.append("REBUILD_PHASE4_4_AND_PHASE5_1_THEN_RECREATE_REVIEW_ONLY_APPROVAL_FIXTURE")
    if "PHASE4_4_REVIEW_PACKET_NOT_READY" in reasons:
        diagnosis.append("PHASE4_4_DEPENDS_ON_PHASE4_3_CANDIDATE_DRAFT_READY")
    if phase4_3.get("blocked") is True and not reasons:
        diagnosis.append("CHECK_PHASE4_3_BLOCK_REASONS")
    if not first and diagnostic_blocked_steps:
        diagnosis.append("NON_FATAL_REVIEW_ONLY_BLOCKED_STEPS_PRESENT_BUT_PHASE7_1_CHAIN_READY")
    return {
        "first_blocked_step": first,
        "first_blocked_reasons": reasons,
        "diagnostic_blocked_steps": diagnostic_blocked_steps,
        "diagnosis": sorted(dict.fromkeys(diagnosis)),
    }


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    doctor = report.get("doctor_summary") or {}
    root = report.get("root_cause_diagnosis") or {}
    ready = report.get("phase7_1_chain_ready_review_only")
    lines = [
        "# Phase 7.1.1 Review Chain State Doctor — Review Only",
        "",
        f"Status: `{report.get('status')}`",
        "",
        "This artifact diagnoses and runs the review-only chain needed before Phase 7.1 payload guard review. It does not enable signed testnet execution and does not submit orders.",
        "",
        "## Summary",
        "",
        f"- Chain ready for Phase 7.1 review-only: `{ready}`",
        f"- First blocked step: `{root.get('first_blocked_step')}`",
        f"- Review-only approval/operator fixtures synced: `{doctor.get('review_only_actual_fixtures_synced')}`",
        "- `ready_for_signed_testnet_execution=false`",
        "- `testnet_order_submission_allowed=false`",
        "- `place_order_enabled=false`",
        "- `signed_order_executor_enabled=false`",
        "",
        "## Diagnosis",
        "",
    ]
    diagnosis = root.get("diagnosis") or []
    lines.extend(f"- `{item}`" for item in diagnosis) if diagnosis else lines.append("- None recorded")
    lines.extend(["", "## Step Results", ""])
    for step in report.get("step_results", []):
        lines.append(f"- `{step.get('step')}` — `{step.get('status')}` blocked=`{step.get('blocked')}`")
    return "\n".join(lines) + "\n"


def run_phase7_1_review_chain(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    sync_review_only_actual_fixtures: bool = True,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    step_results: list[dict[str, Any]] = []
    fixture_sync: dict[str, Any] = {"review_only_actual_fixtures_synced": False}

    for step in CHAIN_SEQUENCE:
        if step == "phase5_manual_approval_intake_validation" and sync_review_only_actual_fixtures:
            fixture_sync = _sync_review_only_actual_files(cfg)
            fixture_sync["review_only_actual_fixtures_synced"] = True
        persister = PERSISTERS[step]
        try:
            result = persister(cfg=cfg)
            step_results.append(_step_summary(step, result))
        except Exception as exc:  # pragma: no cover - intentionally defensive for operator diagnostics
            step_results.append(_step_summary(step, {}, exception=f"{type(exc).__name__}: {exc}"))
            break

    latest_snapshot = _latest_artifact_snapshot(cfg)
    # Prefer direct step results for the current run, but include latest snapshot for files generated by helpers.
    step_summary_map = {item["step"]: item for item in step_results}
    for key, value in latest_snapshot.items():
        step_summary_map.setdefault(key, value)

    root_cause = _diagnose_root_cause(step_summary_map)
    final_phase7_1 = step_summary_map.get("phase7_1_signed_testnet_pre_submit_payload_guard", {})
    ready = (
        final_phase7_1.get("status") == EXPECTED_READY["phase7_1_signed_testnet_pre_submit_payload_guard"]
        and final_phase7_1.get("blocked") is False
        and not any(item.get("unsafe_truthy_fields") for item in step_summary_map.values())
    )
    blockers: list[str] = []
    if not ready:
        blockers.append("REVIEW_CHAIN_NOT_READY_FOR_PHASE7_1_PAYLOAD_GUARD")
    for name, summary in step_summary_map.items():
        unsafe = summary.get("unsafe_truthy_fields") or []
        if unsafe:
            blockers.append(f"UNSAFE_REVIEW_CHAIN_FLAG:{name}:{','.join(unsafe)}")
    for name, expected in EXPECTED_READY.items():
        summary = step_summary_map.get(name, {})
        if summary.get("status") != expected:
            blockers.append(f"EXPECTED_STEP_NOT_READY:{name}")
    blockers = sorted(dict.fromkeys(blockers))
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id("phase7_1_1_review_chain_state_doctor", {"created_at_utc": created, "step_results": step_results, "blockers": blockers}, 24)
    report: dict[str, Any] = {
        "phase7_1_1_review_chain_state_doctor_id": report_id,
        "phase7_1_1_version": PHASE7_1_1_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "state_doctor_only": True,
        "one_command_runner": True,
        "phase7_1_chain_ready_review_only": ready,
        "doctor_summary": {
            "project_root": str(cfg.root),
            "step_count_executed": len(step_results),
            "review_only_actual_fixtures_synced": fixture_sync.get("review_only_actual_fixtures_synced") is True,
            "actual_fixture_sync": fixture_sync,
        },
        "step_results": step_results,
        "latest_artifact_snapshot": latest_snapshot,
        "root_cause_diagnosis": root_cause,
        "block_reasons": blockers,
        "runtime_permission_source": False,
        "signed_testnet_unlock_authority": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
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
        "recommended_next_action": "prepare_phase7_2_executor_enablement_review_packet_keep_executor_disabled" if ready else "inspect_root_cause_diagnosis_and_repair_first_blocked_step",
        "created_at_utc": created,
    }
    report["phase7_1_1_report_sha256"] = sha256_json(report)
    return report


def persist_phase7_1_review_chain_state_doctor_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
    sync_review_only_actual_fixtures: bool = True,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_1_1_review_chain_state_doctor")
    report = run_phase7_1_review_chain(cfg=cfg, sync_review_only_actual_fixtures=sync_review_only_actual_fixtures)
    handoff = _build_handoff_markdown(report)
    atomic_write_json(latest / "review_chain_state_doctor_report.json", report)
    atomic_write_json(latest / "phase7_1_1_review_chain_state_doctor_report.json", report)
    (latest / "PHASE7_1_1_REVIEW_CHAIN_OPERATOR_HANDOFF.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(phase_dir / "review_chain_state_doctor_report.json", report)
    atomic_write_json(phase_dir / "phase7_1_1_review_chain_state_doctor_report.json", report)
    (phase_dir / "PHASE7_1_1_REVIEW_CHAIN_OPERATOR_HANDOFF.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_1_1_REGISTRY_NAME),
        {
            "phase7_1_1_review_chain_state_doctor_id": report.get("phase7_1_1_review_chain_state_doctor_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_1_chain_ready_review_only": report.get("phase7_1_chain_ready_review_only"),
            "first_blocked_step": (report.get("root_cause_diagnosis") or {}).get("first_blocked_step"),
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
        registry_name=PHASE7_1_1_REGISTRY_NAME,
        id_field="phase7_1_1_review_chain_state_doctor_registry_record_id",
        hash_field="phase7_1_1_review_chain_state_doctor_registry_record_sha256",
        id_prefix="phase7_1_1_review_chain_state_doctor_registry_record",
    )
    atomic_write_json(latest / "phase7_1_1_review_chain_state_doctor_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_1_1_review_chain_state_doctor_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_1_1_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "run_phase7_1_review_chain",
    "persist_phase7_1_review_chain_state_doctor_report",
]
