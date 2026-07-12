from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.operator_controlled_p7_import_action_boundary import (
    STATUS_ARMED_REVIEW_ONLY_NO_IMPORT as P53_ARMED_STATUS,
    _valid_p52_source_fixture,
    build_p53_operator_controlled_p7_import_action_boundary_report,
    build_valid_operator_request_fixture,
    validate_armed_boundary_packet,
    validate_p52_staged_source,
)
from crypto_ai_system.execution.p7_accepted_evidence_import_packet_staging import (
    validate_p52_candidate_for_staging,
    validate_staged_p7_import_packet,
)
from crypto_ai_system.execution.p7_import_bridge_dry_run import build_p7_bridge_dry_run_result
from crypto_ai_system.execution.post_submit_evidence_intake import (
    STATUS_RECONCILED_SESSION_CLOSED_REVIEW_ONLY as P7_ACCEPT_STATUS,
)
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_VERSION = "p54_separate_p7_import_executor_final_guard_v1"
P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_REGISTRY_NAME = "p54_separate_p7_import_executor_final_guard_registry"

STATUS_READY_REVIEW_ONLY_EXECUTOR_DISABLED = "P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_READY_REVIEW_ONLY_EXECUTOR_DISABLED"
STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED = (
    "P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED"
)
STATUS_BLOCKED_FAIL_CLOSED = "P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_BLOCKED_FAIL_CLOSED"

_ALLOWED_P53_REPORT_ARTIFACT_TYPE = "p53_operator_controlled_p7_import_action_boundary_report"
_ALLOWED_P53_ARMED_PACKET_ARTIFACT_TYPE = "p53_operator_controlled_p7_import_action_boundary_ARMED_NO_IMPORT"
_ALLOWED_P52_REPORT_ARTIFACT_TYPE = "p52_p7_accepted_evidence_import_packet_staging_report"
_ALLOWED_P52_STAGED_PACKET_ARTIFACT_TYPE = "p52_p7_accepted_evidence_import_packet_STAGED_NO_SUBMIT"
_ALLOWED_NONCE_EVIDENCE_ARTIFACT_TYPE = "p54_one_time_nonce_freshness_evidence"
_ALLOWED_DUPLICATE_LOCK_ARTIFACT_TYPE = "p54_duplicate_import_lock_evidence"
_ALLOWED_NO_SECRET_ARTIFACT_TYPE = "p54_no_secret_evidence_attestation"
_ALLOWED_REGISTRY_POLICY_ARTIFACT_TYPE = "p54_append_only_p7_registry_policy_evidence"
_ALLOWED_FINAL_GUARD_PACKET_ARTIFACT_TYPE = "p54_p7_import_executor_final_guard_PASSED_NO_IMPORT"

_P7_REGISTRY_NAME = "p7_post_submit_evidence_intake_registry"
_P7_REGISTRY_RELATIVE_PATH = "storage/registries/p7_post_submit_evidence_intake_registry.jsonl"

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


def _is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _verify_embedded_hash(payload: Mapping[str, Any] | None, hash_key: str) -> bool:
    data = dict(payload or {})
    expected = data.get(hash_key)
    if not _is_sha256_hex(expected):
        return False
    without_hash = {key: value for key, value in data.items() if key != hash_key}
    return expected == sha256_json(without_hash)


def _walk_forbidden(obj: Any, *, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            key_text = str(key)
            key_l = key_text.lower()
            child_prefix = f"{prefix}.{key_text}" if prefix else key_text
            if any(token in key_l for token in _FORBIDDEN_FIELD_TOKENS):
                safe_boolean_flag = isinstance(value, bool) and any(
                    marker in key_l
                    for marker in (
                        "_logged",
                        "_included",
                        "_accessed",
                        "_created",
                        "_called",
                        "_sent",
                        "_detected",
                    )
                )
                safe_metadata_field = key_l in {
                    "secret_reference_id",
                    "no_secret_logged_evidence_hash",
                    "no_secret_evidence_attestation_sha256",
                }
                if not safe_boolean_flag and not safe_metadata_field:
                    blockers.append(f"P54_FORBIDDEN_FIELD:{child_prefix}")
            blockers.extend(_walk_forbidden(value, prefix=child_prefix))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, prefix=f"{prefix}[{idx}]"))
    elif isinstance(obj, str):
        value_l = obj.lower()
        if any(token in value_l for token in _FORBIDDEN_SCOPE_TOKENS):
            blockers.append(f"P54_FORBIDDEN_SCOPE_TOKEN:{prefix}")
    return blockers


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
            "p7_import_executor_enabled": False,
            "p7_import_executor_action_allowed": False,
            "p7_import_executor_action_executed": False,
            "p7_import_action_enabled": False,
            "p7_import_action_executed": False,
            "p7_report_persisted_by_p54": False,
            "p7_valid_status_written_by_p54": False,
            "p7_intake_execution_performed_by_p54": False,
            "p7_registry_append_performed_by_p54": False,
            "p7_registry_overwrite_performed_by_p54": False,
            "p7_registry_delete_performed_by_p54": False,
            "p7_import_action_nonce_consumed_by_p54": False,
            "p7_duplicate_import_lock_acquired_by_p54": False,
            "p7_import_packet_promoted_to_runtime_authority": False,
            "p8_repeated_session_candidate_created": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        }
    )
    return payload


@dataclass(frozen=True)
class SeparateP7ImportExecutorFinalGuardTemplate:
    final_guard_template_id: str = "p54_separate_p7_import_executor_final_guard_TEMPLATE_EXECUTOR_DISABLED"
    final_guard_version: str = P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_VERSION
    generated_by_review_package: bool = True
    review_only: bool = True
    final_guard_only: bool = True
    executor_disabled_by_default: bool = True
    p53_armed_boundary_required: bool = True
    p53_embedded_hash_revalidation_required: bool = True
    p52_staged_packet_required: bool = True
    p52_embedded_hash_revalidation_required: bool = True
    candidate_hash_chain_revalidation_required: bool = True
    evidence_section_hash_revalidation_required: bool = True
    fresh_p7_schema_dry_run_required: bool = True
    no_secret_evidence_attestation_required: bool = True
    one_time_nonce_freshness_evidence_required: bool = True
    duplicate_import_lock_evidence_required: bool = True
    append_only_p7_registry_policy_required: bool = True
    atomic_nonce_consume_and_registry_append_required_by_future_executor: bool = True
    final_guard_must_be_rechecked_immediately_by_future_executor: bool = True
    p7_import_executor_enablement_allowed_by_p54: bool = False
    p7_import_execution_allowed_by_p54: bool = False
    p7_report_persistence_allowed_by_p54: bool = False
    p7_status_mutation_allowed_by_p54: bool = False
    nonce_consumption_allowed_by_p54: bool = False
    duplicate_lock_acquisition_allowed_by_p54: bool = False
    registry_append_allowed_by_p54: bool = False
    can_grant_runtime_authority: bool = False
    can_enable_testnet_submit: bool = False
    can_enable_live_canary: bool = False
    can_enable_live_scaled: bool = False
    order_endpoint_call_allowed_by_p54: bool = False
    status_endpoint_call_allowed_by_p54: bool = False
    cancel_endpoint_call_allowed_by_p54: bool = False
    http_request_allowed_by_p54: bool = False
    signature_creation_allowed_by_p54: bool = False
    secret_access_allowed_by_p54: bool = False
    p8_must_remain_waiting_after_p54: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p54_final_guard_template_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class OneTimeNonceFreshnessEvidenceTemplate:
    artifact_type: str = _ALLOWED_NONCE_EVIDENCE_ARTIFACT_TYPE
    evidence_version: str = P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_VERSION
    evidence_template_id: str = "p54_one_time_nonce_freshness_evidence_TEMPLATE_NO_CONSUME"
    review_only: bool = True
    one_time_action_nonce_sha256: str = "NONCE_SHA256_REQUIRED"
    source_p53_armed_packet_sha256: str = "P53_ARMED_PACKET_SHA256_REQUIRED"
    nonce_registry_checked: bool = True
    nonce_seen_before: bool = False
    duplicate_nonce_detected: bool = False
    nonce_consumed: bool = False
    nonce_fresh: bool = True
    age_seconds_at_guard: int = 0
    freshness_window_seconds: int = 300
    nonce_freshness_must_be_rechecked_by_future_executor: bool = True
    nonce_registry_append_required_at_execution: bool = True
    nonce_registry_append_performed_by_p54: bool = False
    nonce_consumption_allowed_by_p54: bool = False
    checked_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p54_nonce_freshness_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class DuplicateImportLockEvidenceTemplate:
    artifact_type: str = _ALLOWED_DUPLICATE_LOCK_ARTIFACT_TYPE
    evidence_version: str = P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_VERSION
    evidence_template_id: str = "p54_duplicate_import_lock_evidence_TEMPLATE_NO_LOCK"
    review_only: bool = True
    candidate_sha256: str = "CANDIDATE_SHA256_REQUIRED"
    source_p52_staged_packet_sha256: str = "P52_STAGED_PACKET_SHA256_REQUIRED"
    exchange_order_id: str = "EXCHANGE_ORDER_ID_REQUIRED"
    client_order_id: str = "CLIENT_ORDER_ID_REQUIRED"
    idempotency_key: str = "IDEMPOTENCY_KEY_REQUIRED"
    duplicate_registry_checked: bool = True
    existing_import_record_count: int = 0
    duplicate_import_detected: bool = False
    duplicate_order_id_detected: bool = False
    duplicate_client_order_id_detected: bool = False
    duplicate_idempotency_key_detected: bool = False
    duplicate_import_lock_ready: bool = True
    duplicate_import_lock_acquired: bool = False
    duplicate_import_lock_acquisition_allowed_by_p54: bool = False
    lock_key_sha256: str = "LOCK_KEY_SHA256_REQUIRED"
    atomic_lock_acquisition_required_by_future_executor: bool = True
    lock_release_on_failed_append_required: bool = True
    checked_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p54_duplicate_import_lock_evidence_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class NoSecretEvidenceAttestationTemplate:
    artifact_type: str = _ALLOWED_NO_SECRET_ARTIFACT_TYPE
    evidence_version: str = P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_VERSION
    evidence_template_id: str = "p54_no_secret_evidence_attestation_TEMPLATE_REDACTED_ONLY"
    review_only: bool = True
    candidate_sha256: str = "CANDIDATE_SHA256_REQUIRED"
    source_p52_staged_packet_sha256: str = "P52_STAGED_PACKET_SHA256_REQUIRED"
    no_secret_logged_evidence_hash: str = "NO_SECRET_LOGGED_EVIDENCE_HASH_REQUIRED"
    secret_reference_metadata_only: bool = True
    key_fingerprint_only: bool = True
    redacted_evidence_only: bool = True
    no_secret_scan_completed: bool = True
    no_secret_scan_passed: bool = True
    no_secret_scan_match_count: int = 0
    raw_secret_values_included: bool = False
    api_key_value_included: bool = False
    api_secret_value_included: bool = False
    private_key_included: bool = False
    passphrase_included: bool = False
    raw_signed_payload_included: bool = False
    raw_request_body_included: bool = False
    raw_exchange_payload_included: bool = False
    no_secret_recheck_required_by_future_executor: bool = True
    checked_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p54_no_secret_evidence_attestation_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class AppendOnlyP7RegistryPolicyEvidenceTemplate:
    artifact_type: str = _ALLOWED_REGISTRY_POLICY_ARTIFACT_TYPE
    evidence_version: str = P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_VERSION
    evidence_template_id: str = "p54_append_only_p7_registry_policy_evidence_TEMPLATE_NO_WRITE"
    review_only: bool = True
    registry_name: str = _P7_REGISTRY_NAME
    registry_relative_path: str = _P7_REGISTRY_RELATIVE_PATH
    append_only: bool = True
    atomic_append_required: bool = True
    unique_record_id_required: bool = True
    record_sha256_required: bool = True
    duplicate_check_required: bool = True
    nonce_consume_and_append_must_be_atomic: bool = True
    overwrite_allowed: bool = False
    in_place_update_allowed: bool = False
    delete_allowed: bool = False
    truncate_allowed: bool = False
    registry_append_allowed_by_p54: bool = False
    registry_append_performed_by_p54: bool = False
    registry_overwrite_performed_by_p54: bool = False
    registry_delete_performed_by_p54: bool = False
    registry_policy_must_be_rechecked_by_future_executor: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p54_append_only_p7_registry_policy_evidence_sha256"] = sha256_json(payload)
        return payload


