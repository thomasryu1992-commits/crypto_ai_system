
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.p7_import_bridge_dry_run import (
    STATUS_DRY_RUN_ACCEPTED_REVIEW_ONLY_NO_SUBMIT as P51_ACCEPTED_STATUS,
    _valid_candidate_fixture,
    _valid_p50_source_fixture,
    build_p51_p7_import_bridge_dry_run_report,
    validate_p7_bridge_candidate,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_VERSION = "p52_p7_accepted_evidence_import_packet_staging_v1"
P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_REGISTRY_NAME = "p52_p7_accepted_evidence_import_packet_staging_registry"
STATUS_READY_REVIEW_ONLY_NO_SUBMIT = "P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_READY_REVIEW_ONLY_NO_SUBMIT"
STATUS_STAGED_REVIEW_ONLY_NO_SUBMIT = "P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_STAGED_REVIEW_ONLY_NO_SUBMIT"
STATUS_BLOCKED_FAIL_CLOSED = "P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_BLOCKED_FAIL_CLOSED"

_ALLOWED_P51_ARTIFACT_TYPE = "p51_p7_import_bridge_dry_run_report"
_REQUIRED_CANDIDATE_SECTIONS = (
    "p7_input_preview",
    "status_polling_events",
    "cancel_boundary_evidence",
    "signed_testnet_reconciliation_evidence",
    "signed_testnet_session_close_evidence",
)
_FORBIDDEN_FIELD_TOKENS = (
    "api_key",
    "api_secret",
    "secret_value",
    "private_key",
    "passphrase",
    "raw_signed_payload",
    "raw_request_body",
    "raw_exchange_payload",
    "unredacted_exchange_response",
    "signature",
)
_FORBIDDEN_SCOPE_TOKENS = (
    "mainnet",
    "live_trade",
    "withdraw",
    "transfer",
    "admin",
    "secret_dump",
)


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
            "p7_report_persisted_by_p52": False,
            "p7_valid_status_written_by_p52": False,
            "p7_intake_execution_performed_by_p52": False,
            "p7_import_packet_promoted_to_runtime_authority": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        }
    )
    return payload


@dataclass(frozen=True)
class P7AcceptedEvidenceImportPacketStagingTemplate:
    staging_template_id: str = "p52_p7_accepted_evidence_import_packet_staging_TEMPLATE_NO_SUBMIT"
    staging_version: str = P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_VERSION
    generated_by_review_package: bool = True
    review_only: bool = True
    staging_only: bool = True
    external_runtime_evidence_only: bool = True
    p51_accepted_dry_run_required: bool = True
    p51_candidate_hash_match_required: bool = True
    p7_input_preview_required: bool = True
    p7_report_persistence_allowed: bool = False
    p7_status_mutation_allowed: bool = False
    p7_valid_status_written_by_p52: bool = False
    p7_intake_execution_performed_by_p52: bool = False
    can_grant_runtime_authority: bool = False
    can_enable_testnet_submit: bool = False
    can_enable_live_canary: bool = False
    can_enable_live_scaled: bool = False
    order_endpoint_call_allowed_by_p52: bool = False
    status_endpoint_call_allowed_by_p52: bool = False
    cancel_endpoint_call_allowed_by_p52: bool = False
    http_request_allowed_by_p52: bool = False
    signature_creation_allowed_by_p52: bool = False
    secret_access_allowed_by_p52: bool = False
    packet_must_reference_external_evidence_by_hash: bool = True
    packet_must_not_embed_raw_exchange_response: bool = True
    packet_must_not_embed_raw_signed_payload: bool = True
    packet_must_not_embed_secret_values: bool = True
    staged_packet_requires_separate_operator_import_action: bool = True
    p8_must_remain_waiting_after_p52: bool = True
    required_candidate_sections: tuple[str, ...] = _REQUIRED_CANDIDATE_SECTIONS

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p52_staging_template_sha256"] = sha256_json(payload)
        return payload


