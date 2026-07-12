from __future__ import annotations

import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import (
    default_execution_flag_state,
    truthy_execution_flags,
)
from crypto_ai_system.execution.separate_p7_import_executor_final_guard import (
    STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED,
    build_p54_separate_p7_import_executor_final_guard_report,
    build_valid_p54_guard_inputs_fixture,
    validate_final_guard_passed_packet,
)
from crypto_ai_system.execution.transactional_evidence_store import (
    DuplicateImportError,
    EvidenceIntegrityError,
    InjectedTransactionFailure,
    SQLiteTransactionalEvidenceStore,
    TransactionalEvidenceRecordRequest,
    TransactionalEvidenceStoreDisabledError,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_VERSION = "p57_transactional_p7_importer_integration_v1"
P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_REGISTRY_NAME = (
    "p57_transactional_p7_importer_integration_registry"
)

STATUS_INTEGRATION_VALIDATED_REVIEW_ONLY_IMPORTER_DISABLED = (
    "P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_VALIDATED_REVIEW_ONLY_IMPORTER_DISABLED"
)
STATUS_READY_REVIEW_ONLY_IMPORTER_DISABLED = (
    "P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_READY_REVIEW_ONLY_IMPORTER_DISABLED"
)
STATUS_BLOCKED_FAIL_CLOSED = "P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_BLOCKED_FAIL_CLOSED"

_ALLOWED_SELF_TEST_SCOPE = "p57_transactional_p7_importer_integration_self_test"
_ALLOWED_SELF_TEST_ARTIFACT_TYPE = "p57_transactional_p7_importer_integration_self_test_record"
_REAL_IMPORT_SCOPE = "p7_real_import"
_SELF_TEST_EVIDENCE_ORIGIN = "p57_integration_self_test_fixture"
_REAL_EVIDENCE_ORIGIN = "real_signed_testnet_external_runtime"
_SELF_TEST_APPROVAL_PHRASE = "AUTHORIZE_P57_TRANSACTIONAL_IMPORTER_INTEGRATION_SELF_TEST_ONLY_NO_REAL_IMPORT"

_FORBIDDEN_FIELD_TOKENS = (
    "api_key_value",
    "api_secret_value",
    "secret_value",
    "private_key",
    "passphrase",
    "raw_signed_payload",
    "raw_request_body",
    "raw_exchange_payload",
    "unredacted_exchange_response",
)


class TransactionalP7ImporterIntegrationError(RuntimeError):
    """Base fail-closed error for P57 importer integration."""


class TransactionalP7ImporterIntegrationDisabledError(TransactionalP7ImporterIntegrationError):
    """Raised when real import or disabled importer execution is attempted."""


class TransactionalP7ImporterIntegrationValidationError(TransactionalP7ImporterIntegrationError):
    """Raised when guard, approval, candidate, or payload validation fails."""


def _latest_dir(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    path = Path(raw)
    if not path.is_absolute():
        path = cfg.root / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_latest_json(cfg: AppConfig, filename: str) -> dict[str, Any]:
    payload = read_json(_latest_dir(cfg) / filename, default={})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _verify_embedded_hash(payload: Mapping[str, Any] | None, hash_key: str) -> bool:
    obj = dict(payload or {})
    expected = str(obj.pop(hash_key, "") or "").strip().lower()
    return _is_sha256_hex(expected) and sha256_json(obj) == expected


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
                    blockers.append(f"P57_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
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
            "p7_real_import_enabled": False,
            "p7_real_import_executed": False,
            "p7_valid_status_written_by_p57": False,
            "p7_report_persisted_by_p57": False,
            "p7_runtime_registry_append_performed_by_p57": False,
            "p7_runtime_nonce_consumed_by_p57": False,
            "p7_runtime_duplicate_lock_acquired_by_p57": False,
            "p7_runtime_transaction_started_by_p57": False,
            "p7_runtime_transaction_committed_by_p57": False,
            "p8_repeated_session_candidate_created": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        }
    )
    return payload


@dataclass(frozen=True)
class TransactionalP7ImporterIntegrationConfig:
    integration_self_test_enabled: bool = True
    p7_importer_enabled: bool = False
    real_p7_import_enabled: bool = False
    allow_only_ephemeral_self_test_database: bool = True
    require_p54_final_guard_passed: bool = True
    require_fresh_guard_revalidation: bool = True
    require_candidate_hash_match: bool = True
    require_p7_preview_hash_match: bool = True
    require_operator_approval_hash_match: bool = True
    require_real_signed_testnet_evidence_for_real_import: bool = True
    require_transactional_backend: bool = True
    require_exactly_one_record: bool = True
    require_no_secret_payload: bool = True
    require_duplicate_lock_nonce_record_receipt_single_transaction: bool = True
    fail_closed_on_any_mismatch: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p57_transactional_p7_importer_integration_config_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P57OperatorIntegrationApproval:
    artifact_type: str = "p57_transactional_p7_importer_integration_operator_approval_SELF_TEST_ONLY"
    approval_mode: str = "integration_self_test_only"
    approval_phrase: str = _SELF_TEST_APPROVAL_PHRASE
    approved_p54_packet_sha256: str = "P54_PACKET_SHA256_REQUIRED"
    approved_candidate_sha256: str = "CANDIDATE_SHA256_REQUIRED"
    approved_p7_input_preview_sha256: str = "P7_INPUT_PREVIEW_SHA256_REQUIRED"
    one_time_action_nonce_sha256: str = "NONCE_SHA256_REQUIRED"
    real_p7_import_approved: bool = False
    runtime_authority_granted: bool = False
    review_only: bool = True
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p57_operator_integration_approval_id"] = stable_id(
            "p57_operator_integration_approval", payload, 24
        )
        payload["p57_operator_integration_approval_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P57ImporterIntegrationRequest:
    operation_scope: str
    evidence_origin: str
    final_guard_packet: Mapping[str, Any]
    candidate: Mapping[str, Any]
    operator_approval: Mapping[str, Any]
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "operation_scope": self.operation_scope,
            "evidence_origin": self.evidence_origin,
            "final_guard_packet": dict(self.final_guard_packet),
            "candidate": dict(self.candidate),
            "operator_approval": dict(self.operator_approval),
            "created_at_utc": self.created_at_utc,
        }


