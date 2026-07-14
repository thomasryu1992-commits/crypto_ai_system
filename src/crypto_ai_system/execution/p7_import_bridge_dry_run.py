from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.external_evidence_import_validator import (
    build_p7_input_preview_from_bundle,
    validate_redacted_submit_response_bundle_for_import,
)
from crypto_ai_system.execution.post_submit_evidence_intake import build_post_submit_evidence_intake_report
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P51_P7_IMPORT_BRIDGE_DRY_RUN_VERSION = "p51_p7_import_bridge_dry_run_v1"
P51_P7_IMPORT_BRIDGE_DRY_RUN_REGISTRY_NAME = "p51_p7_import_bridge_dry_run_registry"
STATUS_READY_REVIEW_ONLY_NO_SUBMIT = "P51_P7_IMPORT_BRIDGE_DRY_RUN_READY_REVIEW_ONLY_NO_SUBMIT"
STATUS_DRY_RUN_ACCEPTED_REVIEW_ONLY_NO_SUBMIT = "P51_P7_IMPORT_BRIDGE_DRY_RUN_ACCEPTED_REVIEW_ONLY_NO_SUBMIT"
STATUS_DRY_RUN_REJECTED_REVIEW_ONLY_NO_SUBMIT = "P51_P7_IMPORT_BRIDGE_DRY_RUN_REJECTED_REVIEW_ONLY_NO_SUBMIT"
STATUS_BLOCKED_FAIL_CLOSED = "P51_P7_IMPORT_BRIDGE_DRY_RUN_BLOCKED_FAIL_CLOSED"

_EXPECTED_P50_STATUS = "P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_READY_REVIEW_ONLY_NO_SUBMIT"
_EXPECTED_P7_ACCEPT_STATUS = "P7_POST_SUBMIT_EVIDENCE_INTAKE_RECONCILED_SESSION_CLOSED_REVIEW_ONLY"
_SHA_PLACEHOLDER = "0" * 64
_FORBIDDEN_SCOPE_TOKENS = ("mainnet", "live", "withdraw", "transfer", "admin", "raw_secret", "secret_dump")


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


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _execution_false_payload() -> dict[str, bool]:
    payload = default_execution_flag_state()
    payload.update(
        {
            "actual_order_submission_performed": False,
            "actual_testnet_order_submitted": False,
            "actual_live_order_submitted": False,
            "external_order_submission_performed": False,
            "order_endpoint_called": False,
            "order_status_endpoint_called": False,
            "cancel_endpoint_called": False,
            "cancel_request_sent": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "api_key_value_logged": False,
            "api_secret_value_logged": False,
            "private_key_logged": False,
            "passphrase_logged": False,
            "runtime_scheduler_enabled": False,
            "runtime_loop_started": False,
            "runtime_authority_granted": False,
            "runtime_mutation_performed": False,
            "p7_valid_status_written_by_p51": False,
            "p7_report_persisted_by_p51": False,
            "p7_intake_execution_performed_by_p51": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        }
    )
    return payload


@dataclass(frozen=True)
class P7ImportBridgeDryRunTemplate:
    bridge_dry_run_template_id: str = "p51_p7_import_bridge_dry_run_TEMPLATE_NO_SUBMIT"
    bridge_dry_run_version: str = P51_P7_IMPORT_BRIDGE_DRY_RUN_VERSION
    generated_by_review_package: bool = True
    review_only: bool = True
    dry_run_only: bool = True
    external_runtime_evidence_only: bool = True
    p50_validated_import_required: bool = True
    p7_input_preview_required: bool = True
    p7_dry_run_may_call_validator_function: bool = True
    p7_report_persistence_allowed: bool = False
    p7_status_mutation_allowed: bool = False
    p7_valid_status_written_by_p51: bool = False
    can_grant_runtime_authority: bool = False
    can_enable_testnet_submit: bool = False
    can_enable_live_canary: bool = False
    can_enable_live_scaled: bool = False
    order_endpoint_call_allowed_by_p51: bool = False
    status_endpoint_call_allowed_by_p51: bool = False
    cancel_endpoint_call_allowed_by_p51: bool = False
    http_request_allowed_by_p51: bool = False
    signature_creation_allowed_by_p51: bool = False
    secret_access_allowed_by_p51: bool = False
    required_candidate_sections: tuple[str, ...] = (
        "p7_input_preview",
        "status_polling_events",
        "cancel_boundary_evidence",
        "signed_testnet_reconciliation_evidence",
        "signed_testnet_session_close_evidence",
    )
    required_id_chain_fields: tuple[str, ...] = (
        "source_p6_submit_runtime_action_sha256",
        "exchange_order_id",
        "client_order_id",
        "idempotency_key",
        "execution_id",
        "order_intent_id",
        "risk_gate_id",
        "hot_path_preorder_risk_gate_id",
        "secret_reference_id",
        "key_fingerprint_sha256",
        "no_secret_logged_evidence_hash",
    )
    p51_output_must_remain_no_submit: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p51_bridge_dry_run_template_sha256"] = sha256_json(payload)
        return payload


