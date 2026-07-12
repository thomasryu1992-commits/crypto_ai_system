from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.p7_accepted_evidence_import_packet_staging import (
    STATUS_STAGED_REVIEW_ONLY_NO_SUBMIT as P52_STAGED_STATUS,
    _valid_candidate_fixture,
    build_p52_p7_accepted_evidence_import_packet_staging_report,
    validate_staged_p7_import_packet,
)
from crypto_ai_system.execution.p7_import_bridge_dry_run import build_p51_p7_import_bridge_dry_run_report
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_VERSION = "p53_operator_controlled_p7_import_action_boundary_v1"
P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_REGISTRY_NAME = "p53_operator_controlled_p7_import_action_boundary_registry"
P53_OPERATOR_AUTHORIZATION_EXACT_PHRASE = (
    "I AUTHORIZE ARMING EXACTLY ONE P7 SIGNED TESTNET EVIDENCE IMPORT BOUNDARY WITHOUT EXECUTING THE IMPORT"
)

STATUS_READY_REVIEW_ONLY_NO_IMPORT = "P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_READY_REVIEW_ONLY_NO_IMPORT"
STATUS_ARMED_REVIEW_ONLY_NO_IMPORT = "P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_ARMED_REVIEW_ONLY_NO_IMPORT"
STATUS_BLOCKED_FAIL_CLOSED = "P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_BLOCKED_FAIL_CLOSED"

_ALLOWED_REQUEST_ARTIFACT_TYPE = "p53_operator_controlled_p7_import_action_request"
_ALLOWED_STAGED_PACKET_ARTIFACT_TYPE = "p52_p7_accepted_evidence_import_packet_STAGED_NO_SUBMIT"
_ALLOWED_OPERATOR_DECISION = "ARM_ONE_P7_IMPORT_BOUNDARY_ONLY_NO_IMPORT"

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
            "p7_import_action_enabled": False,
            "p7_import_action_executed": False,
            "p7_report_persisted_by_p53": False,
            "p7_valid_status_written_by_p53": False,
            "p7_intake_execution_performed_by_p53": False,
            "p7_import_packet_promoted_to_runtime_authority": False,
            "p7_import_action_nonce_consumed": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        }
    )
    return payload


@dataclass(frozen=True)
class OperatorControlledP7ImportActionBoundaryTemplate:
    boundary_template_id: str = "p53_operator_controlled_p7_import_action_boundary_TEMPLATE_NO_IMPORT"
    boundary_version: str = P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_VERSION
    generated_by_review_package: bool = True
    review_only: bool = True
    operator_controlled: bool = True
    one_packet_only: bool = True
    p52_staged_packet_required: bool = True
    exact_operator_phrase_required: bool = True
    staged_packet_hash_match_required: bool = True
    candidate_hash_match_required: bool = True
    one_time_action_nonce_required: bool = True
    operator_confirmation_hash_required: bool = True
    fresh_revalidation_at_import_time_required: bool = True
    separate_p7_import_executor_required: bool = True
    p7_import_execution_allowed_by_p53: bool = False
    p7_report_persistence_allowed_by_p53: bool = False
    p7_status_mutation_allowed_by_p53: bool = False
    can_grant_runtime_authority: bool = False
    can_enable_testnet_submit: bool = False
    can_enable_live_canary: bool = False
    can_enable_live_scaled: bool = False
    order_endpoint_call_allowed_by_p53: bool = False
    status_endpoint_call_allowed_by_p53: bool = False
    cancel_endpoint_call_allowed_by_p53: bool = False
    http_request_allowed_by_p53: bool = False
    signature_creation_allowed_by_p53: bool = False
    secret_access_allowed_by_p53: bool = False
    p8_must_remain_waiting_after_p53: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p53_boundary_template_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class OperatorControlledP7ImportActionRequestTemplate:
    artifact_type: str = _ALLOWED_REQUEST_ARTIFACT_TYPE
    request_version: str = P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_VERSION
    request_template_id: str = "p53_operator_controlled_p7_import_action_request_TEMPLATE_NO_IMPORT"
    review_only: bool = True
    operator_controlled: bool = True
    one_packet_only: bool = True
    environment: str = "testnet"
    venue: str = "binance_futures_testnet"
    symbol: str = "BTCUSDT"
    operator_decision: str = _ALLOWED_OPERATOR_DECISION
    exact_operator_authorization_phrase: str = P53_OPERATOR_AUTHORIZATION_EXACT_PHRASE
    operator_reference_id: str = "OPERATOR_REFERENCE_REQUIRED"
    operator_confirmation_hash: str = field(default_factory=lambda: "1" * 64)
    one_time_action_nonce_sha256: str = field(default_factory=lambda: "2" * 64)
    source_p52_staging_report_sha256: str = "P52_REPORT_SHA256_REQUIRED"
    source_p52_staged_packet_sha256: str = "P52_STAGED_PACKET_SHA256_REQUIRED"
    candidate_sha256: str = "CANDIDATE_SHA256_REQUIRED"
    p7_input_preview_sha256: str = "P7_INPUT_PREVIEW_SHA256_REQUIRED"
    p7_import_action_requested: bool = True
    p7_import_execution_allowed_by_p53: bool = False
    p7_report_persistence_allowed_by_p53: bool = False
    p7_status_mutation_allowed_by_p53: bool = False
    runtime_authority_requested: bool = False
    live_canary_requested: bool = False
    live_scaled_requested: bool = False
    order_submission_requested: bool = False
    secret_access_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p53_operator_request_template_sha256"] = sha256_json(payload)
        return payload