def validate_p57_config(
    config: Mapping[str, Any] | TransactionalP7ImporterIntegrationConfig | None,
) -> dict[str, Any]:
    payload = config.to_dict() if isinstance(config, TransactionalP7ImporterIntegrationConfig) else dict(
        config or TransactionalP7ImporterIntegrationConfig().to_dict()
    )
    blockers: list[str] = []
    if not _verify_embedded_hash(
        payload, "p57_transactional_p7_importer_integration_config_sha256"
    ):
        blockers.append("P57_CONFIG_EMBEDDED_SHA256_INVALID")
    for key in (
        "integration_self_test_enabled",
        "allow_only_ephemeral_self_test_database",
        "require_p54_final_guard_passed",
        "require_fresh_guard_revalidation",
        "require_candidate_hash_match",
        "require_p7_preview_hash_match",
        "require_operator_approval_hash_match",
        "require_real_signed_testnet_evidence_for_real_import",
        "require_transactional_backend",
        "require_exactly_one_record",
        "require_no_secret_payload",
        "require_duplicate_lock_nonce_record_receipt_single_transaction",
        "fail_closed_on_any_mismatch",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P57_CONFIG_{key.upper()}_NOT_TRUE")
    for key in ("p7_importer_enabled", "real_p7_import_enabled"):
        if payload.get(key) is not False:
            blockers.append(f"P57_CONFIG_{key.upper()}_MUST_REMAIN_FALSE")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "config_valid": not blockers,
        "config_block_reasons": sorted(dict.fromkeys(blockers)),
    }
    result["p57_config_validation_sha256"] = sha256_json(result)
    return result


