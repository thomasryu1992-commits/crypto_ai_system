from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

PHASE6_1_VERSION = "phase6_1_signed_testnet_operator_unlock_request_template_v1"
PHASE6_1_REGISTRY_NAME = "phase6_1_signed_testnet_operator_unlock_request_template_registry"

STATUS_RECORDED_REVIEW_ONLY = "PHASE6_1_SIGNED_TESTNET_OPERATOR_UNLOCK_REQUEST_TEMPLATE_RECORDED_REVIEW_ONLY"
STATUS_BLOCKED_REVIEW_ONLY = "PHASE6_1_SIGNED_TESTNET_OPERATOR_UNLOCK_REQUEST_TEMPLATE_BLOCKED_REVIEW_ONLY"

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
    "auto_promotion_allowed",
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


def _payload_hash(payload: Mapping[str, Any]) -> str | None:
    data = dict(payload or {})
    if not data:
        return None
    for key in (
        "phase6_report_sha256",
        "signed_testnet_pre_submit_validation_sha256",
        "signed_testnet_execution_enablement_packet_sha256",
        "real_read_only_venue_probe_sha256",
        "testnet_secret_metadata_intake_sha256",
        "signed_testnet_execution_record_sha256",
        "report_sha256",
    ):
        if data.get(key):
            return str(data[key])
    return sha256_json(data)


