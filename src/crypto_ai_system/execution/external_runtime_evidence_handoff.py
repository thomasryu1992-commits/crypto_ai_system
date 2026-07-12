from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION = "p49_external_runtime_evidence_handoff_v1"
P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_REGISTRY_NAME = "p49_external_runtime_evidence_handoff_registry"
STATUS_READY_REVIEW_ONLY_NO_SUBMIT = "P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_READY_REVIEW_ONLY_NO_SUBMIT"
STATUS_BLOCKED_FAIL_CLOSED = "P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_BLOCKED_FAIL_CLOSED"

_ALLOWED_ENVIRONMENTS = {"testnet"}
_ALLOWED_VENUES = {"binance_futures_testnet"}
_ALLOWED_SYMBOLS = {"BTCUSDT"}
_SHA_PLACEHOLDER = "0" * 64
_FORBIDDEN_SECRET_FIELD_NAMES = {
    "api_key",
    "api_secret",
    "secret",
    "secret_value",
    "private_key",
    "passphrase",
    "binance_api_key",
    "binance_api_secret",
    "raw_api_key",
    "raw_api_secret",
}
_FORBIDDEN_SCOPE_TOKENS = (
    "mainnet",
    "live_trade",
    "withdraw",
    "transfer",
    "admin",
    "margin_mutation",
    "leverage_mutation",
)
_FORBIDDEN_LOG_PATTERNS = (
    "api_secret=",
    "apiSecret=",
    "api-secret:",
    "secret_value=",
    "private_key=",
    "passphrase=",
    "BEGIN PRIVATE KEY",
    "BINANCE_API_SECRET=",
    "BINANCE_API_KEY=",
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


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _execution_false_payload() -> dict[str, bool]:
    payload = default_execution_flag_state()
    payload.update(
        {
            "actual_testnet_order_submitted": False,
            "actual_live_order_submitted": False,
            "actual_order_submission_performed": False,
            "external_order_submission_performed": False,
            "order_endpoint_called": False,
            "order_status_endpoint_called": False,
            "cancel_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "api_key_value_logged": False,
            "api_secret_value_logged": False,
            "private_key_logged": False,
            "passphrase_logged": False,
            "secret_file_accessed": False,
            "secret_file_created": False,
            "runtime_network_call_allowed_by_operator": False,
            "runtime_scheduler_enabled": False,
            "runtime_loop_started": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
            "live_execution_unlock_authority": False,
            "signed_testnet_unlock_authority": False,
        }
    )
    return payload


@dataclass(frozen=True)
class RedactedSubmitResponseBundleTemplate:
    bundle_template_id: str = "p49_redacted_submit_response_bundle_TEMPLATE_NO_SUBMIT"
    bundle_schema_version: str = P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION
    evidence_origin: str = "real_signed_testnet_external_runtime"
    generated_by_review_package: bool = True
    can_grant_runtime_authority: bool = False
    review_package_default_no_submit: bool = True
    external_runtime_only: bool = True
    environment: str = "testnet"
    venue: str = "binance_futures_testnet"
    symbol: str = "BTCUSDT"
    order_count: int = 1
    exchange_order_id_required: bool = True
    client_order_id_required: bool = True
    idempotency_key_required: bool = True
    request_hash_required: bool = True
    response_hash_required: bool = True
    raw_exchange_response_redacted_required: bool = True
    raw_exchange_response_redacted_path: str = "EXTERNAL_RUNTIME_OUTPUT/redacted_submit_response.json"
    raw_exchange_payload_included_in_review_package: bool = False
    request_body_included_in_review_package: bool = False
    signed_payload_included_in_review_package: bool = False
    hot_path_preorder_risk_gate_id_required: bool = True
    hot_path_preorder_risk_gate_hash_required: bool = True
    secret_reference_id_required: bool = True
    key_fingerprint_sha256_required: bool = True
    no_secret_log_scan_required: bool = True
    status_polling_evidence_required: bool = True
    cancel_boundary_evidence_required: bool = True
    reconciliation_evidence_required: bool = True
    session_close_evidence_required: bool = True
    p7_bridge_required: bool = True
    actual_endpoint_call_performed_by_this_package: bool = False
    http_request_sent_by_this_package: bool = False
    signature_created_by_this_package: bool = False
    secret_value_accessed_by_this_package: bool = False
    request_hash_placeholder: str = _SHA_PLACEHOLDER
    exchange_response_hash_placeholder: str = _SHA_PLACEHOLDER
    key_fingerprint_sha256_placeholder: str = _SHA_PLACEHOLDER
    no_secret_logged_evidence_hash_placeholder: str = _SHA_PLACEHOLDER

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["redacted_submit_response_bundle_template_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class ExternalRuntimeExecutionTranscriptSchema:
    transcript_schema_id: str = "p49_external_runtime_execution_transcript_SCHEMA_NO_SUBMIT"
    transcript_schema_version: str = P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION
    generated_by_review_package: bool = True
    can_grant_runtime_authority: bool = False
    review_package_default_no_submit: bool = True
    external_runtime_only: bool = True
    environment: str = "testnet"
    venue: str = "binance_futures_testnet"
    symbol: str = "BTCUSDT"
    max_order_count: int = 1
    required_sections: tuple[str, ...] = (
        "operator_arming_reference",
        "p6_external_runtime_preflight_report_hash",
        "p48_connector_request_hash",
        "hot_path_preorder_risk_gate_hash",
        "idempotency_key",
        "redacted_submit_response_hash",
        "status_polling_hash_chain",
        "cancel_boundary_decision",
        "reconciliation_summary",
        "session_close_summary",
        "no_secret_log_scan_report_hash",
    )
    forbidden_sections: tuple[str, ...] = (
        "raw_api_key",
        "raw_api_secret",
        "private_key",
        "passphrase",
        "raw_signed_payload",
        "unredacted_exchange_response",
    )
    raw_secret_values_allowed: bool = False
    raw_signed_payload_allowed: bool = False
    raw_exchange_payload_allowed: bool = False
    order_endpoint_call_performed_by_review_package: bool = False
    http_request_sent_by_review_package: bool = False
    signature_created_by_review_package: bool = False
    secret_value_accessed_by_review_package: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["execution_transcript_schema_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class NoSecretLogScanTemplate:
    scan_template_id: str = "p49_no_secret_log_scan_TEMPLATE"
    scan_template_version: str = P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION
    generated_by_review_package: bool = True
    scanner_is_review_only: bool = True
    raw_log_ingestion_by_review_package: bool = False
    operator_supplies_redacted_log_paths_only: bool = True
    forbidden_patterns: tuple[str, ...] = _FORBIDDEN_LOG_PATTERNS
    forbidden_secret_fields: tuple[str, ...] = tuple(sorted(_FORBIDDEN_SECRET_FIELD_NAMES))
    required_scan_outputs: tuple[str, ...] = (
        "scanned_file_count",
        "forbidden_pattern_match_count",
        "raw_secret_value_match_count",
        "api_key_value_logged",
        "api_secret_value_logged",
        "private_key_logged",
        "passphrase_logged",
        "no_secret_logged_evidence_hash",
    )
    no_secret_log_scan_required_before_p7_intake: bool = True
    can_grant_runtime_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["no_secret_log_scan_template_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P7IntakeBridgeTemplate:
    bridge_template_id: str = "p49_p7_intake_bridge_TEMPLATE_NO_SUBMIT"
    bridge_schema_version: str = P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION
    generated_by_review_package: bool = True
    review_only: bool = True
    can_grant_runtime_authority: bool = False
    p7_intake_target: str = "crypto_ai_system.execution.post_submit_evidence_intake.build_post_submit_evidence_intake_report"
    p7_report_filename: str = "p7_post_submit_evidence_intake_report.json"
    required_external_runtime_inputs: tuple[str, ...] = (
        "p6_submitted_report_redacted.json",
        "redacted_submit_response_bundle.json",
        "external_runtime_execution_transcript.json",
        "no_secret_log_scan_report.json",
        "status_polling_evidence.json",
        "cancel_boundary_evidence.json",
        "signed_testnet_reconciliation_evidence.json",
        "signed_testnet_session_close_evidence.json",
    )
    required_hash_chain: tuple[str, ...] = (
        "p6_single_signed_testnet_submit_runtime_action_sha256",
        "p48_local_runtime_adapter_connector_sha256",
        "request_hash",
        "exchange_response_hash",
        "status_polling_hash_chain_sha256",
        "reconciliation_evidence_sha256",
        "session_close_evidence_sha256",
        "no_secret_logged_evidence_hash",
    )
    output_must_remain_review_only: bool = True
    p7_may_validate_real_evidence_after_external_submit: bool = True
    p8_must_require_repeated_real_sessions_after_p7: bool = True
    no_order_submission_performed_by_bridge: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p7_intake_bridge_template_sha256"] = sha256_json(payload)
        return payload


def scan_log_text_for_secret_leaks(text: str, *, extra_forbidden_tokens: Sequence[str] | None = None) -> dict[str, Any]:
    haystack = str(text or "")
    patterns = list(_FORBIDDEN_LOG_PATTERNS) + [str(token) for token in list(extra_forbidden_tokens or []) if _nonempty(token)]
    matched = sorted({pattern for pattern in patterns if pattern and pattern in haystack})
    result = {
        "artifact_type": "p49_no_secret_log_text_scan_result",
        "scanner_version": P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION,
        "secret_leak_detected": bool(matched),
        "forbidden_pattern_match_count": len(matched),
        "matched_patterns": matched,
        "scan_text_sha256": sha256_json({"text": haystack}),
    }
    result["no_secret_log_text_scan_sha256"] = sha256_json(result)
    return result


def validate_redacted_submit_response_bundle_template(template: Mapping[str, Any] | RedactedSubmitResponseBundleTemplate | None) -> dict[str, Any]:
    payload = template.to_dict() if isinstance(template, RedactedSubmitResponseBundleTemplate) else dict(template or {})
    blockers: list[str] = []
    if payload.get("bundle_schema_version") != P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION:
        blockers.append("P49_BUNDLE_TEMPLATE_VERSION_MISMATCH")
    if payload.get("evidence_origin") != "real_signed_testnet_external_runtime":
        blockers.append("P49_BUNDLE_EVIDENCE_ORIGIN_INVALID")
    if payload.get("generated_by_review_package") is not True:
        blockers.append("P49_BUNDLE_NOT_GENERATED_BY_REVIEW_PACKAGE")
    if payload.get("can_grant_runtime_authority") is not False:
        blockers.append("P49_BUNDLE_CAN_GRANT_RUNTIME_AUTHORITY")
    if payload.get("review_package_default_no_submit") is not True:
        blockers.append("P49_BUNDLE_REVIEW_PACKAGE_NO_SUBMIT_NOT_TRUE")
    if payload.get("external_runtime_only") is not True:
        blockers.append("P49_BUNDLE_NOT_EXTERNAL_RUNTIME_ONLY")
    if payload.get("environment") not in _ALLOWED_ENVIRONMENTS:
        blockers.append("P49_BUNDLE_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") not in _ALLOWED_VENUES:
        blockers.append("P49_BUNDLE_VENUE_NOT_TESTNET_SCOPED")
    if payload.get("symbol") not in _ALLOWED_SYMBOLS:
        blockers.append("P49_BUNDLE_SYMBOL_NOT_BTCUSDT")
    if int(payload.get("order_count") or 0) != 1:
        blockers.append("P49_BUNDLE_ORDER_COUNT_NOT_ONE")
    required_true = (
        "exchange_order_id_required",
        "client_order_id_required",
        "idempotency_key_required",
        "request_hash_required",
        "response_hash_required",
        "raw_exchange_response_redacted_required",
        "hot_path_preorder_risk_gate_id_required",
        "hot_path_preorder_risk_gate_hash_required",
        "secret_reference_id_required",
        "key_fingerprint_sha256_required",
        "no_secret_log_scan_required",
        "status_polling_evidence_required",
        "cancel_boundary_evidence_required",
        "reconciliation_evidence_required",
        "session_close_evidence_required",
        "p7_bridge_required",
    )
    for key in required_true:
        if payload.get(key) is not True:
            blockers.append(f"P49_BUNDLE_{key.upper()}_NOT_TRUE")
    required_false = (
        "raw_exchange_payload_included_in_review_package",
        "request_body_included_in_review_package",
        "signed_payload_included_in_review_package",
        "actual_endpoint_call_performed_by_this_package",
        "http_request_sent_by_this_package",
        "signature_created_by_this_package",
        "secret_value_accessed_by_this_package",
    )
    for key in required_false:
        if payload.get(key) is not False:
            blockers.append(f"P49_BUNDLE_{key.upper()}_NOT_FALSE")
    for key in (
        "request_hash_placeholder",
        "exchange_response_hash_placeholder",
        "key_fingerprint_sha256_placeholder",
        "no_secret_logged_evidence_hash_placeholder",
    ):
        if not _is_sha256_hex(payload.get(key)):
            blockers.append(f"P49_BUNDLE_{key.upper()}_NOT_SHA256_SHAPED")
    for key, value in payload.items():
        key_l = str(key).strip().lower()
        value_l = str(value or "").strip().lower()
        if key_l in _FORBIDDEN_SECRET_FIELD_NAMES and _nonempty(value):
            blockers.append(f"P49_BUNDLE_FORBIDDEN_SECRET_FIELD_PRESENT:{key}")
        if any(token in value_l for token in _FORBIDDEN_SCOPE_TOKENS):
            blockers.append(f"P49_BUNDLE_FORBIDDEN_SCOPE_TOKEN_PRESENT:{key}")
    validation = {
        "redacted_submit_response_bundle_template_valid": not blockers,
        "redacted_submit_response_bundle_template_block_reasons": sorted(dict.fromkeys(blockers)),
        "bundle_template_id": payload.get("bundle_template_id"),
        "environment": payload.get("environment"),
        "venue": payload.get("venue"),
        "symbol": payload.get("symbol"),
        "can_grant_runtime_authority": payload.get("can_grant_runtime_authority") is True,
    }
    validation["redacted_submit_response_bundle_template_validation_sha256"] = sha256_json(validation)
    return validation


def validate_execution_transcript_schema(schema: Mapping[str, Any] | ExternalRuntimeExecutionTranscriptSchema | None) -> dict[str, Any]:
    payload = schema.to_dict() if isinstance(schema, ExternalRuntimeExecutionTranscriptSchema) else dict(schema or {})
    blockers: list[str] = []
    if payload.get("transcript_schema_version") != P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION:
        blockers.append("P49_TRANSCRIPT_SCHEMA_VERSION_MISMATCH")
    if payload.get("generated_by_review_package") is not True:
        blockers.append("P49_TRANSCRIPT_NOT_GENERATED_BY_REVIEW_PACKAGE")
    if payload.get("can_grant_runtime_authority") is not False:
        blockers.append("P49_TRANSCRIPT_CAN_GRANT_RUNTIME_AUTHORITY")
    if payload.get("review_package_default_no_submit") is not True:
        blockers.append("P49_TRANSCRIPT_REVIEW_PACKAGE_NO_SUBMIT_NOT_TRUE")
    if payload.get("external_runtime_only") is not True:
        blockers.append("P49_TRANSCRIPT_NOT_EXTERNAL_RUNTIME_ONLY")
    if payload.get("environment") not in _ALLOWED_ENVIRONMENTS:
        blockers.append("P49_TRANSCRIPT_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") not in _ALLOWED_VENUES:
        blockers.append("P49_TRANSCRIPT_VENUE_NOT_TESTNET_SCOPED")
    if payload.get("symbol") not in _ALLOWED_SYMBOLS:
        blockers.append("P49_TRANSCRIPT_SYMBOL_NOT_BTCUSDT")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("P49_TRANSCRIPT_MAX_ORDER_COUNT_NOT_ONE")
    if len(tuple(payload.get("required_sections") or ())) < 8:
        blockers.append("P49_TRANSCRIPT_REQUIRED_SECTIONS_INCOMPLETE")
    for key in (
        "raw_secret_values_allowed",
        "raw_signed_payload_allowed",
        "raw_exchange_payload_allowed",
        "order_endpoint_call_performed_by_review_package",
        "http_request_sent_by_review_package",
        "signature_created_by_review_package",
        "secret_value_accessed_by_review_package",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P49_TRANSCRIPT_{key.upper()}_NOT_FALSE")
    validation = {
        "execution_transcript_schema_valid": not blockers,
        "execution_transcript_schema_block_reasons": sorted(dict.fromkeys(blockers)),
        "transcript_schema_id": payload.get("transcript_schema_id"),
        "required_section_count": len(tuple(payload.get("required_sections") or ())),
        "can_grant_runtime_authority": payload.get("can_grant_runtime_authority") is True,
    }
    validation["execution_transcript_schema_validation_sha256"] = sha256_json(validation)
    return validation


def validate_no_secret_log_scan_template(template: Mapping[str, Any] | NoSecretLogScanTemplate | None) -> dict[str, Any]:
    payload = template.to_dict() if isinstance(template, NoSecretLogScanTemplate) else dict(template or {})
    blockers: list[str] = []
    if payload.get("scan_template_version") != P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION:
        blockers.append("P49_LOG_SCAN_TEMPLATE_VERSION_MISMATCH")
    if payload.get("generated_by_review_package") is not True:
        blockers.append("P49_LOG_SCAN_NOT_GENERATED_BY_REVIEW_PACKAGE")
    if payload.get("scanner_is_review_only") is not True:
        blockers.append("P49_LOG_SCAN_NOT_REVIEW_ONLY")
    if payload.get("raw_log_ingestion_by_review_package") is not False:
        blockers.append("P49_LOG_SCAN_RAW_LOG_INGESTION_ENABLED")
    if payload.get("operator_supplies_redacted_log_paths_only") is not True:
        blockers.append("P49_LOG_SCAN_REDACTED_LOG_PATHS_ONLY_NOT_TRUE")
    if payload.get("no_secret_log_scan_required_before_p7_intake") is not True:
        blockers.append("P49_LOG_SCAN_NOT_REQUIRED_BEFORE_P7")
    if payload.get("can_grant_runtime_authority") is not False:
        blockers.append("P49_LOG_SCAN_CAN_GRANT_RUNTIME_AUTHORITY")
    if len(tuple(payload.get("forbidden_patterns") or ())) < 5:
        blockers.append("P49_LOG_SCAN_FORBIDDEN_PATTERNS_INCOMPLETE")
    validation = {
        "no_secret_log_scan_template_valid": not blockers,
        "no_secret_log_scan_template_block_reasons": sorted(dict.fromkeys(blockers)),
        "scan_template_id": payload.get("scan_template_id"),
        "forbidden_pattern_count": len(tuple(payload.get("forbidden_patterns") or ())),
    }
    validation["no_secret_log_scan_template_validation_sha256"] = sha256_json(validation)
    return validation


def validate_p7_intake_bridge_template(template: Mapping[str, Any] | P7IntakeBridgeTemplate | None) -> dict[str, Any]:
    payload = template.to_dict() if isinstance(template, P7IntakeBridgeTemplate) else dict(template or {})
    blockers: list[str] = []
    if payload.get("bridge_schema_version") != P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION:
        blockers.append("P49_P7_BRIDGE_VERSION_MISMATCH")
    if payload.get("generated_by_review_package") is not True:
        blockers.append("P49_P7_BRIDGE_NOT_GENERATED_BY_REVIEW_PACKAGE")
    if payload.get("review_only") is not True:
        blockers.append("P49_P7_BRIDGE_NOT_REVIEW_ONLY")
    if payload.get("can_grant_runtime_authority") is not False:
        blockers.append("P49_P7_BRIDGE_CAN_GRANT_RUNTIME_AUTHORITY")
    if payload.get("output_must_remain_review_only") is not True:
        blockers.append("P49_P7_BRIDGE_OUTPUT_REVIEW_ONLY_NOT_TRUE")
    if payload.get("p7_may_validate_real_evidence_after_external_submit") is not True:
        blockers.append("P49_P7_BRIDGE_DOES_NOT_ALLOW_P7_REAL_EVIDENCE_VALIDATION")
    if payload.get("p8_must_require_repeated_real_sessions_after_p7") is not True:
        blockers.append("P49_P7_BRIDGE_DOES_NOT_REQUIRE_P8_REAL_SESSIONS")
    if payload.get("no_order_submission_performed_by_bridge") is not True:
        blockers.append("P49_P7_BRIDGE_ORDER_SUBMISSION_PERFORMED")
    if len(tuple(payload.get("required_external_runtime_inputs") or ())) < 6:
        blockers.append("P49_P7_BRIDGE_REQUIRED_INPUTS_INCOMPLETE")
    if len(tuple(payload.get("required_hash_chain") or ())) < 6:
        blockers.append("P49_P7_BRIDGE_REQUIRED_HASH_CHAIN_INCOMPLETE")
    validation = {
        "p7_intake_bridge_template_valid": not blockers,
        "p7_intake_bridge_template_block_reasons": sorted(dict.fromkeys(blockers)),
        "bridge_template_id": payload.get("bridge_template_id"),
        "required_input_count": len(tuple(payload.get("required_external_runtime_inputs") or ())),
        "required_hash_chain_count": len(tuple(payload.get("required_hash_chain") or ())),
    }
    validation["p7_intake_bridge_template_validation_sha256"] = sha256_json(validation)
    return validation


def validate_p48_connector_source(p48_report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(p48_report or {})
    blockers: list[str] = []
    if payload.get("artifact_type") != "p48_local_runtime_adapter_connector_report":
        blockers.append("P49_P48_CONNECTOR_ARTIFACT_TYPE_INVALID")
    if payload.get("status") != "P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_READY_REVIEW_ONLY_NO_SUBMIT":
        blockers.append("P49_P48_CONNECTOR_STATUS_NOT_READY_NO_SUBMIT")
    if payload.get("review_package_default_no_submit") is not True:
        blockers.append("P49_P48_CONNECTOR_NOT_REVIEW_PACKAGE_NO_SUBMIT")
    if payload.get("connector_design_only") is not True:
        blockers.append("P49_P48_CONNECTOR_NOT_DESIGN_ONLY")
    if payload.get("connector_can_be_attached_by_this_package") is not False:
        blockers.append("P49_P48_CONNECTOR_CAN_ATTACH_BY_THIS_PACKAGE")
    for key in (
        "actual_order_submission_performed",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "secret_value_accessed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P49_P48_CONNECTOR_{key.upper()}_NOT_FALSE")
    validation = {
        "p48_connector_source_valid": not blockers,
        "p48_connector_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "source_status": payload.get("status"),
        "source_sha256": payload.get("p48_local_runtime_adapter_connector_sha256"),
    }
    validation["p48_connector_source_validation_sha256"] = sha256_json(validation)
    return validation


def build_p49_external_runtime_evidence_handoff_report(
    *,
    cfg: AppConfig | None = None,
    bundle_template: Mapping[str, Any] | RedactedSubmitResponseBundleTemplate | None = None,
    transcript_schema: Mapping[str, Any] | ExternalRuntimeExecutionTranscriptSchema | None = None,
    log_scan_template: Mapping[str, Any] | NoSecretLogScanTemplate | None = None,
    p7_bridge_template: Mapping[str, Any] | P7IntakeBridgeTemplate | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p48_report = _read_latest_json(cfg, "p48_local_runtime_adapter_connector_report.json")
    bundle_payload = bundle_template.to_dict() if isinstance(bundle_template, RedactedSubmitResponseBundleTemplate) else dict(bundle_template or RedactedSubmitResponseBundleTemplate().to_dict())
    transcript_payload = transcript_schema.to_dict() if isinstance(transcript_schema, ExternalRuntimeExecutionTranscriptSchema) else dict(transcript_schema or ExternalRuntimeExecutionTranscriptSchema().to_dict())
    scan_payload = log_scan_template.to_dict() if isinstance(log_scan_template, NoSecretLogScanTemplate) else dict(log_scan_template or NoSecretLogScanTemplate().to_dict())
    bridge_payload = p7_bridge_template.to_dict() if isinstance(p7_bridge_template, P7IntakeBridgeTemplate) else dict(p7_bridge_template or P7IntakeBridgeTemplate().to_dict())

    p48_validation = validate_p48_connector_source(p48_report)
    bundle_validation = validate_redacted_submit_response_bundle_template(bundle_payload)
    transcript_validation = validate_execution_transcript_schema(transcript_payload)
    scan_validation = validate_no_secret_log_scan_template(scan_payload)
    bridge_validation = validate_p7_intake_bridge_template(bridge_payload)
    blockers = sorted(
        dict.fromkeys(
            list(p48_validation["p48_connector_source_block_reasons"])
            + list(bundle_validation["redacted_submit_response_bundle_template_block_reasons"])
            + list(transcript_validation["execution_transcript_schema_block_reasons"])
            + list(scan_validation["no_secret_log_scan_template_block_reasons"])
            + list(bridge_validation["p7_intake_bridge_template_block_reasons"])
        )
    )
    status = STATUS_READY_REVIEW_ONLY_NO_SUBMIT if not blockers else STATUS_BLOCKED_FAIL_CLOSED
    report = {
        "artifact_type": "p49_external_runtime_evidence_handoff_report",
        "p49_external_runtime_evidence_handoff_version": P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION,
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "runtime_authority_source": False,
        "handoff_skeleton_only": True,
        "external_runtime_only": True,
        "review_package_default_no_submit": True,
        "actual_endpoint_call_still_requires_separate_operator_local_runtime": True,
        "source_p48_connector_validation": p48_validation,
        "redacted_submit_response_bundle_template": bundle_payload,
        "redacted_submit_response_bundle_template_validation": bundle_validation,
        "external_runtime_execution_transcript_schema": transcript_payload,
        "external_runtime_execution_transcript_schema_validation": transcript_validation,
        "no_secret_log_scan_template": scan_payload,
        "no_secret_log_scan_template_validation": scan_validation,
        "p7_intake_bridge_template": bridge_payload,
        "p7_intake_bridge_template_validation": bridge_validation,
        "next_required_chain": [
            "operator runs separate local runtime outside review ZIP",
            "operator exports redacted submit response bundle",
            "operator exports execution transcript without secrets",
            "operator exports no-secret log scan report",
            "P7 bridge validates real post-submit evidence intake",
            "P8 accumulates repeated clean signed testnet sessions",
        ],
        "block_reasons": blockers,
        "created_at_utc": utc_now_canonical(),
        **_execution_false_payload(),
    }
    unsafe = truthy_execution_flags(report)
    report["unsafe_truthy_execution_flags"] = unsafe
    if unsafe:
        report["status"] = STATUS_BLOCKED_FAIL_CLOSED
        report["blocked"] = True
        report["fail_closed"] = True
        report["block_reasons"] = sorted(dict.fromkeys(blockers + ["P49_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
    report["p49_external_runtime_evidence_handoff_id"] = stable_id("p49_external_runtime_evidence_handoff", report, 24)
    report["p49_external_runtime_evidence_handoff_sha256"] = sha256_json(report)
    return report


def build_p49_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    cases: dict[str, tuple[str, Mapping[str, Any]]] = {
        "mainnet_bundle": ("bundle", {**RedactedSubmitResponseBundleTemplate().to_dict(), "environment": "mainnet", "venue": "binance_mainnet"}),
        "bundle_raw_payload_included": ("bundle", {**RedactedSubmitResponseBundleTemplate().to_dict(), "raw_exchange_payload_included_in_review_package": True}),
        "bundle_secret_field_present": ("bundle", {**RedactedSubmitResponseBundleTemplate().to_dict(), "api_secret": "SHOULD_NOT_EXIST"}),
        "transcript_runtime_authority": ("transcript", {**ExternalRuntimeExecutionTranscriptSchema().to_dict(), "can_grant_runtime_authority": True}),
        "transcript_review_package_endpoint_call": ("transcript", {**ExternalRuntimeExecutionTranscriptSchema().to_dict(), "order_endpoint_call_performed_by_review_package": True}),
        "log_scan_raw_log_ingestion_enabled": ("scan", {**NoSecretLogScanTemplate().to_dict(), "raw_log_ingestion_by_review_package": True}),
        "p7_bridge_order_submission_performed": ("bridge", {**P7IntakeBridgeTemplate().to_dict(), "no_order_submission_performed_by_bridge": False}),
        "p7_bridge_runtime_authority": ("bridge", {**P7IntakeBridgeTemplate().to_dict(), "can_grant_runtime_authority": True}),
    }
    results: dict[str, Any] = {}
    for name, (kind, payload) in cases.items():
        if kind == "bundle":
            validation = validate_redacted_submit_response_bundle_template(payload)
            blocked = validation["redacted_submit_response_bundle_template_valid"] is False
            reasons = validation["redacted_submit_response_bundle_template_block_reasons"]
        elif kind == "transcript":
            validation = validate_execution_transcript_schema(payload)
            blocked = validation["execution_transcript_schema_valid"] is False
            reasons = validation["execution_transcript_schema_block_reasons"]
        elif kind == "scan":
            validation = validate_no_secret_log_scan_template(payload)
            blocked = validation["no_secret_log_scan_template_valid"] is False
            reasons = validation["no_secret_log_scan_template_block_reasons"]
        else:
            validation = validate_p7_intake_bridge_template(payload)
            blocked = validation["p7_intake_bridge_template_valid"] is False
            reasons = validation["p7_intake_bridge_template_block_reasons"]
        results[name] = {
            "fixture_name": name,
            "fixture_kind": kind,
            "blocked_fail_closed": blocked,
            "block_reasons": reasons,
            "validation": validation,
        }
    secret_scan = scan_log_text_for_secret_leaks("INFO ok\nBINANCE_API_SECRET=raw-secret-should-block\n")
    result = {
        "artifact_type": "p49_external_runtime_evidence_handoff_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in results.values()) and secret_scan["secret_leak_detected"] is True,
        "fixture_results": results,
        "secret_scan_negative_fixture": secret_scan,
        **_execution_false_payload(),
    }
    result["p49_negative_fixture_results_sha256"] = sha256_json(result)
    return result


def persist_p49_external_runtime_evidence_handoff(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p49_external_runtime_evidence_handoff")
    report = build_p49_external_runtime_evidence_handoff_report(cfg=cfg)
    negative = build_p49_negative_fixture_results(cfg=cfg)
    bundle_template = report["redacted_submit_response_bundle_template"]
    transcript_schema = report["external_runtime_execution_transcript_schema"]
    log_scan_template = report["no_secret_log_scan_template"]
    p7_bridge_template = report["p7_intake_bridge_template"]
    registry_record = append_registry_record(
        registry_path(cfg, P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_REGISTRY_NAME),
        {
            "artifact_type": "p49_external_runtime_evidence_handoff_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "p49_external_runtime_evidence_handoff_id": report["p49_external_runtime_evidence_handoff_id"],
            "p49_external_runtime_evidence_handoff_sha256": report["p49_external_runtime_evidence_handoff_sha256"],
            "source_p48_connector_sha256": report["source_p48_connector_validation"].get("source_sha256"),
            "actual_order_submission_performed": report["actual_order_submission_performed"],
            "order_endpoint_called": report["order_endpoint_called"],
            "http_request_sent": report["http_request_sent"],
            "signature_created": report["signature_created"],
            "secret_value_accessed": report["secret_value_accessed"],
            "live_canary_execution_enabled": report["live_canary_execution_enabled"],
        },
        registry_name=P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_REGISTRY_NAME,
        id_field="p49_external_runtime_evidence_handoff_registry_record_id",
        hash_field="p49_external_runtime_evidence_handoff_registry_record_sha256",
        id_prefix="p49_external_runtime_evidence_handoff_registry_record",
    )
    report["p49_external_runtime_evidence_handoff_registry_record_id"] = registry_record["p49_external_runtime_evidence_handoff_registry_record_id"]
    report["p49_external_runtime_evidence_handoff_registry_record_sha256"] = registry_record["p49_external_runtime_evidence_handoff_registry_record_sha256"]
    report["p49_external_runtime_evidence_handoff_sha256"] = sha256_json(report)
    summary = {
        "artifact_type": "p49_external_runtime_evidence_handoff_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": report["review_only"],
        "handoff_skeleton_only": report["handoff_skeleton_only"],
        "external_runtime_only": report["external_runtime_only"],
        "actual_order_submission_performed": report["actual_order_submission_performed"],
        "order_endpoint_called": report["order_endpoint_called"],
        "http_request_sent": report["http_request_sent"],
        "signature_created": report["signature_created"],
        "secret_value_accessed": report["secret_value_accessed"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "p49_external_runtime_evidence_handoff_id": report["p49_external_runtime_evidence_handoff_id"],
        "p49_external_runtime_evidence_handoff_sha256": report["p49_external_runtime_evidence_handoff_sha256"],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p49_summary_sha256"] = sha256_json(summary)
    writes = {
        "p49_external_runtime_evidence_handoff_report.json": report,
        "p49_redacted_submit_response_bundle_TEMPLATE_NO_SUBMIT.json": bundle_template,
        "p49_external_runtime_execution_transcript_SCHEMA_NO_SUBMIT.json": transcript_schema,
        "p49_no_secret_log_scan_TEMPLATE.json": log_scan_template,
        "p49_p7_intake_bridge_TEMPLATE_NO_SUBMIT.json": p7_bridge_template,
        "p49_external_runtime_evidence_handoff_negative_fixture_results.json": negative,
        "p49_external_runtime_evidence_handoff_registry_record.json": registry_record,
        "p49_external_runtime_evidence_handoff_summary.json": summary,
    }
    for filename, payload in writes.items():
        atomic_write_json(latest / filename, payload)
        atomic_write_json(storage / filename, payload)
    return report


__all__ = [
    "P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_VERSION",
    "STATUS_READY_REVIEW_ONLY_NO_SUBMIT",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "RedactedSubmitResponseBundleTemplate",
    "ExternalRuntimeExecutionTranscriptSchema",
    "NoSecretLogScanTemplate",
    "P7IntakeBridgeTemplate",
    "scan_log_text_for_secret_leaks",
    "validate_redacted_submit_response_bundle_template",
    "validate_execution_transcript_schema",
    "validate_no_secret_log_scan_template",
    "validate_p7_intake_bridge_template",
    "validate_p48_connector_source",
    "build_p49_external_runtime_evidence_handoff_report",
    "build_p49_negative_fixture_results",
    "persist_p49_external_runtime_evidence_handoff",
]
