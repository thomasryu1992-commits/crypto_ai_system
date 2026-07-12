from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.runtime_disabled_flags import default_execution_flag_state, truthy_execution_flags
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_VERSION = "p50_external_evidence_import_validator_v1"
P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_REGISTRY_NAME = "p50_external_evidence_import_validator_registry"
STATUS_READY_REVIEW_ONLY_NO_SUBMIT = "P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_READY_REVIEW_ONLY_NO_SUBMIT"
STATUS_BLOCKED_FAIL_CLOSED = "P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_BLOCKED_FAIL_CLOSED"

_ALLOWED_ENVIRONMENTS = {"testnet"}
_ALLOWED_VENUES = {"extended_starknet_sepolia"}
_ALLOWED_SYMBOLS = {"BTC-USD"}
_ALLOWED_IMPORT_ROOT_PREFIXES = (
    "EXTERNAL_RUNTIME_OUTPUT/",
    "operator_supplied_external_runtime_evidence/",
)
_SHA_PLACEHOLDER = "0" * 64
_REQUIRED_BUNDLE_FIELDS = (
    "evidence_origin",
    "environment",
    "venue",
    "symbol",
    "exchange_order_id",
    "client_order_id",
    "idempotency_key",
    "request_hash",
    "exchange_response_hash",
    "raw_exchange_response_redacted_path",
    "raw_exchange_response_redacted_sha256",
    "hot_path_preorder_risk_gate_id",
    "hot_path_preorder_risk_gate_hash",
    "secret_reference_id",
    "key_fingerprint_sha256",
    "no_secret_logged_evidence_hash",
    "status_polling_evidence_hash",
    "cancel_boundary_evidence_hash",
    "reconciliation_evidence_hash",
    "session_close_evidence_hash",
)
_REQUIRED_SHA256_FIELDS = (
    "request_hash",
    "exchange_response_hash",
    "raw_exchange_response_redacted_sha256",
    "hot_path_preorder_risk_gate_hash",
    "key_fingerprint_sha256",
    "no_secret_logged_evidence_hash",
    "status_polling_evidence_hash",
    "cancel_boundary_evidence_hash",
    "reconciliation_evidence_hash",
    "session_close_evidence_hash",
)
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
    "unredacted_api_key",
    "unredacted_api_secret",
}
_FORBIDDEN_PAYLOAD_KEYS = _FORBIDDEN_SECRET_FIELD_NAMES | {
    "raw_signed_payload",
    "raw_request_body",
    "raw_exchange_payload",
    "unredacted_exchange_response",
    "signature",
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
_MOCK_ORDER_TOKENS = (
    "mock",
    "fixture",
    "synthetic",
    "sample",
    "dummy",
    "fake",
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
            "secret_file_accessed": False,
            "secret_file_created": False,
            "runtime_scheduler_enabled": False,
            "runtime_loop_started": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
            "runtime_authority_granted": False,
        }
    )
    return payload


