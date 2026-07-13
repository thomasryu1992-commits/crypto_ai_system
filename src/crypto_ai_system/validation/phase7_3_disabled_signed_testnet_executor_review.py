from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.disabled_signed_testnet_executor import (
    DisabledSignedTestnetExecutor,
    unsafe_truthy_fields,
    validate_review_only_would_submit_payload,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical
from crypto_ai_system.validation.phase7_2_executor_enablement_review_packet import (
    persist_phase7_2_executor_enablement_review_packet_report,
)

PHASE7_3_VERSION = "phase7_3_disabled_signed_testnet_executor_review_v1"
PHASE7_3_REGISTRY_NAME = "phase7_3_disabled_signed_testnet_executor_review_registry"
STATUS_RECORDED_REVIEW_ONLY = "PHASE7_3_DISABLED_SIGNED_TESTNET_EXECUTOR_REVIEW_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE7_3_DISABLED_SIGNED_TESTNET_EXECUTOR_REVIEW_BLOCKED_REVIEW_ONLY"

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
    "phase7_2_executor_enablement_review_packet": "phase7_2_executor_enablement_review_packet_report.json",
    "signed_testnet_executor_enablement_review_packet": "signed_testnet_executor_enablement_review_packet_review_only.json",
    "signed_testnet_executor_enablement_disabled_guard": "signed_testnet_executor_enablement_disabled_guard_report.json",
    "phase7_1_signed_testnet_pre_submit_payload_guard": "phase7_1_signed_testnet_pre_submit_payload_guard_report.json",
    "signed_testnet_would_submit_payload_fixture": "signed_testnet_would_submit_payload_FIXTURE_REVIEW_ONLY.json",
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
        "phase7_3_report_sha256",
        "phase7_2_report_sha256",
        "executor_enablement_review_packet_sha256",
        "disabled_executor_enablement_guard_sha256",
        "phase7_1_report_sha256",
        "valid_would_submit_payload_fixture_sha256",
        "blocked_execution_evidence_sha256",
        "blocked_cancel_evidence_sha256",
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


def _build_handoff_markdown(report: Mapping[str, Any]) -> str:
    blockers = report.get("block_reasons") or []
    blocker_lines = "\n".join(f"- `{item}`" for item in blockers) or "- None recorded"
    return "\n".join(
        [
            "# Phase 7.3 Disabled Signed Testnet Executor Review — Review Only",
            "",
            f"Status: `{report.get('status')}`",
            "",
            "This phase implements a disabled signed testnet executor interface. It proves that submit/cancel calls produce blocked review-only evidence and never call exchange endpoints.",
            "",
            "## Result",
            "",
            f"- Submit blocked review-only: `{report.get('submit_order_blocked_review_only')}`",
            f"- Cancel blocked review-only: `{report.get('cancel_order_blocked_review_only')}`",
            f"- Exchange endpoint called: `{report.get('exchange_endpoint_called')}`",
            f"- External order submission performed: `{report.get('external_order_submission_performed')}`",
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
            f"`{report.get('phase7_3_allowed_next_scope')}`",
            "",
        ]
    )


def _invalid_payloads(valid_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    max_notional = valid_payload.get("max_testnet_notional_usd") or 25.0
    try:
        max_notional_float = float(max_notional)
    except (TypeError, ValueError):
        max_notional_float = 25.0
    return {
        "invalid_missing_idempotency_key": {**dict(valid_payload), "idempotency_key": ""},
        "invalid_missing_canonical_id_chain": {**dict(valid_payload), "canonical_id_chain": {}},
        "invalid_unsafe_testnet_order_submission_flag": {**dict(valid_payload), "testnet_order_submission_allowed": True},
        "invalid_unsafe_place_order_flag": {**dict(valid_payload), "place_order_enabled": True},
        "invalid_hard_cap_exceeded": {**dict(valid_payload), "notional": max_notional_float + 1000.0},
    }


def build_phase7_3_disabled_signed_testnet_executor_review_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_2_first: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = cfg or load_config(project_root)
    created = utc_now_canonical()
    if run_phase7_2_first:
        persist_phase7_2_executor_enablement_review_packet_report(cfg=cfg)

    artifacts = {name: _read_latest_json(cfg, file_name) for name, file_name in REQUIRED_SOURCE_ARTIFACTS.items()}
    missing = [name for name, payload in artifacts.items() if not payload]
    unsafe = _unsafe_flags_by_artifact(artifacts)
    source_summary = {name: _source_summary(name, payload) for name, payload in artifacts.items()}

    phase7_2 = artifacts.get("phase7_2_executor_enablement_review_packet", {})
    enablement_packet = artifacts.get("signed_testnet_executor_enablement_review_packet", {})
    enablement_guard = artifacts.get("signed_testnet_executor_enablement_disabled_guard", {})
    phase7_1 = artifacts.get("phase7_1_signed_testnet_pre_submit_payload_guard", {})
    payload = artifacts.get("signed_testnet_would_submit_payload_fixture", {})

    executor = DisabledSignedTestnetExecutor()
    submit_evidence = executor.submit_order(payload)
    cancel_evidence = executor.cancel_order(execution_id=str(submit_evidence.get("execution_id") or ""), payload={"execution_id": submit_evidence.get("execution_id")})
    invalid_submit_results = {name: executor.submit_order(invalid) for name, invalid in _invalid_payloads(payload).items()}

    blockers: list[str] = []
    blockers.extend([f"MISSING_PHASE7_3_SOURCE_ARTIFACT:{name}" for name in missing])
    if unsafe:
        blockers.extend([f"UNSAFE_PHASE7_3_SOURCE_FLAGS:{name}:{','.join(flags)}" for name, flags in unsafe.items()])
    if phase7_2.get("status") != "PHASE7_2_EXECUTOR_ENABLEMENT_REVIEW_PACKET_RECORDED_REVIEW_ONLY" or phase7_2.get("phase7_2_executor_enablement_review_ready") is not True:
        blockers.append("PHASE7_2_EXECUTOR_ENABLEMENT_REVIEW_PACKET_NOT_READY")
    if enablement_packet.get("executor_enablement_review_only") is not True or enablement_packet.get("actual_executor_enablement_performed") is not False:
        blockers.append("EXECUTOR_ENABLEMENT_PACKET_NOT_REVIEW_ONLY")
    if enablement_packet.get("signed_testnet_order_submission_authority") is not False:
        blockers.append("EXECUTOR_ENABLEMENT_PACKET_HAS_ORDER_SUBMISSION_AUTHORITY")
    if enablement_guard.get("guard_passed") is not True or enablement_guard.get("actual_executor_enablement_performed") is not False:
        blockers.append("EXECUTOR_ENABLEMENT_DISABLED_GUARD_NOT_PASSED")
    if phase7_1.get("status") != "PHASE7_1_SIGNED_TESTNET_PRE_SUBMIT_PAYLOAD_GUARD_RECORDED_REVIEW_ONLY" or phase7_1.get("phase7_1_payload_guard_ready_review_only") is not True:
        blockers.append("PHASE7_1_PAYLOAD_GUARD_NOT_READY")
    if payload.get("would_submit_only") is not True or payload.get("do_not_submit_order") is not True:
        blockers.append("WOULD_SUBMIT_PAYLOAD_NOT_REVIEW_ONLY")

    if submit_evidence.get("submit_order_blocked_review_only") is not True or submit_evidence.get("blocked") is not True or submit_evidence.get("fail_closed") is not True:
        blockers.append("SUBMIT_ORDER_DID_NOT_BLOCK_FAIL_CLOSED")
    if submit_evidence.get("exchange_endpoint_called") is not False or submit_evidence.get("external_order_submission_performed") is not False:
        blockers.append("SUBMIT_ORDER_ENDPOINT_OR_EXTERNAL_SUBMISSION_PERFORMED")
    if submit_evidence.get("payload_valid_review_only") is not True:
        blockers.append("VALID_WOULD_SUBMIT_PAYLOAD_DID_NOT_VALIDATE_IN_DISABLED_EXECUTOR")

    if cancel_evidence.get("cancel_order_blocked_review_only") is not True or cancel_evidence.get("blocked") is not True or cancel_evidence.get("fail_closed") is not True:
        blockers.append("CANCEL_ORDER_DID_NOT_BLOCK_FAIL_CLOSED")
    if cancel_evidence.get("exchange_endpoint_called") is not False or cancel_evidence.get("external_order_submission_performed") is not False:
        blockers.append("CANCEL_ORDER_ENDPOINT_OR_EXTERNAL_SUBMISSION_PERFORMED")

    for name, evidence in invalid_submit_results.items():
        validation = evidence.get("payload_validation") if isinstance(evidence.get("payload_validation"), Mapping) else {}
        if evidence.get("submit_order_blocked_review_only") is not True or evidence.get("fail_closed") is not True:
            blockers.append(f"INVALID_PAYLOAD_DID_NOT_BLOCK_FAIL_CLOSED:{name}")
        if validation.get("payload_valid_review_only") is not False:
            blockers.append(f"INVALID_PAYLOAD_VALIDATED_UNEXPECTEDLY:{name}")
        if evidence.get("exchange_endpoint_called") is not False or evidence.get("external_order_submission_performed") is not False:
            blockers.append(f"INVALID_PAYLOAD_ENDPOINT_OR_EXTERNAL_SUBMISSION_PERFORMED:{name}")

    for source_name, source in {"submit_evidence": submit_evidence, "cancel_evidence": cancel_evidence, **invalid_submit_results}.items():
        flags = unsafe_truthy_fields(source)
        if flags:
            blockers.append(f"UNSAFE_DISABLED_EXECUTOR_EVIDENCE_FLAGS:{source_name}:{','.join(flags)}")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if item))
    ready = not blockers
    status = STATUS_RECORDED_REVIEW_ONLY if ready else STATUS_BLOCKED_REVIEW_ONLY
    report_id = stable_id(
        "phase7_3_disabled_signed_testnet_executor_review",
        {"source_summary": source_summary, "submit_hash": sha256_json(submit_evidence), "cancel_hash": sha256_json(cancel_evidence), "blockers": blockers, "created_at_utc": created},
        24,
    )

    submit_evidence = {**submit_evidence, "source_phase7_3_report_id": report_id}
    cancel_evidence = {**cancel_evidence, "source_phase7_3_report_id": report_id}

    report: dict[str, Any] = {
        "phase7_3_disabled_signed_testnet_executor_review_id": report_id,
        "phase7_3_version": PHASE7_3_VERSION,
        "status": status,
        "blocked": not ready,
        "fail_closed": not ready,
        "review_only": True,
        "disabled_executor_review": True,
        "disabled_executor_interface_added": True,
        "blocked_execution_evidence_created": True,
        "blocked_cancel_evidence_created": True,
        "submit_order_blocked_review_only": submit_evidence.get("submit_order_blocked_review_only") is True,
        "cancel_order_blocked_review_only": cancel_evidence.get("cancel_order_blocked_review_only") is True,
        "phase7_3_disabled_executor_review_ready": ready,
        "valid_would_submit_payload_passed_executor_validation": submit_evidence.get("payload_valid_review_only") is True,
        "invalid_payload_fixture_count": len(invalid_submit_results),
        "invalid_payload_fixtures_blocked_fail_closed": all(e.get("submit_order_blocked_review_only") is True and e.get("fail_closed") is True for e in invalid_submit_results.values()),
        "exchange_endpoint_called": False,
        "endpoint_call_count": executor.endpoint_call_count,
        "actual_executor_enablement_performed": False,
        "actual_order_submission_performed": False,
        "actual_cancel_performed": False,
        "phase7_execution_authority": False,
        "phase7_order_submission_authority": False,
        "signed_testnet_executor_enablement_authority": False,
        "signed_testnet_order_submission_authority": False,
        "source_evidence_hash_summary": source_summary,
        "missing_source_artifacts": missing,
        "unsafe_flags_by_artifact": unsafe,
        "invalid_submit_result_summary": {
            name: {
                "status": evidence.get("status"),
                "blocked": evidence.get("blocked"),
                "fail_closed": evidence.get("fail_closed"),
                "payload_valid_review_only": evidence.get("payload_valid_review_only"),
                "payload_blockers": (evidence.get("payload_validation") or {}).get("payload_blockers") if isinstance(evidence.get("payload_validation"), Mapping) else None,
                "exchange_endpoint_called": evidence.get("exchange_endpoint_called"),
                "external_order_submission_performed": evidence.get("external_order_submission_performed"),
            }
            for name, evidence in invalid_submit_results.items()
        },
        "block_reasons": blockers,
        "phase7_3_allowed_next_scope": "disabled_execution_reconciliation_and_session_close_design" if ready else "resolve_phase7_3_disabled_executor_review_blockers",
        "recommended_next_action": "prepare_disabled_execution_reconciliation_session_close_design" if ready else "inspect_phase7_3_blockers_and_rerun_phase7_2_phase7_3",
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
    report["blocked_execution_evidence_sha256"] = sha256_json(submit_evidence)
    report["blocked_cancel_evidence_sha256"] = sha256_json(cancel_evidence)
    report["phase7_3_report_sha256"] = sha256_json(report)
    return report, submit_evidence, cancel_evidence


def persist_phase7_3_disabled_signed_testnet_executor_review_report(
    *, cfg: AppConfig | None = None, project_root: str | Path | None = None, run_phase7_2_first: bool = True
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase7_3_disabled_signed_testnet_executor_review")
    report, submit_evidence, cancel_evidence = build_phase7_3_disabled_signed_testnet_executor_review_report(
        cfg=cfg, run_phase7_2_first=run_phase7_2_first
    )
    handoff = _build_handoff_markdown(report)
    atomic_write_json(latest / "phase7_3_disabled_signed_testnet_executor_review_report.json", report)
    atomic_write_json(latest / "disabled_signed_testnet_blocked_execution_evidence_review_only.json", submit_evidence)
    atomic_write_json(latest / "disabled_signed_testnet_blocked_cancel_evidence_review_only.json", cancel_evidence)
    (latest / "PHASE7_3_DISABLED_SIGNED_TESTNET_EXECUTOR_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    atomic_write_json(phase_dir / "phase7_3_disabled_signed_testnet_executor_review_report.json", report)
    atomic_write_json(phase_dir / "disabled_signed_testnet_blocked_execution_evidence_review_only.json", submit_evidence)
    atomic_write_json(phase_dir / "disabled_signed_testnet_blocked_cancel_evidence_review_only.json", cancel_evidence)
    (phase_dir / "PHASE7_3_DISABLED_SIGNED_TESTNET_EXECUTOR_HANDOFF_REVIEW_ONLY.md").write_text(handoff, encoding="utf-8")
    registry_record = append_registry_record(
        registry_path(cfg, PHASE7_3_REGISTRY_NAME),
        {
            "phase7_3_disabled_signed_testnet_executor_review_id": report.get("phase7_3_disabled_signed_testnet_executor_review_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "phase7_3_disabled_executor_review_ready": report.get("phase7_3_disabled_executor_review_ready"),
            "submit_order_blocked_review_only": report.get("submit_order_blocked_review_only"),
            "cancel_order_blocked_review_only": report.get("cancel_order_blocked_review_only"),
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
        registry_name=PHASE7_3_REGISTRY_NAME,
        id_field="phase7_3_disabled_signed_testnet_executor_review_registry_record_id",
        hash_field="phase7_3_disabled_signed_testnet_executor_review_registry_record_sha256",
        id_prefix="phase7_3_disabled_signed_testnet_executor_review_registry_record",
    )
    atomic_write_json(latest / "phase7_3_disabled_signed_testnet_executor_review_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase7_3_disabled_signed_testnet_executor_review_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE7_3_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase7_3_disabled_signed_testnet_executor_review_report",
    "persist_phase7_3_disabled_signed_testnet_executor_review_report",
]