def validate_p57_operator_approval(
    approval: Mapping[str, Any] | None,
    *,
    final_guard_packet: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(approval or {})
    blockers: list[str] = []
    if not payload:
        blockers.append("P57_OPERATOR_APPROVAL_MISSING")
    if payload.get("artifact_type") != (
        "p57_transactional_p7_importer_integration_operator_approval_SELF_TEST_ONLY"
    ):
        blockers.append("P57_OPERATOR_APPROVAL_ARTIFACT_TYPE_INVALID")
    if payload.get("approval_mode") != "integration_self_test_only":
        blockers.append("P57_OPERATOR_APPROVAL_MODE_INVALID")
    if payload.get("approval_phrase") != _SELF_TEST_APPROVAL_PHRASE:
        blockers.append("P57_OPERATOR_APPROVAL_PHRASE_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("P57_OPERATOR_APPROVAL_REVIEW_ONLY_NOT_TRUE")
    for key in ("real_p7_import_approved", "runtime_authority_granted"):
        if payload.get(key) is not False:
            blockers.append(f"P57_OPERATOR_APPROVAL_{key.upper()}_MUST_BE_FALSE")
    if not _verify_embedded_hash(payload, "p57_operator_integration_approval_sha256"):
        blockers.append("P57_OPERATOR_APPROVAL_EMBEDDED_SHA256_INVALID")
    candidate_sha = sha256_json(dict(candidate))
    p7_preview_sha = sha256_json(dict(candidate.get("p7_input_preview") or {}))
    expected = {
        "approved_p54_packet_sha256": final_guard_packet.get(
            "p54_p7_import_executor_final_guard_packet_sha256"
        ),
        "approved_candidate_sha256": candidate_sha,
        "approved_p7_input_preview_sha256": p7_preview_sha,
        "one_time_action_nonce_sha256": final_guard_packet.get("one_time_action_nonce_sha256"),
    }
    for key, value in expected.items():
        if payload.get(key) != value or not _is_sha256_hex(payload.get(key)):
            blockers.append(f"P57_OPERATOR_APPROVAL_{key.upper()}_MISMATCH")
    blockers.extend(_walk_forbidden(payload))
    result = {
        "operator_approval_present": bool(payload),
        "operator_approval_valid": not blockers,
        "operator_approval_block_reasons": sorted(dict.fromkeys(blockers)),
        "operator_approval_sha256": payload.get("p57_operator_integration_approval_sha256"),
    }
    result["p57_operator_approval_validation_sha256"] = sha256_json(result)
    return result


def validate_p54_candidate_chain(
    final_guard_packet: Mapping[str, Any] | None,
    candidate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    packet = dict(final_guard_packet or {})
    candidate_payload = dict(candidate or {})
    blockers: list[str] = []
    p54_validation = validate_final_guard_passed_packet(packet)
    if not p54_validation.get("final_guard_passed_packet_valid"):
        blockers.extend(p54_validation.get("final_guard_passed_packet_block_reasons") or [])
    if packet.get("status") != STATUS_FINAL_GUARD_PASSED_REVIEW_ONLY_EXECUTOR_DISABLED:
        blockers.append("P57_P54_FINAL_GUARD_STATUS_INVALID")
    if packet.get("final_guard_passed") is not True:
        blockers.append("P57_P54_FINAL_GUARD_NOT_PASSED")
    if packet.get("executor_disabled") is not True:
        blockers.append("P57_P54_EXECUTOR_DISABLED_NOT_TRUE")
    if not candidate_payload:
        blockers.append("P57_CANDIDATE_MISSING")
    candidate_sha = sha256_json(candidate_payload) if candidate_payload else ""
    preview = dict(candidate_payload.get("p7_input_preview") or {})
    preview_sha = sha256_json(preview) if preview else ""
    if packet.get("candidate_sha256") != candidate_sha:
        blockers.append("P57_CANDIDATE_SHA256_MISMATCH")
    if packet.get("p7_input_preview_sha256") != preview_sha:
        blockers.append("P57_P7_INPUT_PREVIEW_SHA256_MISMATCH")
    if preview.get("review_only") is not True or preview.get("p7_input_preview_only") is not True:
        blockers.append("P57_P7_INPUT_PREVIEW_BOUNDARY_INVALID")
    if preview.get("p7_intake_execution_performed") is not False:
        blockers.append("P57_P7_PREVIEW_ALREADY_EXECUTED")
    for key in ("exchange_order_id", "client_order_id", "idempotency_key"):
        if not str(preview.get(key) or "").strip():
            blockers.append(f"P57_P7_PREVIEW_{key.upper()}_MISSING")
    for key in (
        "source_p6_submit_runtime_action_sha256",
        "request_hash",
        "exchange_response_hash",
        "hot_path_preorder_risk_gate_hash",
        "key_fingerprint_sha256",
        "no_secret_logged_evidence_hash",
    ):
        if not _is_sha256_hex(preview.get(key)):
            blockers.append(f"P57_P7_PREVIEW_{key.upper()}_INVALID")
    for required_section in (
        "status_polling_events",
        "cancel_boundary_evidence",
        "signed_testnet_reconciliation_evidence",
        "signed_testnet_session_close_evidence",
    ):
        if required_section not in candidate_payload:
            blockers.append(f"P57_CANDIDATE_{required_section.upper()}_MISSING")
    blockers.extend(_walk_forbidden(candidate_payload))
    unsafe = truthy_execution_flags(packet)
    if unsafe:
        blockers.append("P57_P54_PACKET_UNSAFE_TRUTHY_EXECUTION_FLAGS")
    result = {
        "p54_packet_present": bool(packet),
        "candidate_present": bool(candidate_payload),
        "p54_candidate_chain_valid": not blockers,
        "p54_candidate_chain_block_reasons": sorted(dict.fromkeys(blockers)),
        "candidate_sha256": candidate_sha,
        "p7_input_preview_sha256": preview_sha,
        "p54_packet_sha256": packet.get("p54_p7_import_executor_final_guard_packet_sha256"),
        "p54_validation": p54_validation,
    }
    result["p57_p54_candidate_chain_validation_sha256"] = sha256_json(result)
    return result


def build_valid_p57_operator_approval(
    final_guard_packet: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    return P57OperatorIntegrationApproval(
        approved_p54_packet_sha256=str(
            final_guard_packet.get("p54_p7_import_executor_final_guard_packet_sha256") or ""
        ),
        approved_candidate_sha256=sha256_json(dict(candidate)),
        approved_p7_input_preview_sha256=sha256_json(dict(candidate.get("p7_input_preview") or {})),
        one_time_action_nonce_sha256=str(
            final_guard_packet.get("one_time_action_nonce_sha256") or ""
        ),
    ).to_dict()


def build_valid_p57_integration_request(*, cfg: AppConfig | None = None) -> P57ImporterIntegrationRequest:
    cfg = cfg or load_config()
    inputs = build_valid_p54_guard_inputs_fixture(cfg=cfg)
    p54_report = build_p54_separate_p7_import_executor_final_guard_report(cfg=cfg, **inputs)
    packet = dict(p54_report.get("final_guard_packet") or {})
    candidate = dict(inputs["candidate"])
    approval = build_valid_p57_operator_approval(packet, candidate)
    return P57ImporterIntegrationRequest(
        operation_scope=_ALLOWED_SELF_TEST_SCOPE,
        evidence_origin=_SELF_TEST_EVIDENCE_ORIGIN,
        final_guard_packet=packet,
        candidate=candidate,
        operator_approval=approval,
    )


def build_transactional_store_request(
    request: P57ImporterIntegrationRequest,
) -> TransactionalEvidenceRecordRequest:
    packet = dict(request.final_guard_packet)
    candidate = dict(request.candidate)
    preview = dict(candidate.get("p7_input_preview") or {})
    payload = {
        "artifact_type": _ALLOWED_SELF_TEST_ARTIFACT_TYPE,
        "p57_version": P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_VERSION,
        "integration_self_test_only": True,
        "contains_real_exchange_evidence": False,
        "evidence_origin": request.evidence_origin,
        "source_p54_packet_sha256": packet.get("p54_p7_import_executor_final_guard_packet_sha256"),
        "source_p52_staged_packet_sha256": packet.get("source_p52_staged_packet_sha256"),
        "candidate_sha256": sha256_json(candidate),
        "p7_input_preview_sha256": sha256_json(preview),
        "exchange_order_id": preview.get("exchange_order_id"),
        "client_order_id": preview.get("client_order_id"),
        "idempotency_key": preview.get("idempotency_key"),
        "execution_id": preview.get("execution_id"),
        "order_intent_id": preview.get("order_intent_id"),
        "risk_gate_id": preview.get("risk_gate_id"),
        "request_hash": preview.get("request_hash"),
        "exchange_response_hash": preview.get("exchange_response_hash"),
        "hot_path_preorder_risk_gate_hash": preview.get("hot_path_preorder_risk_gate_hash"),
        "secret_reference_id": preview.get("secret_reference_id"),
        "key_fingerprint_sha256": preview.get("key_fingerprint_sha256"),
        "no_secret_logged_evidence_hash": preview.get("no_secret_logged_evidence_hash"),
        "status_polling_events_sha256": sha256_json(candidate.get("status_polling_events")),
        "cancel_boundary_evidence_sha256": sha256_json(candidate.get("cancel_boundary_evidence")),
        "signed_testnet_reconciliation_evidence_sha256": sha256_json(
            candidate.get("signed_testnet_reconciliation_evidence")
        ),
        "signed_testnet_session_close_evidence_sha256": sha256_json(
            candidate.get("signed_testnet_session_close_evidence")
        ),
        "operator_approval_sha256": request.operator_approval.get(
            "p57_operator_integration_approval_sha256"
        ),
        "runtime_authority": False,
        "p7_valid_status_written": False,
        "p8_candidate_created": False,
    }
    return TransactionalEvidenceRecordRequest(
        operation_scope=request.operation_scope,
        artifact_type=_ALLOWED_SELF_TEST_ARTIFACT_TYPE,
        candidate_sha256=sha256_json(candidate),
        exchange_order_id=str(preview.get("exchange_order_id") or ""),
        client_order_id=str(preview.get("client_order_id") or ""),
        idempotency_key=str(preview.get("idempotency_key") or ""),
        one_time_nonce_sha256=str(packet.get("one_time_action_nonce_sha256") or ""),
        p7_input_preview_sha256=sha256_json(preview),
        payload=payload,
        created_at_utc=request.created_at_utc,
    )


class TransactionalP7ImporterIntegration:
    """P54-to-P56 integration orchestrator with real import disabled by default."""

    def __init__(
        self,
        store: SQLiteTransactionalEvidenceStore,
        *,
        config: TransactionalP7ImporterIntegrationConfig | None = None,
    ) -> None:
        self.store = store
        self.config = config or TransactionalP7ImporterIntegrationConfig()

    def validate_request(self, request: P57ImporterIntegrationRequest) -> dict[str, Any]:
        blockers: list[str] = []
        config_validation = validate_p57_config(self.config)
        blockers.extend(config_validation["config_block_reasons"])
        if request.operation_scope != _ALLOWED_SELF_TEST_SCOPE:
            blockers.append("P57_ONLY_INTEGRATION_SELF_TEST_SCOPE_ALLOWED")
        if request.evidence_origin != _SELF_TEST_EVIDENCE_ORIGIN:
            blockers.append("P57_SELF_TEST_EVIDENCE_ORIGIN_INVALID")
        chain_validation = validate_p54_candidate_chain(
            request.final_guard_packet, request.candidate
        )
        blockers.extend(chain_validation["p54_candidate_chain_block_reasons"])
        approval_validation = validate_p57_operator_approval(
            request.operator_approval,
            final_guard_packet=request.final_guard_packet,
            candidate=request.candidate,
        )
        blockers.extend(approval_validation["operator_approval_block_reasons"])
        forbidden = _walk_forbidden(request.canonical_payload())
        blockers.extend(forbidden)
        result = {
            "request_valid": not blockers,
            "request_block_reasons": sorted(dict.fromkeys(blockers)),
            "config_validation": config_validation,
            "p54_candidate_chain_validation": chain_validation,
            "operator_approval_validation": approval_validation,
        }
        result["p57_request_validation_sha256"] = sha256_json(result)
        return result

    def execute_integration_self_test(
        self,
        request: P57ImporterIntegrationRequest,
        *,
        fault_injection_step: str | None = None,
    ) -> dict[str, Any]:
        validation = self.validate_request(request)
        if not validation["request_valid"]:
            raise TransactionalP7ImporterIntegrationValidationError(
                ";".join(validation["request_block_reasons"])
            )
        store_request = build_transactional_store_request(request)
        receipt = self.store._append_integration_test_record_atomically(
            store_request,
            fault_injection_step=fault_injection_step,
        )
        payload = {
            "artifact_type": "p57_transactional_p7_importer_integration_self_test_receipt",
            "p57_version": P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_VERSION,
            "integration_self_test_only": True,
            "real_p7_import": False,
            "transaction_committed": True,
            "exactly_one_transactional_record_committed": True,
            "source_p54_packet_sha256": request.final_guard_packet.get(
                "p54_p7_import_executor_final_guard_packet_sha256"
            ),
            "candidate_sha256": sha256_json(dict(request.candidate)),
            "p7_input_preview_sha256": sha256_json(
                dict(request.candidate.get("p7_input_preview") or {})
            ),
            "backend_receipt": receipt,
            "p7_importer_enabled": False,
            "p7_real_import_enabled": False,
            "p7_real_import_executed": False,
            "p7_valid_status_written_by_p57": False,
            "p8_repeated_session_candidate_created": False,
            **_execution_false_payload(),
        }
        payload["p57_integration_self_test_receipt_sha256"] = sha256_json(payload)
        return payload

    def execute_real_import(self, request: P57ImporterIntegrationRequest) -> dict[str, Any]:
        raise TransactionalP7ImporterIntegrationDisabledError(
            "P57_REAL_P7_IMPORT_DISABLED_PENDING_REAL_SIGNED_TESTNET_EVIDENCE_AND_SEPARATE_APPROVAL"
        )


def run_p57_transactional_importer_integration_self_test(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    request = build_valid_p57_integration_request(cfg=cfg)
    with tempfile.TemporaryDirectory(prefix="cas_p57_importer_integration_") as tmp:
        commit_store = SQLiteTransactionalEvidenceStore(Path(tmp) / "commit.sqlite3")
        importer = TransactionalP7ImporterIntegration(commit_store)
        receipt = importer.execute_integration_self_test(request)
        counts_after_commit = commit_store.row_counts()
        append_only = commit_store.assert_append_only_guards(
            receipt["backend_receipt"]["record_id"]
        )

        duplicate_blocked = False
        before_duplicate = commit_store.row_counts()
        try:
            importer.execute_integration_self_test(request)
        except DuplicateImportError:
            duplicate_blocked = True
        after_duplicate = commit_store.row_counts()

        rollback_results: dict[str, Any] = {}
        for step in ("after_lock", "after_nonce", "after_record", "before_commit"):
            store = SQLiteTransactionalEvidenceStore(Path(tmp) / f"rollback-{step}.sqlite3")
            worker = TransactionalP7ImporterIntegration(store)
            before = store.row_counts()
            failure_observed = False
            try:
                worker.execute_integration_self_test(request, fault_injection_step=step)
            except InjectedTransactionFailure:
                failure_observed = True
            after = store.row_counts()
            rollback_results[step] = {
                "failure_observed": failure_observed,
                "row_counts_before": before,
                "row_counts_after": after,
                "no_partial_state_published": before == after,
            }

        real_import_blocked = False
        try:
            importer.execute_real_import(
                replace(
                    request,
                    operation_scope=_REAL_IMPORT_SCOPE,
                    evidence_origin=_REAL_EVIDENCE_ORIGIN,
                )
            )
        except TransactionalP7ImporterIntegrationDisabledError:
            real_import_blocked = True

        payload = {
            "artifact_type": "p57_transactional_p7_importer_integration_self_test_report",
            "p57_version": P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_VERSION,
            "ephemeral_database_used": True,
            "ephemeral_database_deleted_after_test": True,
            "p54_guard_to_p56_backend_code_path_exercised": True,
            "commit_receipt": receipt,
            "commit_test_passed": counts_after_commit
            == {
                "import_records": 1,
                "import_locks": 1,
                "consumed_nonces": 1,
                "transaction_receipts": 1,
            },
            "duplicate_import_blocked": duplicate_blocked,
            "duplicate_attempt_created_no_partial_state": before_duplicate == after_duplicate,
            "rollback_results": rollback_results,
            "all_injected_failures_rolled_back_without_partial_state": all(
                item["failure_observed"] and item["no_partial_state_published"]
                for item in rollback_results.values()
            ),
            "append_only_update_blocked": append_only["update_blocked"],
            "append_only_delete_blocked": append_only["delete_blocked"],
            "real_p7_import_scope_blocked_by_p57": real_import_blocked,
            "integration_self_test_passed": bool(
                counts_after_commit
                == {
                    "import_records": 1,
                    "import_locks": 1,
                    "consumed_nonces": 1,
                    "transaction_receipts": 1,
                }
                and duplicate_blocked
                and before_duplicate == after_duplicate
                and all(
                    item["failure_observed"] and item["no_partial_state_published"]
                    for item in rollback_results.values()
                )
                and append_only["update_blocked"]
                and append_only["delete_blocked"]
                and real_import_blocked
            ),
            "real_signed_testnet_evidence_present": False,
            "actual_p7_import_ready": False,
            "p7_importer_enabled": False,
            "runtime_mutation_performed": False,
            "created_at_utc": utc_now_canonical(),
        }
        payload["p57_integration_self_test_report_sha256"] = sha256_json(payload)
        return payload


def build_p57_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    valid = build_valid_p57_integration_request(cfg=cfg)
    cases: dict[str, tuple[P57ImporterIntegrationRequest, TransactionalP7ImporterIntegrationConfig]] = {}

    cases["importer_enablement_attempt"] = (
        valid,
        replace(TransactionalP7ImporterIntegrationConfig(), p7_importer_enabled=True),
    )
    cases["real_import_enablement_attempt"] = (
        valid,
        replace(TransactionalP7ImporterIntegrationConfig(), real_p7_import_enabled=True),
    )

    bad_packet = deepcopy(valid.canonical_payload())
    bad_packet["final_guard_packet"]["candidate_sha256"] = "f" * 64
    cases["p54_packet_tampered"] = (P57ImporterIntegrationRequest(**bad_packet), TransactionalP7ImporterIntegrationConfig())

    bad_candidate = deepcopy(valid.canonical_payload())
    bad_candidate["candidate"]["p7_input_preview"]["client_order_id"] = "mutated-client"
    cases["candidate_hash_mismatch"] = (P57ImporterIntegrationRequest(**bad_candidate), TransactionalP7ImporterIntegrationConfig())

    bad_phrase = deepcopy(valid.canonical_payload())
    bad_phrase["operator_approval"]["approval_phrase"] = "WRONG"
    bad_phrase["operator_approval"]["p57_operator_integration_approval_sha256"] = sha256_json(
        {k: v for k, v in bad_phrase["operator_approval"].items() if k != "p57_operator_integration_approval_sha256"}
    )
    cases["operator_phrase_invalid"] = (P57ImporterIntegrationRequest(**bad_phrase), TransactionalP7ImporterIntegrationConfig())

    bad_approval_hash = deepcopy(valid.canonical_payload())
    bad_approval_hash["operator_approval"]["approved_candidate_sha256"] = "f" * 64
    bad_approval_hash["operator_approval"]["p57_operator_integration_approval_sha256"] = sha256_json(
        {k: v for k, v in bad_approval_hash["operator_approval"].items() if k != "p57_operator_integration_approval_sha256"}
    )
    cases["operator_candidate_hash_mismatch"] = (
        P57ImporterIntegrationRequest(**bad_approval_hash),
        TransactionalP7ImporterIntegrationConfig(),
    )

    real_origin = replace(valid, evidence_origin=_REAL_EVIDENCE_ORIGIN)
    cases["real_evidence_claim_in_self_test"] = (
        real_origin,
        TransactionalP7ImporterIntegrationConfig(),
    )

    real_scope = replace(valid, operation_scope=_REAL_IMPORT_SCOPE)
    cases["real_import_scope_attempt"] = (real_scope, TransactionalP7ImporterIntegrationConfig())

    secret_candidate = deepcopy(valid.canonical_payload())
    secret_candidate["candidate"]["api_secret_value"] = "FORBIDDEN"
    cases["secret_value_field_in_candidate"] = (
        P57ImporterIntegrationRequest(**secret_candidate),
        TransactionalP7ImporterIntegrationConfig(),
    )

    executor_mutation = deepcopy(valid.canonical_payload())
    executor_mutation["final_guard_packet"]["p7_import_executor_enabled"] = True
    cases["p54_executor_enablement_mutation"] = (
        P57ImporterIntegrationRequest(**executor_mutation),
        TransactionalP7ImporterIntegrationConfig(),
    )

    results: dict[str, Any] = {}
    for name, (request, config) in cases.items():
        with tempfile.TemporaryDirectory(prefix=f"cas_p57_negative_{name}_") as tmp:
            importer = TransactionalP7ImporterIntegration(
                SQLiteTransactionalEvidenceStore(Path(tmp) / "negative.sqlite3"),
                config=config,
            )
            blocked = False
            reasons: list[str] = []
            try:
                validation = importer.validate_request(request)
                if not validation["request_valid"]:
                    blocked = True
                    reasons = list(validation["request_block_reasons"])
                else:
                    importer.execute_integration_self_test(request)
            except (
                TransactionalP7ImporterIntegrationError,
                TransactionalEvidenceStoreDisabledError,
                EvidenceIntegrityError,
            ) as exc:
                blocked = True
                reasons = [str(exc)]
            results[name] = {
                "fixture_name": name,
                "blocked_fail_closed": blocked,
                "block_reasons": reasons,
            }

    payload = {
        "artifact_type": "p57_transactional_p7_importer_integration_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(
            item["blocked_fail_closed"] for item in results.values()
        ),
        "fixture_results": results,
        "p7_importer_enabled": False,
        "real_p7_import_enabled": False,
        "actual_p7_import_ready": False,
        **_execution_false_payload(),
    }
    payload["p57_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def build_p57_transactional_p7_importer_integration_report(
    *,
    cfg: AppConfig | None = None,
    self_test_report: Mapping[str, Any] | None = None,
    negative_fixture_results: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p56_report = _read_latest_json(cfg, "p56_transactional_evidence_store_report.json")
    self_test = dict(self_test_report or run_p57_transactional_importer_integration_self_test(cfg=cfg))
    negatives = dict(negative_fixture_results or build_p57_negative_fixture_results(cfg=cfg))
    config = TransactionalP7ImporterIntegrationConfig().to_dict()
    config_validation = validate_p57_config(config)
    blockers: list[str] = []

    if not p56_report:
        blockers.append("P57_P56_REPORT_MISSING")
    else:
        if p56_report.get("backend_transaction_ready") is not True:
            blockers.append("P57_P56_BACKEND_NOT_TRANSACTION_READY")
        if p56_report.get("p7_importer_enabled") is not False:
            blockers.append("P57_P56_IMPORTER_ENABLED_UNEXPECTEDLY")
        if p56_report.get("actual_p7_import_ready") is not False:
            blockers.append("P57_P56_REAL_IMPORT_READY_OVERSTATED")
    blockers.extend(config_validation["config_block_reasons"])
    if self_test.get("integration_self_test_passed") is not True:
        blockers.append("P57_INTEGRATION_SELF_TEST_FAILED")
    if self_test.get("real_p7_import_scope_blocked_by_p57") is not True:
        blockers.append("P57_REAL_IMPORT_SCOPE_NOT_BLOCKED")
    if negatives.get("all_negative_fixtures_blocked_fail_closed") is not True:
        blockers.append("P57_NEGATIVE_FIXTURE_FAILURE")
    blockers.extend(_walk_forbidden(self_test))

    blocked = bool(blockers)
    status = (
        STATUS_BLOCKED_FAIL_CLOSED
        if blocked
        else STATUS_INTEGRATION_VALIDATED_REVIEW_ONLY_IMPORTER_DISABLED
    )
    created_at = utc_now_canonical()
    flags = _execution_false_payload()
    report = {
        "artifact_type": "p57_transactional_p7_importer_integration_report",
        "p57_version": P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "runtime_authority_source": False,
        "integration_implementation_added": True,
        "p54_final_guard_connected_to_p56_transaction_backend": True,
        "transactional_importer_orchestration_implemented": True,
        "integration_self_test_only": True,
        "integration_self_test_passed": self_test.get("integration_self_test_passed") is True,
        "atomic_lock_nonce_record_receipt_commit_proven_through_importer": self_test.get(
            "commit_test_passed"
        )
        is True,
        "duplicate_prevention_proven_through_importer": self_test.get(
            "duplicate_import_blocked"
        )
        is True,
        "rollback_proven_through_importer": self_test.get(
            "all_injected_failures_rolled_back_without_partial_state"
        )
        is True,
        "append_only_guards_proven_through_importer": bool(
            self_test.get("append_only_update_blocked")
            and self_test.get("append_only_delete_blocked")
        ),
        "real_p7_import_scope_blocked": self_test.get("real_p7_import_scope_blocked_by_p57")
        is True,
        "real_signed_testnet_evidence_present": False,
        "real_p7_import_integrated": False,
        "actual_p7_import_ready": False,
        "p7_internal_design_chain_closed": True,
        "next_progress_requires_real_signed_testnet_external_runtime_evidence": True,
        "next_progress_requires_separate_operator_real_import_approval": True,
        "next_progress_requires_non_fixture_p54_revalidation": True,
        "no_additional_p7_review_wrapper_recommended": True,
        "source_p56_report_id": p56_report.get("p56_transactional_evidence_store_id"),
        "source_p56_report_sha256": p56_report.get("p56_transactional_evidence_store_sha256"),
        "config": config,
        "config_validation": config_validation,
        "integration_self_test_report": self_test,
        "negative_fixture_results": negatives,
        **flags,
        "created_at_utc": created_at,
    }
    report["p57_transactional_p7_importer_integration_id"] = stable_id(
        "p57_transactional_p7_importer_integration", report, 24
    )
    report["p57_transactional_p7_importer_integration_sha256"] = sha256_json(report)
    return report


def persist_p57_transactional_p7_importer_integration(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    self_test = run_p57_transactional_importer_integration_self_test(cfg=cfg)
    negatives = build_p57_negative_fixture_results(cfg=cfg)
    report = build_p57_transactional_p7_importer_integration_report(
        cfg=cfg,
        self_test_report=self_test,
        negative_fixture_results=negatives,
    )
    config = TransactionalP7ImporterIntegrationConfig().to_dict()

    runtime_template = {
        "artifact_type": "p57_future_transactional_p7_importer_runtime_config_TEMPLATE_DISABLED",
        "p57_version": P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_VERSION,
        "review_only": True,
        "p7_importer_enabled": False,
        "real_p7_import_enabled": False,
        "real_signed_testnet_evidence_required": True,
        "evidence_origin_required": _REAL_EVIDENCE_ORIGIN,
        "separate_operator_real_import_approval_required": True,
        "fresh_non_fixture_p54_guard_required": True,
        "transactional_backend_required": True,
        "exactly_one_import_record_required": True,
        "database_path": "OPERATOR_SUPPLIED_LOCAL_RUNTIME_PATH_REQUIRED",
        "runtime_authority_source": False,
        **_execution_false_payload(),
    }
    runtime_template["p57_future_runtime_config_sha256"] = sha256_json(runtime_template)

    operator_template = {
        "artifact_type": "p57_future_real_p7_import_operator_approval_TEMPLATE_DISABLED",
        "p57_version": P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_VERSION,
        "review_only": True,
        "real_p7_import_approved": False,
        "p7_importer_enabled": False,
        "approved_candidate_sha256": "REAL_CANDIDATE_SHA256_REQUIRED",
        "approved_p54_packet_sha256": "FRESH_NON_FIXTURE_P54_PACKET_SHA256_REQUIRED",
        "operator_confirmation_sha256": "OPERATOR_CONFIRMATION_SHA256_REQUIRED",
        "one_time_action_nonce_sha256": "FRESH_NONCE_SHA256_REQUIRED",
        "runtime_authority_source": False,
        **_execution_false_payload(),
    }
    operator_template["p57_future_real_import_operator_approval_template_sha256"] = sha256_json(
        operator_template
    )

    summary = {
        "artifact_type": "p57_transactional_p7_importer_integration_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": True,
        "integration_implementation_added": True,
        "p54_to_p56_transactional_path_validated": report[
            "p54_final_guard_connected_to_p56_transaction_backend"
        ],
        "integration_self_test_passed": report["integration_self_test_passed"],
        "real_signed_testnet_evidence_present": False,
        "actual_p7_import_ready": False,
        "p7_importer_enabled": False,
        "no_additional_p7_review_wrapper_recommended": True,
        "created_at_utc": report["created_at_utc"],
    }
    summary["p57_summary_sha256"] = sha256_json(summary)

    registry_record = {
        "artifact_type": "p57_transactional_p7_importer_integration_registry_record",
        "p57_transactional_p7_importer_integration_id": report[
            "p57_transactional_p7_importer_integration_id"
        ],
        "p57_transactional_p7_importer_integration_sha256": report[
            "p57_transactional_p7_importer_integration_sha256"
        ],
        "status": report["status"],
        "review_only": True,
        "integration_self_test_passed": report["integration_self_test_passed"],
        "actual_p7_import_ready": False,
        "p7_importer_enabled": False,
        "created_at_utc": report["created_at_utc"],
    }
    registry_record["p57_registry_record_sha256"] = sha256_json(registry_record)
    append_registry_record(
        registry_path(cfg, P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_REGISTRY_NAME),
        registry_record,
        registry_name=P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_REGISTRY_NAME,
    )

    latest = _latest_dir(cfg)
    outputs = {
        "p57_transactional_p7_importer_integration_report.json": report,
        "p57_transactional_p7_importer_integration_config.json": config,
        "p57_transactional_p7_importer_integration_self_test_report.json": self_test,
        "p57_transactional_p7_importer_integration_negative_fixture_results.json": negatives,
        "p57_future_transactional_p7_importer_runtime_config_TEMPLATE_DISABLED.json": runtime_template,
        "p57_future_real_p7_import_operator_approval_TEMPLATE_DISABLED.json": operator_template,
        "p57_transactional_p7_importer_integration_summary.json": summary,
        "p57_transactional_p7_importer_integration_registry_record.json": registry_record,
    }
    for filename, payload in outputs.items():
        atomic_write_json(latest / filename, payload)
    return report
