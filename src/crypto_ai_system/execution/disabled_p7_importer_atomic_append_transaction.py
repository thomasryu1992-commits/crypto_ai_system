from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.execution.separate_p7_import_executor_final_guard import (
    STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED as P54_PASSED_STATUS,
    build_p54_separate_p7_import_executor_final_guard_report,
    build_valid_p54_guard_inputs_fixture,
    validate_final_guard_passed_packet,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION = (
    "p55_disabled_p7_importer_atomic_append_transaction_v1"
)
P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_REGISTRY_NAME = (
    "p55_disabled_p7_importer_atomic_append_transaction_registry"
)

STATUS_READY_REVIEW_ONLY_IMPORTER_DISABLED = (
    "P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_READY_REVIEW_ONLY_IMPORTER_DISABLED"
)
STATUS_DESIGN_VALID_REVIEW_ONLY_IMPORTER_DISABLED = (
    "P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_DESIGN_VALID_REVIEW_ONLY_IMPORTER_DISABLED"
)
STATUS_BLOCKED_FAIL_CLOSED = (
    "P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_BLOCKED_FAIL_CLOSED"
)

_ALLOWED_P54_REPORT_ARTIFACT_TYPE = "p54_separate_p7_import_executor_final_guard_report"
_ALLOWED_P54_PACKET_ARTIFACT_TYPE = "p54_p7_import_executor_final_guard_PASSED_NO_IMPORT"
_ALLOWED_INTERFACE_ARTIFACT_TYPE = "p55_disabled_p7_importer_interface"
_ALLOWED_TRANSACTION_DESIGN_ARTIFACT_TYPE = "p55_atomic_append_transaction_design"
_ALLOWED_BACKEND_EVIDENCE_ARTIFACT_TYPE = "p55_transaction_backend_capability_evidence"
_ALLOWED_DRY_RUN_ARTIFACT_TYPE = "p55_atomic_append_transaction_dry_run"

_REQUIRED_TRANSACTION_STEPS = (
    "freshly_revalidate_p54_final_guard",
    "begin_atomic_transaction",
    "acquire_duplicate_import_lock",
    "recheck_one_time_nonce_freshness",
    "consume_one_time_nonce",
    "construct_immutable_p7_record",
    "append_exactly_one_p7_record",
    "verify_p7_record_hash_and_unique_id",
    "commit_atomic_transaction",
    "release_duplicate_import_lock",
)

_REQUIRED_FAILURE_RULES = (
    "fail_before_commit_publishes_no_p7_valid_status",
    "append_failure_rolls_back_nonce_and_lock_state",
    "nonce_failure_appends_no_p7_record",
    "duplicate_lock_failure_consumes_no_nonce",
    "verification_failure_does_not_commit",
    "crash_recovery_uses_durable_transaction_journal",
)

_FORBIDDEN_FIELD_TOKENS = (
    "api_key_value",
    "api_secret_value",
    "secret_value",
    "private_key",
    "passphrase",
    "raw_signed_payload",
    "raw_request_body",
    "raw_exchange_payload",
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
    return expected == sha256_json({k: v for k, v in data.items() if k != hash_key})


def _walk_forbidden(obj: Any, *, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            key_l = str(key).lower()
            if any(token in key_l for token in _FORBIDDEN_FIELD_TOKENS):
                safe_boolean = isinstance(value, bool) and any(
                    marker in key_l
                    for marker in ("_included", "_accessed", "_logged", "_created", "_performed")
                )
                if not safe_boolean:
                    blockers.append(f"P55_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden(value, prefix=child))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, prefix=f"{prefix}[{idx}]"))
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
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "runtime_scheduler_enabled": False,
            "runtime_loop_started": False,
            "runtime_authority_granted": False,
            "runtime_mutation_performed": False,
            "p7_importer_enabled": False,
            "p7_importer_action_allowed": False,
            "p7_importer_action_executed": False,
            "p7_atomic_transaction_started": False,
            "p7_atomic_transaction_committed": False,
            "p7_atomic_transaction_rolled_back": False,
            "p7_duplicate_import_lock_acquired_by_p55": False,
            "p7_import_nonce_consumed_by_p55": False,
            "p7_registry_append_performed_by_p55": False,
            "p7_registry_verification_performed_by_p55": False,
            "p7_valid_status_written_by_p55": False,
            "p7_report_persisted_by_p55": False,
            "p7_import_record_created_by_p55": False,
            "p8_repeated_session_candidate_created": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        }
    )
    return payload


@dataclass(frozen=True)
class DisabledP7ImporterInterfaceTemplate:
    artifact_type: str = _ALLOWED_INTERFACE_ARTIFACT_TYPE
    interface_version: str = P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION
    interface_id: str = "p55_disabled_p7_importer_interface_TEMPLATE_NO_IMPORT"
    review_only: bool = True
    importer_disabled_by_default: bool = True
    interface_only: bool = True
    implementation_included: bool = False
    can_enable_importer: bool = False
    can_start_transaction: bool = False
    can_acquire_duplicate_lock: bool = False
    can_consume_nonce: bool = False
    can_append_p7_registry: bool = False
    can_write_p7_valid_status: bool = False
    can_commit_transaction: bool = False
    can_mutate_runtime: bool = False
    can_submit_orders: bool = False
    can_call_exchange_endpoints: bool = False
    can_create_signatures: bool = False
    can_access_secrets: bool = False
    disabled_method_behavior: str = "raise_fail_closed_disabled_importer_error"
    future_executor_must_be_separate_runtime_component: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p55_disabled_p7_importer_interface_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class AtomicAppendTransactionDesignTemplate:
    artifact_type: str = _ALLOWED_TRANSACTION_DESIGN_ARTIFACT_TYPE
    design_version: str = P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION
    design_id: str = "p55_atomic_append_transaction_design_TEMPLATE_NO_IMPORT"
    review_only: bool = True
    design_only: bool = True
    transaction_execution_allowed_by_p55: bool = False
    exact_step_order: tuple[str, ...] = _REQUIRED_TRANSACTION_STEPS
    required_failure_rules: tuple[str, ...] = _REQUIRED_FAILURE_RULES
    duplicate_lock_before_nonce_consume_required: bool = True
    nonce_consume_before_registry_append_required: bool = True
    exactly_one_append_required: bool = True
    immutable_record_required: bool = True
    unique_record_id_required: bool = True
    record_sha256_required: bool = True
    durable_transaction_journal_required: bool = True
    compare_and_set_or_serializable_transaction_required: bool = True
    crash_recovery_required: bool = True
    rollback_before_commit_required: bool = True
    publish_valid_status_only_after_commit: bool = True
    append_only_registry_required: bool = True
    overwrite_allowed: bool = False
    in_place_update_allowed: bool = False
    delete_allowed: bool = False
    partial_commit_allowed: bool = False
    best_effort_multi_file_write_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["exact_step_order"] = list(self.exact_step_order)
        payload["required_failure_rules"] = list(self.required_failure_rules)
        payload["p55_atomic_append_transaction_design_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class TransactionBackendCapabilityEvidenceTemplate:
    artifact_type: str = _ALLOWED_BACKEND_EVIDENCE_ARTIFACT_TYPE
    capability_version: str = P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION
    evidence_id: str = "p55_transaction_backend_capability_evidence_TEMPLATE_CURRENT_BACKEND_NOT_READY"
    review_only: bool = True
    current_backend_name: str = "jsonl_append_only_current"
    current_backend_multi_resource_atomic_transaction_supported: bool = False
    current_backend_compare_and_set_supported: bool = False
    current_backend_durable_distributed_lock_supported: bool = False
    current_backend_transaction_rollback_supported: bool = False
    current_backend_durable_transaction_journal_supported: bool = False
    current_backend_crash_recovery_supported: bool = False
    current_backend_safe_for_real_p7_import: bool = False
    current_backend_blocks_actual_import: bool = True
    future_backend_transaction_capability_required: bool = True
    future_backend_must_prove_atomic_lock_nonce_append_commit: bool = True
    actual_import_ready: bool = False
    capability_evidence_is_not_runtime_authority: bool = True
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p55_transaction_backend_capability_evidence_sha256"] = sha256_json(payload)
        return payload


def validate_disabled_importer_interface(payload: Mapping[str, Any] | DisabledP7ImporterInterfaceTemplate | None) -> dict[str, Any]:
    data = payload.to_dict() if isinstance(payload, DisabledP7ImporterInterfaceTemplate) else dict(payload or {})
    blockers: list[str] = []
    if data.get("artifact_type") != _ALLOWED_INTERFACE_ARTIFACT_TYPE:
        blockers.append("P55_IMPORTER_INTERFACE_ARTIFACT_TYPE_INVALID")
    if data.get("interface_version") != P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION:
        blockers.append("P55_IMPORTER_INTERFACE_VERSION_INVALID")
    if not _verify_embedded_hash(data, "p55_disabled_p7_importer_interface_sha256"):
        blockers.append("P55_IMPORTER_INTERFACE_EMBEDDED_SHA256_INVALID")
    for key in (
        "review_only",
        "importer_disabled_by_default",
        "interface_only",
        "future_executor_must_be_separate_runtime_component",
    ):
        if data.get(key) is not True:
            blockers.append(f"P55_IMPORTER_INTERFACE_{key.upper()}_NOT_TRUE")
    for key in (
        "implementation_included",
        "can_enable_importer",
        "can_start_transaction",
        "can_acquire_duplicate_lock",
        "can_consume_nonce",
        "can_append_p7_registry",
        "can_write_p7_valid_status",
        "can_commit_transaction",
        "can_mutate_runtime",
        "can_submit_orders",
        "can_call_exchange_endpoints",
        "can_create_signatures",
        "can_access_secrets",
    ):
        if data.get(key) is not False:
            blockers.append(f"P55_IMPORTER_INTERFACE_{key.upper()}_NOT_FALSE")
    if data.get("disabled_method_behavior") != "raise_fail_closed_disabled_importer_error":
        blockers.append("P55_IMPORTER_INTERFACE_DISABLED_METHOD_BEHAVIOR_INVALID")
    blockers.extend(_walk_forbidden(data))
    result = {
        "disabled_importer_interface_valid": not blockers,
        "disabled_importer_interface_block_reasons": sorted(dict.fromkeys(blockers)),
        "importer_disabled_by_default": data.get("importer_disabled_by_default") is True,
        "implementation_included": data.get("implementation_included") is True,
    }
    result["disabled_importer_interface_validation_sha256"] = sha256_json(result)
    return result


def validate_atomic_append_transaction_design(
    payload: Mapping[str, Any] | AtomicAppendTransactionDesignTemplate | None,
) -> dict[str, Any]:
    data = payload.to_dict() if isinstance(payload, AtomicAppendTransactionDesignTemplate) else dict(payload or {})
    blockers: list[str] = []
    if data.get("artifact_type") != _ALLOWED_TRANSACTION_DESIGN_ARTIFACT_TYPE:
        blockers.append("P55_TRANSACTION_DESIGN_ARTIFACT_TYPE_INVALID")
    if data.get("design_version") != P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION:
        blockers.append("P55_TRANSACTION_DESIGN_VERSION_INVALID")
    if not _verify_embedded_hash(data, "p55_atomic_append_transaction_design_sha256"):
        blockers.append("P55_TRANSACTION_DESIGN_EMBEDDED_SHA256_INVALID")
    if tuple(data.get("exact_step_order") or ()) != _REQUIRED_TRANSACTION_STEPS:
        blockers.append("P55_TRANSACTION_DESIGN_STEP_ORDER_INVALID")
    if set(data.get("required_failure_rules") or ()) != set(_REQUIRED_FAILURE_RULES):
        blockers.append("P55_TRANSACTION_DESIGN_FAILURE_RULES_INVALID")
    for key in (
        "review_only",
        "design_only",
        "duplicate_lock_before_nonce_consume_required",
        "nonce_consume_before_registry_append_required",
        "exactly_one_append_required",
        "immutable_record_required",
        "unique_record_id_required",
        "record_sha256_required",
        "durable_transaction_journal_required",
        "compare_and_set_or_serializable_transaction_required",
        "crash_recovery_required",
        "rollback_before_commit_required",
        "publish_valid_status_only_after_commit",
        "append_only_registry_required",
    ):
        if data.get(key) is not True:
            blockers.append(f"P55_TRANSACTION_DESIGN_{key.upper()}_NOT_TRUE")
    for key in (
        "transaction_execution_allowed_by_p55",
        "overwrite_allowed",
        "in_place_update_allowed",
        "delete_allowed",
        "partial_commit_allowed",
        "best_effort_multi_file_write_allowed",
    ):
        if data.get(key) is not False:
            blockers.append(f"P55_TRANSACTION_DESIGN_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(data))
    result = {
        "atomic_append_transaction_design_valid": not blockers,
        "atomic_append_transaction_design_block_reasons": sorted(dict.fromkeys(blockers)),
        "exact_step_order_valid": tuple(data.get("exact_step_order") or ()) == _REQUIRED_TRANSACTION_STEPS,
        "atomicity_required": data.get("compare_and_set_or_serializable_transaction_required") is True,
    }
    result["atomic_append_transaction_design_validation_sha256"] = sha256_json(result)
    return result


def validate_backend_capability_evidence(
    payload: Mapping[str, Any] | TransactionBackendCapabilityEvidenceTemplate | None,
) -> dict[str, Any]:
    data = (
        payload.to_dict()
        if isinstance(payload, TransactionBackendCapabilityEvidenceTemplate)
        else dict(payload or {})
    )
    blockers: list[str] = []
    if data.get("artifact_type") != _ALLOWED_BACKEND_EVIDENCE_ARTIFACT_TYPE:
        blockers.append("P55_BACKEND_CAPABILITY_ARTIFACT_TYPE_INVALID")
    if data.get("capability_version") != P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION:
        blockers.append("P55_BACKEND_CAPABILITY_VERSION_INVALID")
    if not _verify_embedded_hash(data, "p55_transaction_backend_capability_evidence_sha256"):
        blockers.append("P55_BACKEND_CAPABILITY_EMBEDDED_SHA256_INVALID")
    for key in (
        "review_only",
        "current_backend_blocks_actual_import",
        "future_backend_transaction_capability_required",
        "future_backend_must_prove_atomic_lock_nonce_append_commit",
        "capability_evidence_is_not_runtime_authority",
    ):
        if data.get(key) is not True:
            blockers.append(f"P55_BACKEND_CAPABILITY_{key.upper()}_NOT_TRUE")
    for key in (
        "current_backend_multi_resource_atomic_transaction_supported",
        "current_backend_compare_and_set_supported",
        "current_backend_durable_distributed_lock_supported",
        "current_backend_transaction_rollback_supported",
        "current_backend_durable_transaction_journal_supported",
        "current_backend_crash_recovery_supported",
        "current_backend_safe_for_real_p7_import",
        "actual_import_ready",
    ):
        if data.get(key) is not False:
            blockers.append(f"P55_BACKEND_CAPABILITY_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden(data))
    result = {
        "backend_capability_evidence_valid": not blockers,
        "backend_capability_evidence_block_reasons": sorted(dict.fromkeys(blockers)),
        "current_backend_safe_for_real_p7_import": data.get("current_backend_safe_for_real_p7_import") is True,
        "current_backend_blocks_actual_import": data.get("current_backend_blocks_actual_import") is True,
        "actual_import_ready": data.get("actual_import_ready") is True,
    }
    result["backend_capability_evidence_validation_sha256"] = sha256_json(result)
    return result


def validate_p54_source(p54_report: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(p54_report or {})
    blockers: list[str] = []
    if not data:
        return {
            "p54_source_present": False,
            "p54_source_valid_for_p55": False,
            "p54_source_block_reasons": [],
            "final_guard_packet": None,
        }
    if data.get("artifact_type") != _ALLOWED_P54_REPORT_ARTIFACT_TYPE:
        blockers.append("P55_P54_SOURCE_ARTIFACT_TYPE_INVALID")
    if data.get("status") != P54_PASSED_STATUS:
        blockers.append("P55_P54_SOURCE_STATUS_NOT_FINAL_GUARD_PASSED")
    if not _verify_embedded_hash(data, "p54_separate_p7_import_executor_final_guard_sha256"):
        blockers.append("P55_P54_SOURCE_EMBEDDED_SHA256_INVALID")
    for key in ("review_only", "final_guard_only", "final_guard_passed"):
        if data.get(key) is not True:
            blockers.append(f"P55_P54_SOURCE_{key.upper()}_NOT_TRUE")
    for key in (
        "p7_import_executor_enabled",
        "p7_import_executor_action_allowed",
        "p7_import_executor_action_executed",
        "p7_registry_append_performed_by_p54",
        "p7_import_action_nonce_consumed_by_p54",
        "p7_duplicate_import_lock_acquired_by_p54",
        "actual_order_submission_performed",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "secret_value_accessed",
        "runtime_authority_granted",
        "live_canary_execution_enabled",
        "live_scaled_execution_enabled",
    ):
        if data.get(key) is not False:
            blockers.append(f"P55_P54_SOURCE_{key.upper()}_NOT_FALSE")
    packet = dict(data.get("final_guard_packet") or {})
    packet_validation = validate_final_guard_passed_packet(packet)
    blockers.extend(packet_validation.get("final_guard_passed_packet_block_reasons") or [])
    if packet.get("artifact_type") != _ALLOWED_P54_PACKET_ARTIFACT_TYPE:
        blockers.append("P55_P54_FINAL_GUARD_PACKET_ARTIFACT_TYPE_INVALID")
    blockers.extend(_walk_forbidden(data))
    result = {
        "p54_source_present": True,
        "p54_source_valid_for_p55": not blockers,
        "p54_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "final_guard_packet": packet if not blockers else None,
        "p54_source_sha256": data.get("p54_separate_p7_import_executor_final_guard_sha256"),
        "p54_final_guard_packet_sha256": packet.get("p54_p7_import_executor_final_guard_packet_sha256"),
    }
    result["p54_source_validation_sha256"] = sha256_json(result)
    return result


def build_atomic_append_dry_run(
    *,
    p54_report: Mapping[str, Any],
    interface: Mapping[str, Any],
    design: Mapping[str, Any],
    backend_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    packet = dict(p54_report.get("final_guard_packet") or {})
    steps = [
        {
            "sequence": idx + 1,
            "step": step,
            "simulated_only": True,
            "performed": False,
            "mutation_performed": False,
        }
        for idx, step in enumerate(_REQUIRED_TRANSACTION_STEPS)
    ]
    payload = {
        "artifact_type": _ALLOWED_DRY_RUN_ARTIFACT_TYPE,
        "dry_run_version": P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION,
        "status": "P55_ATOMIC_APPEND_TRANSACTION_DRY_RUN_VALID_NO_MUTATION",
        "review_only": True,
        "dry_run_only": True,
        "source_p54_report_sha256": p54_report.get("p54_separate_p7_import_executor_final_guard_sha256"),
        "source_p54_final_guard_packet_sha256": packet.get("p54_p7_import_executor_final_guard_packet_sha256"),
        "source_candidate_sha256": packet.get("candidate_sha256"),
        "source_nonce_sha256": packet.get("one_time_action_nonce_sha256"),
        "disabled_importer_interface_sha256": interface.get("p55_disabled_p7_importer_interface_sha256"),
        "transaction_design_sha256": design.get("p55_atomic_append_transaction_design_sha256"),
        "backend_capability_evidence_sha256": backend_evidence.get(
            "p55_transaction_backend_capability_evidence_sha256"
        ),
        "transaction_steps": steps,
        "current_backend_safe_for_real_p7_import": False,
        "current_backend_blocks_actual_import": True,
        "actual_import_ready": False,
        "transaction_started": False,
        "duplicate_lock_acquired": False,
        "nonce_consumed": False,
        "p7_record_constructed": False,
        "p7_registry_append_performed": False,
        "p7_record_verified": False,
        "transaction_committed": False,
        "transaction_rolled_back": False,
        "p7_valid_status_written": False,
        "runtime_mutation_performed": False,
        "created_at_utc": utc_now_canonical(),
        **_execution_false_payload(),
    }
    payload["p55_atomic_append_transaction_dry_run_id"] = stable_id(
        "p55_atomic_append_transaction_dry_run", payload, 24
    )
    payload["p55_atomic_append_transaction_dry_run_sha256"] = sha256_json(payload)
    return payload


def validate_atomic_append_dry_run(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(payload or {})
    blockers: list[str] = []
    if data.get("artifact_type") != _ALLOWED_DRY_RUN_ARTIFACT_TYPE:
        blockers.append("P55_DRY_RUN_ARTIFACT_TYPE_INVALID")
    if not _verify_embedded_hash(data, "p55_atomic_append_transaction_dry_run_sha256"):
        blockers.append("P55_DRY_RUN_EMBEDDED_SHA256_INVALID")
    if data.get("status") != "P55_ATOMIC_APPEND_TRANSACTION_DRY_RUN_VALID_NO_MUTATION":
        blockers.append("P55_DRY_RUN_STATUS_INVALID")
    for key in ("review_only", "dry_run_only", "current_backend_blocks_actual_import"):
        if data.get(key) is not True:
            blockers.append(f"P55_DRY_RUN_{key.upper()}_NOT_TRUE")
    for key in (
        "current_backend_safe_for_real_p7_import",
        "actual_import_ready",
        "transaction_started",
        "duplicate_lock_acquired",
        "nonce_consumed",
        "p7_record_constructed",
        "p7_registry_append_performed",
        "p7_record_verified",
        "transaction_committed",
        "transaction_rolled_back",
        "p7_valid_status_written",
        "runtime_mutation_performed",
    ):
        if data.get(key) is not False:
            blockers.append(f"P55_DRY_RUN_{key.upper()}_NOT_FALSE")
    steps = list(data.get("transaction_steps") or [])
    if [item.get("step") for item in steps] != list(_REQUIRED_TRANSACTION_STEPS):
        blockers.append("P55_DRY_RUN_STEP_ORDER_INVALID")
    for item in steps:
        if item.get("simulated_only") is not True or item.get("performed") is not False or item.get(
            "mutation_performed"
        ) is not False:
            blockers.append("P55_DRY_RUN_STEP_MUTATION_OR_EXECUTION_DETECTED")
            break
    for key in (
        "source_p54_report_sha256",
        "source_p54_final_guard_packet_sha256",
        "source_candidate_sha256",
        "source_nonce_sha256",
        "disabled_importer_interface_sha256",
        "transaction_design_sha256",
        "backend_capability_evidence_sha256",
    ):
        if not _is_sha256_hex(data.get(key)):
            blockers.append(f"P55_DRY_RUN_{key.upper()}_INVALID")
    blockers.extend(_walk_forbidden(data))
    result = {
        "atomic_append_dry_run_valid": not blockers,
        "atomic_append_dry_run_block_reasons": sorted(dict.fromkeys(blockers)),
        "transaction_steps_simulated_only": not any(
            item.get("performed") is True or item.get("mutation_performed") is True for item in steps
        ),
        "actual_import_ready": data.get("actual_import_ready") is True,
    }
    result["atomic_append_dry_run_validation_sha256"] = sha256_json(result)
    return result


def build_p55_disabled_p7_importer_atomic_append_transaction_report(
    *,
    cfg: AppConfig | None = None,
    p54_report: Mapping[str, Any] | None = None,
    importer_interface: Mapping[str, Any] | DisabledP7ImporterInterfaceTemplate | None = None,
    transaction_design: Mapping[str, Any] | AtomicAppendTransactionDesignTemplate | None = None,
    backend_capability_evidence: Mapping[str, Any] | TransactionBackendCapabilityEvidenceTemplate | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    explicit = any(
        item is not None
        for item in (p54_report, importer_interface, transaction_design, backend_capability_evidence)
    )
    source_p54 = dict(
        p54_report
        or _read_latest_json(cfg, "p54_separate_p7_import_executor_final_guard_report.json")
    )
    interface_payload = (
        importer_interface.to_dict()
        if isinstance(importer_interface, DisabledP7ImporterInterfaceTemplate)
        else dict(importer_interface or DisabledP7ImporterInterfaceTemplate().to_dict())
    )
    design_payload = (
        transaction_design.to_dict()
        if isinstance(transaction_design, AtomicAppendTransactionDesignTemplate)
        else dict(transaction_design or AtomicAppendTransactionDesignTemplate().to_dict())
    )
    backend_payload = (
        backend_capability_evidence.to_dict()
        if isinstance(backend_capability_evidence, TransactionBackendCapabilityEvidenceTemplate)
        else dict(backend_capability_evidence or TransactionBackendCapabilityEvidenceTemplate().to_dict())
    )
    evaluation_requested = bool(explicit or source_p54.get("status") == P54_PASSED_STATUS)

    interface_validation = validate_disabled_importer_interface(interface_payload)
    design_validation = validate_atomic_append_transaction_design(design_payload)
    backend_validation = validate_backend_capability_evidence(backend_payload)
    p54_validation = validate_p54_source(source_p54) if evaluation_requested else {
        "p54_source_present": bool(source_p54),
        "p54_source_valid_for_p55": False,
        "p54_source_block_reasons": [],
        "final_guard_packet": None,
    }

    blockers: list[str] = []
    blockers.extend(interface_validation["disabled_importer_interface_block_reasons"])
    blockers.extend(design_validation["atomic_append_transaction_design_block_reasons"])
    blockers.extend(backend_validation["backend_capability_evidence_block_reasons"])
    if evaluation_requested:
        blockers.extend(p54_validation.get("p54_source_block_reasons") or [])

    dry_run: dict[str, Any] | None = None
    dry_run_validation = {
        "atomic_append_dry_run_valid": False,
        "atomic_append_dry_run_block_reasons": [],
    }
    design_valid = bool(evaluation_requested and not blockers)
    if design_valid:
        dry_run = build_atomic_append_dry_run(
            p54_report=source_p54,
            interface=interface_payload,
            design=design_payload,
            backend_evidence=backend_payload,
        )
        dry_run_validation = validate_atomic_append_dry_run(dry_run)
        blockers.extend(dry_run_validation["atomic_append_dry_run_block_reasons"])
        design_valid = not blockers
        if not design_valid:
            dry_run = None

    if blockers:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif design_valid:
        status = STATUS_DESIGN_VALID_REVIEW_ONLY_IMPORTER_DISABLED
    else:
        status = STATUS_READY_REVIEW_ONLY_IMPORTER_DISABLED

    report = {
        "artifact_type": "p55_disabled_p7_importer_atomic_append_transaction_report",
        "p55_version": P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
        "review_only": True,
        "design_only": True,
        "importer_disabled_by_default": True,
        "runtime_authority_source": False,
        "review_package_default_no_submit": True,
        "evaluation_requested": evaluation_requested,
        "source_p54_validation": p54_validation,
        "disabled_importer_interface": interface_payload,
        "disabled_importer_interface_validation": interface_validation,
        "atomic_append_transaction_design": design_payload,
        "atomic_append_transaction_design_validation": design_validation,
        "transaction_backend_capability_evidence": backend_payload,
        "transaction_backend_capability_evidence_validation": backend_validation,
        "atomic_append_transaction_dry_run": dry_run,
        "atomic_append_transaction_dry_run_validation": dry_run_validation,
        "transaction_design_valid": design_valid,
        "current_backend_transaction_ready": False,
        "current_backend_safe_for_real_p7_import": False,
        "actual_p7_import_ready": False,
        "p7_importer_enabled": False,
        "p7_importer_action_allowed": False,
        "p7_importer_action_executed": False,
        "p7_atomic_transaction_started": False,
        "p7_atomic_transaction_committed": False,
        "p7_atomic_transaction_rolled_back": False,
        "p7_duplicate_import_lock_acquired_by_p55": False,
        "p7_import_nonce_consumed_by_p55": False,
        "p7_registry_append_performed_by_p55": False,
        "p7_registry_verification_performed_by_p55": False,
        "p7_valid_status_written_by_p55": False,
        "p7_report_persisted_by_p55": False,
        "p7_import_record_created_by_p55": False,
        "p7_internal_design_chain_closed_after_p55": design_valid,
        "remaining_real_p7_gate": (
            "external signed-testnet submit evidence plus a separately approved transactional importer backend"
        ),
        "next_required_chain": [
            "stop adding review-only P7 wrapper phases after P55",
            "obtain one real signed-testnet external-runtime evidence bundle under separate operator approval",
            "provide a transaction-capable backend with durable lock, nonce, journal, rollback, and atomic append guarantees",
            "run P50-P54 checks against the real redacted evidence",
            "only then perform one separately approved P7 import transaction",
            "after multiple clean real P7 records, proceed to P8 repeated-session validation",
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
        report["transaction_design_valid"] = False
        report["atomic_append_transaction_dry_run"] = None
        report["p7_internal_design_chain_closed_after_p55"] = False
        report["block_reasons"] = sorted(
            dict.fromkeys(report["block_reasons"] + ["P55_UNSAFE_TRUTHY_EXECUTION_FLAGS"])
        )
    report["p55_disabled_p7_importer_atomic_append_transaction_id"] = stable_id(
        "p55_disabled_p7_importer_atomic_append_transaction", report, 24
    )
    report["p55_disabled_p7_importer_atomic_append_transaction_sha256"] = sha256_json(report)
    return report


def build_valid_p55_inputs_fixture(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    p54_inputs = build_valid_p54_guard_inputs_fixture(cfg=cfg)
    p54_report = build_p54_separate_p7_import_executor_final_guard_report(cfg=cfg, **p54_inputs)
    return {
        "p54_report": p54_report,
        "importer_interface": DisabledP7ImporterInterfaceTemplate().to_dict(),
        "transaction_design": AtomicAppendTransactionDesignTemplate().to_dict(),
        "backend_capability_evidence": TransactionBackendCapabilityEvidenceTemplate().to_dict(),
    }


def _rehash(payload: dict[str, Any], hash_key: str) -> None:
    payload[hash_key] = sha256_json({k: v for k, v in payload.items() if k != hash_key})


def build_p55_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    valid = build_valid_p55_inputs_fixture(cfg=cfg)
    cases: dict[str, dict[str, Any]] = {}

    bad = deepcopy(valid)
    bad["p54_report"]["p54_separate_p7_import_executor_final_guard_sha256"] = "f" * 64
    cases["p54_report_hash_tampering"] = bad

    bad = deepcopy(valid)
    bad["importer_interface"]["can_enable_importer"] = True
    _rehash(bad["importer_interface"], "p55_disabled_p7_importer_interface_sha256")
    cases["importer_enablement_attempt"] = bad

    bad = deepcopy(valid)
    bad["importer_interface"]["can_append_p7_registry"] = True
    _rehash(bad["importer_interface"], "p55_disabled_p7_importer_interface_sha256")
    cases["registry_append_permission_attempt"] = bad

    bad = deepcopy(valid)
    steps = list(bad["transaction_design"]["exact_step_order"])
    steps[2], steps[4] = steps[4], steps[2]
    bad["transaction_design"]["exact_step_order"] = steps
    _rehash(bad["transaction_design"], "p55_atomic_append_transaction_design_sha256")
    cases["nonce_before_duplicate_lock"] = bad

    bad = deepcopy(valid)
    steps = list(bad["transaction_design"]["exact_step_order"])
    append_idx = steps.index("append_exactly_one_p7_record")
    consume_idx = steps.index("consume_one_time_nonce")
    steps[append_idx], steps[consume_idx] = steps[consume_idx], steps[append_idx]
    bad["transaction_design"]["exact_step_order"] = steps
    _rehash(bad["transaction_design"], "p55_atomic_append_transaction_design_sha256")
    cases["append_before_nonce_consume"] = bad

    bad = deepcopy(valid)
    bad["transaction_design"]["rollback_before_commit_required"] = False
    _rehash(bad["transaction_design"], "p55_atomic_append_transaction_design_sha256")
    cases["rollback_requirement_removed"] = bad

    bad = deepcopy(valid)
    bad["transaction_design"]["overwrite_allowed"] = True
    _rehash(bad["transaction_design"], "p55_atomic_append_transaction_design_sha256")
    cases["registry_overwrite_allowed"] = bad

    bad = deepcopy(valid)
    bad["backend_capability_evidence"]["actual_import_ready"] = True
    _rehash(
        bad["backend_capability_evidence"],
        "p55_transaction_backend_capability_evidence_sha256",
    )
    cases["backend_falsely_claims_actual_import_ready"] = bad

    bad = deepcopy(valid)
    bad["backend_capability_evidence"]["current_backend_safe_for_real_p7_import"] = True
    _rehash(
        bad["backend_capability_evidence"],
        "p55_transaction_backend_capability_evidence_sha256",
    )
    cases["current_backend_falsely_claims_safe"] = bad

    bad = deepcopy(valid)
    bad["importer_interface"]["api_secret_value"] = "FORBIDDEN"
    _rehash(bad["importer_interface"], "p55_disabled_p7_importer_interface_sha256")
    cases["secret_value_field_injected"] = bad

    results: dict[str, Any] = {}
    all_blocked = True
    for name, inputs in cases.items():
        report = build_p55_disabled_p7_importer_atomic_append_transaction_report(cfg=cfg, **inputs)
        blocked = report["status"] == STATUS_BLOCKED_FAIL_CLOSED and report["blocked"] is True
        all_blocked = all_blocked and blocked
        results[name] = {
            "status": report["status"],
            "blocked": blocked,
            "block_reasons": report["block_reasons"],
        }

    valid_report = build_p55_disabled_p7_importer_atomic_append_transaction_report(cfg=cfg, **valid)
    payload = {
        "artifact_type": "p55_disabled_p7_importer_atomic_append_transaction_negative_fixture_results",
        "p55_version": P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION,
        "case_count": len(results),
        "results": results,
        "all_negative_fixtures_blocked_fail_closed": all_blocked,
        "valid_fixture_transaction_design_valid_importer_disabled": (
            valid_report["status"] == STATUS_DESIGN_VALID_REVIEW_ONLY_IMPORTER_DISABLED
            and valid_report["transaction_design_valid"] is True
            and valid_report["p7_importer_enabled"] is False
            and valid_report["actual_p7_import_ready"] is False
        ),
        "created_at_utc": utc_now_canonical(),
    }
    payload["p55_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_p55_disabled_p7_importer_atomic_append_transaction(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_p55_disabled_p7_importer_atomic_append_transaction_report(cfg=cfg)
    interface = DisabledP7ImporterInterfaceTemplate().to_dict()
    design = AtomicAppendTransactionDesignTemplate().to_dict()
    backend = TransactionBackendCapabilityEvidenceTemplate().to_dict()
    dry_run_template = {
        "artifact_type": _ALLOWED_DRY_RUN_ARTIFACT_TYPE,
        "dry_run_version": P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION,
        "status": "P55_ATOMIC_APPEND_TRANSACTION_DRY_RUN_TEMPLATE_NO_MUTATION",
        "review_only": True,
        "dry_run_only": True,
        "source_p54_report_sha256": "P54_REPORT_SHA256_REQUIRED",
        "source_p54_final_guard_packet_sha256": "P54_FINAL_GUARD_PACKET_SHA256_REQUIRED",
        "source_candidate_sha256": "CANDIDATE_SHA256_REQUIRED",
        "source_nonce_sha256": "NONCE_SHA256_REQUIRED",
        "transaction_steps": [
            {
                "sequence": idx + 1,
                "step": step,
                "simulated_only": True,
                "performed": False,
                "mutation_performed": False,
            }
            for idx, step in enumerate(_REQUIRED_TRANSACTION_STEPS)
        ],
        "actual_import_ready": False,
        **_execution_false_payload(),
    }
    dry_run_template["p55_atomic_append_transaction_dry_run_template_sha256"] = sha256_json(
        dry_run_template
    )
    negative = build_p55_negative_fixture_results(cfg=cfg)

    registry_record = {
        "artifact_type": "p55_disabled_p7_importer_atomic_append_transaction_registry_record",
        "p55_disabled_p7_importer_atomic_append_transaction_id": report[
            "p55_disabled_p7_importer_atomic_append_transaction_id"
        ],
        "p55_disabled_p7_importer_atomic_append_transaction_sha256": report[
            "p55_disabled_p7_importer_atomic_append_transaction_sha256"
        ],
        "status": report["status"],
        "review_only": True,
        "design_only": True,
        "transaction_design_valid": report["transaction_design_valid"],
        "current_backend_transaction_ready": False,
        "actual_p7_import_ready": False,
        "p7_importer_enabled": False,
        "created_at_utc": report["created_at_utc"],
    }
    registry_record["p55_registry_record_sha256"] = sha256_json(registry_record)
    append_registry_record(
        registry_path(cfg, P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_REGISTRY_NAME),
        registry_record,
        registry_name=P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_REGISTRY_NAME,
    )

    summary = {
        "artifact_type": "p55_disabled_p7_importer_atomic_append_transaction_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": True,
        "design_only": True,
        "transaction_design_valid": report["transaction_design_valid"],
        "current_backend_transaction_ready": False,
        "current_backend_safe_for_real_p7_import": False,
        "actual_p7_import_ready": False,
        "p7_importer_enabled": False,
        "p7_importer_action_executed": False,
        "p7_atomic_transaction_started": False,
        "p7_registry_append_performed_by_p55": False,
        "p7_valid_status_written_by_p55": False,
        "p7_internal_design_chain_closed_after_p55": report[
            "p7_internal_design_chain_closed_after_p55"
        ],
        "negative_fixtures_all_blocked": negative[
            "all_negative_fixtures_blocked_fail_closed"
        ],
        "valid_fixture_transaction_design_valid_importer_disabled": negative[
            "valid_fixture_transaction_design_valid_importer_disabled"
        ],
        "p55_disabled_p7_importer_atomic_append_transaction_id": report[
            "p55_disabled_p7_importer_atomic_append_transaction_id"
        ],
        "p55_disabled_p7_importer_atomic_append_transaction_sha256": report[
            "p55_disabled_p7_importer_atomic_append_transaction_sha256"
        ],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p55_summary_sha256"] = sha256_json(summary)

    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p55_disabled_p7_importer_atomic_append_transaction")
    writes = {
        "p55_disabled_p7_importer_atomic_append_transaction_report.json": report,
        "p55_disabled_p7_importer_interface_TEMPLATE_NO_IMPORT.json": interface,
        "p55_atomic_append_transaction_design_TEMPLATE_NO_IMPORT.json": design,
        "p55_transaction_backend_capability_evidence_TEMPLATE_CURRENT_BACKEND_NOT_READY.json": backend,
        "p55_atomic_append_transaction_dry_run_TEMPLATE_NO_MUTATION.json": dry_run_template,
        "p55_disabled_p7_importer_atomic_append_transaction_negative_fixture_results.json": negative,
        "p55_disabled_p7_importer_atomic_append_transaction_registry_record.json": registry_record,
        "p55_disabled_p7_importer_atomic_append_transaction_summary.json": summary,
    }
    for filename, payload in writes.items():
        atomic_write_json(latest / filename, payload)
        atomic_write_json(storage / filename, payload)
    return report


__all__ = [
    "P55_DISABLED_P7_IMPORTER_ATOMIC_APPEND_TRANSACTION_VERSION",
    "STATUS_READY_REVIEW_ONLY_IMPORTER_DISABLED",
    "STATUS_DESIGN_VALID_REVIEW_ONLY_IMPORTER_DISABLED",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "DisabledP7ImporterInterfaceTemplate",
    "AtomicAppendTransactionDesignTemplate",
    "TransactionBackendCapabilityEvidenceTemplate",
    "validate_disabled_importer_interface",
    "validate_atomic_append_transaction_design",
    "validate_backend_capability_evidence",
    "validate_p54_source",
    "build_atomic_append_dry_run",
    "validate_atomic_append_dry_run",
    "build_p55_disabled_p7_importer_atomic_append_transaction_report",
    "build_valid_p55_inputs_fixture",
    "build_p55_negative_fixture_results",
    "persist_p55_disabled_p7_importer_atomic_append_transaction",
]