def _walk_forbidden(obj: Any, *, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            key_text = str(key)
            key_l = key_text.lower()
            child_prefix = f"{prefix}.{key_text}" if prefix else key_text
            if any(token in key_l for token in _FORBIDDEN_FIELD_TOKENS):
                safe_boolean_flag = isinstance(value, bool) and any(
                    marker in key_l for marker in ("_logged", "_included", "_accessed", "_created", "_called", "_sent")
                )
                if key_l not in {"secret_reference_id", "no_secret_logged_evidence_hash"} and not safe_boolean_flag:
                    blockers.append(f"P53_FORBIDDEN_FIELD:{child_prefix}")
            blockers.extend(_walk_forbidden(value, prefix=child_prefix))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, prefix=f"{prefix}[{idx}]"))
    elif isinstance(obj, str):
        value_l = obj.lower()
        if any(token in value_l for token in _FORBIDDEN_SCOPE_TOKENS):
            blockers.append(f"P53_FORBIDDEN_SCOPE_TOKEN:{prefix}")
    return blockers


def validate_p53_boundary_template(
    template: Mapping[str, Any] | OperatorControlledP7ImportActionBoundaryTemplate | None,
) -> dict[str, Any]:
    payload = template.to_dict() if isinstance(template, OperatorControlledP7ImportActionBoundaryTemplate) else dict(template or {})
    blockers: list[str] = []
    if payload.get("boundary_version") != P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_VERSION:
        blockers.append("P53_TEMPLATE_VERSION_MISMATCH")
    for key in (
        "generated_by_review_package",
        "review_only",
        "operator_controlled",
        "one_packet_only",
        "p52_staged_packet_required",
        "exact_operator_phrase_required",
        "staged_packet_hash_match_required",
        "candidate_hash_match_required",
        "one_time_action_nonce_required",
        "operator_confirmation_hash_required",
        "fresh_revalidation_at_import_time_required",
        "separate_p7_import_executor_required",
        "p8_must_remain_waiting_after_p53",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P53_TEMPLATE_{key.upper()}_NOT_TRUE")
    for key in (
        "p7_import_execution_allowed_by_p53",
        "p7_report_persistence_allowed_by_p53",
        "p7_status_mutation_allowed_by_p53",
        "can_grant_runtime_authority",
        "can_enable_testnet_submit",
        "can_enable_live_canary",
        "can_enable_live_scaled",
        "order_endpoint_call_allowed_by_p53",
        "status_endpoint_call_allowed_by_p53",
        "cancel_endpoint_call_allowed_by_p53",
        "http_request_allowed_by_p53",
        "signature_creation_allowed_by_p53",
        "secret_access_allowed_by_p53",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P53_TEMPLATE_{key.upper()}_NOT_FALSE")
    validation = {
        "p53_boundary_template_valid": not blockers,
        "p53_boundary_template_block_reasons": sorted(dict.fromkeys(blockers)),
        "boundary_template_id": payload.get("boundary_template_id"),
    }
    validation["p53_boundary_template_validation_sha256"] = sha256_json(validation)
    return validation


def validate_p52_staged_source(p52_report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(p52_report or {})
    blockers: list[str] = []
    if not payload:
        return {
            "p52_source_present": False,
            "p52_source_valid_for_p53": False,
            "p52_source_block_reasons": [],
            "staged_packet": None,
            "staged_packet_sha256": None,
        }
    if payload.get("artifact_type") != "p52_p7_accepted_evidence_import_packet_staging_report":
        blockers.append("P53_P52_SOURCE_ARTIFACT_TYPE_INVALID")
    if payload.get("status") != P52_STAGED_STATUS:
        blockers.append("P53_P52_SOURCE_STATUS_NOT_STAGED_REVIEW_ONLY_NO_SUBMIT")
    for key in ("review_only", "staging_only", "external_runtime_only", "review_package_default_no_submit"):
        if payload.get(key) is not True:
            blockers.append(f"P53_P52_SOURCE_{key.upper()}_NOT_TRUE")
    for key in (
        "runtime_authority_source",
        "p7_report_persisted_by_p52",
        "p7_valid_status_written_by_p52",
        "p7_intake_execution_performed_by_p52",
        "actual_order_submission_performed",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "secret_value_accessed",
        "live_canary_execution_enabled",
        "live_scaled_execution_enabled",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P53_P52_SOURCE_{key.upper()}_NOT_FALSE")
    if payload.get("p7_import_packet_staged") is not True:
        blockers.append("P53_P52_SOURCE_PACKET_NOT_STAGED")
    staged_packet = dict(payload.get("staged_packet") or {})
    packet_validation = validate_staged_p7_import_packet(staged_packet)
    blockers.extend(packet_validation.get("staged_packet_block_reasons") or [])
    if staged_packet.get("artifact_type") != _ALLOWED_STAGED_PACKET_ARTIFACT_TYPE:
        blockers.append("P53_P52_STAGED_PACKET_ARTIFACT_TYPE_INVALID")
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P53_P52_SOURCE_UNSAFE_TRUTHY_EXECUTION_FLAGS")
    validation = {
        "p52_source_present": True,
        "p52_source_valid_for_p53": not blockers,
        "p52_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "source_status": payload.get("status"),
        "source_p52_report_sha256": payload.get("p52_p7_accepted_evidence_import_packet_staging_sha256"),
        "staged_packet": staged_packet if staged_packet else None,
        "staged_packet_sha256": staged_packet.get("p52_staged_p7_import_packet_sha256"),
        "staged_packet_validation": packet_validation,
    }
    validation["p52_source_validation_sha256"] = sha256_json(validation)
    return validation


def build_valid_operator_request_fixture(p52_report: Mapping[str, Any]) -> dict[str, Any]:
    staged_packet = dict(p52_report.get("staged_packet") or {})
    request = OperatorControlledP7ImportActionRequestTemplate(
        operator_reference_id="operator_fixture_p53_review_only",
        source_p52_staging_report_sha256=str(p52_report.get("p52_p7_accepted_evidence_import_packet_staging_sha256") or ""),
        source_p52_staged_packet_sha256=str(staged_packet.get("p52_staged_p7_import_packet_sha256") or ""),
        candidate_sha256=str(staged_packet.get("candidate_sha256") or ""),
        p7_input_preview_sha256=str(staged_packet.get("p7_input_preview_sha256") or ""),
    ).to_dict()
    request["artifact_type"] = _ALLOWED_REQUEST_ARTIFACT_TYPE
    request["request_id"] = stable_id("p53_operator_request", request, 24)
    request["request_sha256"] = sha256_json(request)
    return request


def validate_operator_request(
    operator_request: Mapping[str, Any] | None,
    *,
    p52_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(operator_request or {})
    blockers: list[str] = []
    if not payload:
        return {
            "operator_request_present": False,
            "operator_request_valid_for_arming": False,
            "operator_request_block_reasons": [],
            "operator_request_sha256": None,
        }
    if payload.get("artifact_type") != _ALLOWED_REQUEST_ARTIFACT_TYPE:
        blockers.append("P53_OPERATOR_REQUEST_ARTIFACT_TYPE_INVALID")
    if payload.get("request_sha256"):
        request_without_hash = {k: v for k, v in payload.items() if k != "request_sha256"}
        if payload.get("request_sha256") != sha256_json(request_without_hash):
            blockers.append("P53_OPERATOR_REQUEST_SHA256_MISMATCH")
    if payload.get("request_version") != P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_VERSION:
        blockers.append("P53_OPERATOR_REQUEST_VERSION_MISMATCH")
    if payload.get("exact_operator_authorization_phrase") != P53_OPERATOR_AUTHORIZATION_EXACT_PHRASE:
        blockers.append("P53_OPERATOR_REQUEST_EXACT_PHRASE_INVALID")
    if payload.get("operator_decision") != _ALLOWED_OPERATOR_DECISION:
        blockers.append("P53_OPERATOR_REQUEST_DECISION_INVALID")
    if payload.get("environment") != "testnet":
        blockers.append("P53_OPERATOR_REQUEST_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") != "binance_futures_testnet":
        blockers.append("P53_OPERATOR_REQUEST_VENUE_INVALID")
    if payload.get("symbol") != "BTCUSDT":
        blockers.append("P53_OPERATOR_REQUEST_SYMBOL_INVALID")
    for key in ("review_only", "operator_controlled", "one_packet_only", "p7_import_action_requested"):
        if payload.get(key) is not True:
            blockers.append(f"P53_OPERATOR_REQUEST_{key.upper()}_NOT_TRUE")
    for key in (
        "p7_import_execution_allowed_by_p53",
        "p7_report_persistence_allowed_by_p53",
        "p7_status_mutation_allowed_by_p53",
        "runtime_authority_requested",
        "live_canary_requested",
        "live_scaled_requested",
        "order_submission_requested",
        "secret_access_requested",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P53_OPERATOR_REQUEST_{key.upper()}_NOT_FALSE")
    if not str(payload.get("operator_reference_id") or "").strip():
        blockers.append("P53_OPERATOR_REQUEST_OPERATOR_REFERENCE_ID_MISSING")
    for key in ("operator_confirmation_hash", "one_time_action_nonce_sha256"):
        if not _is_sha256_hex(payload.get(key)):
            blockers.append(f"P53_OPERATOR_REQUEST_{key.upper()}_INVALID")
    source_validation = validate_p52_staged_source(p52_report)
    if p52_report:
        staged_packet = dict((p52_report or {}).get("staged_packet") or {})
        expected_pairs = {
            "source_p52_staging_report_sha256": (p52_report or {}).get("p52_p7_accepted_evidence_import_packet_staging_sha256"),
            "source_p52_staged_packet_sha256": staged_packet.get("p52_staged_p7_import_packet_sha256"),
            "candidate_sha256": staged_packet.get("candidate_sha256"),
            "p7_input_preview_sha256": staged_packet.get("p7_input_preview_sha256"),
        }
        for key, expected in expected_pairs.items():
            if not expected or payload.get(key) != expected:
                blockers.append(f"P53_OPERATOR_REQUEST_{key.upper()}_MISMATCH")
        blockers.extend(source_validation.get("p52_source_block_reasons") or [])
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "operator_request_present": True,
        "operator_request_valid_for_arming": not blockers,
        "operator_request_block_reasons": sorted(dict.fromkeys(blockers)),
        "operator_request_sha256": payload.get("request_sha256") or sha256_json(payload),
        "exact_phrase_valid": payload.get("exact_operator_authorization_phrase") == P53_OPERATOR_AUTHORIZATION_EXACT_PHRASE,
        "one_time_action_nonce_present": _is_sha256_hex(payload.get("one_time_action_nonce_sha256")),
        "source_hashes_match": not any("_MISMATCH" in reason for reason in blockers),
    }
    validation["operator_request_validation_sha256"] = sha256_json(validation)
    return validation


def build_armed_p7_import_action_boundary_packet(
    *,
    p52_report: Mapping[str, Any],
    operator_request: Mapping[str, Any],
) -> dict[str, Any]:
    staged_packet = dict(p52_report.get("staged_packet") or {})
    packet = {
        "artifact_type": "p53_operator_controlled_p7_import_action_boundary_ARMED_NO_IMPORT",
        "boundary_version": P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_VERSION,
        "status": STATUS_ARMED_REVIEW_ONLY_NO_IMPORT,
        "review_only": True,
        "operator_controlled": True,
        "one_packet_only": True,
        "armed_boundary_only": True,
        "runtime_authority_source": False,
        "cannot_be_used_as_runtime_authority": True,
        "p7_import_action_boundary_armed": True,
        "p7_import_action_enabled": False,
        "p7_import_action_executed": False,
        "p7_report_persisted_by_p53": False,
        "p7_valid_status_written_by_p53": False,
        "p7_intake_execution_performed_by_p53": False,
        "requires_separate_p7_import_executor": True,
        "requires_fresh_revalidation_at_import_time": True,
        "requires_one_time_nonce_consumption_by_separate_executor": True,
        "p8_repeated_session_candidate_created": False,
        "source_p52_staging_report_id": p52_report.get("p52_p7_accepted_evidence_import_packet_staging_id"),
        "source_p52_staging_report_sha256": p52_report.get("p52_p7_accepted_evidence_import_packet_staging_sha256"),
        "source_p52_staged_packet_id": staged_packet.get("p52_staged_p7_import_packet_id"),
        "source_p52_staged_packet_sha256": staged_packet.get("p52_staged_p7_import_packet_sha256"),
        "candidate_sha256": staged_packet.get("candidate_sha256"),
        "p7_input_preview_sha256": staged_packet.get("p7_input_preview_sha256"),
        "operator_request_id": operator_request.get("request_id"),
        "operator_request_sha256": operator_request.get("request_sha256") or sha256_json(operator_request),
        "operator_reference_id": operator_request.get("operator_reference_id"),
        "operator_confirmation_hash": operator_request.get("operator_confirmation_hash"),
        "one_time_action_nonce_sha256": operator_request.get("one_time_action_nonce_sha256"),
        "exact_operator_authorization_phrase_sha256": sha256_json(P53_OPERATOR_AUTHORIZATION_EXACT_PHRASE),
        "created_at_utc": utc_now_canonical(),
        **_execution_false_payload(),
    }
    packet["p53_armed_p7_import_action_boundary_id"] = stable_id("p53_armed_p7_import_action_boundary", packet, 24)
    packet["p53_armed_p7_import_action_boundary_sha256"] = sha256_json(packet)
    return packet


def validate_armed_boundary_packet(packet: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(packet or {})
    blockers: list[str] = []
    if not payload:
        return {
            "armed_boundary_packet_present": False,
            "armed_boundary_packet_valid": False,
            "armed_boundary_packet_block_reasons": [],
            "armed_boundary_packet_sha256": None,
        }
    if payload.get("artifact_type") != "p53_operator_controlled_p7_import_action_boundary_ARMED_NO_IMPORT":
        blockers.append("P53_ARMED_PACKET_ARTIFACT_TYPE_INVALID")
    if payload.get("status") != STATUS_ARMED_REVIEW_ONLY_NO_IMPORT:
        blockers.append("P53_ARMED_PACKET_STATUS_INVALID")
    for key in (
        "review_only",
        "operator_controlled",
        "one_packet_only",
        "armed_boundary_only",
        "cannot_be_used_as_runtime_authority",
        "p7_import_action_boundary_armed",
        "requires_separate_p7_import_executor",
        "requires_fresh_revalidation_at_import_time",
        "requires_one_time_nonce_consumption_by_separate_executor",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P53_ARMED_PACKET_{key.upper()}_NOT_TRUE")
    for key in (
        "runtime_authority_source",
        "p7_import_action_enabled",
        "p7_import_action_executed",
        "p7_report_persisted_by_p53",
        "p7_valid_status_written_by_p53",
        "p7_intake_execution_performed_by_p53",
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
            blockers.append(f"P53_ARMED_PACKET_{key.upper()}_NOT_FALSE")
    for key in (
        "source_p52_staging_report_sha256",
        "source_p52_staged_packet_sha256",
        "candidate_sha256",
        "p7_input_preview_sha256",
        "operator_request_sha256",
        "operator_confirmation_hash",
        "one_time_action_nonce_sha256",
    ):
        if not _is_sha256_hex(payload.get(key)):
            blockers.append(f"P53_ARMED_PACKET_{key.upper()}_INVALID")
    blockers.extend(_walk_forbidden(payload))
    unsafe = truthy_execution_flags(payload)
    if unsafe:
        blockers.append("P53_ARMED_PACKET_UNSAFE_TRUTHY_EXECUTION_FLAGS")
    validation = {
        "armed_boundary_packet_present": True,
        "armed_boundary_packet_valid": not blockers,
        "armed_boundary_packet_block_reasons": sorted(dict.fromkeys(blockers)),
        "armed_boundary_packet_sha256": payload.get("p53_armed_p7_import_action_boundary_sha256"),
    }
    validation["armed_boundary_packet_validation_sha256"] = sha256_json(validation)
    return validation


def build_p53_operator_controlled_p7_import_action_boundary_report(
    *,
    cfg: AppConfig | None = None,
    p52_report: Mapping[str, Any] | None = None,
    operator_request: Mapping[str, Any] | None = None,
    boundary_template: Mapping[str, Any] | OperatorControlledP7ImportActionBoundaryTemplate | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    source_p52 = dict(p52_report or _read_latest_json(cfg, "p52_p7_accepted_evidence_import_packet_staging_report.json"))
    template_payload = (
        boundary_template.to_dict()
        if isinstance(boundary_template, OperatorControlledP7ImportActionBoundaryTemplate)
        else dict(boundary_template or OperatorControlledP7ImportActionBoundaryTemplate().to_dict())
    )
    template_validation = validate_p53_boundary_template(template_payload)
    source_validation = validate_p52_staged_source(source_p52)
    request_validation = validate_operator_request(operator_request, p52_report=source_p52 if source_p52 else None)

    blockers = list(template_validation["p53_boundary_template_block_reasons"])
    request_present = request_validation["operator_request_present"]
    if request_present:
        blockers.extend(source_validation.get("p52_source_block_reasons") or [])
        blockers.extend(request_validation["operator_request_block_reasons"])

    armed_packet: dict[str, Any] | None = None
    armed_validation: dict[str, Any] = {
        "armed_boundary_packet_present": False,
        "armed_boundary_packet_valid": False,
        "armed_boundary_packet_block_reasons": [],
        "armed_boundary_packet_sha256": None,
    }
    if request_present and not blockers:
        armed_packet = build_armed_p7_import_action_boundary_packet(
            p52_report=source_p52,
            operator_request=dict(operator_request or {}),
        )
        armed_validation = validate_armed_boundary_packet(armed_packet)
        blockers.extend(armed_validation["armed_boundary_packet_block_reasons"])

    if blockers:
        status = STATUS_BLOCKED_FAIL_CLOSED
    elif armed_packet:
        status = STATUS_ARMED_REVIEW_ONLY_NO_IMPORT
    else:
        status = STATUS_READY_REVIEW_ONLY_NO_IMPORT

    report = {
        "artifact_type": "p53_operator_controlled_p7_import_action_boundary_report",
        "p53_boundary_version": P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_VERSION,
        "status": status,
        "blocked": status == STATUS_BLOCKED_FAIL_CLOSED,
        "fail_closed": status == STATUS_BLOCKED_FAIL_CLOSED,
        "review_only": True,
        "operator_controlled": True,
        "armed_boundary_only": True,
        "runtime_authority_source": False,
        "review_package_default_no_submit": True,
        "boundary_template": template_payload,
        "boundary_template_validation": template_validation,
        "source_p52_validation": source_validation,
        "operator_request_supplied": request_present,
        "operator_request_validation": request_validation,
        "p7_import_action_boundary_armed": bool(armed_packet and not blockers),
        "armed_boundary_packet": armed_packet if armed_packet and not blockers else None,
        "armed_boundary_packet_validation": armed_validation,
        "p7_import_action_enabled": False,
        "p7_import_action_executed": False,
        "p7_report_persisted_by_p53": False,
        "p7_valid_status_written_by_p53": False,
        "p7_intake_execution_performed_by_p53": False,
        "p7_status_mutation_performed": False,
        "p8_repeated_session_candidate_created": False,
        "actual_p7_import_requires_separate_executor_and_fresh_revalidation": True,
        "actual_endpoint_call_still_requires_separate_operator_local_runtime": True,
        "next_required_chain": [
            "operator reviews the P53 armed boundary packet and source P52 staged packet",
            "a separate P7 import executor must freshly revalidate hashes, one-time nonce, P7 schema, and no-secret evidence",
            "only that separate executor may persist one real P7 evidence record after explicit operator control",
            "P8 remains waiting until multiple clean real P7 evidence records exist",
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
        report["block_reasons"] = sorted(dict.fromkeys(report["block_reasons"] + ["P53_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
        report["p7_import_action_boundary_armed"] = False
        report["armed_boundary_packet"] = None
    report["p53_operator_controlled_p7_import_action_boundary_id"] = stable_id(
        "p53_operator_controlled_p7_import_action_boundary", report, 24
    )
    report["p53_operator_controlled_p7_import_action_boundary_sha256"] = sha256_json(report)
    return report


def _valid_p52_source_fixture(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    candidate = _valid_candidate_fixture()
    p51 = build_p51_p7_import_bridge_dry_run_report(cfg=cfg, candidate=candidate)
    return build_p52_p7_accepted_evidence_import_packet_staging_report(cfg=cfg, p51_report=p51, candidate=candidate)


def build_p53_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    valid_p52 = _valid_p52_source_fixture(cfg=cfg)
    valid_request = build_valid_operator_request_fixture(valid_p52)
    cases: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}

    invalid_phrase = deepcopy(valid_request)
    invalid_phrase["exact_operator_authorization_phrase"] = "AUTHORIZE IMPORT"
    cases["invalid_exact_phrase"] = (valid_p52, invalid_phrase)

    hash_mismatch = deepcopy(valid_request)
    hash_mismatch["source_p52_staged_packet_sha256"] = "f" * 64
    cases["staged_packet_hash_mismatch"] = (valid_p52, hash_mismatch)

    mainnet_scope = deepcopy(valid_request)
    mainnet_scope["environment"] = "mainnet"
    cases["mainnet_scope"] = (valid_p52, mainnet_scope)

    runtime_authority = deepcopy(valid_request)
    runtime_authority["runtime_authority_requested"] = True
    cases["runtime_authority_requested"] = (valid_p52, runtime_authority)

    import_execution = deepcopy(valid_request)
    import_execution["p7_import_execution_allowed_by_p53"] = True
    cases["p53_import_execution_attempt"] = (valid_p52, import_execution)

    secret_field = deepcopy(valid_request)
    secret_field["api_secret"] = "forbidden"
    cases["secret_field_in_request"] = (valid_p52, secret_field)

    invalid_packet_source = deepcopy(valid_p52)
    invalid_packet_source["staged_packet"]["p7_valid_status_written_by_p52"] = True
    cases["mutated_staged_packet"] = (invalid_packet_source, valid_request)

    results: dict[str, Any] = {}
    for name, (source, request) in cases.items():
        report = build_p53_operator_controlled_p7_import_action_boundary_report(
            cfg=cfg,
            p52_report=source,
            operator_request=request,
        )
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": report["blocked"] is True,
            "status": report["status"],
            "block_reasons": report["block_reasons"],
            "p7_import_action_boundary_armed": report["p7_import_action_boundary_armed"],
            "p7_import_action_executed": report["p7_import_action_executed"],
            "p7_report_persisted_by_p53": report["p7_report_persisted_by_p53"],
        }

    armed = build_p53_operator_controlled_p7_import_action_boundary_report(
        cfg=cfg,
        p52_report=valid_p52,
        operator_request=valid_request,
    )
    payload = {
        "artifact_type": "p53_operator_controlled_p7_import_action_boundary_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()),
        "fixture_results": results,
        "valid_fixture_arms_boundary_no_import": armed["p7_import_action_boundary_armed"] is True,
        "valid_fixture_status": armed["status"],
        "p7_import_action_executed": False,
        "p7_report_persisted_by_p53": False,
        "p7_valid_status_written_by_p53": False,
        **_execution_false_payload(),
    }
    payload["p53_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def persist_p53_operator_controlled_p7_import_action_boundary(
    *,
    cfg: AppConfig | None = None,
    p52_report: Mapping[str, Any] | None = None,
    operator_request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    report = build_p53_operator_controlled_p7_import_action_boundary_report(
        cfg=cfg,
        p52_report=p52_report,
        operator_request=operator_request,
    )
    template = OperatorControlledP7ImportActionBoundaryTemplate().to_dict()
    request_template = OperatorControlledP7ImportActionRequestTemplate().to_dict()
    armed_template = {
        "artifact_type": "p53_operator_controlled_p7_import_action_boundary_ARMED_TEMPLATE_NO_IMPORT",
        "status": STATUS_READY_REVIEW_ONLY_NO_IMPORT,
        "review_only": True,
        "operator_controlled": True,
        "p7_import_action_boundary_armed": False,
        "p7_import_action_enabled": False,
        "p7_import_action_executed": False,
        "p7_report_persisted_by_p53": False,
        "p7_valid_status_written_by_p53": False,
        "requires_separate_p7_import_executor": True,
        "requires_fresh_revalidation_at_import_time": True,
        "source_p52_staged_packet_sha256": "P52_STAGED_PACKET_SHA256_REQUIRED",
        "candidate_sha256": "CANDIDATE_SHA256_REQUIRED",
        "one_time_action_nonce_sha256": "ONE_TIME_NONCE_SHA256_REQUIRED",
        **_execution_false_payload(),
    }
    armed_template["p53_armed_boundary_template_sha256"] = sha256_json(armed_template)
    negative = build_p53_negative_fixture_results(cfg=cfg)

    registry_record = {
        "artifact_type": "p53_operator_controlled_p7_import_action_boundary_registry_record",
        "p53_operator_controlled_p7_import_action_boundary_id": report[
            "p53_operator_controlled_p7_import_action_boundary_id"
        ],
        "p53_operator_controlled_p7_import_action_boundary_sha256": report[
            "p53_operator_controlled_p7_import_action_boundary_sha256"
        ],
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": True,
        "operator_controlled": True,
        "p7_import_action_boundary_armed": report["p7_import_action_boundary_armed"],
        "p7_import_action_executed": False,
        "p7_report_persisted_by_p53": False,
        "created_at_utc": report["created_at_utc"],
    }
    registry_record["p53_registry_record_sha256"] = sha256_json(registry_record)
    append_registry_record(
        registry_path(cfg, P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_REGISTRY_NAME),
        registry_record,
        registry_name=P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_REGISTRY_NAME,
    )

    summary = {
        "artifact_type": "p53_operator_controlled_p7_import_action_boundary_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": report["review_only"],
        "operator_controlled": report["operator_controlled"],
        "operator_request_supplied": report["operator_request_supplied"],
        "p7_import_action_boundary_armed": report["p7_import_action_boundary_armed"],
        "p7_import_action_enabled": report["p7_import_action_enabled"],
        "p7_import_action_executed": report["p7_import_action_executed"],
        "p7_report_persisted_by_p53": report["p7_report_persisted_by_p53"],
        "p7_valid_status_written_by_p53": report["p7_valid_status_written_by_p53"],
        "actual_order_submission_performed": report["actual_order_submission_performed"],
        "order_endpoint_called": report["order_endpoint_called"],
        "http_request_sent": report["http_request_sent"],
        "signature_created": report["signature_created"],
        "secret_value_accessed": report["secret_value_accessed"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "valid_fixture_arms_boundary_no_import": negative["valid_fixture_arms_boundary_no_import"],
        "p53_operator_controlled_p7_import_action_boundary_id": report[
            "p53_operator_controlled_p7_import_action_boundary_id"
        ],
        "p53_operator_controlled_p7_import_action_boundary_sha256": report[
            "p53_operator_controlled_p7_import_action_boundary_sha256"
        ],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p53_summary_sha256"] = sha256_json(summary)

    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p53_operator_controlled_p7_import_action_boundary")
    writes = {
        "p53_operator_controlled_p7_import_action_boundary_report.json": report,
        "p53_operator_controlled_p7_import_action_boundary_TEMPLATE_NO_IMPORT.json": template,
        "p53_operator_controlled_p7_import_action_request_TEMPLATE_NO_IMPORT.json": request_template,
        "p53_operator_controlled_p7_import_action_boundary_ARMED_TEMPLATE_NO_IMPORT.json": armed_template,
        "p53_operator_controlled_p7_import_action_boundary_negative_fixture_results.json": negative,
        "p53_operator_controlled_p7_import_action_boundary_registry_record.json": registry_record,
        "p53_operator_controlled_p7_import_action_boundary_summary.json": summary,
    }
    for filename, payload in writes.items():
        atomic_write_json(latest / filename, payload)
        atomic_write_json(storage / filename, payload)
    return report


__all__ = [
    "P53_OPERATOR_CONTROLLED_P7_IMPORT_ACTION_BOUNDARY_VERSION",
    "P53_OPERATOR_AUTHORIZATION_EXACT_PHRASE",
    "STATUS_READY_REVIEW_ONLY_NO_IMPORT",
    "STATUS_ARMED_REVIEW_ONLY_NO_IMPORT",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "OperatorControlledP7ImportActionBoundaryTemplate",
    "OperatorControlledP7ImportActionRequestTemplate",
    "validate_p53_boundary_template",
    "validate_p52_staged_source",
    "build_valid_operator_request_fixture",
    "validate_operator_request",
    "build_armed_p7_import_action_boundary_packet",
    "validate_armed_boundary_packet",
    "build_p53_operator_controlled_p7_import_action_boundary_report",
    "build_p53_negative_fixture_results",
    "persist_p53_operator_controlled_p7_import_action_boundary",
]