def _source_blockers(phase6: Mapping[str, Any], pre_submit: Mapping[str, Any], probe: Mapping[str, Any], enablement: Mapping[str, Any], executor: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if phase6.get("status") != "PHASE6_SIGNED_TESTNET_PREPARATION_PREVIEW_RECORDED_REVIEW_ONLY":
        blockers.append("PHASE6_PREPARATION_PREVIEW_NOT_RECORDED")
    if phase6.get("ready_for_signed_testnet_execution") is not False:
        blockers.append("PHASE6_READY_FLAG_UNEXPECTED")
    if phase6.get("testnet_order_submission_allowed") is not False:
        blockers.append("PHASE6_TESTNET_ORDER_SUBMISSION_UNEXPECTED")
    if not pre_submit:
        blockers.append("SIGNED_TESTNET_PRE_SUBMIT_VALIDATION_MISSING")
    if not probe:
        blockers.append("REAL_READ_ONLY_VENUE_PROBE_MISSING")
    if not enablement:
        blockers.append("SIGNED_TESTNET_ENABLEMENT_PACKET_MISSING")
    if not executor:
        blockers.append("SIGNED_TESTNET_DISABLED_EXECUTOR_EVIDENCE_MISSING")
    for name, payload in {
        "phase6": phase6,
        "pre_submit": pre_submit,
        "probe": probe,
        "enablement": enablement,
        "executor": executor,
    }.items():
        for field in UNSAFE_TRUTHY_FIELDS:
            if _safe_bool(dict(payload or {}).get(field)):
                blockers.append(f"UNSAFE_SOURCE_FLAG:{name}:{field}")
    return sorted(dict.fromkeys(blockers))


def _build_unlock_request_template(*, phase6: Mapping[str, Any], pre_submit: Mapping[str, Any], probe: Mapping[str, Any], enablement: Mapping[str, Any], created: str) -> dict[str, Any]:
    seed = {
        "phase6_id": phase6.get("phase6_signed_testnet_preparation_preview_id"),
        "pre_submit_hash": _payload_hash(pre_submit),
        "venue_probe_hash": _payload_hash(probe),
        "enablement_hash": _payload_hash(enablement),
    }
    template: dict[str, Any] = {
        "template_type": "signed_testnet_operator_unlock_request_template",
        "template_version": PHASE6_1_VERSION,
        "review_only": True,
        "operator_action_required": True,
        "do_not_write_automatically": True,
        "write_target_when_manually_approved": "storage/latest/operator_unlock_request.json",
        "optional_archive_target_when_manually_approved": "storage/signed_testnet/operator_unlock_request.json",
        "instructions": [
            "Copy this template only after manual approval intake has passed and the operator has rechecked hard caps and kill switch state.",
            "Fill operator_id, operator_ticket_or_signature, hard cap fields, and canonical_utc_timestamp manually.",
            "Do not change pre_submit_validation_hash, venue_probe_hash, enablement_packet_hash, or phase6_preparation_preview_hash unless source artifacts are regenerated and re-reviewed.",
            "Saving this template itself is not an execution unlock and does not allow testnet order submission.",
        ],
        "operator_unlock_request_id": stable_id("operator_unlock_request_template", seed, 24),
        "operator_id": "MANUAL_REQUIRED_OPERATOR_ID",
        "operator_ticket_or_signature": "MANUAL_REQUIRED_OPERATOR_TICKET_OR_SIGNATURE",
        "canonical_utc_timestamp": "MANUAL_REQUIRED_CANONICAL_UTC_TIMESTAMP",
        "approval_intake_id": "MANUAL_REQUIRED_VALIDATED_APPROVAL_INTAKE_ID",
        "approval_packet_id": "MANUAL_REQUIRED_VALIDATED_APPROVAL_PACKET_ID",
        "phase6_signed_testnet_preparation_preview_id": phase6.get("phase6_signed_testnet_preparation_preview_id"),
        "phase6_preparation_preview_hash": phase6.get("phase6_report_sha256"),
        "pre_submit_validation_hash": _payload_hash(pre_submit),
        "venue_probe_hash": _payload_hash(probe),
        "enablement_packet_hash": _payload_hash(enablement),
        "requested_stage": "signed_testnet_preparation_review_only",
        "requested_action": "operator_unlock_request_review_only_template",
        "allowed_symbol": pre_submit.get("symbol") or "BTCUSDT",
        "max_testnet_notional_usd": "MANUAL_REQUIRED_NUMERIC_HARD_CAP",
        "max_testnet_order_count": "MANUAL_REQUIRED_INTEGER_HARD_CAP",
        "max_testnet_daily_loss_usd": "MANUAL_REQUIRED_NUMERIC_DAILY_LOSS_CAP",
        "kill_switch_rechecked": "MANUAL_REQUIRED_TRUE",
        "hard_caps_rechecked": "MANUAL_REQUIRED_TRUE",
        "pre_order_risk_gate_rechecked": "MANUAL_REQUIRED_TRUE",
        "reconciliation_required_after_any_testnet_session": True,
        "manual_checks_required": [
            "Confirm Phase 5 manual approval intake has passed with a real human submission.",
            "Confirm operator_id and ticket_or_signature are manually filled.",
            "Confirm hard caps are numeric, conservative, and match the approval scope.",
            "Confirm manual kill switch is available and tested before any later executor enablement.",
            "Confirm the latest pre-submit validation, venue probe, and enablement packet hashes match this request.",
            "Confirm this request is for signed testnet preparation only, not live canary or live scaled execution.",
        ],
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
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "created_at_utc": created,
    }
    template["operator_unlock_request_template_sha256"] = sha256_json(template)
    return template


def _build_handoff_markdown(template: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    manual_checks = "\n".join(f"- {item}" for item in template.get("manual_checks_required", []))
    return f"""# Phase 6.1 Signed Testnet Operator Unlock Request Template — Review Only

Status: `{report.get('status')}`

This handoff prepares the operator unlock request template required before any future signed testnet enablement review. It does not create an actual operator unlock request, does not enable the signed executor, and does not submit testnet or live orders.

## Template Location

- Review-only template: `storage/latest/operator_unlock_request_template_review_only.json`
- Operator copy target, only after manual approval and hard-cap recheck: `storage/latest/operator_unlock_request.json`

## Required Manual Fields

- `operator_id`
- `operator_ticket_or_signature`
- `canonical_utc_timestamp`
- `approval_intake_id`
- `approval_packet_id`
- `max_testnet_notional_usd`
- `max_testnet_order_count`
- `max_testnet_daily_loss_usd`
- `kill_switch_rechecked`
- `hard_caps_rechecked`
- `pre_order_risk_gate_rechecked`

## Hashes That Must Not Be Changed

- `phase6_preparation_preview_hash`: `{template.get('phase6_preparation_preview_hash')}`
- `pre_submit_validation_hash`: `{template.get('pre_submit_validation_hash')}`
- `venue_probe_hash`: `{template.get('venue_probe_hash')}`
- `enablement_packet_hash`: `{template.get('enablement_packet_hash')}`

## Manual Checks

{manual_checks}

## Safety Invariants

- `ready_for_signed_testnet_execution=false`
- `testnet_order_submission_allowed=false`
- `place_order_enabled=false`
- `cancel_order_enabled=false`
- `signed_order_executor_enabled=false`
- `external_order_submission_performed=false`
- `live_trading_allowed=false`
- `runtime_settings_mutated=false`
- `score_weights_mutated=false`
- `auto_promotion_allowed=false`

## Next Step

Only after a human creates `storage/latest/operator_unlock_request.json`, rerun Phase 6 preparation and the signed testnet enablement packet. If approval intake has not been validated or any hard-cap / kill-switch evidence is missing, signed testnet execution must remain disabled.
"""


def build_phase6_1_signed_testnet_operator_unlock_request_template_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    created = utc_now_canonical()
    phase6 = _read_latest_json(cfg, "phase6_signed_testnet_preparation_preview_report.json")
    phase5 = _read_latest_json(cfg, "phase5_manual_approval_intake_validation_report.json")
    pre_submit = _read_latest_json(cfg, "signed_testnet_pre_submit_validation_report.json")
    probe = _read_latest_json(cfg, "real_read_only_venue_probe.json")
    enablement = _read_latest_json(cfg, "signed_testnet_execution_enablement_packet.json")
    executor = _read_latest_json(cfg, "signed_testnet_order_execution_record.json")
    actual_unlock_request_path = latest / "operator_unlock_request.json"

    blockers = _source_blockers(phase6, pre_submit, probe, enablement, executor)
    if actual_unlock_request_path.exists():
        blockers.append("ACTUAL_OPERATOR_UNLOCK_REQUEST_PRESENT_UNEXPECTED")
    if phase5.get("approval_intake_validated") is not False:
        blockers.append("PHASE5_APPROVAL_INTAKE_VALIDATED_UNEXPECTED_FOR_TEMPLATE_BASELINE")
    # Missing actual operator unlock request is expected and keeps execution disabled; do not make it a blocker for template recording.
    blockers = sorted(dict.fromkeys(blockers))
    blocked = bool(blockers)
    status = STATUS_BLOCKED_REVIEW_ONLY if blocked else STATUS_RECORDED_REVIEW_ONLY
    template = _build_unlock_request_template(phase6=phase6, pre_submit=pre_submit, probe=probe, enablement=enablement, created=created) if not blocked else {}
    report_id = stable_id(
        "phase6_1_signed_testnet_operator_unlock_request_template",
        {
            "phase6_id": phase6.get("phase6_signed_testnet_preparation_preview_id"),
            "template_sha256": template.get("operator_unlock_request_template_sha256"),
            "created_at_utc": created,
            "blocked": blocked,
        },
        24,
    )
    report: dict[str, Any] = {
        "phase6_1_signed_testnet_operator_unlock_request_template_id": report_id,
        "phase6_1_version": PHASE6_1_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "review_only": True,
        "operator_unlock_request_template_created": bool(template),
        "operator_unlock_request_created": False,
        "actual_operator_unlock_request_path_created": False,
        "operator_unlock_request_present": actual_unlock_request_path.exists(),
        "operator_unlock_request_template_path": "storage/latest/operator_unlock_request_template_review_only.json",
        "operator_unlock_request_actual_target_path": "storage/latest/operator_unlock_request.json",
        "operator_unlock_request_archive_target_path": "storage/signed_testnet/operator_unlock_request.json",
        "operator_handoff_markdown_path": "storage/latest/OPERATOR_UNLOCK_REQUEST_HANDOFF_REVIEW_ONLY.md",
        "operator_template_sha256": template.get("operator_unlock_request_template_sha256"),
        "phase6_status": phase6.get("status"),
        "phase6_signed_testnet_preparation_preview_id": phase6.get("phase6_signed_testnet_preparation_preview_id"),
        "phase6_preparation_preview_hash": phase6.get("phase6_report_sha256"),
        "phase5_status": phase5.get("status"),
        "approval_intake_validated": False,
        "approval_packet_created": False,
        "pre_submit_validation_hash": _payload_hash(pre_submit),
        "venue_probe_hash": _payload_hash(probe),
        "enablement_packet_hash": _payload_hash(enablement),
        "disabled_executor_hash": _payload_hash(executor),
        "block_reasons": blockers,
        "readiness_blockers": [
            "ACTUAL_MANUAL_APPROVAL_SUBMISSION_MISSING",
            "APPROVAL_INTAKE_NOT_VALIDATED",
            "ACTUAL_OPERATOR_UNLOCK_REQUEST_MISSING",
        ],
        "signed_testnet_preparation_ready": False,
        "signed_testnet_preparation_ready_reason": "operator_unlock_request_template_only_and_approval_intake_not_validated",
        "recommended_next_action": "human_operator_may_copy_template_after_manual_approval_and_hard_cap_recheck" if not blocked else "repair_phase6_template_sources_before_operator_handoff",
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
    report["phase6_1_report_sha256"] = sha256_json(report)
    return report


def persist_phase6_1_signed_testnet_operator_unlock_request_template_report(
    *,
    cfg: AppConfig | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config(project_root)
    latest = _latest_dir(cfg)
    phase_dir = _storage_dir(cfg, "storage/phase6_1_signed_testnet_operator_unlock_request_template")
    signed_testnet_dir = _storage_dir(cfg, "storage/signed_testnet")
    report = build_phase6_1_signed_testnet_operator_unlock_request_template_report(cfg=cfg)

    phase6 = _read_latest_json(cfg, "phase6_signed_testnet_preparation_preview_report.json")
    pre_submit = _read_latest_json(cfg, "signed_testnet_pre_submit_validation_report.json")
    probe = _read_latest_json(cfg, "real_read_only_venue_probe.json")
    enablement = _read_latest_json(cfg, "signed_testnet_execution_enablement_packet.json")
    template = _build_unlock_request_template(phase6=phase6, pre_submit=pre_submit, probe=probe, enablement=enablement, created=str(report["created_at_utc"])) if not report.get("blocked") else {}

    atomic_write_json(latest / "phase6_1_signed_testnet_operator_unlock_request_template_report.json", report)
    atomic_write_json(phase_dir / "phase6_1_signed_testnet_operator_unlock_request_template_report.json", report)
    if template:
        atomic_write_json(latest / "operator_unlock_request_template_review_only.json", template)
        atomic_write_json(phase_dir / "operator_unlock_request_template_review_only.json", template)
        atomic_write_json(signed_testnet_dir / "operator_unlock_request_TEMPLATE_REVIEW_ONLY.json", template)
        handoff_md = _build_handoff_markdown(template, report)
        (latest / "OPERATOR_UNLOCK_REQUEST_HANDOFF_REVIEW_ONLY.md").write_text(handoff_md, encoding="utf-8")
        (phase_dir / "OPERATOR_UNLOCK_REQUEST_HANDOFF_REVIEW_ONLY.md").write_text(handoff_md, encoding="utf-8")

    registry_record = append_registry_record(
        registry_path(cfg, PHASE6_1_REGISTRY_NAME),
        {
            "phase6_1_signed_testnet_operator_unlock_request_template_id": report.get("phase6_1_signed_testnet_operator_unlock_request_template_id"),
            "status": report.get("status"),
            "blocked": report.get("blocked"),
            "fail_closed": report.get("fail_closed"),
            "operator_unlock_request_template_created": report.get("operator_unlock_request_template_created"),
            "operator_unlock_request_created": False,
            "actual_operator_unlock_request_path_created": False,
            "approval_intake_validated": False,
            "signed_testnet_preparation_ready": False,
            "ready_for_signed_testnet_execution": False,
            "testnet_order_submission_allowed": False,
            "external_order_submission_performed": False,
            "place_order_enabled": False,
            "cancel_order_enabled": False,
            "signed_order_executor_enabled": False,
            "api_key_value_access_allowed": False,
            "secret_file_access_allowed": False,
            "runtime_settings_mutated": False,
            "score_weights_mutated": False,
            "auto_promotion_allowed": False,
            "created_at_utc": report.get("created_at_utc"),
        },
        registry_name=PHASE6_1_REGISTRY_NAME,
        id_field="phase6_1_signed_testnet_operator_unlock_request_template_registry_record_id",
        hash_field="phase6_1_signed_testnet_operator_unlock_request_template_registry_record_sha256",
        id_prefix="phase6_1_signed_testnet_operator_unlock_request_template_registry_record",
    )
    atomic_write_json(latest / "phase6_1_signed_testnet_operator_unlock_request_template_registry_record.json", registry_record)
    atomic_write_json(phase_dir / "phase6_1_signed_testnet_operator_unlock_request_template_registry_record.json", registry_record)
    return report


__all__ = [
    "PHASE6_1_VERSION",
    "STATUS_RECORDED_REVIEW_ONLY",
    "STATUS_BLOCKED_REVIEW_ONLY",
    "build_phase6_1_signed_testnet_operator_unlock_request_template_report",
    "persist_phase6_1_signed_testnet_operator_unlock_request_template_report",
]