def validate_p50_import_validator_source(p50_report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(p50_report or {})
    blockers: list[str] = []
    if payload.get("artifact_type") != "p50_external_evidence_import_validator_report":
        blockers.append("P51_P50_SOURCE_ARTIFACT_TYPE_INVALID")
    if payload.get("status") != _EXPECTED_P50_STATUS:
        blockers.append("P51_P50_SOURCE_STATUS_NOT_READY_REVIEW_ONLY_NO_SUBMIT")
    for key in (
        "review_only",
        "external_runtime_only",
        "review_package_default_no_submit",
        "p7_input_preview_only",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P51_P50_SOURCE_{key.upper()}_NOT_TRUE")
    for key in (
        "runtime_authority_source",
        "p7_intake_execution_performed",
        "p7_valid_status_written_by_p50",
        "actual_order_submission_performed",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "secret_value_accessed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P51_P50_SOURCE_{key.upper()}_NOT_FALSE")
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P51_P50_SOURCE_UNSAFE_TRUTHY_EXECUTION_FLAGS")
    p50_candidate_ready = False
    if payload.get("candidate_import_payload_supplied") is True:
        bundle_validation = dict(payload.get("candidate_bundle_validation") or {})
        transcript_validation = dict(payload.get("candidate_transcript_validation") or {})
        log_validation = dict(payload.get("candidate_no_secret_log_scan_validation") or {})
        if bundle_validation.get("redacted_submit_response_bundle_import_valid") is not True:
            blockers.append("P51_P50_CANDIDATE_BUNDLE_NOT_VALIDATED")
        if transcript_validation.get("execution_transcript_import_valid") is not True:
            blockers.append("P51_P50_CANDIDATE_TRANSCRIPT_NOT_VALIDATED")
        if log_validation.get("no_secret_log_scan_report_valid") is not True:
            blockers.append("P51_P50_CANDIDATE_LOG_SCAN_NOT_VALIDATED")
        p50_candidate_ready = not blockers
    validation = {
        "p50_import_validator_source_valid": not blockers,
        "p50_import_validator_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "source_status": payload.get("status"),
        "source_sha256": payload.get("p50_external_evidence_import_validator_sha256"),
        "candidate_import_payload_supplied": payload.get("candidate_import_payload_supplied") is True,
        "p50_candidate_ready_for_p7_dry_run": p50_candidate_ready,
    }
    validation["p50_import_validator_source_validation_sha256"] = sha256_json(validation)
    return validation


def validate_bridge_dry_run_template(template: Mapping[str, Any] | P7ImportBridgeDryRunTemplate | None) -> dict[str, Any]:
    payload = template.to_dict() if isinstance(template, P7ImportBridgeDryRunTemplate) else dict(template or {})
    blockers: list[str] = []
    if payload.get("bridge_dry_run_version") != P51_P7_IMPORT_BRIDGE_DRY_RUN_VERSION:
        blockers.append("P51_TEMPLATE_VERSION_MISMATCH")
    for key in (
        "generated_by_review_package",
        "review_only",
        "dry_run_only",
        "external_runtime_evidence_only",
        "p50_validated_import_required",
        "p7_input_preview_required",
        "p7_dry_run_may_call_validator_function",
        "p51_output_must_remain_no_submit",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P51_TEMPLATE_{key.upper()}_NOT_TRUE")
    for key in (
        "p7_report_persistence_allowed",
        "p7_status_mutation_allowed",
        "p7_valid_status_written_by_p51",
        "can_grant_runtime_authority",
        "can_enable_testnet_submit",
        "can_enable_live_canary",
        "can_enable_live_scaled",
        "order_endpoint_call_allowed_by_p51",
        "status_endpoint_call_allowed_by_p51",
        "cancel_endpoint_call_allowed_by_p51",
        "http_request_allowed_by_p51",
        "signature_creation_allowed_by_p51",
        "secret_access_allowed_by_p51",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P51_TEMPLATE_{key.upper()}_NOT_FALSE")
    required_sections = set(payload.get("required_candidate_sections") or ())
    if required_sections < {
        "p7_input_preview",
        "status_polling_events",
        "cancel_boundary_evidence",
        "signed_testnet_reconciliation_evidence",
        "signed_testnet_session_close_evidence",
    }:
        blockers.append("P51_TEMPLATE_REQUIRED_CANDIDATE_SECTIONS_INCOMPLETE")
    validation = {
        "bridge_dry_run_template_valid": not blockers,
        "bridge_dry_run_template_block_reasons": sorted(dict.fromkeys(blockers)),
        "bridge_dry_run_template_id": payload.get("bridge_dry_run_template_id"),
    }
    validation["bridge_dry_run_template_validation_sha256"] = sha256_json(validation)
    return validation


def _candidate_forbidden_tokens(candidate: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    text = sha256_json(candidate)  # deterministic serialization hash is safe, but not content-bearing.
    # Check top-level keys and explicitly textual top-level values only; nested validation is delegated to P7.
    for key, value in candidate.items():
        key_l = str(key).lower()
        if any(token in key_l for token in ("secret_value", "api_key", "api_secret", "private_key", "passphrase", "raw_signed_payload", "raw_request_body")):
            blockers.append(f"P51_CANDIDATE_FORBIDDEN_TOP_LEVEL_KEY:{key}")
        if isinstance(value, str):
            value_l = value.lower()
            if any(token in value_l for token in _FORBIDDEN_SCOPE_TOKENS):
                blockers.append(f"P51_CANDIDATE_FORBIDDEN_SCOPE_TOKEN:{key}")
    _ = text
    return blockers


def validate_p7_bridge_candidate(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(candidate or {})
    blockers: list[str] = []
    if not payload:
        return {
            "p7_bridge_candidate_present": False,
            "p7_bridge_candidate_valid_for_dry_run": False,
            "p7_bridge_candidate_block_reasons": [],
            "candidate_sha256": None,
            "p7_input_preview_present": False,
        }
    for key in (
        "runtime_authority_granted",
        "p7_valid_status_written_by_p51",
        "p7_report_persisted_by_p51",
        "order_endpoint_called_by_p51",
        "http_request_sent_by_p51",
        "signature_created_by_p51",
        "secret_value_accessed_by_p51",
    ):
        if payload.get(key) is True:
            blockers.append(f"P51_CANDIDATE_{key.upper()}_NOT_ALLOWED")
    required_sections = (
        "p7_input_preview",
        "status_polling_events",
        "cancel_boundary_evidence",
        "signed_testnet_reconciliation_evidence",
        "signed_testnet_session_close_evidence",
    )
    for key in required_sections:
        if key not in payload:
            blockers.append(f"P51_CANDIDATE_REQUIRED_SECTION_MISSING:{key}")
    preview = dict(payload.get("p7_input_preview") or {})
    for key in P7ImportBridgeDryRunTemplate().required_id_chain_fields:
        if not _nonempty(preview.get(key)):
            blockers.append(f"P51_CANDIDATE_PREVIEW_REQUIRED_ID_FIELD_MISSING:{key}")
    for key in (
        "source_p6_submit_runtime_action_sha256",
        "request_hash",
        "exchange_response_hash",
        "hot_path_preorder_risk_gate_hash",
        "key_fingerprint_sha256",
        "no_secret_logged_evidence_hash",
    ):
        if _nonempty(preview.get(key)) and not _is_sha256_hex(preview.get(key)):
            blockers.append(f"P51_CANDIDATE_PREVIEW_{key.upper()}_NOT_SHA256_HEX")
    if str(preview.get("artifact_type") or "") not in {"p50_p7_input_preview_NO_SUBMIT", "p51_p7_input_preview_candidate"}:
        blockers.append("P51_CANDIDATE_PREVIEW_ARTIFACT_TYPE_INVALID")
    for key in (
        "p7_intake_execution_performed",
        "p7_valid_status_written_by_p50",
        "order_endpoint_called_by_p50",
        "http_request_sent_by_p50",
        "signature_created_by_p50",
        "secret_value_accessed_by_p50",
    ):
        if preview.get(key) is True:
            blockers.append(f"P51_CANDIDATE_PREVIEW_{key.upper()}_NOT_ALLOWED")
    blockers.extend(_candidate_forbidden_tokens(payload))
    validation = {
        "p7_bridge_candidate_present": True,
        "p7_bridge_candidate_valid_for_dry_run": not blockers,
        "p7_bridge_candidate_block_reasons": sorted(dict.fromkeys(blockers)),
        "candidate_sha256": sha256_json(payload),
        "p7_input_preview_present": bool(preview),
        "status_polling_event_count": len(list(payload.get("status_polling_events") or [])),
    }
    validation["p7_bridge_candidate_validation_sha256"] = sha256_json(validation)
    return validation


def _p6_submitted_shell_from_preview(preview: Mapping[str, Any]) -> dict[str, Any]:
    p6_hash = str(preview.get("source_p6_submit_runtime_action_sha256") or _SHA_PLACEHOLDER)
    return {
        "status": "P6_SINGLE_SIGNED_TESTNET_SUBMIT_RUNTIME_ACTION_SUBMITTED_BY_EXTERNAL_RUNTIME_REDACTED_EVIDENCE",
        "p6_single_signed_testnet_submit_runtime_action_id": "p51_p7_import_bridge_dry_run_external_runtime_shell",
        "p6_single_signed_testnet_submit_runtime_action_sha256": p6_hash,
        "p51_dry_run_shell_only": True,
        "actual_order_submission_performed": True,
        "actual_testnet_order_submitted": True,
        "external_order_submission_performed": True,
        "order_endpoint_called": True,
        "http_request_sent": True,
        "signature_created": True,
        "signed_request_created": True,
        "real_exchange_order_id_present": True,
        "secret_value_accessed": False,
        "secret_value_logged": False,
        "testnet_order_submission_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
    }


def _order_intake_from_preview(preview: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_p6_submit_runtime_action_sha256": preview.get("source_p6_submit_runtime_action_sha256"),
        "exchange": "binance_futures_testnet",
        "environment": "testnet",
        "symbol": "BTCUSDT",
        "order_count": 1,
        "exchange_order_id": preview.get("exchange_order_id"),
        "client_order_id": preview.get("client_order_id"),
        "idempotency_key": preview.get("idempotency_key"),
        "execution_id": preview.get("execution_id"),
        "order_intent_id": preview.get("order_intent_id"),
        "risk_gate_id": preview.get("risk_gate_id"),
        "request_hash": preview.get("request_hash"),
        "exchange_response_hash": preview.get("exchange_response_hash"),
        "raw_exchange_response_redacted_path": preview.get("raw_exchange_response_redacted_path"),
        "hot_path_preorder_risk_gate_id": preview.get("hot_path_preorder_risk_gate_id"),
        "hot_path_preorder_risk_gate_hash": preview.get("hot_path_preorder_risk_gate_hash"),
        "secret_reference_id": preview.get("secret_reference_id"),
        "key_fingerprint_sha256": preview.get("key_fingerprint_sha256"),
        "no_secret_logged_evidence_hash": preview.get("no_secret_logged_evidence_hash"),
        "evidence_origin": "real_signed_testnet_external_runtime",
        "mock_or_fixture_evidence": False,
        "synthetic_or_sample_evidence": False,
        "order_endpoint_called": True,
        "http_request_sent": True,
        "signature_created": True,
        "signed_request_created": True,
        "real_exchange_response": True,
        "secret_value_included": False,
        "api_key_value_included": False,
        "api_secret_value_included": False,
        "private_key_included": False,
        "passphrase_included": False,
        "mainnet_key_scope_allowed": False,
        "withdrawal_permission_allowed": False,
        "transfer_permission_allowed": False,
        "admin_permission_allowed": False,
    }


def build_p7_bridge_dry_run_result(candidate: Mapping[str, Any], *, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    preview = dict(candidate.get("p7_input_preview") or {})
    p7_report = build_post_submit_evidence_intake_report(
        cfg=cfg,
        p6_report=_p6_submitted_shell_from_preview(preview),
        order_id_intake=_order_intake_from_preview(preview),
        status_polling_events=list(candidate.get("status_polling_events") or []),
        cancel_boundary=dict(candidate.get("cancel_boundary_evidence") or {}),
        reconciliation_evidence=dict(candidate.get("signed_testnet_reconciliation_evidence") or {}),
        session_close_evidence=dict(candidate.get("signed_testnet_session_close_evidence") or {}),
    )
    p7_would_accept = bool(
        p7_report.get("status") == _EXPECTED_P7_ACCEPT_STATUS
        and p7_report.get("post_submit_chain_complete") is True
        and p7_report.get("signed_testnet_promotion_allowed") is False
        and p7_report.get("live_canary_execution_enabled") is False
        and p7_report.get("live_scaled_execution_enabled") is False
    )
    validation = {
        "p7_bridge_dry_run_performed": True,
        "p7_report_persisted_by_p51": False,
        "p7_valid_status_written_by_p51": False,
        "p7_would_accept_imported_evidence": p7_would_accept,
        "p7_would_reject_imported_evidence": not p7_would_accept,
        "p7_dry_run_status": p7_report.get("status"),
        "p7_dry_run_block_reasons": list(p7_report.get("block_reasons") or []),
        "p7_post_submit_chain_complete": p7_report.get("post_submit_chain_complete") is True,
        "p7_terminal_status_observed": p7_report.get("terminal_status_observed") is True,
        "p7_signed_testnet_promotion_allowed": p7_report.get("signed_testnet_promotion_allowed") is True,
        "p7_live_canary_execution_enabled": p7_report.get("live_canary_execution_enabled") is True,
        "p7_live_scaled_execution_enabled": p7_report.get("live_scaled_execution_enabled") is True,
        "p7_dry_run_report_sha256": sha256_json(p7_report),
        "p7_dry_run_report_inline": p7_report,
    }
    validation["p7_bridge_dry_run_result_sha256"] = sha256_json({k: v for k, v in validation.items() if k != "p7_dry_run_report_inline"})
    return validation


def build_p51_p7_import_bridge_dry_run_report(
    *,
    cfg: AppConfig | None = None,
    p50_report: Mapping[str, Any] | None = None,
    bridge_template: Mapping[str, Any] | P7ImportBridgeDryRunTemplate | None = None,
    candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    source_p50 = dict(p50_report or _read_latest_json(cfg, "p50_external_evidence_import_validator_report.json"))
    template_payload = bridge_template.to_dict() if isinstance(bridge_template, P7ImportBridgeDryRunTemplate) else dict(bridge_template or P7ImportBridgeDryRunTemplate().to_dict())
    p50_validation = validate_p50_import_validator_source(source_p50)
    template_validation = validate_bridge_dry_run_template(template_payload)
    candidate_validation = validate_p7_bridge_candidate(candidate)
    dry_run_result = None
    blockers = sorted(
        dict.fromkeys(
            list(p50_validation["p50_import_validator_source_block_reasons"])
            + list(template_validation["bridge_dry_run_template_block_reasons"])
            + (list(candidate_validation["p7_bridge_candidate_block_reasons"]) if candidate_validation["p7_bridge_candidate_present"] else [])
        )
    )
    if candidate_validation["p7_bridge_candidate_present"] and not blockers:
        dry_run_result = build_p7_bridge_dry_run_result(dict(candidate or {}), cfg=cfg)
        if dry_run_result.get("p7_signed_testnet_promotion_allowed") is True:
            blockers.append("P51_P7_DRY_RUN_SIGNED_TESTNET_PROMOTION_ALLOWED")
        if dry_run_result.get("p7_live_canary_execution_enabled") is True:
            blockers.append("P51_P7_DRY_RUN_LIVE_CANARY_EXECUTION_ENABLED")
        if dry_run_result.get("p7_live_scaled_execution_enabled") is True:
            blockers.append("P51_P7_DRY_RUN_LIVE_SCALED_EXECUTION_ENABLED")
    if blockers:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif dry_run_result and dry_run_result.get("p7_would_accept_imported_evidence") is True:
        status = STATUS_DRY_RUN_ACCEPTED_REVIEW_ONLY_NO_SUBMIT
    elif dry_run_result:
        status = STATUS_DRY_RUN_REJECTED_REVIEW_ONLY_NO_SUBMIT
    else:
        status = STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    report = {
        "artifact_type": "p51_p7_import_bridge_dry_run_report",
        "p51_p7_import_bridge_dry_run_version": P51_P7_IMPORT_BRIDGE_DRY_RUN_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
        "review_only": True,
        "dry_run_only": True,
        "external_runtime_only": True,
        "runtime_authority_source": False,
        "review_package_default_no_submit": True,
        "source_p50_import_validator_validation": p50_validation,
        "bridge_dry_run_template": template_payload,
        "bridge_dry_run_template_validation": template_validation,
        "candidate_supplied": candidate_validation["p7_bridge_candidate_present"],
        "candidate_validation": candidate_validation,
        "p7_bridge_dry_run_result": dry_run_result,
        "p7_bridge_dry_run_performed": bool(dry_run_result),
        "p7_would_accept_imported_evidence": bool(dry_run_result and dry_run_result.get("p7_would_accept_imported_evidence") is True),
        "p7_would_reject_imported_evidence": bool(dry_run_result and dry_run_result.get("p7_would_reject_imported_evidence") is True),
        "p7_report_persisted_by_p51": False,
        "p7_valid_status_written_by_p51": False,
        "p7_intake_execution_performed_by_p51": False,
        "p7_status_mutation_performed": False,
        "actual_endpoint_call_still_requires_separate_operator_local_runtime": True,
        "next_required_chain": [
            "operator supplies a P50-validated candidate with full P7 status/cancel/reconciliation/session-close evidence",
            "P51 dry-runs P7 acceptance without persisting P7 status",
            "operator reviews dry-run result and blockers",
            "only a separate P7 import action may persist real post-submit evidence after explicit operator control",
            "P8 repeated clean session validator remains waiting until multiple real P7 evidence records exist",
        ],
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "created_at_utc": utc_now_canonical(),
        **_execution_false_payload(),
    }
    unsafe = truthy_execution_flags(report)
    report["unsafe_truthy_execution_flags"] = unsafe
    if unsafe:
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["blocked"] = True
        report["fail_closed"] = True
        report["block_reasons"] = sorted(dict.fromkeys(report["block_reasons"] + ["P51_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
    report["p51_p7_import_bridge_dry_run_id"] = stable_id("p51_p7_import_bridge_dry_run", report, 24)
    report["p51_p7_import_bridge_dry_run_sha256"] = sha256_json(report)
    return report


def _valid_candidate_fixture() -> dict[str, Any]:
    good_sha = "a" * 64
    exchange_order_id = "testnet_order_12345"
    client_order_id = "client_order_12345"
    idempotency_key = "idem_12345"
    preview = {
        "artifact_type": "p51_p7_input_preview_candidate",
        "review_only": True,
        "p7_input_preview_only": True,
        "p7_intake_execution_performed": False,
        "p7_valid_status_written_by_p50": False,
        "source_p6_submit_runtime_action_sha256": good_sha,
        "exchange_order_id": exchange_order_id,
        "client_order_id": client_order_id,
        "idempotency_key": idempotency_key,
        "execution_id": "execution_12345",
        "order_intent_id": "order_intent_12345",
        "risk_gate_id": "risk_gate_12345",
        "request_hash": good_sha,
        "exchange_response_hash": good_sha,
        "raw_exchange_response_redacted_path": "EXTERNAL_RUNTIME_OUTPUT/redacted_submit_response_bundle.json",
        "hot_path_preorder_risk_gate_id": "risk_gate_12345",
        "hot_path_preorder_risk_gate_hash": good_sha,
        "secret_reference_id": "metadata_only_testnet_key_ref",
        "key_fingerprint_sha256": good_sha,
        "no_secret_logged_evidence_hash": good_sha,
        "order_endpoint_called_by_p50": False,
        "http_request_sent_by_p50": False,
        "signature_created_by_p50": False,
        "secret_value_accessed_by_p50": False,
    }
    status_event = {
        "event_id": "status_poll_event_12345",
        "endpoint_type": "signed_testnet_private_order_status",
        "method": "GET",
        "exchange_order_id": exchange_order_id,
        "client_order_id": client_order_id,
        "exchange_order_status": "FILLED",
        "request_hash": good_sha,
        "response_hash": good_sha,
        "timestamp_utc": utc_now_canonical(),
        "retry_count": 0,
        "api_latency_ms": 120,
        "rate_limit_status": "ok",
        "order_status_endpoint_called": True,
        "http_request_sent": True,
        "signature_created": True,
        "signed_request_created": True,
        "real_exchange_response": True,
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
    }
    cancel = {
        "cancel_boundary_decision_recorded": True,
        "exchange_order_id": exchange_order_id,
        "final_status_before_cancel_decision": "FILLED",
        "cancel_required": False,
        "cancel_requested": False,
        "cancel_endpoint_called": False,
        "cancel_request_sent": False,
        "cancel_response_hash": None,
        "duplicate_cancel_prevented": True,
        "cancel_final_status": None,
        "cancel_block_reason": "not_required_terminal_status",
        "secret_value_logged": False,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
    }
    recon = {
        "reconciliation_id": "reconciliation_12345",
        "exchange_order_id": exchange_order_id,
        "client_order_id": client_order_id,
        "idempotency_key": idempotency_key,
        "execution_id": "execution_12345",
        "order_intent_id": "order_intent_12345",
        "risk_gate_id": "risk_gate_12345",
        "final_exchange_order_status": "FILLED",
        "exchange_response_hash_match": True,
        "status_polling_hash_chain_match": True,
        "order_intent_match": True,
        "idempotency_key_match": True,
        "fee_reconciled": True,
        "fill_quantity_reconciled": True,
        "position_delta_reconciled": True,
        "slippage_recorded": True,
        "reconciliation_mismatch_count": 0,
        "api_error_count": 0,
        "secret_value_logged": False,
        "live_position_sync_enabled_by_this_module": False,
        "live_trading_allowed_by_this_module": False,
    }
    close = {
        "session_close_id": "session_close_12345",
        "exchange_order_id": exchange_order_id,
        "reconciliation_id": "reconciliation_12345",
        "final_exchange_order_status": "FILLED",
        "session_closed": True,
        "session_close_status": "CLOSED_CLEAN_REVIEW_ONLY",
        "reconciliation_clean": True,
        "no_open_testnet_order_remaining": True,
        "no_duplicate_submit_detected": True,
        "post_submit_relock_confirmed": True,
        "place_order_enabled_after_close": False,
        "cancel_order_enabled_after_close": False,
        "signed_order_executor_enabled_after_close": False,
        "testnet_order_submission_allowed_after_close": False,
        "signed_testnet_promotion_allowed": False,
        "live_canary_preparation_allowed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
    }
    return {
        "p7_input_preview": preview,
        "status_polling_events": [status_event],
        "cancel_boundary_evidence": cancel,
        "signed_testnet_reconciliation_evidence": recon,
        "signed_testnet_session_close_evidence": close,
    }


def _valid_p50_source_fixture() -> dict[str, Any]:
    payload = {
        "artifact_type": "p50_external_evidence_import_validator_report",
        "status": _EXPECTED_P50_STATUS,
        "review_only": True,
        "external_runtime_only": True,
        "review_package_default_no_submit": True,
        "p7_input_preview_only": True,
        "runtime_authority_source": False,
        "p7_intake_execution_performed": False,
        "p7_valid_status_written_by_p50": False,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
        "candidate_import_payload_supplied": True,
        "candidate_bundle_validation": {
            "redacted_submit_response_bundle_import_valid": True,
        },
        "candidate_transcript_validation": {
            "execution_transcript_import_valid": True,
        },
        "candidate_no_secret_log_scan_validation": {
            "no_secret_log_scan_report_valid": True,
        },
    }
    payload["p50_external_evidence_import_validator_sha256"] = sha256_json(payload)
    return payload


def build_p51_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    valid = _valid_candidate_fixture()
    source = _valid_p50_source_fixture()
    cases: dict[str, Mapping[str, Any] | None] = {
        "missing_status_polling_events": {k: v for k, v in valid.items() if k != "status_polling_events"},
        "mock_exchange_order_id": {
            **valid,
            "p7_input_preview": {**valid["p7_input_preview"], "exchange_order_id": "mock_order_123"},
        },
        "p6_hash_not_sha256": {
            **valid,
            "p7_input_preview": {**valid["p7_input_preview"], "source_p6_submit_runtime_action_sha256": "not-a-sha"},
        },
        "candidate_attempts_p7_status_write": {**valid, "p7_valid_status_written_by_p51": True},
        "candidate_runtime_authority": {**valid, "runtime_authority_granted": True},
        "missing_order_intent_id": {
            **valid,
            "p7_input_preview": {**valid["p7_input_preview"], "order_intent_id": ""},
        },
    }
    results: dict[str, Any] = {}
    for name, candidate in cases.items():
        report = build_p51_p7_import_bridge_dry_run_report(cfg=cfg, p50_report=source, candidate=candidate)
        blocked_or_rejected = bool(report["blocked"] is True or report["p7_would_reject_imported_evidence"] is True)
        results[name] = {
            "fixture_name": name,
            "blocked_or_rejected_fail_closed": blocked_or_rejected,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "p7_dry_run_block_reasons": (report.get("p7_bridge_dry_run_result") or {}).get("p7_dry_run_block_reasons"),
            "p7_would_accept_imported_evidence": report["p7_would_accept_imported_evidence"],
            "p7_report_persisted_by_p51": report["p7_report_persisted_by_p51"],
            "p7_valid_status_written_by_p51": report["p7_valid_status_written_by_p51"],
        }
    accepted = build_p51_p7_import_bridge_dry_run_report(cfg=cfg, p50_report=source, candidate=valid)
    payload = {
        "artifact_type": "p51_p7_import_bridge_dry_run_negative_fixture_results",
        "all_negative_fixtures_blocked_or_rejected_fail_closed": all(item["blocked_or_rejected_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "valid_candidate_fixture_would_accept_p7": accepted["p7_would_accept_imported_evidence"] is True,
        "valid_candidate_fixture_status": accepted["status"],
        "p7_report_persisted_by_p51": False,
        "p7_valid_status_written_by_p51": False,
        **_execution_false_payload(),
    }
    payload["p51_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_p51_p7_import_bridge_dry_run(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p51_p7_import_bridge_dry_run")
    report = build_p51_p7_import_bridge_dry_run_report(cfg=cfg)
    negative = build_p51_negative_fixture_results(cfg=cfg)
    template = report["bridge_dry_run_template"]
    registry_record = append_registry_record(
        registry_path(cfg, P51_P7_IMPORT_BRIDGE_DRY_RUN_REGISTRY_NAME),
        {
            "artifact_type": "p51_p7_import_bridge_dry_run_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "p51_p7_import_bridge_dry_run_id": report["p51_p7_import_bridge_dry_run_id"],
            "p51_p7_import_bridge_dry_run_sha256": report["p51_p7_import_bridge_dry_run_sha256"],
            "source_p50_import_validator_sha256": report["source_p50_import_validator_validation"].get("source_sha256"),
            "candidate_supplied": report["candidate_supplied"],
            "p7_bridge_dry_run_performed": report["p7_bridge_dry_run_performed"],
            "p7_would_accept_imported_evidence": report["p7_would_accept_imported_evidence"],
            "p7_report_persisted_by_p51": report["p7_report_persisted_by_p51"],
            "p7_valid_status_written_by_p51": report["p7_valid_status_written_by_p51"],
            "actual_order_submission_performed": report["actual_order_submission_performed"],
            "order_endpoint_called": report["order_endpoint_called"],
            "http_request_sent": report["http_request_sent"],
            "signature_created": report["signature_created"],
            "secret_value_accessed": report["secret_value_accessed"],
        },
        registry_name=P51_P7_IMPORT_BRIDGE_DRY_RUN_REGISTRY_NAME,
        id_field="p51_p7_import_bridge_dry_run_registry_record_id",
        hash_field="p51_p7_import_bridge_dry_run_registry_record_sha256",
        id_prefix="p51_p7_import_bridge_dry_run_registry_record",
    )
    report["p51_p7_import_bridge_dry_run_registry_record_id"] = registry_record["p51_p7_import_bridge_dry_run_registry_record_id"]
    report["p51_p7_import_bridge_dry_run_registry_record_sha256"] = registry_record["p51_p7_import_bridge_dry_run_registry_record_sha256"]
    report["p51_p7_import_bridge_dry_run_sha256"] = sha256_json(report)
    summary = {
        "artifact_type": "p51_p7_import_bridge_dry_run_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": report["review_only"],
        "dry_run_only": report["dry_run_only"],
        "candidate_supplied": report["candidate_supplied"],
        "p7_bridge_dry_run_performed": report["p7_bridge_dry_run_performed"],
        "p7_would_accept_imported_evidence": report["p7_would_accept_imported_evidence"],
        "p7_report_persisted_by_p51": report["p7_report_persisted_by_p51"],
        "p7_valid_status_written_by_p51": report["p7_valid_status_written_by_p51"],
        "actual_order_submission_performed": report["actual_order_submission_performed"],
        "order_endpoint_called": report["order_endpoint_called"],
        "http_request_sent": report["http_request_sent"],
        "signature_created": report["signature_created"],
        "secret_value_accessed": report["secret_value_accessed"],
        "negative_fixtures_all_blocked_or_rejected": negative["all_negative_fixtures_blocked_or_rejected_fail_closed"],
        "valid_candidate_fixture_would_accept_p7": negative["valid_candidate_fixture_would_accept_p7"],
        "p51_p7_import_bridge_dry_run_id": report["p51_p7_import_bridge_dry_run_id"],
        "p51_p7_import_bridge_dry_run_sha256": report["p51_p7_import_bridge_dry_run_sha256"],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p51_summary_sha256"] = sha256_json(summary)
    writes = {
        "p51_p7_import_bridge_dry_run_report.json": report,
        "p51_p7_import_bridge_dry_run_TEMPLATE_NO_SUBMIT.json": template,
        "p51_p7_import_bridge_dry_run_negative_fixture_results.json": negative,
        "p51_p7_import_bridge_dry_run_registry_record.json": registry_record,
        "p51_p7_import_bridge_dry_run_summary.json": summary,
    }
    for filename, payload in writes.items():
        atomic_write_json(latest / filename, payload)
        atomic_write_json(storage / filename, payload)
    return report


__all__ = [
    "P51_P7_IMPORT_BRIDGE_DRY_RUN_VERSION",
    "STATUS_READY_REVIEW_ONLY_NO_SUBMIT",
    "STATUS_DRY_RUN_ACCEPTED_REVIEW_ONLY_NO_SUBMIT",
    "STATUS_DRY_RUN_REJECTED_REVIEW_ONLY_NO_SUBMIT",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "P7ImportBridgeDryRunTemplate",
    "validate_p50_import_validator_source",
    "validate_bridge_dry_run_template",
    "validate_p7_bridge_candidate",
    "build_p7_bridge_dry_run_result",
    "build_p51_p7_import_bridge_dry_run_report",
    "build_p51_negative_fixture_results",
    "persist_p51_p7_import_bridge_dry_run",
]