def _walk_forbidden(obj: Any, *, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            key_text = str(key)
            key_l = key_text.lower()
            child_prefix = f"{prefix}.{key_text}" if prefix else key_text
            if any(token in key_l for token in _FORBIDDEN_FIELD_TOKENS):
                # Allow metadata-only names and boolean evidence flags.  P52 must reject
                # secret-bearing fields, but imported external-runtime evidence is expected
                # to contain safe booleans such as secret_value_logged=false or
                # signature_created=true from the separate signed-testnet runtime.
                safe_boolean_flag = isinstance(value, bool) and any(
                    marker in key_l
                    for marker in (
                        "_logged",
                        "_included",
                        "_accessed",
                        "_created",
                        "_called",
                        "_sent",
                    )
                )
                if key_l not in {"secret_reference_id", "no_secret_logged_evidence_hash"} and not safe_boolean_flag:
                    blockers.append(f"P52_FORBIDDEN_FIELD:{child_prefix}")
            blockers.extend(_walk_forbidden(value, prefix=child_prefix))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, prefix=f"{prefix}[{idx}]"))
    elif isinstance(obj, str):
        value_l = obj.lower()
        if any(token in value_l for token in _FORBIDDEN_SCOPE_TOKENS):
            blockers.append(f"P52_FORBIDDEN_SCOPE_TOKEN:{prefix}")
    return blockers