def validate_p54_final_guard_template(
    template: Mapping[str, Any] | SeparateP7ImportExecutorFinalGuardTemplate | None,
) -> dict[str, Any]:
    payload = template.to_dict() if isinstance(template, SeparateP7ImportExecutorFinalGuardTemplate) else dict(template or {})
    blockers: list[str] = []
    if payload.get("final_guard_version") != P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_VERSION:
        blockers.append("P54_TEMPLATE_VERSION_MISMATCH")
    for key in (
        "generated_by_review_package",
        "review_only",
        "final_guard_only",
        "executor_disabled_by_default",
        "p53_armed_boundary_required",
        "p53_embedded_hash_revalidation_required",
        "p52_staged_packet_required",
        "p52_embedded_hash_revalidation_required",
        "candidate_hash_chain_revalidation_required",
        "evidence_section_hash_revalidation_required",
        "fresh_p7_schema_dry_run_required",
        "no_secret_evidence_attestation_required",
        "one_time_nonce_freshness_evidence_required",
        "duplicate_import_lock_evidence_required",
        "append_only_p7_registry_policy_required",
        "atomic_nonce_consume_and_registry_append_required_by_future_executor",
        "final_guard_must_be_rechecked_immediately_by_future_executor",
        "p8_must_remain_waiting_after_p54",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P54_TEMPLATE_{key.upper()}_NOT_TRUE")
    for key in (
        "p7_import_executor_enablement_allowed_by_p54",
        "p7_import_execution_allowed_by_p54",
        "p7_report_persistence_allowed_by_p54",
        "p7_status_mutation_allowed_by_p54",
        "nonce_consumption_allowed_by_p54",
        "duplicate_lock_acquisition_allowed_by_p54",
        "registry_append_allowed_by_p54",
        "can_grant_runtime_authority",
        "can_enable_testnet_submit",
        "can_enable_live_canary",
        "can_enable_live_scaled",
        "order_endpoint_call_allowed_by_p54",
        "status_endpoint_call_allowed_by_p54",
        "cancel_endpoint_call_allowed_by_p54",
        "http_request_allowed_by_p54",
        "signature_creation_allowed_by_p54",
        "secret_access_allowed_by_p54",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P54_TEMPLATE_{key.upper()}_NOT_FALSE")
    validation = {
        "p54_final_guard_template_valid": not blockers,
        "p54_final_guard_template_block_reasons": sorted(dict.fromkeys(blockers)),
        "final_guard_template_id": payload.get("final_guard_template_id"),
    }
    validation["p54_final_guard_template_validation_sha256"] = sha256_json(validation)
    return validation


def validate_p53_armed_source(
    p53_report: Mapping[str, Any] | None,
    *,
    p52_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(p53_report or {})
    blockers: list[str] = []
    if not payload:
        return {
            "p53_source_present": False,
            "p53_source_valid_for_p54": False,
            "p53_source_block_reasons": [],
            "armed_boundary_packet": None,
        }
    if payload.get("artifact_type") != _ALLOWED_P53_REPORT_ARTIFACT_TYPE:
        blockers.append("P54_P53_SOURCE_ARTIFACT_TYPE_INVALID")
    if payload.get("status") != P53_ARMED_STATUS:
        blockers.append("P54_P53_SOURCE_STATUS_NOT_ARMED_REVIEW_ONLY_NO_IMPORT")
    if not _verify_embedded_hash(payload, "p53_operator_controlled_p7_import_action_boundary_sha256"):
        blockers.append("P54_P53_SOURCE_EMBEDDED_SHA256_INVALID")
    for key in ("review_only", "operator_controlled", "armed_boundary_only", "p7_import_action_boundary_armed"):
        if payload.get(key) is not True:
            blockers.append(f"P54_P53_SOURCE_{key.upper()}_NOT_TRUE")
    for key in (
        "runtime_authority_source",
        "p7_import_action_enabled",
        "p7_import_action_executed",
        "p7_report_persisted_by_p53",
        "p7_valid_status_written_by_p53",
        "p7_intake_execution_performed_by_p53",
        "actual_order_submission_performed",
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
            blockers.append(f"P54_P53_SOURCE_{key.upper()}_NOT_FALSE")
    armed_packet = dict(payload.get("armed_boundary_packet") or {})
    armed_validation = validate_armed_boundary_packet(armed_packet)
    blockers.extend(armed_validation.get("armed_boundary_packet_block_reasons") or [])
    if armed_packet.get("artifact_type") != _ALLOWED_P53_ARMED_PACKET_ARTIFACT_TYPE:
        blockers.append("P54_P53_ARMED_PACKET_ARTIFACT_TYPE_INVALID")
    if not _verify_embedded_hash(armed_packet, "p53_armed_p7_import_action_boundary_sha256"):
        blockers.append("P54_P53_ARMED_PACKET_EMBEDDED_SHA256_INVALID")
    if p52_report:
        staged_packet = dict((p52_report or {}).get("staged_packet") or {})
        expected_pairs = {
            "source_p52_staging_report_sha256": (p52_report or {}).get(
                "p52_p7_accepted_evidence_import_packet_staging_sha256"
            ),
            "source_p52_staged_packet_sha256": staged_packet.get("p52_staged_p7_import_packet_sha256"),
            "candidate_sha256": staged_packet.get("candidate_sha256"),
            "p7_input_preview_sha256": staged_packet.get("p7_input_preview_sha256"),
        }
        for key, expected in expected_pairs.items():
            if not expected or armed_packet.get(key) != expected:
                blockers.append(f"P54_P53_ARMED_PACKET_{key.upper()}_MISMATCH")
    blockers.extend(_walk_forbidden(payload))
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P54_P53_SOURCE_UNSAFE_TRUTHY_EXECUTION_FLAGS")
    validation = {
        "p53_source_present": True,
        "p53_source_valid_for_p54": not blockers,
        "p53_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "source_status": payload.get("status"),
        "source_p53_report_sha256": payload.get("p53_operator_controlled_p7_import_action_boundary_sha256"),
        "armed_boundary_packet": armed_packet if armed_packet else None,
        "armed_boundary_packet_validation": armed_validation,
        "armed_boundary_packet_sha256": armed_packet.get("p53_armed_p7_import_action_boundary_sha256"),
    }
    validation["p53_source_validation_sha256"] = sha256_json(validation)
    return validation


def validate_p52_source_and_candidate_chain(
    p52_report: Mapping[str, Any] | None,
    *,
    candidate: Mapping[str, Any] | None,
    p53_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(p52_report or {})
    candidate_payload = dict(candidate or {})
    blockers: list[str] = []
    if not payload:
        return {
            "p52_source_present": False,
            "p52_source_and_candidate_chain_valid": False,
            "p52_source_and_candidate_chain_block_reasons": [],
            "staged_packet": None,
        }
    if payload.get("artifact_type") != _ALLOWED_P52_REPORT_ARTIFACT_TYPE:
        blockers.append("P54_P52_SOURCE_ARTIFACT_TYPE_INVALID")
    native_source_validation = validate_p52_staged_source(payload)
    blockers.extend(native_source_validation.get("p52_source_block_reasons") or [])
    if not _verify_embedded_hash(payload, "p52_p7_accepted_evidence_import_packet_staging_sha256"):
        blockers.append("P54_P52_SOURCE_EMBEDDED_SHA256_INVALID")
    staged_packet = dict(payload.get("staged_packet") or {})
    staged_validation = validate_staged_p7_import_packet(staged_packet)
    blockers.extend(staged_validation.get("staged_packet_block_reasons") or [])
    if staged_packet.get("artifact_type") != _ALLOWED_P52_STAGED_PACKET_ARTIFACT_TYPE:
        blockers.append("P54_P52_STAGED_PACKET_ARTIFACT_TYPE_INVALID")
    if not _verify_embedded_hash(staged_packet, "p52_staged_p7_import_packet_sha256"):
        blockers.append("P54_P52_STAGED_PACKET_EMBEDDED_SHA256_INVALID")
    candidate_validation = validate_p52_candidate_for_staging(candidate_payload)
    blockers.extend(candidate_validation.get("candidate_block_reasons") or [])
    if not candidate_payload:
        blockers.append("P54_CANDIDATE_REQUIRED_FOR_FINAL_GUARD")
    candidate_sha256 = sha256_json(candidate_payload) if candidate_payload else None
    if candidate_sha256 != staged_packet.get("candidate_sha256"):
        blockers.append("P54_CANDIDATE_SHA256_MISMATCH_WITH_P52_STAGED_PACKET")
    preview = dict(candidate_payload.get("p7_input_preview") or {})
    if sha256_json(preview) != staged_packet.get("p7_input_preview_sha256"):
        blockers.append("P54_P7_INPUT_PREVIEW_SHA256_MISMATCH_WITH_P52_STAGED_PACKET")
    section_hashes = dict(staged_packet.get("evidence_section_hashes") or {})
    for section in _REQUIRED_CANDIDATE_SECTIONS:
        if section_hashes.get(section) != sha256_json(candidate_payload.get(section)):
            blockers.append(f"P54_CANDIDATE_SECTION_SHA256_MISMATCH:{section}")
    if p53_report:
        armed_packet = dict((p53_report or {}).get("armed_boundary_packet") or {})
        if armed_packet.get("source_p52_staging_report_sha256") != payload.get(
            "p52_p7_accepted_evidence_import_packet_staging_sha256"
        ):
            blockers.append("P54_P53_TO_P52_REPORT_SHA256_MISMATCH")
        if armed_packet.get("source_p52_staged_packet_sha256") != staged_packet.get(
            "p52_staged_p7_import_packet_sha256"
        ):
            blockers.append("P54_P53_TO_P52_STAGED_PACKET_SHA256_MISMATCH")
        if armed_packet.get("candidate_sha256") != candidate_sha256:
            blockers.append("P54_P53_TO_CANDIDATE_SHA256_MISMATCH")
    blockers.extend(_walk_forbidden(candidate_payload))
    validation = {
        "p52_source_present": True,
        "p52_source_and_candidate_chain_valid": not blockers,
        "p52_source_and_candidate_chain_block_reasons": sorted(dict.fromkeys(blockers)),
        "source_p52_report_sha256": payload.get("p52_p7_accepted_evidence_import_packet_staging_sha256"),
        "staged_packet": staged_packet if staged_packet else None,
        "staged_packet_sha256": staged_packet.get("p52_staged_p7_import_packet_sha256"),
        "candidate_sha256": candidate_sha256,
        "p7_input_preview_sha256": sha256_json(preview) if preview else None,
        "native_p52_source_validation": native_source_validation,
        "native_staged_packet_validation": staged_validation,
        "native_candidate_validation": candidate_validation,
        "all_candidate_section_hashes_match": not any(
            reason.startswith("P54_CANDIDATE_SECTION_SHA256_MISMATCH") for reason in blockers
        ),
    }
    validation["p52_source_and_candidate_chain_validation_sha256"] = sha256_json(validation)
    return validation


def _lock_key_material(*, candidate_sha256: str, staged_packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_sha256": candidate_sha256,
        "exchange_order_id": staged_packet.get("exchange_order_id"),
        "client_order_id": staged_packet.get("client_order_id"),
        "idempotency_key": staged_packet.get("idempotency_key"),
    }


def build_valid_nonce_freshness_evidence(p53_report: Mapping[str, Any]) -> dict[str, Any]:
    armed_packet = dict(p53_report.get("armed_boundary_packet") or {})
    evidence = OneTimeNonceFreshnessEvidenceTemplate(
        one_time_action_nonce_sha256=str(armed_packet.get("one_time_action_nonce_sha256") or ""),
        source_p53_armed_packet_sha256=str(armed_packet.get("p53_armed_p7_import_action_boundary_sha256") or ""),
    ).to_dict()
    evidence["p54_nonce_freshness_evidence_id"] = stable_id("p54_nonce_freshness_evidence", evidence, 24)
    evidence["p54_nonce_freshness_evidence_sha256"] = sha256_json(
        {key: value for key, value in evidence.items() if key != "p54_nonce_freshness_evidence_sha256"}
    )
    return evidence


def validate_nonce_freshness_evidence(
    evidence: Mapping[str, Any] | None,
    *,
    p53_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        return {
            "nonce_freshness_evidence_present": False,
            "nonce_freshness_evidence_valid": False,
            "nonce_freshness_evidence_block_reasons": ["P54_NONCE_FRESHNESS_EVIDENCE_MISSING"],
        }
    if payload.get("artifact_type") != _ALLOWED_NONCE_EVIDENCE_ARTIFACT_TYPE:
        blockers.append("P54_NONCE_EVIDENCE_ARTIFACT_TYPE_INVALID")
    if not _verify_embedded_hash(payload, "p54_nonce_freshness_evidence_sha256"):
        blockers.append("P54_NONCE_EVIDENCE_EMBEDDED_SHA256_INVALID")
    armed_packet = dict((p53_report or {}).get("armed_boundary_packet") or {})
    if payload.get("one_time_action_nonce_sha256") != armed_packet.get("one_time_action_nonce_sha256"):
        blockers.append("P54_NONCE_EVIDENCE_NONCE_SHA256_MISMATCH")
    if payload.get("source_p53_armed_packet_sha256") != armed_packet.get(
        "p53_armed_p7_import_action_boundary_sha256"
    ):
        blockers.append("P54_NONCE_EVIDENCE_P53_ARMED_PACKET_SHA256_MISMATCH")
    for key in (
        "review_only",
        "nonce_registry_checked",
        "nonce_fresh",
        "nonce_freshness_must_be_rechecked_by_future_executor",
        "nonce_registry_append_required_at_execution",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P54_NONCE_EVIDENCE_{key.upper()}_NOT_TRUE")
    for key in (
        "nonce_seen_before",
        "duplicate_nonce_detected",
        "nonce_consumed",
        "nonce_registry_append_performed_by_p54",
        "nonce_consumption_allowed_by_p54",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P54_NONCE_EVIDENCE_{key.upper()}_NOT_FALSE")
    if not _is_sha256_hex(payload.get("one_time_action_nonce_sha256")):
        blockers.append("P54_NONCE_EVIDENCE_NONCE_SHA256_INVALID")
    age = payload.get("age_seconds_at_guard")
    window = payload.get("freshness_window_seconds")
    if not isinstance(age, int) or age < 0:
        blockers.append("P54_NONCE_EVIDENCE_AGE_SECONDS_INVALID")
    if not isinstance(window, int) or window <= 0:
        blockers.append("P54_NONCE_EVIDENCE_FRESHNESS_WINDOW_INVALID")
    if isinstance(age, int) and isinstance(window, int) and age > window:
        blockers.append("P54_NONCE_EVIDENCE_STALE")
    validation = {
        "nonce_freshness_evidence_present": True,
        "nonce_freshness_evidence_valid": not blockers,
        "nonce_freshness_evidence_block_reasons": sorted(dict.fromkeys(blockers)),
        "one_time_action_nonce_sha256": payload.get("one_time_action_nonce_sha256"),
        "nonce_fresh": payload.get("nonce_fresh") is True,
        "nonce_consumed": payload.get("nonce_consumed") is True,
        "nonce_seen_before": payload.get("nonce_seen_before") is True,
    }
    validation["nonce_freshness_evidence_validation_sha256"] = sha256_json(validation)
    return validation


def build_valid_duplicate_import_lock_evidence(p52_report: Mapping[str, Any]) -> dict[str, Any]:
    staged_packet = dict(p52_report.get("staged_packet") or {})
    candidate_sha256 = str(staged_packet.get("candidate_sha256") or "")
    lock_key_sha256 = sha256_json(_lock_key_material(candidate_sha256=candidate_sha256, staged_packet=staged_packet))
    evidence = DuplicateImportLockEvidenceTemplate(
        candidate_sha256=candidate_sha256,
        source_p52_staged_packet_sha256=str(staged_packet.get("p52_staged_p7_import_packet_sha256") or ""),
        exchange_order_id=str(staged_packet.get("exchange_order_id") or ""),
        client_order_id=str(staged_packet.get("client_order_id") or ""),
        idempotency_key=str(staged_packet.get("idempotency_key") or ""),
        lock_key_sha256=lock_key_sha256,
    ).to_dict()
    evidence["p54_duplicate_import_lock_evidence_id"] = stable_id("p54_duplicate_import_lock_evidence", evidence, 24)
    evidence["p54_duplicate_import_lock_evidence_sha256"] = sha256_json(
        {key: value for key, value in evidence.items() if key != "p54_duplicate_import_lock_evidence_sha256"}
    )
    return evidence


def validate_duplicate_import_lock_evidence(
    evidence: Mapping[str, Any] | None,
    *,
    p52_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        return {
            "duplicate_import_lock_evidence_present": False,
            "duplicate_import_lock_evidence_valid": False,
            "duplicate_import_lock_evidence_block_reasons": ["P54_DUPLICATE_IMPORT_LOCK_EVIDENCE_MISSING"],
        }
    if payload.get("artifact_type") != _ALLOWED_DUPLICATE_LOCK_ARTIFACT_TYPE:
        blockers.append("P54_DUPLICATE_LOCK_EVIDENCE_ARTIFACT_TYPE_INVALID")
    if not _verify_embedded_hash(payload, "p54_duplicate_import_lock_evidence_sha256"):
        blockers.append("P54_DUPLICATE_LOCK_EVIDENCE_EMBEDDED_SHA256_INVALID")
    staged_packet = dict((p52_report or {}).get("staged_packet") or {})
    expected_pairs = {
        "candidate_sha256": staged_packet.get("candidate_sha256"),
        "source_p52_staged_packet_sha256": staged_packet.get("p52_staged_p7_import_packet_sha256"),
        "exchange_order_id": staged_packet.get("exchange_order_id"),
        "client_order_id": staged_packet.get("client_order_id"),
        "idempotency_key": staged_packet.get("idempotency_key"),
    }
    for key, expected in expected_pairs.items():
        if not expected or payload.get(key) != expected:
            blockers.append(f"P54_DUPLICATE_LOCK_EVIDENCE_{key.upper()}_MISMATCH")
    expected_lock_key = sha256_json(
        _lock_key_material(candidate_sha256=str(staged_packet.get("candidate_sha256") or ""), staged_packet=staged_packet)
    )
    if payload.get("lock_key_sha256") != expected_lock_key:
        blockers.append("P54_DUPLICATE_LOCK_EVIDENCE_LOCK_KEY_SHA256_MISMATCH")
    for key in (
        "review_only",
        "duplicate_registry_checked",
        "duplicate_import_lock_ready",
        "atomic_lock_acquisition_required_by_future_executor",
        "lock_release_on_failed_append_required",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P54_DUPLICATE_LOCK_EVIDENCE_{key.upper()}_NOT_TRUE")
    for key in (
        "duplicate_import_detected",
        "duplicate_order_id_detected",
        "duplicate_client_order_id_detected",
        "duplicate_idempotency_key_detected",
        "duplicate_import_lock_acquired",
        "duplicate_import_lock_acquisition_allowed_by_p54",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P54_DUPLICATE_LOCK_EVIDENCE_{key.upper()}_NOT_FALSE")
    if payload.get("existing_import_record_count") != 0:
        blockers.append("P54_DUPLICATE_LOCK_EVIDENCE_EXISTING_IMPORT_RECORD_COUNT_NOT_ZERO")
    validation = {
        "duplicate_import_lock_evidence_present": True,
        "duplicate_import_lock_evidence_valid": not blockers,
        "duplicate_import_lock_evidence_block_reasons": sorted(dict.fromkeys(blockers)),
        "lock_key_sha256": payload.get("lock_key_sha256"),
        "duplicate_import_detected": payload.get("duplicate_import_detected") is True,
        "duplicate_import_lock_ready": payload.get("duplicate_import_lock_ready") is True,
        "duplicate_import_lock_acquired": payload.get("duplicate_import_lock_acquired") is True,
    }
    validation["duplicate_import_lock_evidence_validation_sha256"] = sha256_json(validation)
    return validation


def build_valid_no_secret_evidence_attestation(p52_report: Mapping[str, Any]) -> dict[str, Any]:
    staged_packet = dict(p52_report.get("staged_packet") or {})
    evidence = NoSecretEvidenceAttestationTemplate(
        candidate_sha256=str(staged_packet.get("candidate_sha256") or ""),
        source_p52_staged_packet_sha256=str(staged_packet.get("p52_staged_p7_import_packet_sha256") or ""),
        no_secret_logged_evidence_hash=str(staged_packet.get("no_secret_logged_evidence_hash") or ""),
    ).to_dict()
    evidence["p54_no_secret_evidence_attestation_id"] = stable_id("p54_no_secret_evidence_attestation", evidence, 24)
    evidence["p54_no_secret_evidence_attestation_sha256"] = sha256_json(
        {key: value for key, value in evidence.items() if key != "p54_no_secret_evidence_attestation_sha256"}
    )
    return evidence


def validate_no_secret_evidence_attestation(
    evidence: Mapping[str, Any] | None,
    *,
    p52_report: Mapping[str, Any] | None,
    candidate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        return {
            "no_secret_evidence_attestation_present": False,
            "no_secret_evidence_attestation_valid": False,
            "no_secret_evidence_attestation_block_reasons": ["P54_NO_SECRET_EVIDENCE_ATTESTATION_MISSING"],
        }
    if payload.get("artifact_type") != _ALLOWED_NO_SECRET_ARTIFACT_TYPE:
        blockers.append("P54_NO_SECRET_EVIDENCE_ARTIFACT_TYPE_INVALID")
    if not _verify_embedded_hash(payload, "p54_no_secret_evidence_attestation_sha256"):
        blockers.append("P54_NO_SECRET_EVIDENCE_EMBEDDED_SHA256_INVALID")
    staged_packet = dict((p52_report or {}).get("staged_packet") or {})
    candidate_sha256 = sha256_json(dict(candidate or {})) if candidate else None
    expected_pairs = {
        "candidate_sha256": candidate_sha256,
        "source_p52_staged_packet_sha256": staged_packet.get("p52_staged_p7_import_packet_sha256"),
        "no_secret_logged_evidence_hash": staged_packet.get("no_secret_logged_evidence_hash"),
    }
    for key, expected in expected_pairs.items():
        if not expected or payload.get(key) != expected:
            blockers.append(f"P54_NO_SECRET_EVIDENCE_{key.upper()}_MISMATCH")
    for key in (
        "review_only",
        "secret_reference_metadata_only",
        "key_fingerprint_only",
        "redacted_evidence_only",
        "no_secret_scan_completed",
        "no_secret_scan_passed",
        "no_secret_recheck_required_by_future_executor",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P54_NO_SECRET_EVIDENCE_{key.upper()}_NOT_TRUE")
    for key in (
        "raw_secret_values_included",
        "api_key_value_included",
        "api_secret_value_included",
        "private_key_included",
        "passphrase_included",
        "raw_signed_payload_included",
        "raw_request_body_included",
        "raw_exchange_payload_included",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P54_NO_SECRET_EVIDENCE_{key.upper()}_NOT_FALSE")
    if payload.get("no_secret_scan_match_count") != 0:
        blockers.append("P54_NO_SECRET_EVIDENCE_SCAN_MATCH_COUNT_NOT_ZERO")
    if not _is_sha256_hex(payload.get("no_secret_logged_evidence_hash")):
        blockers.append("P54_NO_SECRET_EVIDENCE_HASH_INVALID")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "no_secret_evidence_attestation_present": True,
        "no_secret_evidence_attestation_valid": not blockers,
        "no_secret_evidence_attestation_block_reasons": sorted(dict.fromkeys(blockers)),
        "no_secret_scan_passed": payload.get("no_secret_scan_passed") is True,
        "no_secret_scan_match_count": payload.get("no_secret_scan_match_count"),
        "no_secret_logged_evidence_hash": payload.get("no_secret_logged_evidence_hash"),
    }
    validation["no_secret_evidence_attestation_validation_sha256"] = sha256_json(validation)
    return validation


def build_valid_append_only_registry_policy_evidence() -> dict[str, Any]:
    evidence = AppendOnlyP7RegistryPolicyEvidenceTemplate().to_dict()
    evidence["p54_append_only_p7_registry_policy_evidence_id"] = stable_id(
        "p54_append_only_p7_registry_policy_evidence", evidence, 24
    )
    evidence["p54_append_only_p7_registry_policy_evidence_sha256"] = sha256_json(
        {key: value for key, value in evidence.items() if key != "p54_append_only_p7_registry_policy_evidence_sha256"}
    )
    return evidence


def validate_append_only_registry_policy_evidence(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(evidence or {})
    blockers: list[str] = []
    if not payload:
        return {
            "append_only_registry_policy_evidence_present": False,
            "append_only_registry_policy_evidence_valid": False,
            "append_only_registry_policy_evidence_block_reasons": ["P54_APPEND_ONLY_REGISTRY_POLICY_EVIDENCE_MISSING"],
        }
    if payload.get("artifact_type") != _ALLOWED_REGISTRY_POLICY_ARTIFACT_TYPE:
        blockers.append("P54_REGISTRY_POLICY_ARTIFACT_TYPE_INVALID")
    if not _verify_embedded_hash(payload, "p54_append_only_p7_registry_policy_evidence_sha256"):
        blockers.append("P54_REGISTRY_POLICY_EMBEDDED_SHA256_INVALID")
    if payload.get("registry_name") != _P7_REGISTRY_NAME:
        blockers.append("P54_REGISTRY_POLICY_REGISTRY_NAME_INVALID")
    if payload.get("registry_relative_path") != _P7_REGISTRY_RELATIVE_PATH:
        blockers.append("P54_REGISTRY_POLICY_RELATIVE_PATH_INVALID")
    for key in (
        "review_only",
        "append_only",
        "atomic_append_required",
        "unique_record_id_required",
        "record_sha256_required",
        "duplicate_check_required",
        "nonce_consume_and_append_must_be_atomic",
        "registry_policy_must_be_rechecked_by_future_executor",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P54_REGISTRY_POLICY_{key.upper()}_NOT_TRUE")
    for key in (
        "overwrite_allowed",
        "in_place_update_allowed",
        "delete_allowed",
        "truncate_allowed",
        "registry_append_allowed_by_p54",
        "registry_append_performed_by_p54",
        "registry_overwrite_performed_by_p54",
        "registry_delete_performed_by_p54",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P54_REGISTRY_POLICY_{key.upper()}_NOT_FALSE")
    validation = {
        "append_only_registry_policy_evidence_present": True,
        "append_only_registry_policy_evidence_valid": not blockers,
        "append_only_registry_policy_evidence_block_reasons": sorted(dict.fromkeys(blockers)),
        "registry_name": payload.get("registry_name"),
        "registry_relative_path": payload.get("registry_relative_path"),
        "append_only": payload.get("append_only") is True,
        "registry_append_performed_by_p54": payload.get("registry_append_performed_by_p54") is True,
    }
    validation["append_only_registry_policy_evidence_validation_sha256"] = sha256_json(validation)
    return validation


def build_fresh_p7_schema_dry_run_validation(
    candidate: Mapping[str, Any] | None,
    *,
    cfg: AppConfig | None = None,
) -> dict[str, Any]:
    if not candidate:
        return {
            "fresh_p7_schema_dry_run_performed": False,
            "fresh_p7_schema_dry_run_valid": False,
            "fresh_p7_schema_dry_run_block_reasons": ["P54_FRESH_P7_SCHEMA_DRY_RUN_CANDIDATE_MISSING"],
        }
    result = build_p7_bridge_dry_run_result(dict(candidate), cfg=cfg)
    blockers: list[str] = []
    if result.get("p7_bridge_dry_run_performed") is not True:
        blockers.append("P54_FRESH_P7_SCHEMA_DRY_RUN_NOT_PERFORMED")
    if result.get("p7_would_accept_imported_evidence") is not True:
        blockers.append("P54_FRESH_P7_SCHEMA_DRY_RUN_NOT_ACCEPTED")
    if result.get("p7_dry_run_status") != P7_ACCEPT_STATUS:
        blockers.append("P54_FRESH_P7_SCHEMA_DRY_RUN_STATUS_INVALID")
    if result.get("p7_post_submit_chain_complete") is not True:
        blockers.append("P54_FRESH_P7_SCHEMA_DRY_RUN_CHAIN_INCOMPLETE")
    for key in (
        "p7_report_persisted_by_p51",
        "p7_valid_status_written_by_p51",
        "p7_signed_testnet_promotion_allowed",
        "p7_live_canary_execution_enabled",
        "p7_live_scaled_execution_enabled",
    ):
        if result.get(key) is not False:
            blockers.append(f"P54_FRESH_P7_SCHEMA_DRY_RUN_{key.upper()}_NOT_FALSE")
    validation = {
        "fresh_p7_schema_dry_run_performed": True,
        "fresh_p7_schema_dry_run_valid": not blockers,
        "fresh_p7_schema_dry_run_block_reasons": sorted(dict.fromkeys(blockers)),
        "p7_would_accept_imported_evidence": result.get("p7_would_accept_imported_evidence") is True,
        "p7_dry_run_status": result.get("p7_dry_run_status"),
        "p7_post_submit_chain_complete": result.get("p7_post_submit_chain_complete") is True,
        "p7_terminal_status_observed": result.get("p7_terminal_status_observed") is True,
        "p7_dry_run_report_sha256": result.get("p7_dry_run_report_sha256"),
        "p7_bridge_dry_run_result_sha256": result.get("p7_bridge_dry_run_result_sha256"),
        "p7_report_persisted_by_p54": False,
        "p7_valid_status_written_by_p54": False,
    }
    validation["fresh_p7_schema_dry_run_validation_sha256"] = sha256_json(validation)
    return validation


def build_final_guard_passed_packet(
    *,
    p53_report: Mapping[str, Any],
    p52_report: Mapping[str, Any],
    candidate: Mapping[str, Any],
    nonce_evidence: Mapping[str, Any],
    duplicate_lock_evidence: Mapping[str, Any],
    no_secret_evidence: Mapping[str, Any],
    registry_policy_evidence: Mapping[str, Any],
    p7_dry_run_validation: Mapping[str, Any],
) -> dict[str, Any]:
    armed_packet = dict(p53_report.get("armed_boundary_packet") or {})
    staged_packet = dict(p52_report.get("staged_packet") or {})
    packet = {
        "artifact_type": _ALLOWED_FINAL_GUARD_PACKET_ARTIFACT_TYPE,
        "final_guard_version": P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_VERSION,
        "status": STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED,
        "review_only": True,
        "final_guard_only": True,
        "executor_disabled": True,
        "cannot_execute_import": True,
        "cannot_be_used_as_runtime_authority": True,
        "final_guard_passed": True,
        "p7_import_executor_enabled": False,
        "p7_import_executor_action_allowed": False,
        "p7_import_executor_action_executed": False,
        "requires_separate_p7_import_executor_implementation": True,
        "requires_fresh_full_guard_revalidation_immediately_before_execution": True,
        "requires_atomic_duplicate_lock_acquisition": True,
        "requires_atomic_nonce_consume_and_append_only_registry_write": True,
        "requires_fail_closed_rollback_if_append_fails": True,
        "requires_exactly_one_p7_record": True,
        "source_p53_report_id": p53_report.get("p53_operator_controlled_p7_import_action_boundary_id"),
        "source_p53_report_sha256": p53_report.get("p53_operator_controlled_p7_import_action_boundary_sha256"),
        "source_p53_armed_packet_id": armed_packet.get("p53_armed_p7_import_action_boundary_id"),
        "source_p53_armed_packet_sha256": armed_packet.get("p53_armed_p7_import_action_boundary_sha256"),
        "source_p52_report_id": p52_report.get("p52_p7_accepted_evidence_import_packet_staging_id"),
        "source_p52_report_sha256": p52_report.get("p52_p7_accepted_evidence_import_packet_staging_sha256"),
        "source_p52_staged_packet_id": staged_packet.get("p52_staged_p7_import_packet_id"),
        "source_p52_staged_packet_sha256": staged_packet.get("p52_staged_p7_import_packet_sha256"),
        "candidate_sha256": sha256_json(dict(candidate)),
        "p7_input_preview_sha256": staged_packet.get("p7_input_preview_sha256"),
        "one_time_action_nonce_sha256": nonce_evidence.get("one_time_action_nonce_sha256"),
        "nonce_freshness_evidence_sha256": nonce_evidence.get("p54_nonce_freshness_evidence_sha256"),
        "duplicate_import_lock_key_sha256": duplicate_lock_evidence.get("lock_key_sha256"),
        "duplicate_import_lock_evidence_sha256": duplicate_lock_evidence.get(
            "p54_duplicate_import_lock_evidence_sha256"
        ),
        "no_secret_evidence_attestation_sha256": no_secret_evidence.get(
            "p54_no_secret_evidence_attestation_sha256"
        ),
        "append_only_registry_policy_evidence_sha256": registry_policy_evidence.get(
            "p54_append_only_p7_registry_policy_evidence_sha256"
        ),
        "fresh_p7_schema_dry_run_validation_sha256": p7_dry_run_validation.get(
            "fresh_p7_schema_dry_run_validation_sha256"
        ),
        "p7_dry_run_report_sha256": p7_dry_run_validation.get("p7_dry_run_report_sha256"),
        "p7_registry_name": _P7_REGISTRY_NAME,
        "p7_registry_relative_path": _P7_REGISTRY_RELATIVE_PATH,
        "p7_report_persisted_by_p54": False,
        "p7_valid_status_written_by_p54": False,
        "p7_intake_execution_performed_by_p54": False,
        "p7_registry_append_performed_by_p54": False,
        "p7_import_action_nonce_consumed_by_p54": False,
        "p7_duplicate_import_lock_acquired_by_p54": False,
        "p8_repeated_session_candidate_created": False,
        "created_at_utc": utc_now_canonical(),
        **_execution_false_payload(),
    }
    packet["p54_p7_import_executor_final_guard_packet_id"] = stable_id(
        "p54_p7_import_executor_final_guard_packet", packet, 24
    )
    packet["p54_p7_import_executor_final_guard_packet_sha256"] = sha256_json(packet)
    return packet


def validate_final_guard_passed_packet(packet: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(packet or {})
    blockers: list[str] = []
    if not payload:
        return {
            "final_guard_passed_packet_present": False,
            "final_guard_passed_packet_valid": False,
            "final_guard_passed_packet_block_reasons": [],
        }
    if payload.get("artifact_type") != _ALLOWED_FINAL_GUARD_PACKET_ARTIFACT_TYPE:
        blockers.append("P54_FINAL_GUARD_PACKET_ARTIFACT_TYPE_INVALID")
    if payload.get("status") != STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED:
        blockers.append("P54_FINAL_GUARD_PACKET_STATUS_INVALID")
    if not _verify_embedded_hash(payload, "p54_p7_import_executor_final_guard_packet_sha256"):
        blockers.append("P54_FINAL_GUARD_PACKET_EMBEDDED_SHA256_INVALID")
    for key in (
        "review_only",
        "final_guard_only",
        "executor_disabled",
        "cannot_execute_import",
        "cannot_be_used_as_runtime_authority",
        "final_guard_passed",
        "requires_separate_p7_import_executor_implementation",
        "requires_fresh_full_guard_revalidation_immediately_before_execution",
        "requires_atomic_duplicate_lock_acquisition",
        "requires_atomic_nonce_consume_and_append_only_registry_write",
        "requires_fail_closed_rollback_if_append_fails",
        "requires_exactly_one_p7_record",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P54_FINAL_GUARD_PACKET_{key.upper()}_NOT_TRUE")
    for key in (
        "p7_import_executor_enabled",
        "p7_import_executor_action_allowed",
        "p7_import_executor_action_executed",
        "p7_report_persisted_by_p54",
        "p7_valid_status_written_by_p54",
        "p7_intake_execution_performed_by_p54",
        "p7_registry_append_performed_by_p54",
        "p7_import_action_nonce_consumed_by_p54",
        "p7_duplicate_import_lock_acquired_by_p54",
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
            blockers.append(f"P54_FINAL_GUARD_PACKET_{key.upper()}_NOT_FALSE")
    for key in (
        "source_p53_report_sha256",
        "source_p53_armed_packet_sha256",
        "source_p52_report_sha256",
        "source_p52_staged_packet_sha256",
        "candidate_sha256",
        "p7_input_preview_sha256",
        "one_time_action_nonce_sha256",
        "nonce_freshness_evidence_sha256",
        "duplicate_import_lock_key_sha256",
        "duplicate_import_lock_evidence_sha256",
        "no_secret_evidence_attestation_sha256",
        "append_only_registry_policy_evidence_sha256",
        "fresh_p7_schema_dry_run_validation_sha256",
        "p7_dry_run_report_sha256",
    ):
        if not _is_sha256_hex(payload.get(key)):
            blockers.append(f"P54_FINAL_GUARD_PACKET_{key.upper()}_INVALID")
    blockers.extend(_walk_forbidden(payload))
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P54_FINAL_GUARD_PACKET_UNSAFE_TRUTHY_EXECUTION_FLAGS")
    validation = {
        "final_guard_passed_packet_present": True,
        "final_guard_passed_packet_valid": not blockers,
        "final_guard_passed_packet_block_reasons": sorted(dict.fromkeys(blockers)),
        "final_guard_packet_sha256": payload.get("p54_p7_import_executor_final_guard_packet_sha256"),
    }
    validation["final_guard_passed_packet_validation_sha256"] = sha256_json(validation)
    return validation


def build_p54_separate_p7_import_executor_final_guard_report(
    *,
    cfg: AppConfig | None = None,
    p53_report: Mapping[str, Any] | None = None,
    p52_report: Mapping[str, Any] | None = None,
    candidate: Mapping[str, Any] | None = None,
    nonce_freshness_evidence: Mapping[str, Any] | None = None,
    duplicate_import_lock_evidence: Mapping[str, Any] | None = None,
    no_secret_evidence_attestation: Mapping[str, Any] | None = None,
    append_only_registry_policy_evidence: Mapping[str, Any] | None = None,
    final_guard_template: Mapping[str, Any] | SeparateP7ImportExecutorFinalGuardTemplate | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p53_explicit = p53_report is not None
    p52_explicit = p52_report is not None
    candidate_explicit = candidate is not None
    evidence_explicit = any(
        item is not None
        for item in (
            nonce_freshness_evidence,
            duplicate_import_lock_evidence,
            no_secret_evidence_attestation,
            append_only_registry_policy_evidence,
        )
    )
    source_p53 = dict(p53_report or _read_latest_json(cfg, "p53_operator_controlled_p7_import_action_boundary_report.json"))
    source_p52 = dict(p52_report or _read_latest_json(cfg, "p52_p7_accepted_evidence_import_packet_staging_report.json"))
    candidate_payload = dict(candidate or {})
    template_payload = (
        final_guard_template.to_dict()
        if isinstance(final_guard_template, SeparateP7ImportExecutorFinalGuardTemplate)
        else dict(final_guard_template or SeparateP7ImportExecutorFinalGuardTemplate().to_dict())
    )
    evaluation_requested = bool(
        p53_explicit
        or p52_explicit
        or candidate_explicit
        or evidence_explicit
        or source_p53.get("status") == P53_ARMED_STATUS
    )

    template_validation = validate_p54_final_guard_template(template_payload)
    blockers = list(template_validation["p54_final_guard_template_block_reasons"])

    p53_validation: dict[str, Any] = {
        "p53_source_present": bool(source_p53),
        "p53_source_valid_for_p54": False,
        "p53_source_block_reasons": [],
    }
    p52_chain_validation: dict[str, Any] = {
        "p52_source_present": bool(source_p52),
        "p52_source_and_candidate_chain_valid": False,
        "p52_source_and_candidate_chain_block_reasons": [],
    }
    nonce_validation: dict[str, Any] = {
        "nonce_freshness_evidence_present": nonce_freshness_evidence is not None,
        "nonce_freshness_evidence_valid": False,
        "nonce_freshness_evidence_block_reasons": [],
    }
    duplicate_validation: dict[str, Any] = {
        "duplicate_import_lock_evidence_present": duplicate_import_lock_evidence is not None,
        "duplicate_import_lock_evidence_valid": False,
        "duplicate_import_lock_evidence_block_reasons": [],
    }
    no_secret_validation: dict[str, Any] = {
        "no_secret_evidence_attestation_present": no_secret_evidence_attestation is not None,
        "no_secret_evidence_attestation_valid": False,
        "no_secret_evidence_attestation_block_reasons": [],
    }
    registry_validation: dict[str, Any] = {
        "append_only_registry_policy_evidence_present": append_only_registry_policy_evidence is not None,
        "append_only_registry_policy_evidence_valid": False,
        "append_only_registry_policy_evidence_block_reasons": [],
    }
    p7_dry_run_validation: dict[str, Any] = {
        "fresh_p7_schema_dry_run_performed": False,
        "fresh_p7_schema_dry_run_valid": False,
        "fresh_p7_schema_dry_run_block_reasons": [],
    }

    if evaluation_requested:
        p53_validation = validate_p53_armed_source(source_p53, p52_report=source_p52)
        p52_chain_validation = validate_p52_source_and_candidate_chain(
            source_p52, candidate=candidate_payload, p53_report=source_p53
        )
        nonce_validation = validate_nonce_freshness_evidence(
            nonce_freshness_evidence, p53_report=source_p53
        )
        duplicate_validation = validate_duplicate_import_lock_evidence(
            duplicate_import_lock_evidence, p52_report=source_p52
        )
        no_secret_validation = validate_no_secret_evidence_attestation(
            no_secret_evidence_attestation, p52_report=source_p52, candidate=candidate_payload
        )
        registry_validation = validate_append_only_registry_policy_evidence(append_only_registry_policy_evidence)
        p7_dry_run_validation = build_fresh_p7_schema_dry_run_validation(candidate_payload, cfg=cfg)
        blockers.extend(p53_validation.get("p53_source_block_reasons") or [])
        blockers.extend(p52_chain_validation.get("p52_source_and_candidate_chain_block_reasons") or [])
        blockers.extend(nonce_validation.get("nonce_freshness_evidence_block_reasons") or [])
        blockers.extend(duplicate_validation.get("duplicate_import_lock_evidence_block_reasons") or [])
        blockers.extend(no_secret_validation.get("no_secret_evidence_attestation_block_reasons") or [])
        blockers.extend(registry_validation.get("append_only_registry_policy_evidence_block_reasons") or [])
        blockers.extend(p7_dry_run_validation.get("fresh_p7_schema_dry_run_block_reasons") or [])

    final_guard_passed = bool(evaluation_requested and not blockers)
    final_guard_packet: dict[str, Any] | None = None
    final_guard_packet_validation: dict[str, Any] = {
        "final_guard_passed_packet_present": False,
        "final_guard_passed_packet_valid": False,
        "final_guard_passed_packet_block_reasons": [],
    }
    if final_guard_passed:
        final_guard_packet = build_final_guard_passed_packet(
            p53_report=source_p53,
            p52_report=source_p52,
            candidate=candidate_payload,
            nonce_evidence=dict(nonce_freshness_evidence or {}),
            duplicate_lock_evidence=dict(duplicate_import_lock_evidence or {}),
            no_secret_evidence=dict(no_secret_evidence_attestation or {}),
            registry_policy_evidence=dict(append_only_registry_policy_evidence or {}),
            p7_dry_run_validation=p7_dry_run_validation,
        )
        final_guard_packet_validation = validate_final_guard_passed_packet(final_guard_packet)
        blockers.extend(final_guard_packet_validation.get("final_guard_passed_packet_block_reasons") or [])
        final_guard_passed = not blockers
        if not final_guard_passed:
            final_guard_packet = None

    if blockers:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif final_guard_passed:
        status = STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED
    else:
        status = STATUS_READY_REVIEW_ONLY_EXECUTOR_DISABLED

    report = {
        "artifact_type": "p54_separate_p7_import_executor_final_guard_report",
        "p54_final_guard_version": P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
        "review_only": True,
        "final_guard_only": True,
        "executor_disabled_by_default": True,
        "runtime_authority_source": False,
        "review_package_default_no_submit": True,
        "final_guard_evaluation_requested": evaluation_requested,
        "final_guard_template": template_payload,
        "final_guard_template_validation": template_validation,
        "source_p53_validation": p53_validation,
        "source_p52_candidate_chain_validation": p52_chain_validation,
        "nonce_freshness_evidence_validation": nonce_validation,
        "duplicate_import_lock_evidence_validation": duplicate_validation,
        "no_secret_evidence_attestation_validation": no_secret_validation,
        "append_only_registry_policy_evidence_validation": registry_validation,
        "fresh_p7_schema_dry_run_validation": p7_dry_run_validation,
        "final_guard_passed": final_guard_passed,
        "final_guard_packet": final_guard_packet,
        "final_guard_packet_validation": final_guard_packet_validation,
        "p7_import_executor_enabled": False,
        "p7_import_executor_action_allowed": False,
        "p7_import_executor_action_executed": False,
        "p7_import_action_enabled": False,
        "p7_import_action_executed": False,
        "p7_report_persisted_by_p54": False,
        "p7_valid_status_written_by_p54": False,
        "p7_intake_execution_performed_by_p54": False,
        "p7_registry_append_performed_by_p54": False,
        "p7_registry_overwrite_performed_by_p54": False,
        "p7_registry_delete_performed_by_p54": False,
        "p7_import_action_nonce_consumed_by_p54": False,
        "p7_duplicate_import_lock_acquired_by_p54": False,
        "p8_repeated_session_candidate_created": False,
        "actual_p7_import_still_requires_separate_executor_implementation_and_explicit_operator_control": True,
        "next_required_chain": [
            "operator reviews the P54 final guard packet and all referenced hashes",
            "a separately implemented P7 import executor must repeat every P54 check immediately before execution",
            "the future executor must atomically acquire the duplicate-import lock and consume the one-time nonce",
            "the future executor may append exactly one immutable P7 evidence record only if every fresh check still passes",
            "if registry append fails, nonce/lock state must fail closed and no valid P7 status may be published",
            "P8 remains waiting until multiple clean real P7 records exist",
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
        report["final_guard_passed"] = False
        report["final_guard_packet"] = None
        report["block_reasons"] = sorted(
            dict.fromkeys(report["block_reasons"] + ["P54_UNSAFE_TRUTHY_EXECUTION_FLAGS"])
        )
    report["p54_separate_p7_import_executor_final_guard_id"] = stable_id(
        "p54_separate_p7_import_executor_final_guard", report, 24
    )
    report["p54_separate_p7_import_executor_final_guard_sha256"] = sha256_json(report)
    return report


def build_valid_p54_guard_inputs_fixture(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    p52 = _valid_p52_source_fixture(cfg=cfg)
    request = build_valid_operator_request_fixture(p52)
    p53 = build_p53_operator_controlled_p7_import_action_boundary_report(
        cfg=cfg,
        p52_report=p52,
        operator_request=request,
    )
    # The fixture candidate is reconstructed through the same P52 fixture chain.
    from crypto_ai_system.execution.p7_accepted_evidence_import_packet_staging import _valid_candidate_fixture

    candidate = _valid_candidate_fixture()
    return {
        "p52_report": p52,
        "p53_report": p53,
        "candidate": candidate,
        "nonce_freshness_evidence": build_valid_nonce_freshness_evidence(p53),
        "duplicate_import_lock_evidence": build_valid_duplicate_import_lock_evidence(p52),
        "no_secret_evidence_attestation": build_valid_no_secret_evidence_attestation(p52),
        "append_only_registry_policy_evidence": build_valid_append_only_registry_policy_evidence(),
    }


def build_p54_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    valid = build_valid_p54_guard_inputs_fixture(cfg=cfg)
    cases: dict[str, dict[str, Any]] = {}

    unarmed_p53 = deepcopy(valid)
    unarmed_p53["p53_report"] = build_p53_operator_controlled_p7_import_action_boundary_report(
        cfg=cfg,
        p52_report=valid["p52_report"],
    )
    cases["p53_not_armed"] = unarmed_p53

    p53_hash_mismatch = deepcopy(valid)
    p53_hash_mismatch["p53_report"]["p53_operator_controlled_p7_import_action_boundary_sha256"] = "f" * 64
    cases["p53_report_hash_mismatch"] = p53_hash_mismatch

    nonce_seen = deepcopy(valid)
    nonce_seen["nonce_freshness_evidence"]["nonce_seen_before"] = True
    nonce_seen["nonce_freshness_evidence"]["p54_nonce_freshness_evidence_sha256"] = sha256_json(
        {
            key: value
            for key, value in nonce_seen["nonce_freshness_evidence"].items()
            if key != "p54_nonce_freshness_evidence_sha256"
        }
    )
    cases["nonce_seen_before"] = nonce_seen

    stale_nonce = deepcopy(valid)
    stale_nonce["nonce_freshness_evidence"]["age_seconds_at_guard"] = 301
    stale_nonce["nonce_freshness_evidence"]["p54_nonce_freshness_evidence_sha256"] = sha256_json(
        {
            key: value
            for key, value in stale_nonce["nonce_freshness_evidence"].items()
            if key != "p54_nonce_freshness_evidence_sha256"
        }
    )
    cases["stale_nonce"] = stale_nonce

    duplicate = deepcopy(valid)
    duplicate["duplicate_import_lock_evidence"]["duplicate_import_detected"] = True
    duplicate["duplicate_import_lock_evidence"]["existing_import_record_count"] = 1
    duplicate["duplicate_import_lock_evidence"]["p54_duplicate_import_lock_evidence_sha256"] = sha256_json(
        {
            key: value
            for key, value in duplicate["duplicate_import_lock_evidence"].items()
            if key != "p54_duplicate_import_lock_evidence_sha256"
        }
    )
    cases["duplicate_import_detected"] = duplicate

    p54_lock_acquisition = deepcopy(valid)
    p54_lock_acquisition["duplicate_import_lock_evidence"]["duplicate_import_lock_acquired"] = True
    p54_lock_acquisition["duplicate_import_lock_evidence"]["p54_duplicate_import_lock_evidence_sha256"] = sha256_json(
        {
            key: value
            for key, value in p54_lock_acquisition["duplicate_import_lock_evidence"].items()
            if key != "p54_duplicate_import_lock_evidence_sha256"
        }
    )
    cases["lock_acquired_by_p54_attempt"] = p54_lock_acquisition

    secret_scan_match = deepcopy(valid)
    secret_scan_match["no_secret_evidence_attestation"]["no_secret_scan_match_count"] = 1
    secret_scan_match["no_secret_evidence_attestation"]["no_secret_scan_passed"] = False
    secret_scan_match["no_secret_evidence_attestation"]["p54_no_secret_evidence_attestation_sha256"] = sha256_json(
        {
            key: value
            for key, value in secret_scan_match["no_secret_evidence_attestation"].items()
            if key != "p54_no_secret_evidence_attestation_sha256"
        }
    )
    cases["no_secret_scan_match"] = secret_scan_match

    registry_overwrite = deepcopy(valid)
    registry_overwrite["append_only_registry_policy_evidence"]["overwrite_allowed"] = True
    registry_overwrite["append_only_registry_policy_evidence"][
        "p54_append_only_p7_registry_policy_evidence_sha256"
    ] = sha256_json(
        {
            key: value
            for key, value in registry_overwrite["append_only_registry_policy_evidence"].items()
            if key != "p54_append_only_p7_registry_policy_evidence_sha256"
        }
    )
    cases["registry_overwrite_allowed"] = registry_overwrite

    candidate_hash_mismatch = deepcopy(valid)
    candidate_hash_mismatch["candidate"]["p7_input_preview"]["client_order_id"] = "mutated_client_order_id"
    cases["candidate_hash_mismatch"] = candidate_hash_mismatch

    missing_reconciliation = deepcopy(valid)
    missing_reconciliation["candidate"].pop("signed_testnet_reconciliation_evidence", None)
    cases["candidate_missing_reconciliation"] = missing_reconciliation

    results: dict[str, Any] = {}
    for name, inputs in cases.items():
        report = build_p54_separate_p7_import_executor_final_guard_report(cfg=cfg, **inputs)
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "final_guard_passed": report["final_guard_passed"],
            "p7_import_executor_enabled": report["p7_import_executor_enabled"],
            "p7_import_executor_action_executed": report["p7_import_executor_action_executed"],
            "p7_report_persisted_by_p54": report["p7_report_persisted_by_p54"],
        }

    valid_report = build_p54_separate_p7_import_executor_final_guard_report(cfg=cfg, **valid)
    payload = {
        "artifact_type": "p54_separate_p7_import_executor_final_guard_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(
            item["blocked_fail_closed"] for item in results.values()
        ),
        "fixture_results": results,
        "valid_fixture_final_guard_passed_executor_disabled": bool(
            valid_report["final_guard_passed"]
            and valid_report["status"] == STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED
            and valid_report["p7_import_executor_enabled"] is False
            and valid_report["p7_import_executor_action_executed"] is False
        ),
        "valid_fixture_status": valid_report["status"],
        "p7_import_executor_enabled": False,
        "p7_import_executor_action_executed": False,
        "p7_report_persisted_by_p54": False,
        "p7_valid_status_written_by_p54": False,
        **_execution_false_payload(),
    }
    payload["p54_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_p54_separate_p7_import_executor_final_guard(
    *,
    cfg: AppConfig | None = None,
    p53_report: Mapping[str, Any] | None = None,
    p52_report: Mapping[str, Any] | None = None,
    candidate: Mapping[str, Any] | None = None,
    nonce_freshness_evidence: Mapping[str, Any] | None = None,
    duplicate_import_lock_evidence: Mapping[str, Any] | None = None,
    no_secret_evidence_attestation: Mapping[str, Any] | None = None,
    append_only_registry_policy_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_p54_separate_p7_import_executor_final_guard_report(
        cfg=cfg,
        p53_report=p53_report,
        p52_report=p52_report,
        candidate=candidate,
        nonce_freshness_evidence=nonce_freshness_evidence,
        duplicate_import_lock_evidence=duplicate_import_lock_evidence,
        no_secret_evidence_attestation=no_secret_evidence_attestation,
        append_only_registry_policy_evidence=append_only_registry_policy_evidence,
    )
    final_guard_template = SeparateP7ImportExecutorFinalGuardTemplate().to_dict()
    nonce_template = OneTimeNonceFreshnessEvidenceTemplate().to_dict()
    duplicate_lock_template = DuplicateImportLockEvidenceTemplate().to_dict()
    no_secret_template = NoSecretEvidenceAttestationTemplate().to_dict()
    registry_policy_template = AppendOnlyP7RegistryPolicyEvidenceTemplate().to_dict()
    passed_packet_template = {
        "artifact_type": "p54_p7_import_executor_final_guard_PASSED_TEMPLATE_EXECUTOR_DISABLED",
        "status": STATUS_READY_REVIEW_ONLY_EXECUTOR_DISABLED,
        "review_only": True,
        "final_guard_only": True,
        "executor_disabled": True,
        "final_guard_passed": False,
        "p7_import_executor_enabled": False,
        "p7_import_executor_action_allowed": False,
        "p7_import_executor_action_executed": False,
        "p7_report_persisted_by_p54": False,
        "p7_valid_status_written_by_p54": False,
        "p7_registry_append_performed_by_p54": False,
        "p7_import_action_nonce_consumed_by_p54": False,
        "p7_duplicate_import_lock_acquired_by_p54": False,
        "requires_separate_p7_import_executor_implementation": True,
        "requires_fresh_full_guard_revalidation_immediately_before_execution": True,
        "source_p53_armed_packet_sha256": "P53_ARMED_PACKET_SHA256_REQUIRED",
        "source_p52_staged_packet_sha256": "P52_STAGED_PACKET_SHA256_REQUIRED",
        "candidate_sha256": "CANDIDATE_SHA256_REQUIRED",
        "one_time_action_nonce_sha256": "ONE_TIME_NONCE_SHA256_REQUIRED",
        **_execution_false_payload(),
    }
    passed_packet_template["p54_final_guard_passed_packet_template_sha256"] = sha256_json(passed_packet_template)
    negative = build_p54_negative_fixture_results(cfg=cfg)

    registry_record = {
        "artifact_type": "p54_separate_p7_import_executor_final_guard_registry_record",
        "p54_separate_p7_import_executor_final_guard_id": report[
            "p54_separate_p7_import_executor_final_guard_id"
        ],
        "p54_separate_p7_import_executor_final_guard_sha256": report[
            "p54_separate_p7_import_executor_final_guard_sha256"
        ],
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": True,
        "final_guard_only": True,
        "final_guard_passed": report["final_guard_passed"],
        "p7_import_executor_enabled": False,
        "p7_import_executor_action_executed": False,
        "p7_report_persisted_by_p54": False,
        "created_at_utc": report["created_at_utc"],
    }
    registry_record["p54_registry_record_sha256"] = sha256_json(registry_record)
    append_registry_record(
        registry_path(cfg, P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_REGISTRY_NAME),
        registry_record,
        registry_name=P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_REGISTRY_NAME,
    )

    summary = {
        "artifact_type": "p54_separate_p7_import_executor_final_guard_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": report["review_only"],
        "final_guard_only": report["final_guard_only"],
        "final_guard_evaluation_requested": report["final_guard_evaluation_requested"],
        "final_guard_passed": report["final_guard_passed"],
        "p7_import_executor_enabled": report["p7_import_executor_enabled"],
        "p7_import_executor_action_allowed": report["p7_import_executor_action_allowed"],
        "p7_import_executor_action_executed": report["p7_import_executor_action_executed"],
        "p7_report_persisted_by_p54": report["p7_report_persisted_by_p54"],
        "p7_valid_status_written_by_p54": report["p7_valid_status_written_by_p54"],
        "p7_registry_append_performed_by_p54": report["p7_registry_append_performed_by_p54"],
        "p7_import_action_nonce_consumed_by_p54": report["p7_import_action_nonce_consumed_by_p54"],
        "p7_duplicate_import_lock_acquired_by_p54": report["p7_duplicate_import_lock_acquired_by_p54"],
        "actual_order_submission_performed": report["actual_order_submission_performed"],
        "order_endpoint_called": report["order_endpoint_called"],
        "http_request_sent": report["http_request_sent"],
        "signature_created": report["signature_created"],
        "secret_value_accessed": report["secret_value_accessed"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "valid_fixture_final_guard_passed_executor_disabled": negative[
            "valid_fixture_final_guard_passed_executor_disabled"
        ],
        "p54_separate_p7_import_executor_final_guard_id": report[
            "p54_separate_p7_import_executor_final_guard_id"
        ],
        "p54_separate_p7_import_executor_final_guard_sha256": report[
            "p54_separate_p7_import_executor_final_guard_sha256"
        ],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p54_summary_sha256"] = sha256_json(summary)

    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p54_separate_p7_import_executor_final_guard")
    writes = {
        "p54_separate_p7_import_executor_final_guard_report.json": report,
        "p54_separate_p7_import_executor_final_guard_TEMPLATE_EXECUTOR_DISABLED.json": final_guard_template,
        "p54_one_time_nonce_freshness_evidence_TEMPLATE_NO_CONSUME.json": nonce_template,
        "p54_duplicate_import_lock_evidence_TEMPLATE_NO_LOCK.json": duplicate_lock_template,
        "p54_no_secret_evidence_attestation_TEMPLATE_REDACTED_ONLY.json": no_secret_template,
        "p54_append_only_p7_registry_policy_evidence_TEMPLATE_NO_WRITE.json": registry_policy_template,
        "p54_p7_import_executor_final_guard_PASSED_TEMPLATE_EXECUTOR_DISABLED.json": passed_packet_template,
        "p54_separate_p7_import_executor_final_guard_negative_fixture_results.json": negative,
        "p54_separate_p7_import_executor_final_guard_registry_record.json": registry_record,
        "p54_separate_p7_import_executor_final_guard_summary.json": summary,
    }
    for filename, payload in writes.items():
        atomic_write_json(latest / filename, payload)
        atomic_write_json(storage / filename, payload)
    return report


__all__ = [
    "P54_SEPARATE_P7_IMPORT_EXECUTOR_FINAL_GUARD_VERSION",
    "STATUS_READY_REVIEW_ONLY_EXECUTOR_DISABLED",
    "STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "SeparateP7ImportExecutorFinalGuardTemplate",
    "OneTimeNonceFreshnessEvidenceTemplate",
    "DuplicateImportLockEvidenceTemplate",
    "NoSecretEvidenceAttestationTemplate",
    "AppendOnlyP7RegistryPolicyEvidenceTemplate",
    "validate_p54_final_guard_template",
    "validate_p53_armed_source",
    "validate_p52_source_and_candidate_chain",
    "build_valid_nonce_freshness_evidence",
    "validate_nonce_freshness_evidence",
    "build_valid_duplicate_import_lock_evidence",
    "validate_duplicate_import_lock_evidence",
    "build_valid_no_secret_evidence_attestation",
    "validate_no_secret_evidence_attestation",
    "build_valid_append_only_registry_policy_evidence",
    "validate_append_only_registry_policy_evidence",
    "build_fresh_p7_schema_dry_run_validation",
    "build_final_guard_passed_packet",
    "validate_final_guard_passed_packet",
    "build_p54_separate_p7_import_executor_final_guard_report",
    "build_valid_p54_guard_inputs_fixture",
    "build_p54_negative_fixture_results",
    "persist_p54_separate_p7_import_executor_final_guard",
]