@dataclass(frozen=True)
class ExternalEvidenceImportManifestTemplate:
    import_manifest_template_id: str = "p50_external_evidence_import_manifest_TEMPLATE_NO_SUBMIT"
    import_validator_version: str = P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_VERSION
    generated_by_review_package: bool = True
    review_only: bool = True
    import_validator_skeleton_only: bool = True
    external_runtime_only: bool = True
    can_grant_runtime_authority: bool = False
    p7_target: str = "crypto_ai_system.execution.post_submit_evidence_intake"
    p7_report_filename: str = "p7_post_submit_evidence_intake_report.json"
    environment: str = "testnet"
    venue: str = "extended_starknet_sepolia"
    symbol: str = "BTC-USD"
    max_order_count: int = 1
    allowed_import_root_prefixes: tuple[str, ...] = _ALLOWED_IMPORT_ROOT_PREFIXES
    imported_paths_must_be_relative: bool = True
    imported_paths_must_stay_under_allowed_roots: bool = True
    path_traversal_allowed: bool = False
    raw_secret_values_allowed: bool = False
    raw_request_body_allowed: bool = False
    raw_signed_payload_allowed: bool = False
    raw_exchange_payload_allowed: bool = False
    unredacted_exchange_response_allowed: bool = False
    no_secret_log_scan_required: bool = True
    no_secret_log_scan_must_pass: bool = True
    schema_hash_validation_required: bool = True
    bundle_hash_validation_required: bool = True
    p49_handoff_report_required: bool = True
    no_order_submission_performed_by_importer: bool = True
    order_endpoint_call_performed_by_importer: bool = False
    http_request_sent_by_importer: bool = False
    signature_created_by_importer: bool = False
    secret_value_accessed_by_importer: bool = False
    required_bundle_fields: tuple[str, ...] = _REQUIRED_BUNDLE_FIELDS
    required_sha256_fields: tuple[str, ...] = _REQUIRED_SHA256_FIELDS
    required_import_files: tuple[str, ...] = (
        "redacted_submit_response_bundle.json",
        "external_runtime_execution_transcript.json",
        "no_secret_log_scan_report.json",
        "status_polling_evidence.json",
        "cancel_boundary_evidence.json",
        "signed_testnet_reconciliation_evidence.json",
        "signed_testnet_session_close_evidence.json",
    )
    optional_operator_supplied_hash_manifest: str = "operator_supplied_external_runtime_evidence/import_hash_manifest.json"
    p50_output_must_remain_review_only: bool = True
    p50_may_build_p7_input_preview: bool = True
    p50_must_not_write_p7_valid_status: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["external_evidence_import_manifest_template_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P7ImportPreviewTemplate:
    import_preview_template_id: str = "p50_p7_import_preview_TEMPLATE_NO_SUBMIT"
    import_preview_version: str = P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_VERSION
    generated_by_review_package: bool = True
    review_only: bool = True
    can_grant_runtime_authority: bool = False
    p7_input_preview_only: bool = True
    p7_intake_execution_performed: bool = False
    p7_status_mutation_performed: bool = False
    p7_valid_status_written_by_p50: bool = False
    no_order_submission_performed_by_preview: bool = True
    no_endpoint_call_performed_by_preview: bool = True
    no_signature_created_by_preview: bool = True
    no_secret_accessed_by_preview: bool = True
    required_preview_fields: tuple[str, ...] = (
        "source_p6_submit_runtime_action_sha256",
        "exchange_order_id",
        "client_order_id",
        "idempotency_key",
        "request_hash",
        "exchange_response_hash",
        "raw_exchange_response_redacted_path",
        "hot_path_preorder_risk_gate_id",
        "hot_path_preorder_risk_gate_hash",
        "secret_reference_id",
        "key_fingerprint_sha256",
        "no_secret_logged_evidence_hash",
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p7_import_preview_template_sha256"] = sha256_json(payload)
        return payload


def validate_p49_handoff_source(p49_report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(p49_report or {})
    blockers: list[str] = []
    if payload.get("artifact_type") != "p49_external_runtime_evidence_handoff_report":
        blockers.append("P50_P49_HANDOFF_ARTIFACT_TYPE_INVALID")
    if payload.get("status") != "P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_READY_REVIEW_ONLY_NO_SUBMIT":
        blockers.append("P50_P49_HANDOFF_STATUS_NOT_READY_NO_SUBMIT")
    for key in (
        "review_only",
        "handoff_skeleton_only",
        "external_runtime_only",
        "review_package_default_no_submit",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P50_P49_HANDOFF_{key.upper()}_NOT_TRUE")
    if payload.get("runtime_authority_source") is not False:
        blockers.append("P50_P49_HANDOFF_RUNTIME_AUTHORITY_SOURCE_NOT_FALSE")
    for key in (
        "actual_order_submission_performed",
        "order_endpoint_called",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "secret_value_accessed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P50_P49_HANDOFF_{key.upper()}_NOT_FALSE")
    validation = {
        "p49_handoff_source_valid": not blockers,
        "p49_handoff_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "source_status": payload.get("status"),
        "source_sha256": payload.get("p49_external_runtime_evidence_handoff_sha256"),
    }
    validation["p49_handoff_source_validation_sha256"] = sha256_json(validation)
    return validation


def validate_import_manifest_template(template: Mapping[str, Any] | ExternalEvidenceImportManifestTemplate | None) -> dict[str, Any]:
    payload = template.to_dict() if isinstance(template, ExternalEvidenceImportManifestTemplate) else dict(template or {})
    blockers: list[str] = []
    if payload.get("import_validator_version") != P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_VERSION:
        blockers.append("P50_IMPORT_MANIFEST_VERSION_MISMATCH")
    for key in (
        "generated_by_review_package",
        "review_only",
        "import_validator_skeleton_only",
        "external_runtime_only",
        "imported_paths_must_be_relative",
        "imported_paths_must_stay_under_allowed_roots",
        "no_secret_log_scan_required",
        "no_secret_log_scan_must_pass",
        "schema_hash_validation_required",
        "bundle_hash_validation_required",
        "p49_handoff_report_required",
        "no_order_submission_performed_by_importer",
        "p50_output_must_remain_review_only",
        "p50_may_build_p7_input_preview",
        "p50_must_not_write_p7_valid_status",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P50_IMPORT_MANIFEST_{key.upper()}_NOT_TRUE")
    for key in (
        "can_grant_runtime_authority",
        "path_traversal_allowed",
        "raw_secret_values_allowed",
        "raw_request_body_allowed",
        "raw_signed_payload_allowed",
        "raw_exchange_payload_allowed",
        "unredacted_exchange_response_allowed",
        "order_endpoint_call_performed_by_importer",
        "http_request_sent_by_importer",
        "signature_created_by_importer",
        "secret_value_accessed_by_importer",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P50_IMPORT_MANIFEST_{key.upper()}_NOT_FALSE")
    if payload.get("environment") not in _ALLOWED_ENVIRONMENTS:
        blockers.append("P50_IMPORT_MANIFEST_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") not in _ALLOWED_VENUES:
        blockers.append("P50_IMPORT_MANIFEST_VENUE_NOT_TESTNET_SCOPED")
    if payload.get("symbol") not in _ALLOWED_SYMBOLS:
        blockers.append("P50_IMPORT_MANIFEST_SYMBOL_NOT_BTC_USD")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("P50_IMPORT_MANIFEST_MAX_ORDER_COUNT_NOT_ONE")
    if tuple(payload.get("allowed_import_root_prefixes") or ()) != _ALLOWED_IMPORT_ROOT_PREFIXES:
        blockers.append("P50_IMPORT_MANIFEST_ALLOWED_ROOTS_CHANGED")
    if set(payload.get("required_bundle_fields") or ()) < set(_REQUIRED_BUNDLE_FIELDS):
        blockers.append("P50_IMPORT_MANIFEST_REQUIRED_BUNDLE_FIELDS_INCOMPLETE")
    if set(payload.get("required_sha256_fields") or ()) < set(_REQUIRED_SHA256_FIELDS):
        blockers.append("P50_IMPORT_MANIFEST_REQUIRED_SHA256_FIELDS_INCOMPLETE")
    validation = {
        "import_manifest_template_valid": not blockers,
        "import_manifest_template_block_reasons": sorted(dict.fromkeys(blockers)),
        "import_manifest_template_id": payload.get("import_manifest_template_id"),
        "required_bundle_field_count": len(tuple(payload.get("required_bundle_fields") or ())),
        "required_sha256_field_count": len(tuple(payload.get("required_sha256_fields") or ())),
    }
    validation["import_manifest_template_validation_sha256"] = sha256_json(validation)
    return validation


def _path_is_allowed(path_value: Any, *, allowed_prefixes: Sequence[str] = _ALLOWED_IMPORT_ROOT_PREFIXES) -> tuple[bool, list[str]]:
    text = str(path_value or "").strip().replace("\\", "/")
    reasons: list[str] = []
    if not text:
        reasons.append("P50_IMPORT_PATH_EMPTY")
        return False, reasons
    pure = PurePosixPath(text)
    if pure.is_absolute() or text.startswith("/"):
        reasons.append("P50_IMPORT_PATH_ABSOLUTE_NOT_ALLOWED")
    if any(part == ".." for part in pure.parts):
        reasons.append("P50_IMPORT_PATH_TRAVERSAL_NOT_ALLOWED")
    if "~" in pure.parts:
        reasons.append("P50_IMPORT_PATH_HOME_EXPANSION_NOT_ALLOWED")
    if not any(text.startswith(prefix) for prefix in allowed_prefixes):
        reasons.append("P50_IMPORT_PATH_NOT_UNDER_ALLOWED_ROOT")
    lowered = text.lower()
    secret_path_tokens = ("private_key", "passphrase", "api_key", "api_secret", "secret_dump", "raw_secret", "unredacted_secret")
    if any(token in lowered for token in secret_path_tokens):
        reasons.append("P50_IMPORT_PATH_SECRET_NAMING_NOT_ALLOWED")
    return not reasons, reasons


def validate_import_paths(paths: Mapping[str, Any] | None, *, allowed_prefixes: Sequence[str] = _ALLOWED_IMPORT_ROOT_PREFIXES) -> dict[str, Any]:
    payload = dict(paths or {})
    blockers: list[str] = []
    path_results: dict[str, Any] = {}
    required_path_keys = (
        "redacted_submit_response_bundle_path",
        "external_runtime_execution_transcript_path",
        "no_secret_log_scan_report_path",
        "status_polling_evidence_path",
        "cancel_boundary_evidence_path",
        "reconciliation_evidence_path",
        "session_close_evidence_path",
    )
    for key in required_path_keys:
        ok, reasons = _path_is_allowed(payload.get(key), allowed_prefixes=allowed_prefixes)
        path_results[key] = {"path": payload.get(key), "valid": ok, "block_reasons": reasons}
        blockers.extend([f"{key}:{reason}" for reason in reasons])
    validation = {
        "import_paths_valid": not blockers,
        "import_paths_block_reasons": sorted(dict.fromkeys(blockers)),
        "path_results": path_results,
    }
    validation["import_paths_validation_sha256"] = sha256_json(validation)
    return validation


def _contains_forbidden_key(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for key, value in payload.items():
        key_l = str(key).strip().lower()
        value_l = str(value or "").strip().lower()
        if key_l in _FORBIDDEN_PAYLOAD_KEYS and _nonempty(value):
            blockers.append(f"P50_FORBIDDEN_IMPORT_PAYLOAD_KEY_PRESENT:{key}")
        if any(token in value_l for token in _FORBIDDEN_SCOPE_TOKENS):
            blockers.append(f"P50_FORBIDDEN_SCOPE_TOKEN_PRESENT:{key}")
    return blockers


def validate_redacted_submit_response_bundle_for_import(bundle: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(bundle or {})
    blockers: list[str] = []
    for key in _REQUIRED_BUNDLE_FIELDS:
        if not _nonempty(payload.get(key)):
            blockers.append(f"P50_BUNDLE_REQUIRED_FIELD_MISSING:{key}")
    if payload.get("evidence_origin") != "real_signed_testnet_external_runtime":
        blockers.append("P50_BUNDLE_EVIDENCE_ORIGIN_INVALID")
    if payload.get("environment") not in _ALLOWED_ENVIRONMENTS:
        blockers.append("P50_BUNDLE_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") not in _ALLOWED_VENUES:
        blockers.append("P50_BUNDLE_VENUE_NOT_TESTNET_SCOPED")
    if payload.get("symbol") not in _ALLOWED_SYMBOLS:
        blockers.append("P50_BUNDLE_SYMBOL_NOT_BTC_USD")
    if int(payload.get("order_count") or 1) != 1:
        blockers.append("P50_BUNDLE_ORDER_COUNT_NOT_ONE")
    exchange_order_id = str(payload.get("exchange_order_id") or "").strip().lower()
    if exchange_order_id and any(token in exchange_order_id for token in _MOCK_ORDER_TOKENS):
        blockers.append("P50_BUNDLE_EXCHANGE_ORDER_ID_LOOKS_MOCK_OR_FIXTURE")
    for key in _REQUIRED_SHA256_FIELDS:
        if not _is_sha256_hex(payload.get(key)):
            blockers.append(f"P50_BUNDLE_{key.upper()}_NOT_SHA256_HEX")
    for key in (
        "raw_exchange_payload_included",
        "raw_request_body_included",
        "raw_signed_payload_included",
        "secret_value_included",
        "unredacted_exchange_response_included",
        "runtime_authority_granted_by_bundle",
        "p7_valid_status_granted_by_bundle",
        "live_canary_allowed_by_bundle",
        "live_scaled_allowed_by_bundle",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P50_BUNDLE_{key.upper()}_NOT_FALSE")
    ok_path, path_reasons = _path_is_allowed(payload.get("raw_exchange_response_redacted_path"))
    if not ok_path:
        blockers.extend([f"raw_exchange_response_redacted_path:{reason}" for reason in path_reasons])
    blockers.extend(_contains_forbidden_key(payload))
    validation = {
        "redacted_submit_response_bundle_import_valid": not blockers,
        "redacted_submit_response_bundle_import_block_reasons": sorted(dict.fromkeys(blockers)),
        "exchange_order_id_present": _nonempty(payload.get("exchange_order_id")),
        "request_hash": payload.get("request_hash"),
        "exchange_response_hash": payload.get("exchange_response_hash"),
    }
    validation["redacted_submit_response_bundle_import_validation_sha256"] = sha256_json(validation)
    return validation


def validate_no_secret_log_scan_report(report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(report or {})
    blockers: list[str] = []
    if payload.get("scan_scope") not in {"external_runtime_redacted_logs", "redacted_external_runtime_logs"}:
        blockers.append("P50_LOG_SCAN_SCOPE_INVALID")
    for key in (
        "forbidden_pattern_match_count",
        "raw_secret_value_match_count",
        "secret_field_match_count",
    ):
        if int(payload.get(key) or 0) != 0:
            blockers.append(f"P50_LOG_SCAN_{key.upper()}_NONZERO")
    for key in (
        "api_key_value_logged",
        "api_secret_value_logged",
        "private_key_logged",
        "passphrase_logged",
        "secret_value_logged",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P50_LOG_SCAN_{key.upper()}_NOT_FALSE")
    if not _is_sha256_hex(payload.get("no_secret_logged_evidence_hash")):
        blockers.append("P50_LOG_SCAN_NO_SECRET_LOGGED_EVIDENCE_HASH_NOT_SHA256_HEX")
    if payload.get("can_grant_runtime_authority") is not False:
        blockers.append("P50_LOG_SCAN_CAN_GRANT_RUNTIME_AUTHORITY_NOT_FALSE")
    blockers.extend(_contains_forbidden_key(payload))
    validation = {
        "no_secret_log_scan_report_valid": not blockers,
        "no_secret_log_scan_report_block_reasons": sorted(dict.fromkeys(blockers)),
        "scanned_file_count": int(payload.get("scanned_file_count") or 0),
        "no_secret_logged_evidence_hash": payload.get("no_secret_logged_evidence_hash"),
    }
    validation["no_secret_log_scan_report_validation_sha256"] = sha256_json(validation)
    return validation


def validate_execution_transcript_for_import(transcript: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(transcript or {})
    blockers: list[str] = []
    if payload.get("evidence_origin") != "real_signed_testnet_external_runtime":
        blockers.append("P50_TRANSCRIPT_EVIDENCE_ORIGIN_INVALID")
    if payload.get("environment") not in _ALLOWED_ENVIRONMENTS:
        blockers.append("P50_TRANSCRIPT_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") not in _ALLOWED_VENUES:
        blockers.append("P50_TRANSCRIPT_VENUE_NOT_TESTNET_SCOPED")
    if payload.get("symbol") not in _ALLOWED_SYMBOLS:
        blockers.append("P50_TRANSCRIPT_SYMBOL_NOT_BTC_USD")
    for key in (
        "operator_arming_reference",
        "p6_external_runtime_preflight_report_hash",
        "p48_connector_request_hash",
        "hot_path_preorder_risk_gate_hash",
        "idempotency_key",
        "redacted_submit_response_hash",
        "status_polling_hash_chain",
        "reconciliation_summary_hash",
        "session_close_summary_hash",
        "no_secret_log_scan_report_hash",
    ):
        if not _nonempty(payload.get(key)):
            blockers.append(f"P50_TRANSCRIPT_REQUIRED_FIELD_MISSING:{key}")
    for key in (
        "p6_external_runtime_preflight_report_hash",
        "p48_connector_request_hash",
        "hot_path_preorder_risk_gate_hash",
        "redacted_submit_response_hash",
        "reconciliation_summary_hash",
        "session_close_summary_hash",
        "no_secret_log_scan_report_hash",
    ):
        if _nonempty(payload.get(key)) and not _is_sha256_hex(payload.get(key)):
            blockers.append(f"P50_TRANSCRIPT_{key.upper()}_NOT_SHA256_HEX")
    for key in (
        "raw_secret_values_included",
        "raw_signed_payload_included",
        "raw_request_body_included",
        "raw_exchange_payload_included",
        "unredacted_exchange_response_included",
        "review_package_endpoint_call_performed",
        "review_package_signature_created",
        "review_package_secret_accessed",
        "can_grant_runtime_authority",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P50_TRANSCRIPT_{key.upper()}_NOT_FALSE")
    blockers.extend(_contains_forbidden_key(payload))
    validation = {
        "execution_transcript_import_valid": not blockers,
        "execution_transcript_import_block_reasons": sorted(dict.fromkeys(blockers)),
        "evidence_origin": payload.get("evidence_origin"),
        "symbol": payload.get("symbol"),
    }
    validation["execution_transcript_import_validation_sha256"] = sha256_json(validation)
    return validation


def validate_p7_import_preview_template(template: Mapping[str, Any] | P7ImportPreviewTemplate | None) -> dict[str, Any]:
    payload = template.to_dict() if isinstance(template, P7ImportPreviewTemplate) else dict(template or {})
    blockers: list[str] = []
    if payload.get("import_preview_version") != P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_VERSION:
        blockers.append("P50_P7_PREVIEW_VERSION_MISMATCH")
    for key in (
        "generated_by_review_package",
        "review_only",
        "p7_input_preview_only",
        "no_order_submission_performed_by_preview",
        "no_endpoint_call_performed_by_preview",
        "no_signature_created_by_preview",
        "no_secret_accessed_by_preview",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P50_P7_PREVIEW_{key.upper()}_NOT_TRUE")
    for key in (
        "can_grant_runtime_authority",
        "p7_intake_execution_performed",
        "p7_status_mutation_performed",
        "p7_valid_status_written_by_p50",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P50_P7_PREVIEW_{key.upper()}_NOT_FALSE")
    if set(payload.get("required_preview_fields") or ()) < {
        "exchange_order_id",
        "request_hash",
        "exchange_response_hash",
        "secret_reference_id",
        "no_secret_logged_evidence_hash",
    }:
        blockers.append("P50_P7_PREVIEW_REQUIRED_FIELDS_INCOMPLETE")
    validation = {
        "p7_import_preview_template_valid": not blockers,
        "p7_import_preview_template_block_reasons": sorted(dict.fromkeys(blockers)),
        "import_preview_template_id": payload.get("import_preview_template_id"),
    }
    validation["p7_import_preview_template_validation_sha256"] = sha256_json(validation)
    return validation


def build_p7_input_preview_from_bundle(bundle: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(bundle or {})
    preview = {
        "artifact_type": "p50_p7_input_preview_NO_SUBMIT",
        "review_only": True,
        "p7_input_preview_only": True,
        "p7_intake_execution_performed": False,
        "p7_valid_status_written_by_p50": False,
        "source_p6_submit_runtime_action_sha256": payload.get("source_p6_submit_runtime_action_sha256") or payload.get("p6_single_signed_testnet_submit_runtime_action_sha256") or _SHA_PLACEHOLDER,
        "exchange_order_id": payload.get("exchange_order_id"),
        "client_order_id": payload.get("client_order_id"),
        "idempotency_key": payload.get("idempotency_key"),
        "request_hash": payload.get("request_hash"),
        "exchange_response_hash": payload.get("exchange_response_hash"),
        "raw_exchange_response_redacted_path": payload.get("raw_exchange_response_redacted_path"),
        "hot_path_preorder_risk_gate_id": payload.get("hot_path_preorder_risk_gate_id"),
        "hot_path_preorder_risk_gate_hash": payload.get("hot_path_preorder_risk_gate_hash"),
        "secret_reference_id": payload.get("secret_reference_id"),
        "key_fingerprint_sha256": payload.get("key_fingerprint_sha256"),
        "no_secret_logged_evidence_hash": payload.get("no_secret_logged_evidence_hash"),
        "order_endpoint_called_by_p50": False,
        "http_request_sent_by_p50": False,
        "signature_created_by_p50": False,
        "secret_value_accessed_by_p50": False,
        "created_at_utc": utc_now_canonical(),
    }
    preview["p50_p7_input_preview_sha256"] = sha256_json(preview)
    return preview


def build_p50_external_evidence_import_validator_report(
    *,
    cfg: AppConfig | None = None,
    import_manifest_template: Mapping[str, Any] | ExternalEvidenceImportManifestTemplate | None = None,
    p7_preview_template: Mapping[str, Any] | P7ImportPreviewTemplate | None = None,
    candidate_bundle: Mapping[str, Any] | None = None,
    candidate_transcript: Mapping[str, Any] | None = None,
    candidate_log_scan_report: Mapping[str, Any] | None = None,
    candidate_import_paths: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p49_report = _read_latest_json(cfg, "p49_external_runtime_evidence_handoff_report.json")
    manifest_payload = import_manifest_template.to_dict() if isinstance(import_manifest_template, ExternalEvidenceImportManifestTemplate) else dict(import_manifest_template or ExternalEvidenceImportManifestTemplate().to_dict())
    preview_template_payload = p7_preview_template.to_dict() if isinstance(p7_preview_template, P7ImportPreviewTemplate) else dict(p7_preview_template or P7ImportPreviewTemplate().to_dict())

    p49_validation = validate_p49_handoff_source(p49_report)
    manifest_validation = validate_import_manifest_template(manifest_payload)
    preview_template_validation = validate_p7_import_preview_template(preview_template_payload)
    import_path_validation = validate_import_paths(
        candidate_import_paths
        or {
            "redacted_submit_response_bundle_path": "EXTERNAL_RUNTIME_OUTPUT/redacted_submit_response_bundle.json",
            "external_runtime_execution_transcript_path": "EXTERNAL_RUNTIME_OUTPUT/external_runtime_execution_transcript.json",
            "no_secret_log_scan_report_path": "EXTERNAL_RUNTIME_OUTPUT/no_secret_log_scan_report.json",
            "status_polling_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/status_polling_evidence.json",
            "cancel_boundary_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/cancel_boundary_evidence.json",
            "reconciliation_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_reconciliation_evidence.json",
            "session_close_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_session_close_evidence.json",
        }
    )
    bundle_validation = None
    transcript_validation = None
    log_scan_validation = None
    p7_input_preview = None
    candidate_present = any(item is not None for item in (candidate_bundle, candidate_transcript, candidate_log_scan_report, candidate_import_paths))
    if candidate_bundle is not None:
        bundle_validation = validate_redacted_submit_response_bundle_for_import(candidate_bundle)
        p7_input_preview = build_p7_input_preview_from_bundle(candidate_bundle)
    if candidate_transcript is not None:
        transcript_validation = validate_execution_transcript_for_import(candidate_transcript)
    if candidate_log_scan_report is not None:
        log_scan_validation = validate_no_secret_log_scan_report(candidate_log_scan_report)

    blockers = sorted(
        dict.fromkeys(
            list(p49_validation["p49_handoff_source_block_reasons"])
            + list(manifest_validation["import_manifest_template_block_reasons"])
            + list(preview_template_validation["p7_import_preview_template_block_reasons"])
            + list(import_path_validation["import_paths_block_reasons"])
            + (list(bundle_validation["redacted_submit_response_bundle_import_block_reasons"]) if bundle_validation else [])
            + (list(transcript_validation["execution_transcript_import_block_reasons"]) if transcript_validation else [])
            + (list(log_scan_validation["no_secret_log_scan_report_block_reasons"]) if log_scan_validation else [])
        )
    )
    status = STATUS_READY_REVIEW_ONLY_NO_SUBMIT if not blockers else STATUS_BLOCKED_FAIL_CLOSED
    report = {
        "artifact_type": "p50_external_evidence_import_validator_report",
        "p50_external_evidence_import_validator_version": P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_VERSION,
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "review_only": True,
        "runtime_authority_source": False,
        "import_validator_skeleton_only": candidate_present is False,
        "candidate_import_payload_supplied": candidate_present,
        "external_runtime_only": True,
        "review_package_default_no_submit": True,
        "p7_input_preview_only": True,
        "p7_intake_execution_performed": False,
        "p7_valid_status_written_by_p50": False,
        "actual_endpoint_call_still_requires_separate_operator_local_runtime": True,
        "source_p49_handoff_validation": p49_validation,
        "external_evidence_import_manifest_template": manifest_payload,
        "external_evidence_import_manifest_template_validation": manifest_validation,
        "p7_import_preview_template": preview_template_payload,
        "p7_import_preview_template_validation": preview_template_validation,
        "candidate_import_paths_validation": import_path_validation,
        "candidate_bundle_validation": bundle_validation,
        "candidate_transcript_validation": transcript_validation,
        "candidate_no_secret_log_scan_validation": log_scan_validation,
        "p7_input_preview": p7_input_preview,
        "next_required_chain": [
            "operator completes one separately approved signed-testnet external-runtime submit",
            "operator exports redacted submit response bundle and transcript",
            "P50 import validator verifies schema/hash/no-secret/import-path boundaries",
            "P7 intake consumes only P50-validated redacted evidence",
            "P8 accumulates repeated clean real signed-testnet sessions",
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
        report["block_reasons"] = sorted(dict.fromkeys(blockers + ["P50_UNSAFE_TRUTHY_EXECUTION_FLAGS"]))
    report["p50_external_evidence_import_validator_id"] = stable_id("p50_external_evidence_import_validator", report, 24)
    report["p50_external_evidence_import_validator_sha256"] = sha256_json(report)
    return report


def build_p50_negative_fixture_results(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    good_sha = "a" * 64
    base_bundle = {
        "evidence_origin": "real_signed_testnet_external_runtime",
        "environment": "testnet",
        "venue": "extended_starknet_sepolia",
        "symbol": "BTC-USD",
        "order_count": 1,
        "exchange_order_id": "testnet_order_12345",
        "client_order_id": "client_order_12345",
        "idempotency_key": "idem_12345",
        "request_hash": good_sha,
        "exchange_response_hash": good_sha,
        "raw_exchange_response_redacted_path": "EXTERNAL_RUNTIME_OUTPUT/redacted_submit_response.json",
        "raw_exchange_response_redacted_sha256": good_sha,
        "hot_path_preorder_risk_gate_id": "risk_gate_12345",
        "hot_path_preorder_risk_gate_hash": good_sha,
        "secret_reference_id": "secret_ref_metadata_only",
        "key_fingerprint_sha256": good_sha,
        "no_secret_logged_evidence_hash": good_sha,
        "status_polling_evidence_hash": good_sha,
        "cancel_boundary_evidence_hash": good_sha,
        "reconciliation_evidence_hash": good_sha,
        "session_close_evidence_hash": good_sha,
        "raw_exchange_payload_included": False,
        "raw_request_body_included": False,
        "raw_signed_payload_included": False,
        "secret_value_included": False,
        "unredacted_exchange_response_included": False,
        "runtime_authority_granted_by_bundle": False,
        "p7_valid_status_granted_by_bundle": False,
        "live_canary_allowed_by_bundle": False,
        "live_scaled_allowed_by_bundle": False,
    }
    base_transcript = {
        "evidence_origin": "real_signed_testnet_external_runtime",
        "environment": "testnet",
        "venue": "extended_starknet_sepolia",
        "symbol": "BTC-USD",
        "operator_arming_reference": "operator_arming_ref_12345",
        "p6_external_runtime_preflight_report_hash": good_sha,
        "p48_connector_request_hash": good_sha,
        "hot_path_preorder_risk_gate_hash": good_sha,
        "idempotency_key": "idem_12345",
        "redacted_submit_response_hash": good_sha,
        "status_polling_hash_chain": [good_sha],
        "reconciliation_summary_hash": good_sha,
        "session_close_summary_hash": good_sha,
        "no_secret_log_scan_report_hash": good_sha,
        "raw_secret_values_included": False,
        "raw_signed_payload_included": False,
        "raw_request_body_included": False,
        "raw_exchange_payload_included": False,
        "unredacted_exchange_response_included": False,
        "review_package_endpoint_call_performed": False,
        "review_package_signature_created": False,
        "review_package_secret_accessed": False,
        "can_grant_runtime_authority": False,
    }
    base_log_scan = {
        "scan_scope": "external_runtime_redacted_logs",
        "scanned_file_count": 1,
        "forbidden_pattern_match_count": 0,
        "raw_secret_value_match_count": 0,
        "secret_field_match_count": 0,
        "api_key_value_logged": False,
        "api_secret_value_logged": False,
        "private_key_logged": False,
        "passphrase_logged": False,
        "secret_value_logged": False,
        "no_secret_logged_evidence_hash": good_sha,
        "can_grant_runtime_authority": False,
    }
    fixture_results = {
        "mainnet_bundle": {
            "blocked_fail_closed": validate_redacted_submit_response_bundle_for_import({**base_bundle, "environment": "mainnet", "venue": "binance_mainnet"})["redacted_submit_response_bundle_import_valid"] is False,
            "block_reasons": validate_redacted_submit_response_bundle_for_import({**base_bundle, "environment": "mainnet", "venue": "binance_mainnet"})["redacted_submit_response_bundle_import_block_reasons"],
        },
        "bundle_secret_field_present": {
            "blocked_fail_closed": validate_redacted_submit_response_bundle_for_import({**base_bundle, "api_secret": "redacted-but-field-forbidden"})["redacted_submit_response_bundle_import_valid"] is False,
            "block_reasons": validate_redacted_submit_response_bundle_for_import({**base_bundle, "api_secret": "redacted-but-field-forbidden"})["redacted_submit_response_bundle_import_block_reasons"],
        },
        "bundle_hash_missing": {
            "blocked_fail_closed": validate_redacted_submit_response_bundle_for_import({**base_bundle, "request_hash": ""})["redacted_submit_response_bundle_import_valid"] is False,
            "block_reasons": validate_redacted_submit_response_bundle_for_import({**base_bundle, "request_hash": ""})["redacted_submit_response_bundle_import_block_reasons"],
        },
        "absolute_import_path": {
            "blocked_fail_closed": validate_import_paths({
                "redacted_submit_response_bundle_path": "/tmp/redacted_submit_response_bundle.json",
                "external_runtime_execution_transcript_path": "EXTERNAL_RUNTIME_OUTPUT/external_runtime_execution_transcript.json",
                "no_secret_log_scan_report_path": "EXTERNAL_RUNTIME_OUTPUT/no_secret_log_scan_report.json",
                "status_polling_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/status_polling_evidence.json",
                "cancel_boundary_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/cancel_boundary_evidence.json",
                "reconciliation_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_reconciliation_evidence.json",
                "session_close_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_session_close_evidence.json",
            })["import_paths_valid"] is False,
            "block_reasons": validate_import_paths({
                "redacted_submit_response_bundle_path": "/tmp/redacted_submit_response_bundle.json",
                "external_runtime_execution_transcript_path": "EXTERNAL_RUNTIME_OUTPUT/external_runtime_execution_transcript.json",
                "no_secret_log_scan_report_path": "EXTERNAL_RUNTIME_OUTPUT/no_secret_log_scan_report.json",
                "status_polling_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/status_polling_evidence.json",
                "cancel_boundary_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/cancel_boundary_evidence.json",
                "reconciliation_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_reconciliation_evidence.json",
                "session_close_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_session_close_evidence.json",
            })["import_paths_block_reasons"],
        },
        "path_traversal": {
            "blocked_fail_closed": validate_import_paths({
                "redacted_submit_response_bundle_path": "EXTERNAL_RUNTIME_OUTPUT/../secret_dump.json",
                "external_runtime_execution_transcript_path": "EXTERNAL_RUNTIME_OUTPUT/external_runtime_execution_transcript.json",
                "no_secret_log_scan_report_path": "EXTERNAL_RUNTIME_OUTPUT/no_secret_log_scan_report.json",
                "status_polling_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/status_polling_evidence.json",
                "cancel_boundary_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/cancel_boundary_evidence.json",
                "reconciliation_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_reconciliation_evidence.json",
                "session_close_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_session_close_evidence.json",
            })["import_paths_valid"] is False,
            "block_reasons": validate_import_paths({
                "redacted_submit_response_bundle_path": "EXTERNAL_RUNTIME_OUTPUT/../secret_dump.json",
                "external_runtime_execution_transcript_path": "EXTERNAL_RUNTIME_OUTPUT/external_runtime_execution_transcript.json",
                "no_secret_log_scan_report_path": "EXTERNAL_RUNTIME_OUTPUT/no_secret_log_scan_report.json",
                "status_polling_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/status_polling_evidence.json",
                "cancel_boundary_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/cancel_boundary_evidence.json",
                "reconciliation_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_reconciliation_evidence.json",
                "session_close_evidence_path": "EXTERNAL_RUNTIME_OUTPUT/signed_testnet_session_close_evidence.json",
            })["import_paths_block_reasons"],
        },
        "log_scan_nonzero": {
            "blocked_fail_closed": validate_no_secret_log_scan_report({**base_log_scan, "forbidden_pattern_match_count": 1})["no_secret_log_scan_report_valid"] is False,
            "block_reasons": validate_no_secret_log_scan_report({**base_log_scan, "forbidden_pattern_match_count": 1})["no_secret_log_scan_report_block_reasons"],
        },
        "transcript_runtime_authority": {
            "blocked_fail_closed": validate_execution_transcript_for_import({**base_transcript, "can_grant_runtime_authority": True})["execution_transcript_import_valid"] is False,
            "block_reasons": validate_execution_transcript_for_import({**base_transcript, "can_grant_runtime_authority": True})["execution_transcript_import_block_reasons"],
        },
        "p7_preview_status_mutation": {
            "blocked_fail_closed": validate_p7_import_preview_template(P7ImportPreviewTemplate(p7_valid_status_written_by_p50=True))["p7_import_preview_template_valid"] is False,
            "block_reasons": validate_p7_import_preview_template(P7ImportPreviewTemplate(p7_valid_status_written_by_p50=True))["p7_import_preview_template_block_reasons"],
        },
    }
    result = {
        "artifact_type": "p50_external_evidence_import_validator_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(item["blocked_fail_closed"] for item in fixture_results.values()),
        "fixture_results": fixture_results,
        **_execution_false_payload(),
    }
    result["p50_negative_fixture_results_sha256"] = sha256_json(result)
    return result


def persist_p50_external_evidence_import_validator(*, cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    latest = _latest_dir(cfg)
    storage = _storage_dir(cfg, "storage/p50_external_evidence_import_validator")
    report = build_p50_external_evidence_import_validator_report(cfg=cfg)
    negative = build_p50_negative_fixture_results(cfg=cfg)
    import_template = report["external_evidence_import_manifest_template"]
    preview_template = report["p7_import_preview_template"]
    registry_record = append_registry_record(
        registry_path(cfg, P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_REGISTRY_NAME),
        {
            "artifact_type": "p50_external_evidence_import_validator_registry_record",
            "status": report["status"],
            "blocked": report["blocked"],
            "p50_external_evidence_import_validator_id": report["p50_external_evidence_import_validator_id"],
            "p50_external_evidence_import_validator_sha256": report["p50_external_evidence_import_validator_sha256"],
            "source_p49_handoff_sha256": report["source_p49_handoff_validation"].get("source_sha256"),
            "candidate_import_payload_supplied": report["candidate_import_payload_supplied"],
            "p7_intake_execution_performed": report["p7_intake_execution_performed"],
            "p7_valid_status_written_by_p50": report["p7_valid_status_written_by_p50"],
            "actual_order_submission_performed": report["actual_order_submission_performed"],
            "order_endpoint_called": report["order_endpoint_called"],
            "http_request_sent": report["http_request_sent"],
            "signature_created": report["signature_created"],
            "secret_value_accessed": report["secret_value_accessed"],
        },
        registry_name=P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_REGISTRY_NAME,
        id_field="p50_external_evidence_import_validator_registry_record_id",
        hash_field="p50_external_evidence_import_validator_registry_record_sha256",
        id_prefix="p50_external_evidence_import_validator_registry_record",
    )
    report["p50_external_evidence_import_validator_registry_record_id"] = registry_record["p50_external_evidence_import_validator_registry_record_id"]
    report["p50_external_evidence_import_validator_registry_record_sha256"] = registry_record["p50_external_evidence_import_validator_registry_record_sha256"]
    report["p50_external_evidence_import_validator_sha256"] = sha256_json(report)
    summary = {
        "artifact_type": "p50_external_evidence_import_validator_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": report["review_only"],
        "import_validator_skeleton_only": report["import_validator_skeleton_only"],
        "external_runtime_only": report["external_runtime_only"],
        "candidate_import_payload_supplied": report["candidate_import_payload_supplied"],
        "p7_intake_execution_performed": report["p7_intake_execution_performed"],
        "p7_valid_status_written_by_p50": report["p7_valid_status_written_by_p50"],
        "actual_order_submission_performed": report["actual_order_submission_performed"],
        "order_endpoint_called": report["order_endpoint_called"],
        "http_request_sent": report["http_request_sent"],
        "signature_created": report["signature_created"],
        "secret_value_accessed": report["secret_value_accessed"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked_fail_closed"],
        "p50_external_evidence_import_validator_id": report["p50_external_evidence_import_validator_id"],
        "p50_external_evidence_import_validator_sha256": report["p50_external_evidence_import_validator_sha256"],
        "created_at_utc": report["created_at_utc"],
    }
    summary["p50_summary_sha256"] = sha256_json(summary)
    writes = {
        "p50_external_evidence_import_validator_report.json": report,
        "p50_external_evidence_import_manifest_TEMPLATE_NO_SUBMIT.json": import_template,
        "p50_p7_import_preview_TEMPLATE_NO_SUBMIT.json": preview_template,
        "p50_external_evidence_import_validator_negative_fixture_results.json": negative,
        "p50_external_evidence_import_validator_registry_record.json": registry_record,
        "p50_external_evidence_import_validator_summary.json": summary,
    }
    for filename, payload in writes.items():
        atomic_write_json(latest / filename, payload)
        atomic_write_json(storage / filename, payload)
    return report


__all__ = [
    "P50_EXTERNAL_EVIDENCE_IMPORT_VALIDATOR_VERSION",
    "STATUS_READY_REVIEW_ONLY_NO_SUBMIT",
    "STATUS_BLOCKED_FAIL_CLOSED",
    "ExternalEvidenceImportManifestTemplate",
    "P7ImportPreviewTemplate",
    "validate_p49_handoff_source",
    "validate_import_manifest_template",
    "validate_import_paths",
    "validate_redacted_submit_response_bundle_for_import",
    "validate_no_secret_log_scan_report",
    "validate_execution_transcript_for_import",
    "validate_p7_import_preview_template",
    "build_p7_input_preview_from_bundle",
    "build_p50_external_evidence_import_validator_report",
    "build_p50_negative_fixture_results",
    "persist_p50_external_evidence_import_validator",
]