def validate_p52_staging_template(
    template: Mapping[str, Any] | P7AcceptedEvidenceImportPacketStagingTemplate | None,
) -> dict[str, Any]:
    payload = template.to_dict() if isinstance(template, P7AcceptedEvidenceImportPacketStagingTemplate) else dict(template or {})
    blockers: list[str] = []
    if payload.get("staging_version") != P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_VERSION:
        blockers.append("P52_TEMPLATE_VERSION_MISMATCH")
    for key in (
        "generated_by_review_package",
        "review_only",
        "staging_only",
        "external_runtime_evidence_only",
        "p51_accepted_dry_run_required",
        "p51_candidate_hash_match_required",
        "p7_input_preview_required",
        "packet_must_reference_external_evidence_by_hash",
        "packet_must_not_embed_raw_exchange_response",
        "packet_must_not_embed_raw_signed_payload",
        "packet_must_not_embed_secret_values",
        "staged_packet_requires_separate_operator_import_action",
        "p8_must_remain_waiting_after_p52",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P52_TEMPLATE_{key.upper()}_NOT_TRUE")
    for key in (
        "p7_report_persistence_allowed",
        "p7_status_mutation_allowed",
        "p7_valid_status_written_by_p52",
        "p7_intake_execution_performed_by_p52",
        "can_grant_runtime_authority",
        "can_enable_testnet_submit",
        "can_enable_live_canary",
        "can_enable_live_scaled",
        "order_endpoint_call_allowed_by_p52",
        "status_endpoint_call_allowed_by_p52",
        "cancel_endpoint_call_allowed_by_p52",
        "http_request_allowed_by_p52",
        "signature_creation_allowed_by_p52",
        "secret_access_allowed_by_p52",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P52_TEMPLATE_{key.upper()}_NOT_FALSE")
    sections = set(payload.get("required_candidate_sections") or [])
    if not set(_REQUIRED_CANDIDATE_SECTIONS).issubset(sections):
        blockers.append("P52_TEMPLATE_REQUIRED_CANDIDATE_SECTIONS_INCOMPLETE")
    validation = {
        "p52_staging_template_valid": not blockers,
        "p52_staging_template_block_reasons": sorted(dict.fromkeys(blockers)),
        "staging_template_id": payload.get("staging_template_id"),
    }
    validation["p52_staging_template_validation_sha256"] = sha256_json(validation)
    return validation


def validate_p51_accepted_dry_run_source(
    p51_report: Mapping[str, Any] | None,
    *,
    candidate: Mapping[str, Any] | None = None,
    candidate_supplied: bool = False,
) -> dict[str, Any]:
    payload = dict(p51_report or {})
    blockers: list[str] = []
    if not payload:
        return {
            "p51_source_present": False,
            "p51_source_valid_for_staging": False,
            "p51_source_ready_for_staging": False,
            "p51_source_block_reasons": [] if not candidate_supplied else ["P52_P51_SOURCE_MISSING"],
            "source_status": None,
            "source_sha256": None,
            "candidate_hash_match": False,
        }
    if payload.get("artifact_type") != _ALLOWED_P51_ARTIFACT_TYPE:
        blockers.append("P52_P51_SOURCE_ARTIFACT_TYPE_INVALID")
    if payload.get("status") != P51_ACCEPTED_STATUS:
        blockers.append("P52_P51_SOURCE_STATUS_NOT_ACCEPTED_REVIEW_ONLY_NO_SUBMIT")
    for key in ("review_only", "dry_run_only", "external_runtime_only", "review_package_default_no_submit"):
        if payload.get(key) is not True:
            blockers.append(f"P52_P51_SOURCE_{key.upper()}_NOT_TRUE")
    for key in (
        "runtime_authority_source",
        "p7_report_persisted_by_p51",
        "p7_valid_status_written_by_p51",
        "p7_intake_execution_performed_by_p51",
        "actual_order_submission_performed",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "secret_value_accessed",
        "live_canary_execution_enabled",
        "live_scaled_execution_enabled",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P52_P51_SOURCE_{key.upper()}_NOT_FALSE")
    if payload.get("p7_would_accept_imported_evidence") is not True:
        blockers.append("P52_P51_SOURCE_P7_WOULD_ACCEPT_NOT_TRUE")
    if payload.get("p7_bridge_dry_run_performed") is not True:
        blockers.append("P52_P51_SOURCE_DRY_RUN_NOT_PERFORMED")
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P52_P51_SOURCE_UNSAFE_TRUTHY_EXECUTION_FLAGS")
    candidate_hash_match = False
    if candidate is not None:
        expected = (payload.get("candidate_validation") or {}).get("candidate_sha256")
        actual = sha256_json(candidate)
        candidate_hash_match = bool(expected and expected == actual)
        if not candidate_hash_match:
            blockers.append("P52_P51_SOURCE_CANDIDATE_SHA256_MISMATCH")
    elif candidate_supplied:
        blockers.append("P52_CANDIDATE_REQUIRED_FOR_STAGING")
    validation = {
        "p51_source_present": True,
        "p51_source_valid_for_staging": not blockers,
        "p51_source_ready_for_staging": not blockers,
        "p51_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "source_status": payload.get("status"),
        "source_sha256": payload.get("p51_p7_import_bridge_dry_run_sha256"),
        "candidate_hash_match": candidate_hash_match,
        "p7_would_accept_imported_evidence": payload.get("p7_would_accept_imported_evidence") is True,
        "p7_report_persisted_by_p51": payload.get("p7_report_persisted_by_p51") is True,
        "p7_valid_status_written_by_p51": payload.get("p7_valid_status_written_by_p51") is True,
    }
    validation["p51_source_validation_sha256"] = sha256_json(validation)
    return validation


def validate_p52_candidate_for_staging(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(candidate or {})
    p51_validation = validate_p7_bridge_candidate(payload) if payload else {
        "p7_bridge_candidate_present": False,
        "p7_bridge_candidate_valid_for_dry_run": False,
        "p7_bridge_candidate_block_reasons": [],
        "candidate_sha256": None,
    }
    blockers = list(p51_validation.get("p7_bridge_candidate_block_reasons") or [])
    if not payload:
        return {
            "candidate_present": False,
            "candidate_valid_for_p52_staging": False,
            "candidate_block_reasons": [],
            "candidate_sha256": None,
            "required_sections_present": False,
        }
    for key in _REQUIRED_CANDIDATE_SECTIONS:
        if key not in payload:
            blockers.append(f"P52_CANDIDATE_REQUIRED_SECTION_MISSING:{key}")
    for key in (
        "runtime_authority_granted",
        "p7_valid_status_written_by_p52",
        "p7_report_persisted_by_p52",
        "p7_intake_execution_performed_by_p52",
        "order_endpoint_called_by_p52",
        "http_request_sent_by_p52",
        "signature_created_by_p52",
        "secret_value_accessed_by_p52",
    ):
        if payload.get(key) is True:
            blockers.append(f"P52_CANDIDATE_{key.upper()}_NOT_ALLOWED")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "candidate_present": True,
        "candidate_valid_for_p52_staging": not blockers,
        "candidate_block_reasons": sorted(dict.fromkeys(blockers)),
        "candidate_sha256": sha256_json(payload),
        "required_sections_present": set(_REQUIRED_CANDIDATE_SECTIONS).issubset(set(payload.keys())),
        "p51_candidate_validation": p51_validation,
    }
    validation["candidate_p52_staging_validation_sha256"] = sha256_json(validation)
    return validation


def build_staged_p7_import_packet(
    *,
    candidate: Mapping[str, Any],
    p51_report: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(candidate)
    preview = dict(payload.get("p7_input_preview") or {})
    section_hashes = {
        section: sha256_json(payload.get(section))
        for section in _REQUIRED_CANDIDATE_SECTIONS
    }
    packet = {
        "artifact_type": "p52_p7_accepted_evidence_import_packet_STAGED_NO_SUBMIT",
        "staging_version": P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_VERSION,
        "status": STATUS_STAGED_REVIEW_ONLY_NO_SUBMIT,
        "review_only": True,
        "staging_only": True,
        "external_runtime_only": True,
        "runtime_authority_source": False,
        "cannot_be_used_as_runtime_authority": True,
        "requires_separate_operator_p7_import_action": True,
        "p7_import_packet_staged": True,
        "p7_report_persisted_by_p52": False,
        "p7_valid_status_written_by_p52": False,
        "p7_intake_execution_performed_by_p52": False,
        "p8_repeated_session_candidate_created": False,
        "source_p51_p7_import_bridge_dry_run_id": p51_report.get("p51_p7_import_bridge_dry_run_id"),
        "source_p51_p7_import_bridge_dry_run_sha256": p51_report.get("p51_p7_import_bridge_dry_run_sha256"),
        "source_p51_candidate_sha256": (p51_report.get("candidate_validation") or {}).get("candidate_sha256"),
        "candidate_sha256": sha256_json(payload),
        "candidate_hash_match_verified": True,
        "p7_input_preview": preview,
        "p7_input_preview_sha256": sha256_json(preview),
        "evidence_section_hashes": section_hashes,
        "external_evidence_reference_paths": {
            "raw_exchange_response_redacted_path": preview.get("raw_exchange_response_redacted_path"),
        },
        "exchange_order_id": preview.get("exchange_order_id"),
        "client_order_id": preview.get("client_order_id"),
        "idempotency_key": preview.get("idempotency_key"),
        "order_intent_id": preview.get("order_intent_id"),
        "risk_gate_id": preview.get("risk_gate_id"),
        "hot_path_preorder_risk_gate_id": preview.get("hot_path_preorder_risk_gate_id"),
        "secret_reference_id": preview.get("secret_reference_id"),
        "key_fingerprint_sha256": preview.get("key_fingerprint_sha256"),
        "no_secret_logged_evidence_hash": preview.get("no_secret_logged_evidence_hash"),
        "request_hash": preview.get("request_hash"),
        "exchange_response_hash": preview.get("exchange_response_hash"),
        "created_at_utc": utc_now_canonical(),
        **_execution_false_payload(),
    }
    packet["p52_staged_p7_import_packet_id"] = stable_id("p52_staged_p7_import_packet", packet, 24)
    packet["p52_staged_p7_import_packet_sha256"] = sha256_json(packet)
    return packet


def validate_staged_p7_import_packet(packet: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(packet or {})
    blockers: list[str] = []
    if not payload:
        return {
            "staged_packet_present": False,
            "staged_packet_valid": False,
            "staged_packet_block_reasons": [],
            "staged_packet_sha256": None,
        }
    if payload.get("artifact_type") != "p52_p7_accepted_evidence_import_packet_STAGED_NO_SUBMIT":
        blockers.append("P52_STAGED_PACKET_ARTIFACT_TYPE_INVALID")
    if payload.get("status") != STATUS_STAGED_REVIEW_ONLY_NO_SUBMIT:
        blockers.append("P52_STAGED_PACKET_STATUS_INVALID")
    for key in (
        "review_only",
        "staging_only",
        "external_runtime_only",
        "cannot_be_used_as_runtime_authority",
        "requires_separate_operator_p7_import_action",
        "p7_import_packet_staged",
        "candidate_hash_match_verified",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P52_STAGED_PACKET_{key.upper()}_NOT_TRUE")
    for key in (
        "runtime_authority_source",
        "p7_report_persisted_by_p52",
        "p7_valid_status_written_by_p52",
        "p7_intake_execution_performed_by_p52",
        "p8_repeated_session_candidate_created",
        "actual_order_submission_performed",
        "actual_testnet_order_submitted",
        "actual_live_order_submitted",
        "external_order_submission_performed",
        "order_endpoint_called",
        "order_status_endpoint_called",
        "cancel_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "secret_value_accessed",
        "runtime_scheduler_enabled",
        "live_canary_execution_enabled",
        "live_scaled_execution_enabled",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P52_STAGED_PACKET_{key.upper()}_NOT_FALSE")
    if not payload.get("source_p51_p7_import_bridge_dry_run_sha256"):
        blockers.append("P52_STAGED_PACKET_SOURCE_P51_SHA_MISSING")
    if not payload.get("candidate_sha256"):
        blockers.append("P52_STAGED_PACKET_CANDIDATE_SHA_MISSING")
    section_hashes = dict(payload.get("evidence_section_hashes") or {})
    for section in _REQUIRED_CANDIDATE_SECTIONS:
        if not section_hashes.get(section):
            blockers.append(f"P52_STAGED_PACKET_SECTION_HASH_MISSING:{section}")
    blockers.extend(_walk_forbidden(payload))
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P52_STAGED_PACKET_UNSAFE_TRUTHY_EXECUTION_FLAGS")
    validation = {
        "staged_packet_present": True,
        "staged_packet_valid": not blockers,
        "staged_packet_block_reasons": sorted(dict.fromkeys(blockers)),
        "staged_packet_sha256": payload.get("p52_staged_p7_import_packet_sha256"),
    }
    validation["staged_packet_validation_sha256"] = sha256_json(validation)
    return validation


def build_p52_p7_accepted_evidence_import_packet_staging_report(
    *,
    cfg: AppConfig | None = None,
    p51_report: Mapping[str, Any] | None = None,
    staging_template: Mapping[str, Any] | P7AcceptedEvidenceImportPacketStagingTemplate | None = None,
    candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    source_p51 = dict(p51_report or _read_latest_json(cfg, "p51_p7_import_bridge_dry_run_report.json"))
    template_payload = staging_template.to_dict() if isinstance(staging_template, P7AcceptedEvidenceImportPacketStagingTemplate) else dict(staging_template or P7AcceptedEvidenceImportPacketStagingTemplate().to_dict())
    template_validation = validate_p52_staging_template(template_payload)
    candidate_validation = validate_p52_candidate_for_staging(candidate)
    p51_validation = validate_p51_accepted_dry_run_source(
        source_p51,
        candidate=candidate,
        candidate_supplied=candidate_validation["candidate_present"],
    )
    blockers = list(template_validation["p52_staging_template_block_reasons"])
    if candidate_validation["candidate_present"]:
        blockers.extend(candidate_validation["candidate_block_reasons"])
        blockers.extend(p51_validation["p51_source_block_reasons"])
    staged_packet: dict[str, Any] | None = None
    staged_packet_validation: dict[str, Any] = {
        "staged_packet_present": False,
        "staged_packet_valid": False,
        "staged_packet_block_reasons": [],
        "staged_packet_sha256": None,
    }
    if candidate_validation["candidate_present"] and not blockers:
        staged_packet = build_staged_p7_import_packet(candidate=dict(candidate or {}), p51_report=source_p51)
        staged_packet_validation = validate_staged_p7_import_packet(staged_packet)
        blockers.extend(staged_packet_validation["staged_packet_block_reasons"])
    if blockers:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif staged_packet:
        status = STATUS_STAGED_REVIEW_ONLY_NO_SUBMIT
    else:
        status = STATUS_READY_REVIEW_ONLY_NO_SUBMIT
    report = {
        "artifact_type": "p52_p7_accepted_evidence_import_packet_staging_report",
        "p52_staging_version": P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
        "review_only": True,
        "staging_only": True,
        "external_runtime_only": True,
        "runtime_authority_source": False,
        "review_package_default_no_submit": True,
        "source_p51_validation": p51_validation,
        "staging_template": template_payload,
        "staging_template_validation": template_validation,
        "candidate_supplied": candidate_validation["candidate_present"],
        "candidate_validation": candidate_validation,
        "p7_import_packet_staged": bool(staged_packet and not blockers),
        "staged_packet": staged_packet if staged_packet and not blockers else None,
        "staged_packet_validation": staged_packet_validation,
        "p7_report_persisted_by_p52": False,
        "p7_valid_status_written_by_p52": False,
        "p7_intake_execution_performed_by_p52": False,
        "p7_status_mutation_performed": False,
        "p8_repeated_session_candidate_created": False,
        "actual_p7_import_still_requires_separate_operator_action": True,
        "actual_endpoint_call_still_requires_separate_operator_local_runtime": True,
        "next_required_chain": [
            "operator reviews the P52 staged import packet and source P51 dry-run acceptance",
            "a separate controlled P7 import action may persist real post-submit evidence after explicit operator control",
            "P7 accepted evidence records must be accumulated before P8 repeated clean session validation",
            "P8 remains waiting until multiple real P7 evidence records exist",
            "P9/P10/live paths remain blocked until P8 is valid",
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
        report["block_reasons"] = sorted(dict.fromkeys(report["block_reasons"] + ["P52_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
        report["p7_import_packet_staged"] = False
        report["staged_packet"] = None
    report["p52_p7_accepted_evidence_import_packet_staging_id"] = stable_id("p52_p7_accepted_evidence_import_packet_staging", report, 24)
    report["p52_p7_accepted_evidence_import_packet_staging_sha256"] = sha256_json(report)
    return report


def build_p52_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    valid_candidate = _valid_candidate_fixture()
    p50_source = _valid_p50_source_fixture()
    accepted_p51 = build_p51_p7_import_bridge_dry_run_report(
        cfg=cfg, p50_report=p50_source, candidate=valid_candidate
    )
    rejected_candidate = deepcopy(valid_candidate)
    rejected_candidate["p7_input_preview"]["exchange_order_id"] = "mock_order_123"
    rejected_p51 = build_p51_p7_import_bridge_dry_run_report(
        cfg=cfg, p50_report=p50_source, candidate=rejected_candidate
    )
    tampered_candidate = deepcopy(valid_candidate)
    tampered_candidate["p7_input_preview"]["client_order_id"] = "client_order_tampered"
    status_write_source = {**accepted_p51, "p7_valid_status_written_by_p51": True}
    cases: dict[str, tuple[Mapping[str, Any], Mapping[str, Any] | None]] = {
        "p51_not_accepted": (rejected_p51, rejected_candidate),
        "candidate_hash_mismatch": (accepted_p51, tampered_candidate),
        "p51_status_write_attempt": (status_write_source, valid_candidate),
        "candidate_runtime_authority": (accepted_p51, {**valid_candidate, "runtime_authority_granted": True}),
        "candidate_secret_field": (accepted_p51, {**valid_candidate, "api_secret": "redacted-but-forbidden-field"}),
        "candidate_missing_reconciliation": (
            accepted_p51,
            {k: v for k, v in valid_candidate.items() if k != "signed_testnet_reconciliation_evidence"},
        ),
    }
    results: dict[str, Any] = {}
    for name, (source, candidate) in cases.items():
        report = build_p52_p7_accepted_evidence_import_packet_staging_report(cfg=cfg, p51_report=source, candidate=candidate)
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "p7_import_packet_staged": report["p7_import_packet_staged"],
            "p7_report_persisted_by_p52": report["p7_report_persisted_by_p52"],
            "p7_valid_status_written_by_p52": report["p7_valid_status_written_by_p52"],
        }
    accepted = build_p52_p7_accepted_evidence_import_packet_staging_report(
        cfg=cfg,
        p51_report=accepted_p51,
        candidate=valid_candidate,
    )
    payload = {
        "artifact_type": "p52_p7_accepted_evidence_import_packet_staging_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "valid_candidate_fixture_stages_packet": accepted["p7_import_packet_staged"] is True,
        "valid_candidate_fixture_status": accepted["status"],
        "p7_report_persisted_by_p52": False,
        "p7_valid_status_written_by_p52": False,
        **_execution_false_payload(),
    }
    payload["p52_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_p52_p7_accepted_evidence_import_packet_staging(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p52_p7_accepted_evidence_import_packet_staging")
    report = build_p52_p7_accepted_evidence_import_packet_staging_report(cfg=cfg)
    negative = build_p52_negative_fixture_results(cfg=cfg)
    template = report["staging_template"]
    packet_template = build_p52_p7_accepted_evidence_import_packet_staging_report(
        cfg=cfg,
        p51_report=build_p51_p7_import_bridge_dry_run_report(
            cfg=cfg,
            p50_report=_valid_p50_source_fixture(),
            candidate=_valid_candidate_fixture(),
        ),
        candidate=_valid_candidate_fixture(),
    ).get("staged_packet")
    registry_record = append_registry_record(
        registry_path(cfg, P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_REGISTRY_NAME),
        {
            "artifact_type": "p52_p7_accepted_evidence_import_packet_staging_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "p52_p7_accepted_evidence_import_packet_staging_id": report["p52_p7_accepted_evidence_import_packet_staging_id"],
            "p52_p7_accepted_evidence_import_packet_staging_sha256": report["p52_p7_accepted_evidence_import_packet_staging_sha256"],
            "source_p51_sha256": report["source_p51_validation"].get("source_sha256"),
            "candidate_supplied": report["candidate_supplied"],
            "p7_import_packet_staged": report["p7_import_packet_staged"],
            "p7_report_persisted_by_p52": report["p7_report_persisted_by_p52"],
            "p7_valid_status_written_by_p52": report["p7_valid_status_written_by_p52"],
            "actual_order_submission_performed": report["actual_order_submission_performed"],
            "order_endpoint_called": report["order_endpoint_called"],
            "http_request_sent": report["http_request_sent"],
            "signature_created": report["signature_created"],
            "secret_value_accessed": report["secret_value_accessed"],
        },
        registry_name=P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_REGISTRY_NAME,
        id_field="p52_p7_accepted_evidence_import_packet_staging_registry_record_id",
        hash_field="p52_p7_accepted_evidence_import_packet_staging_registry_record_sha256",
        id_prefix="p52_p7_accepted_evidence_import_packet_staging_registry_record",
    )
    report["p52_p7_accepted_evidence_import_packet_staging_registry_record_id"] = registry_record[
        "p52_p7_accepted_evidence_import_packet_staging_registry_record_id"
    ]
    report["p52_p7_accepted_evidence_import_packet_staging_registry_record_sha256"] = registry_record[
        "p52_p7_accepted_evidence_import_packet_staging_registry_record_sha256"
    ]
    report["p52_p7_accepted_evidence_import_packet_staging_sha256"] = sha256_json(report)
    summary = {
        "artifact_type": "p52_p7_accepted_evidence_import_packet_staging_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": report["review_only"],
        "staging_only": report["staging_only"],
        "candidate_supplied": report["candidate_supplied"],
        "p7_import_packet_staged": report["p7_import_packet_staged"],
        "p7_report_persisted_by_p52": report["p7_report_persisted_by_p52"],
        "p7_valid_status_written_by_p52": report["p7_valid_status_written_by_p52"],
        "actual_order_submission_performed": report["actual_order_submission_performed"],
        "order_endpoint_called": report["order_endpoint_called"],
        "http_request_sent": report["http_request_sent"],
        "signature_created": report["signature_created"],
        "secret_value_accessed": report["secret_value_accessed"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "valid_candidate_fixture_stages_packet": negative["valid_candidate_fixture_stages_packet"],
        "p52_p7_accepted_evidence_import_packet_staging_id": report["p52_p7_accepted_evidence_import_packet_staging_id"],
        "p52_p7_accepted_evidence_import_packet_staging_sha256": report["p52_p7_accepted_evidence_import_packet_staging_sha256"],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p52_summary_sha256"] = sha256_json(summary)
    writes = {
        "p52_p7_accepted_evidence_import_packet_staging_report.json": report,
        "p52_p7_accepted_evidence_import_packet_staging_TEMPLATE_NO_SUBMIT.json": template,
        "p52_p7_accepted_evidence_import_packet_STAGED_TEMPLATE_NO_SUBMIT.json": packet_template,
        "p52_p7_accepted_evidence_import_packet_staging_negative_fixture_results.json": negative,
        "p52_p7_accepted_evidence_import_packet_staging_registry_record.json": registry_record,
        "p52_p7_accepted_evidence_import_packet_staging_summary.json": summary,
    }
    for filename, payload in writes.items():
        atomic_write_json(latest / filename, payload)
        atomic_write_json(storage / filename, payload)
    return report


__all__ = [
    "P52_P7_ACCEPTED_EVIDENCE_IMPORT_PACKET_STAGING_VERSION",
    "STATUS_READY_REVIEW_ONLY_NO_SUBMIT",
    "STATUS_STAGED_REVIEW_ONLY_NO_SUBMIT",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "P7AcceptedEvidenceImportPacketStagingTemplate",
    "validate_p52_staging_template",
    "validate_p51_accepted_dry_run_source",
    "validate_p52_candidate_for_staging",
    "build_staged_p7_import_packet",
    "validate_staged_p7_import_packet",
    "build_p52_p7_accepted_evidence_import_packet_staging_report",
    "build_p52_negative_fixture_results",
    "persist_p52_p7_accepted_evidence_import_packet_staging",
]
