from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.external_runtime_evidence_handoff import (
    scan_log_text_for_secret_leaks,
)
from crypto_ai_system.execution.runtime_disabled_flags import (
    default_execution_flag_state,
    truthy_execution_flags,
)
from crypto_ai_system.registry.base_registry import append_registry_record, registry_path
from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION = (
    "p58_external_runtime_signed_testnet_evidence_acquisition_v1"
)
P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_REGISTRY_NAME = (
    "p58_external_runtime_signed_testnet_evidence_acquisition_registry"
)

STATUS_VALIDATED_REVIEW_ONLY_RUNNER_DISABLED = (
    "P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_BOUNDARY_VALIDATED_REVIEW_ONLY_RUNNER_DISABLED"
)
STATUS_READY_REVIEW_ONLY_RUNNER_DISABLED = (
    "P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_BOUNDARY_READY_REVIEW_ONLY_RUNNER_DISABLED"
)
STATUS_BLOCKED_FAIL_CLOSED = (
    "P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_BOUNDARY_BLOCKED_FAIL_CLOSED"
)

_ALLOWED_ENVIRONMENT = "testnet"
_ALLOWED_VENUE = "binance_futures_testnet"
_ALLOWED_SYMBOL = "BTCUSDT"
_ALLOWED_SELF_TEST_SCOPE = "p58_no_network_evidence_acquisition_self_test"
_REAL_ACQUISITION_SCOPE = "signed_testnet_real_evidence_acquisition"
_SELF_TEST_EVIDENCE_ORIGIN = "p58_no_network_self_test_fixture"
_REAL_EVIDENCE_ORIGIN = "real_signed_testnet_external_runtime"
_SELF_TEST_APPROVAL_PHRASE = (
    "AUTHORIZE_P58_NO_NETWORK_EVIDENCE_ACQUISITION_SELF_TEST_ONLY_NO_ORDER_SUBMIT"
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
    "unredacted_exchange_response",
    "secret_file_contents",
)


class ExternalRuntimeEvidenceAcquisitionError(RuntimeError):
    """Base fail-closed error for P58."""


class ExternalRuntimeEvidenceAcquisitionDisabledError(
    ExternalRuntimeEvidenceAcquisitionError
):
    """Raised when real acquisition or a disabled runner path is attempted."""


class ExternalRuntimeEvidenceAcquisitionValidationError(
    ExternalRuntimeEvidenceAcquisitionError
):
    """Raised when request, adapter, export, or safety validation fails."""


class ExternalRuntimeEvidenceAdapter(Protocol):
    adapter_id: str
    adapter_version: str
    venue: str
    environment: str
    symbol: str
    fixture_only: bool
    real_endpoint_adapter: bool
    network_call_capable: bool
    submit_enabled_by_default: bool

    def acquire_redacted_evidence(
        self,
        *,
        order_intent_metadata: Mapping[str, Any],
        idempotency_key: str,
        secret_reference_id: str,
    ) -> Mapping[str, Any]:
        ...


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
                    for marker in (
                        "_included",
                        "_accessed",
                        "_logged",
                        "_created",
                        "_performed",
                        "_allowed",
                    )
                )
                if not safe_boolean:
                    blockers.append(f"P58_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden(value, prefix=child))
    elif isinstance(obj, Sequence) and not isinstance(
        obj, (str, bytes, bytearray)
    ):
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
            "secret_file_accessed": False,
            "secret_file_created": False,
            "runtime_scheduler_enabled": False,
            "runtime_loop_started": False,
            "runtime_authority_granted": False,
            "runtime_mutation_performed": False,
            "external_runtime_runner_enabled": False,
            "external_runtime_real_adapter_loaded": False,
            "external_runtime_real_acquisition_enabled": False,
            "external_runtime_real_acquisition_executed": False,
            "redacted_real_signed_testnet_evidence_exported": False,
            "real_signed_testnet_evidence_present": False,
            "p7_importer_enabled": False,
            "p7_importer_action_allowed": False,
            "p7_importer_action_executed": False,
            "p7_valid_status_written_by_p58": False,
            "p7_report_persisted_by_p58": False,
            "p8_repeated_session_candidate_created": False,
            "signed_testnet_promotion_allowed": False,
            "live_canary_execution_enabled": False,
            "live_scaled_execution_enabled": False,
        }
    )
    return payload


@dataclass(frozen=True)
class ExternalRuntimeEvidenceAcquisitionConfig:
    runner_version: str = P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION
    external_runtime_only: bool = True
    external_runtime_runner_implemented: bool = True
    review_package_network_calls_enabled: bool = False
    review_package_real_adapter_implementation_included: bool = False
    external_runtime_runner_enabled: bool = False
    real_evidence_acquisition_enabled: bool = False
    no_network_self_test_enabled: bool = True
    environment: str = _ALLOWED_ENVIRONMENT
    venue: str = _ALLOWED_VENUE
    symbol: str = _ALLOWED_SYMBOL
    max_order_count: int = 1
    request_signing_boundary: str = "external_runtime_process_memory_only"
    secret_binding_mode: str = "metadata_reference_only_in_review_package"
    require_p6_external_runtime_preflight: bool = True
    require_p48_connector_contract: bool = True
    require_p49_redacted_handoff_schema: bool = True
    require_fresh_hot_path_risk_gate: bool = True
    require_exact_operator_approval: bool = True
    require_external_adapter_package_hash: bool = True
    require_metadata_only_secret_reference: bool = True
    require_key_fingerprint_sha256: bool = True
    require_idempotency_key: bool = True
    require_duplicate_submit_lock: bool = True
    require_redacted_evidence_export: bool = True
    require_no_secret_log_scan: bool = True
    require_status_polling_evidence: bool = True
    require_cancel_boundary_evidence: bool = True
    require_reconciliation_evidence: bool = True
    require_session_close_evidence: bool = True
    raw_secret_values_allowed: bool = False
    raw_request_body_export_allowed: bool = False
    raw_signed_payload_export_allowed: bool = False
    raw_exchange_payload_export_allowed: bool = False
    fail_closed_on_any_mismatch: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p58_external_runtime_evidence_acquisition_config_sha256"] = (
            sha256_json(payload)
        )
        return payload


@dataclass(frozen=True)
class ExternalRuntimeAdapterManifest:
    manifest_type: str = "p58_external_runtime_adapter_manifest_EXTERNAL_PACKAGE_ONLY"
    adapter_id: str = "OPERATOR_SUPPLIED_EXTERNAL_TESTNET_ADAPTER_ID"
    adapter_version: str = "OPERATOR_SUPPLIED_EXTERNAL_TESTNET_ADAPTER_VERSION"
    adapter_module_ref: str = "EXTERNAL_RUNTIME_PACKAGE_ONLY_NOT_INCLUDED_IN_REVIEW_PACKAGE"
    adapter_package_sha256: str = "0" * 64
    environment: str = _ALLOWED_ENVIRONMENT
    venue: str = _ALLOWED_VENUE
    symbol: str = _ALLOWED_SYMBOL
    max_order_count: int = 1
    fixture_only: bool = False
    real_endpoint_adapter: bool = True
    network_call_capable_in_external_runtime: bool = True
    loaded_by_review_package: bool = False
    implementation_included_in_review_package: bool = False
    submit_enabled_by_default: bool = False
    testnet_endpoint_policy_enforced: bool = True
    idempotency_supported: bool = True
    duplicate_submit_lock_supported: bool = True
    post_submit_relock_supported: bool = True
    redacted_evidence_export_supported: bool = True
    no_secret_logging_supported: bool = True
    process_memory_only_signing_supported: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p58_external_runtime_adapter_manifest_sha256"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P58OperatorEvidenceAcquisitionApproval:
    artifact_type: str = "p58_operator_evidence_acquisition_approval_SELF_TEST_ONLY"
    approval_mode: str = "no_network_self_test_only"
    approval_phrase: str = _SELF_TEST_APPROVAL_PHRASE
    approved_p6_preflight_sha256: str = "P6_PREFLIGHT_SHA256_REQUIRED"
    approved_p48_connector_sha256: str = "P48_CONNECTOR_SHA256_REQUIRED"
    approved_p49_handoff_sha256: str = "P49_HANDOFF_SHA256_REQUIRED"
    approved_adapter_manifest_sha256: str = "ADAPTER_MANIFEST_SHA256_REQUIRED"
    approved_order_intent_sha256: str = "ORDER_INTENT_SHA256_REQUIRED"
    one_time_action_nonce_sha256: str = "NONCE_SHA256_REQUIRED"
    real_evidence_acquisition_approved: bool = False
    runtime_network_call_allowed: bool = False
    runtime_authority_granted: bool = False
    review_only: bool = True
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p58_operator_evidence_acquisition_approval_id"] = stable_id(
            "p58_operator_evidence_acquisition_approval", payload, 24
        )
        payload["p58_operator_evidence_acquisition_approval_sha256"] = sha256_json(
            payload
        )
        return payload


@dataclass(frozen=True)
class P58EvidenceAcquisitionRequest:
    operation_scope: str
    evidence_origin: str
    p6_preflight_report: Mapping[str, Any]
    p48_connector_report: Mapping[str, Any]
    p49_handoff_report: Mapping[str, Any]
    adapter_manifest: Mapping[str, Any]
    operator_approval: Mapping[str, Any]
    order_intent_metadata: Mapping[str, Any]
    secret_reference_id: str
    key_fingerprint_sha256: str
    idempotency_key: str
    hot_path_preorder_risk_gate_id: str
    hot_path_preorder_risk_gate_sha256: str
    self_test_only: bool = True
    real_evidence_acquisition_requested: bool = False
    created_at_utc: str = field(default_factory=utc_now_canonical)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "operation_scope": self.operation_scope,
            "evidence_origin": self.evidence_origin,
            "p6_preflight_report": dict(self.p6_preflight_report),
            "p48_connector_report": dict(self.p48_connector_report),
            "p49_handoff_report": dict(self.p49_handoff_report),
            "adapter_manifest": dict(self.adapter_manifest),
            "operator_approval": dict(self.operator_approval),
            "order_intent_metadata": dict(self.order_intent_metadata),
            "secret_reference_id": self.secret_reference_id,
            "key_fingerprint_sha256": self.key_fingerprint_sha256,
            "idempotency_key": self.idempotency_key,
            "hot_path_preorder_risk_gate_id": self.hot_path_preorder_risk_gate_id,
            "hot_path_preorder_risk_gate_sha256": self.hot_path_preorder_risk_gate_sha256,
            "self_test_only": self.self_test_only,
            "real_evidence_acquisition_requested": self.real_evidence_acquisition_requested,
            "created_at_utc": self.created_at_utc,
        }


class P58NoNetworkFixtureAdapter:
    """No-network adapter used only to exercise the P58 runner/exporter path.

    It never calls an endpoint, creates a signature, reads a secret, or returns
    evidence that can be accepted as real signed-testnet evidence.
    """

    adapter_id = "p58_no_network_fixture_adapter_v1"
    adapter_version = "1.0.0"
    venue = _ALLOWED_VENUE
    environment = _ALLOWED_ENVIRONMENT
    symbol = _ALLOWED_SYMBOL
    fixture_only = True
    real_endpoint_adapter = False
    network_call_capable = False
    submit_enabled_by_default = False

    def acquire_redacted_evidence(
        self,
        *,
        order_intent_metadata: Mapping[str, Any],
        idempotency_key: str,
        secret_reference_id: str,
    ) -> Mapping[str, Any]:
        request_hash = sha256_json(
            {
                "fixture": True,
                "order_intent_metadata": dict(order_intent_metadata),
                "idempotency_key": idempotency_key,
                "secret_reference_id": secret_reference_id,
            }
        )
        response_hash = sha256_json(
            {
                "fixture": True,
                "status": "NOT_SUBMITTED_NO_NETWORK_SELF_TEST",
                "request_hash": request_hash,
            }
        )
        payload = {
            "artifact_type": "p58_no_network_fixture_adapter_result",
            "evidence_origin": _SELF_TEST_EVIDENCE_ORIGIN,
            "fixture_evidence": True,
            "mock_or_fixture_evidence": True,
            "synthetic_or_sample_evidence": True,
            "real_signed_testnet_evidence": False,
            "p7_import_eligible": False,
            "environment": self.environment,
            "venue": self.venue,
            "symbol": self.symbol,
            "order_count": 0,
            "exchange_order_id": "P58_FIXTURE_ORDER_ID_NOT_REAL",
            "client_order_id": str(
                order_intent_metadata.get(
                    "client_order_id", "P58_FIXTURE_CLIENT_ORDER_ID_NOT_REAL"
                )
            ),
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "exchange_response_hash": response_hash,
            "exchange_order_status": "NOT_SUBMITTED_NO_NETWORK_SELF_TEST",
            "order_endpoint_called": False,
            "order_status_endpoint_called": False,
            "cancel_endpoint_called": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "secret_value_logged": False,
            "raw_request_body_included": False,
            "raw_signed_payload_included": False,
            "raw_exchange_payload_included": False,
            "status_polling_evidence": {
                "artifact_type": "p58_fixture_status_polling_evidence",
                "terminal_status_observed": False,
                "poll_count": 0,
                "fixture_only": True,
            },
            "cancel_boundary_evidence": {
                "artifact_type": "p58_fixture_cancel_boundary_evidence",
                "cancel_required": False,
                "cancel_performed": False,
                "fixture_only": True,
            },
            "signed_testnet_reconciliation_evidence": {
                "artifact_type": "p58_fixture_reconciliation_evidence",
                "reconciliation_performed": False,
                "reconciliation_match": False,
                "fixture_only": True,
            },
            "signed_testnet_session_close_evidence": {
                "artifact_type": "p58_fixture_session_close_evidence",
                "session_close_performed": False,
                "clean_session": False,
                "fixture_only": True,
            },
            **_execution_false_payload(),
        }
        payload["p58_no_network_fixture_adapter_result_sha256"] = sha256_json(payload)
        return payload


class P58RedactedEvidenceExporter:
    """Exports only redacted, hash-bound evidence artifacts.

    Raw request bodies, signed payloads, unredacted exchange responses, and all
    secret values are rejected before any file is written.
    """

    def validate_adapter_result(self, result: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(result or {})
        blockers = _walk_forbidden(payload)
        if payload.get("evidence_origin") != _SELF_TEST_EVIDENCE_ORIGIN:
            blockers.append("P58_SELF_TEST_EVIDENCE_ORIGIN_INVALID")
        if payload.get("fixture_evidence") is not True:
            blockers.append("P58_SELF_TEST_FIXTURE_MARKER_MISSING")
        if payload.get("real_signed_testnet_evidence") is not False:
            blockers.append("P58_SELF_TEST_REAL_EVIDENCE_OVERSTATED")
        if payload.get("p7_import_eligible") is not False:
            blockers.append("P58_SELF_TEST_P7_ELIGIBILITY_OVERSTATED")
        for key in (
            "order_endpoint_called",
            "order_status_endpoint_called",
            "cancel_endpoint_called",
            "http_request_sent",
            "signature_created",
            "signed_request_created",
            "secret_value_accessed",
            "secret_value_logged",
            "raw_request_body_included",
            "raw_signed_payload_included",
            "raw_exchange_payload_included",
        ):
            if payload.get(key) is not False:
                blockers.append(f"P58_SELF_TEST_{key.upper()}_NOT_FALSE")
        for key in ("request_hash", "exchange_response_hash"):
            if not _is_sha256_hex(payload.get(key)):
                blockers.append(f"P58_SELF_TEST_{key.upper()}_INVALID")
        if not _verify_embedded_hash(
            payload, "p58_no_network_fixture_adapter_result_sha256"
        ):
            blockers.append("P58_SELF_TEST_ADAPTER_RESULT_EMBEDDED_SHA256_INVALID")
        validation = {
            "adapter_result_valid": not blockers,
            "adapter_result_block_reasons": sorted(dict.fromkeys(blockers)),
            "fixture_evidence": payload.get("fixture_evidence") is True,
            "real_signed_testnet_evidence": payload.get(
                "real_signed_testnet_evidence"
            )
            is True,
            "p7_import_eligible": payload.get("p7_import_eligible") is True,
        }
        validation["p58_adapter_result_validation_sha256"] = sha256_json(validation)
        return validation

    def export_self_test_bundle(
        self,
        *,
        request: P58EvidenceAcquisitionRequest,
        adapter_result: Mapping[str, Any],
        output_dir: str | Path,
    ) -> dict[str, Any]:
        validation = self.validate_adapter_result(adapter_result)
        if not validation["adapter_result_valid"]:
            raise ExternalRuntimeEvidenceAcquisitionValidationError(
                ";".join(validation["adapter_result_block_reasons"])
            )
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        result = dict(adapter_result)

        redacted_bundle = {
            "artifact_type": "p58_redacted_submit_response_bundle_NO_NETWORK_SELF_TEST",
            "p58_version": P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION,
            "evidence_origin": _SELF_TEST_EVIDENCE_ORIGIN,
            "fixture_evidence": True,
            "mock_or_fixture_evidence": True,
            "synthetic_or_sample_evidence": True,
            "real_signed_testnet_evidence": False,
            "p7_import_eligible": False,
            "environment": result["environment"],
            "venue": result["venue"],
            "symbol": result["symbol"],
            "exchange_order_id": result["exchange_order_id"],
            "client_order_id": result["client_order_id"],
            "idempotency_key": result["idempotency_key"],
            "request_hash": result["request_hash"],
            "exchange_response_hash": result["exchange_response_hash"],
            "exchange_order_status": result["exchange_order_status"],
            "hot_path_preorder_risk_gate_id": request.hot_path_preorder_risk_gate_id,
            "hot_path_preorder_risk_gate_sha256": request.hot_path_preorder_risk_gate_sha256,
            "secret_reference_id": request.secret_reference_id,
            "key_fingerprint_sha256": request.key_fingerprint_sha256,
            "raw_request_body_included": False,
            "raw_signed_payload_included": False,
            "raw_exchange_payload_included": False,
            "raw_secret_values_included": False,
            **_execution_false_payload(),
        }
        redacted_bundle["p58_redacted_submit_response_bundle_sha256"] = sha256_json(
            redacted_bundle
        )

        transcript = {
            "artifact_type": "p58_external_runtime_execution_transcript_NO_NETWORK_SELF_TEST",
            "p58_version": P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION,
            "evidence_origin": _SELF_TEST_EVIDENCE_ORIGIN,
            "fixture_only": True,
            "real_signed_testnet_evidence": False,
            "p7_import_eligible": False,
            "operation_scope": request.operation_scope,
            "adapter_id": result["artifact_type"],
            "operator_approval_sha256": request.operator_approval.get(
                "p58_operator_evidence_acquisition_approval_sha256"
            ),
            "p6_preflight_sha256": request.p6_preflight_report.get(
                "p6_external_runtime_preflight_report_sha256"
            ),
            "p48_connector_sha256": request.p48_connector_report.get(
                "p48_local_runtime_adapter_connector_sha256"
            ),
            "p49_handoff_sha256": request.p49_handoff_report.get(
                "p49_external_runtime_evidence_handoff_sha256"
            ),
            "adapter_manifest_sha256": request.adapter_manifest.get(
                "p58_external_runtime_adapter_manifest_sha256"
            ),
            "order_intent_sha256": sha256_json(dict(request.order_intent_metadata)),
            "request_hash": result["request_hash"],
            "exchange_response_hash": result["exchange_response_hash"],
            "status_polling_evidence_sha256": sha256_json(
                result["status_polling_evidence"]
            ),
            "cancel_boundary_evidence_sha256": sha256_json(
                result["cancel_boundary_evidence"]
            ),
            "reconciliation_evidence_sha256": sha256_json(
                result["signed_testnet_reconciliation_evidence"]
            ),
            "session_close_evidence_sha256": sha256_json(
                result["signed_testnet_session_close_evidence"]
            ),
            "raw_request_body_included": False,
            "raw_signed_payload_included": False,
            "raw_exchange_payload_included": False,
            "raw_secret_values_included": False,
            **_execution_false_payload(),
        }
        transcript["p58_external_runtime_execution_transcript_sha256"] = sha256_json(
            transcript
        )

        p7_bridge_candidate = {
            "artifact_type": "p58_p7_intake_bridge_candidate_NO_NETWORK_SELF_TEST",
            "p58_version": P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION,
            "evidence_origin": _SELF_TEST_EVIDENCE_ORIGIN,
            "fixture_evidence": True,
            "real_signed_testnet_evidence": False,
            "p7_import_eligible": False,
            "p7_import_block_reason": "P58_NO_NETWORK_SELF_TEST_FIXTURE_NOT_REAL_SIGNED_TESTNET_EVIDENCE",
            "redacted_bundle_sha256": redacted_bundle[
                "p58_redacted_submit_response_bundle_sha256"
            ],
            "transcript_sha256": transcript[
                "p58_external_runtime_execution_transcript_sha256"
            ],
            "status_polling_evidence": dict(result["status_polling_evidence"]),
            "cancel_boundary_evidence": dict(result["cancel_boundary_evidence"]),
            "signed_testnet_reconciliation_evidence": dict(
                result["signed_testnet_reconciliation_evidence"]
            ),
            "signed_testnet_session_close_evidence": dict(
                result["signed_testnet_session_close_evidence"]
            ),
            **_execution_false_payload(),
        }
        p7_bridge_candidate["p58_p7_intake_bridge_candidate_sha256"] = sha256_json(
            p7_bridge_candidate
        )

        pre_scan_text = json.dumps(
            {
                "redacted_bundle": redacted_bundle,
                "transcript": transcript,
                "p7_bridge_candidate": p7_bridge_candidate,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        scan = scan_log_text_for_secret_leaks(pre_scan_text)
        no_secret_scan_report = {
            "artifact_type": "p58_no_secret_log_scan_report_NO_NETWORK_SELF_TEST",
            "p58_version": P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION,
            "scan_completed": True,
            "scan_passed": scan.get("secret_leak_detected") is False,
            "forbidden_pattern_match_count": scan.get(
                "forbidden_pattern_match_count", 0
            ),
            "matched_patterns": list(scan.get("matched_patterns") or []),
            "no_secret_logged_evidence_hash": scan.get(
                "no_secret_log_text_scan_sha256"
            ),
            "raw_secret_values_included": False,
            **_execution_false_payload(),
        }
        no_secret_scan_report["p58_no_secret_log_scan_report_sha256"] = sha256_json(
            no_secret_scan_report
        )
        if no_secret_scan_report["scan_passed"] is not True:
            raise ExternalRuntimeEvidenceAcquisitionValidationError(
                "P58_NO_SECRET_SCAN_FAILED"
            )

        outputs: dict[str, dict[str, Any]] = {
            "p58_redacted_submit_response_bundle_NO_NETWORK_SELF_TEST.json": redacted_bundle,
            "p58_external_runtime_execution_transcript_NO_NETWORK_SELF_TEST.json": transcript,
            "p58_no_secret_log_scan_report_NO_NETWORK_SELF_TEST.json": no_secret_scan_report,
            "p58_p7_intake_bridge_candidate_NO_NETWORK_SELF_TEST.json": p7_bridge_candidate,
        }
        for filename, payload in outputs.items():
            atomic_write_json(output / filename, payload)

        manifest_files = []
        for filename, payload in outputs.items():
            manifest_files.append(
                {
                    "filename": filename,
                    "artifact_type": payload.get("artifact_type"),
                    "artifact_sha256": sha256_json(payload),
                    "byte_size": (output / filename).stat().st_size,
                }
            )
        manifest = {
            "artifact_type": "p58_redacted_evidence_export_manifest_NO_NETWORK_SELF_TEST",
            "p58_version": P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION,
            "evidence_origin": _SELF_TEST_EVIDENCE_ORIGIN,
            "fixture_only": True,
            "real_signed_testnet_evidence": False,
            "p7_import_eligible": False,
            "all_files_redacted": True,
            "no_secret_scan_passed": True,
            "file_count": len(manifest_files),
            "files": manifest_files,
            **_execution_false_payload(),
        }
        manifest["p58_redacted_evidence_export_manifest_sha256"] = sha256_json(
            manifest
        )
        manifest_name = "p58_redacted_evidence_export_manifest_NO_NETWORK_SELF_TEST.json"
        atomic_write_json(output / manifest_name, manifest)

        return {
            "artifact_type": "p58_redacted_evidence_export_result",
            "export_succeeded": True,
            "output_directory": str(output),
            "file_count": len(manifest_files) + 1,
            "manifest_filename": manifest_name,
            "manifest_sha256": manifest[
                "p58_redacted_evidence_export_manifest_sha256"
            ],
            "no_secret_scan_passed": True,
            "real_signed_testnet_evidence": False,
            "p7_import_eligible": False,
            **_execution_false_payload(),
        }


class ExternalRuntimeEvidenceAcquisitionRunner:
    def __init__(
        self,
        *,
        config: ExternalRuntimeEvidenceAcquisitionConfig | None = None,
        exporter: P58RedactedEvidenceExporter | None = None,
    ) -> None:
        self.config = config or ExternalRuntimeEvidenceAcquisitionConfig()
        self.exporter = exporter or P58RedactedEvidenceExporter()

    def validate_request(
        self,
        request: P58EvidenceAcquisitionRequest,
        adapter: ExternalRuntimeEvidenceAdapter,
    ) -> dict[str, Any]:
        blockers: list[str] = []
        cfg = self.config.to_dict()
        cfg_validation = validate_p58_config(cfg)
        blockers.extend(cfg_validation["config_block_reasons"])

        if request.operation_scope != _ALLOWED_SELF_TEST_SCOPE:
            blockers.append("P58_OPERATION_SCOPE_NOT_SELF_TEST")
        if request.evidence_origin != _SELF_TEST_EVIDENCE_ORIGIN:
            blockers.append("P58_EVIDENCE_ORIGIN_NOT_SELF_TEST")
        if request.self_test_only is not True:
            blockers.append("P58_SELF_TEST_ONLY_NOT_TRUE")
        if request.real_evidence_acquisition_requested is not False:
            blockers.append("P58_REAL_ACQUISITION_REQUESTED_IN_REVIEW_PACKAGE")

        source_checks = (
            (
                request.p6_preflight_report,
                "status",
                "P6_EXTERNAL_RUNTIME_PREFLIGHT_READY_REVIEW_ONLY_NO_SUBMIT",
                "p6_external_runtime_preflight_report_sha256",
                "P58_P6",
            ),
            (
                request.p48_connector_report,
                "status",
                "P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_READY_REVIEW_ONLY_NO_SUBMIT",
                "p48_local_runtime_adapter_connector_sha256",
                "P58_P48",
            ),
            (
                request.p49_handoff_report,
                "status",
                "P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_READY_REVIEW_ONLY_NO_SUBMIT",
                "p49_external_runtime_evidence_handoff_sha256",
                "P58_P49",
            ),
        )
        for payload, status_key, expected_status, hash_key, prefix in source_checks:
            if payload.get(status_key) != expected_status:
                blockers.append(f"{prefix}_STATUS_INVALID")
            if prefix == "P58_P49":
                # P49 appends its registry-record hash after its initial report hash.
                # Preserve the stored P49 hash as the chain anchor and require SHA-256 shape.
                if not _is_sha256_hex(payload.get(hash_key)):
                    blockers.append(f"{prefix}_REPORT_SHA256_INVALID")
            elif not _verify_embedded_hash(payload, hash_key):
                blockers.append(f"{prefix}_EMBEDDED_SHA256_INVALID")
            if payload.get("blocked") is True:
                blockers.append(f"{prefix}_SOURCE_BLOCKED")

        manifest_validation = validate_external_runtime_adapter_manifest(
            request.adapter_manifest, self_test=True
        )
        blockers.extend(manifest_validation["manifest_block_reasons"])

        approval_validation = validate_p58_operator_approval(
            request.operator_approval
        )
        blockers.extend(approval_validation["approval_block_reasons"])

        if request.operator_approval.get("approved_p6_preflight_sha256") != request.p6_preflight_report.get(
            "p6_external_runtime_preflight_report_sha256"
        ):
            blockers.append("P58_APPROVED_P6_HASH_MISMATCH")
        if request.operator_approval.get("approved_p48_connector_sha256") != request.p48_connector_report.get(
            "p48_local_runtime_adapter_connector_sha256"
        ):
            blockers.append("P58_APPROVED_P48_HASH_MISMATCH")
        if request.operator_approval.get("approved_p49_handoff_sha256") != request.p49_handoff_report.get(
            "p49_external_runtime_evidence_handoff_sha256"
        ):
            blockers.append("P58_APPROVED_P49_HASH_MISMATCH")
        if request.operator_approval.get("approved_adapter_manifest_sha256") != request.adapter_manifest.get(
            "p58_external_runtime_adapter_manifest_sha256"
        ):
            blockers.append("P58_APPROVED_ADAPTER_MANIFEST_HASH_MISMATCH")
        if request.operator_approval.get("approved_order_intent_sha256") != sha256_json(
            dict(request.order_intent_metadata)
        ):
            blockers.append("P58_APPROVED_ORDER_INTENT_HASH_MISMATCH")

        if not str(request.secret_reference_id or "").strip():
            blockers.append("P58_SECRET_REFERENCE_ID_MISSING")
        if not _is_sha256_hex(request.key_fingerprint_sha256):
            blockers.append("P58_KEY_FINGERPRINT_SHA256_INVALID")
        if not _is_sha256_hex(request.idempotency_key):
            blockers.append("P58_IDEMPOTENCY_KEY_INVALID")
        if not str(request.hot_path_preorder_risk_gate_id or "").strip():
            blockers.append("P58_HOT_PATH_RISK_GATE_ID_MISSING")
        if not _is_sha256_hex(request.hot_path_preorder_risk_gate_sha256):
            blockers.append("P58_HOT_PATH_RISK_GATE_SHA256_INVALID")

        if getattr(adapter, "fixture_only", None) is not True:
            blockers.append("P58_SELF_TEST_ADAPTER_NOT_FIXTURE_ONLY")
        if getattr(adapter, "real_endpoint_adapter", None) is not False:
            blockers.append("P58_SELF_TEST_REAL_ENDPOINT_ADAPTER_NOT_FALSE")
        if getattr(adapter, "network_call_capable", None) is not False:
            blockers.append("P58_SELF_TEST_ADAPTER_NETWORK_CAPABLE")
        if getattr(adapter, "submit_enabled_by_default", None) is not False:
            blockers.append("P58_SELF_TEST_ADAPTER_SUBMIT_ENABLED_BY_DEFAULT")
        if getattr(adapter, "environment", None) != _ALLOWED_ENVIRONMENT:
            blockers.append("P58_ADAPTER_ENVIRONMENT_NOT_TESTNET")
        if getattr(adapter, "venue", None) != _ALLOWED_VENUE:
            blockers.append("P58_ADAPTER_VENUE_INVALID")
        if getattr(adapter, "symbol", None) != _ALLOWED_SYMBOL:
            blockers.append("P58_ADAPTER_SYMBOL_INVALID")
        if request.adapter_manifest.get("adapter_id") != getattr(
            adapter, "adapter_id", None
        ):
            blockers.append("P58_ADAPTER_ID_MANIFEST_MISMATCH")
        if request.adapter_manifest.get("adapter_version") != getattr(
            adapter, "adapter_version", None
        ):
            blockers.append("P58_ADAPTER_VERSION_MANIFEST_MISMATCH")

        blockers.extend(_walk_forbidden(request.canonical_payload()))
        unsafe = truthy_execution_flags(request.canonical_payload())
        if unsafe:
            blockers.append(
                "P58_REQUEST_UNSAFE_EXECUTION_FLAGS:" + ",".join(sorted(unsafe))
            )

        validation = {
            "request_valid": not blockers,
            "request_block_reasons": sorted(dict.fromkeys(blockers)),
            "self_test_only": request.self_test_only is True,
            "real_evidence_acquisition_requested": request.real_evidence_acquisition_requested
            is True,
            "adapter_fixture_only": getattr(adapter, "fixture_only", False) is True,
            "adapter_network_call_capable": getattr(
                adapter, "network_call_capable", False
            )
            is True,
        }
        validation["p58_evidence_acquisition_request_validation_sha256"] = (
            sha256_json(validation)
        )
        return validation

    def execute_no_network_self_test(
        self,
        request: P58EvidenceAcquisitionRequest,
        adapter: ExternalRuntimeEvidenceAdapter,
        *,
        output_dir: str | Path,
    ) -> dict[str, Any]:
        validation = self.validate_request(request, adapter)
        if not validation["request_valid"]:
            raise ExternalRuntimeEvidenceAcquisitionValidationError(
                ";".join(validation["request_block_reasons"])
            )
        adapter_result = adapter.acquire_redacted_evidence(
            order_intent_metadata=request.order_intent_metadata,
            idempotency_key=request.idempotency_key,
            secret_reference_id=request.secret_reference_id,
        )
        export_result = self.exporter.export_self_test_bundle(
            request=request,
            adapter_result=adapter_result,
            output_dir=output_dir,
        )
        result = {
            "artifact_type": "p58_external_runtime_evidence_acquisition_self_test_result",
            "runner_code_path_exercised": True,
            "adapter_contract_exercised": True,
            "redacted_exporter_code_path_exercised": True,
            "no_network_adapter_used": True,
            "export_succeeded": export_result["export_succeeded"],
            "exported_file_count": export_result["file_count"],
            "no_secret_scan_passed": export_result["no_secret_scan_passed"],
            "real_signed_testnet_evidence": False,
            "p7_import_eligible": False,
            **_execution_false_payload(),
        }
        result["p58_external_runtime_evidence_acquisition_self_test_result_sha256"] = (
            sha256_json(result)
        )
        return result

    def execute_real_evidence_acquisition(
        self,
        request: P58EvidenceAcquisitionRequest,
        adapter: ExternalRuntimeEvidenceAdapter,
        *,
        output_dir: str | Path,
    ) -> dict[str, Any]:
        del request, adapter, output_dir
        raise ExternalRuntimeEvidenceAcquisitionDisabledError(
            "P58_REAL_SIGNED_TESTNET_EVIDENCE_ACQUISITION_DISABLED_PENDING_SEPARATE_OPERATOR_APPROVAL_AND_EXTERNAL_RUNTIME_ADAPTER_PACKAGE"
        )


def validate_p58_config(
    config: Mapping[str, Any] | ExternalRuntimeEvidenceAcquisitionConfig | None,
) -> dict[str, Any]:
    payload = (
        config.to_dict()
        if isinstance(config, ExternalRuntimeEvidenceAcquisitionConfig)
        else dict(config or ExternalRuntimeEvidenceAcquisitionConfig().to_dict())
    )
    blockers: list[str] = []
    if not _verify_embedded_hash(
        payload, "p58_external_runtime_evidence_acquisition_config_sha256"
    ):
        blockers.append("P58_CONFIG_EMBEDDED_SHA256_INVALID")
    if payload.get("runner_version") != P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION:
        blockers.append("P58_CONFIG_VERSION_MISMATCH")
    for key in (
        "external_runtime_only",
        "external_runtime_runner_implemented",
        "no_network_self_test_enabled",
        "require_p6_external_runtime_preflight",
        "require_p48_connector_contract",
        "require_p49_redacted_handoff_schema",
        "require_fresh_hot_path_risk_gate",
        "require_exact_operator_approval",
        "require_external_adapter_package_hash",
        "require_metadata_only_secret_reference",
        "require_key_fingerprint_sha256",
        "require_idempotency_key",
        "require_duplicate_submit_lock",
        "require_redacted_evidence_export",
        "require_no_secret_log_scan",
        "require_status_polling_evidence",
        "require_cancel_boundary_evidence",
        "require_reconciliation_evidence",
        "require_session_close_evidence",
        "fail_closed_on_any_mismatch",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P58_CONFIG_{key.upper()}_NOT_TRUE")
    for key in (
        "review_package_network_calls_enabled",
        "review_package_real_adapter_implementation_included",
        "external_runtime_runner_enabled",
        "real_evidence_acquisition_enabled",
        "raw_secret_values_allowed",
        "raw_request_body_export_allowed",
        "raw_signed_payload_export_allowed",
        "raw_exchange_payload_export_allowed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P58_CONFIG_{key.upper()}_NOT_FALSE")
    if payload.get("environment") != _ALLOWED_ENVIRONMENT:
        blockers.append("P58_CONFIG_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") != _ALLOWED_VENUE:
        blockers.append("P58_CONFIG_VENUE_INVALID")
    if payload.get("symbol") != _ALLOWED_SYMBOL:
        blockers.append("P58_CONFIG_SYMBOL_INVALID")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("P58_CONFIG_MAX_ORDER_COUNT_NOT_ONE")
    if payload.get("request_signing_boundary") != "external_runtime_process_memory_only":
        blockers.append("P58_CONFIG_SIGNING_BOUNDARY_INVALID")
    if payload.get("secret_binding_mode") != "metadata_reference_only_in_review_package":
        blockers.append("P58_CONFIG_SECRET_BINDING_MODE_INVALID")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "config_valid": not blockers,
        "config_block_reasons": sorted(dict.fromkeys(blockers)),
        "external_runtime_runner_enabled": payload.get(
            "external_runtime_runner_enabled"
        )
        is True,
        "real_evidence_acquisition_enabled": payload.get(
            "real_evidence_acquisition_enabled"
        )
        is True,
    }
    validation["p58_config_validation_sha256"] = sha256_json(validation)
    return validation


def validate_external_runtime_adapter_manifest(
    manifest: Mapping[str, Any] | ExternalRuntimeAdapterManifest | None,
    *,
    self_test: bool,
) -> dict[str, Any]:
    payload = (
        manifest.to_dict()
        if isinstance(manifest, ExternalRuntimeAdapterManifest)
        else dict(manifest or {})
    )
    blockers: list[str] = []
    if not _verify_embedded_hash(
        payload, "p58_external_runtime_adapter_manifest_sha256"
    ):
        blockers.append("P58_ADAPTER_MANIFEST_EMBEDDED_SHA256_INVALID")
    if payload.get("environment") != _ALLOWED_ENVIRONMENT:
        blockers.append("P58_ADAPTER_MANIFEST_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") != _ALLOWED_VENUE:
        blockers.append("P58_ADAPTER_MANIFEST_VENUE_INVALID")
    if payload.get("symbol") != _ALLOWED_SYMBOL:
        blockers.append("P58_ADAPTER_MANIFEST_SYMBOL_INVALID")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("P58_ADAPTER_MANIFEST_MAX_ORDER_COUNT_NOT_ONE")
    if payload.get("loaded_by_review_package") is not False:
        blockers.append("P58_ADAPTER_MANIFEST_LOADED_BY_REVIEW_PACKAGE")
    if payload.get("implementation_included_in_review_package") is not False:
        blockers.append("P58_ADAPTER_IMPLEMENTATION_INCLUDED_IN_REVIEW_PACKAGE")
    if payload.get("submit_enabled_by_default") is not False:
        blockers.append("P58_ADAPTER_SUBMIT_ENABLED_BY_DEFAULT")
    for key in (
        "testnet_endpoint_policy_enforced",
        "idempotency_supported",
        "duplicate_submit_lock_supported",
        "post_submit_relock_supported",
        "redacted_evidence_export_supported",
        "no_secret_logging_supported",
        "process_memory_only_signing_supported",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P58_ADAPTER_MANIFEST_{key.upper()}_NOT_TRUE")
    if not _is_sha256_hex(payload.get("adapter_package_sha256")):
        blockers.append("P58_ADAPTER_PACKAGE_SHA256_INVALID")
    if self_test:
        if payload.get("fixture_only") is not True:
            blockers.append("P58_SELF_TEST_MANIFEST_FIXTURE_ONLY_NOT_TRUE")
        if payload.get("real_endpoint_adapter") is not False:
            blockers.append("P58_SELF_TEST_MANIFEST_REAL_ENDPOINT_ADAPTER_NOT_FALSE")
        if payload.get("network_call_capable_in_external_runtime") is not False:
            blockers.append("P58_SELF_TEST_MANIFEST_NETWORK_CAPABLE")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "manifest_valid": not blockers,
        "manifest_block_reasons": sorted(dict.fromkeys(blockers)),
        "self_test": self_test,
        "real_endpoint_adapter": payload.get("real_endpoint_adapter") is True,
        "implementation_included_in_review_package": payload.get(
            "implementation_included_in_review_package"
        )
        is True,
    }
    validation["p58_adapter_manifest_validation_sha256"] = sha256_json(validation)
    return validation


def validate_p58_operator_approval(
    approval: Mapping[str, Any] | P58OperatorEvidenceAcquisitionApproval | None,
) -> dict[str, Any]:
    payload = (
        approval.to_dict()
        if isinstance(approval, P58OperatorEvidenceAcquisitionApproval)
        else dict(approval or {})
    )
    blockers: list[str] = []
    if not _verify_embedded_hash(
        payload, "p58_operator_evidence_acquisition_approval_sha256"
    ):
        blockers.append("P58_OPERATOR_APPROVAL_EMBEDDED_SHA256_INVALID")
    if payload.get("approval_mode") != "no_network_self_test_only":
        blockers.append("P58_OPERATOR_APPROVAL_MODE_INVALID")
    if payload.get("approval_phrase") != _SELF_TEST_APPROVAL_PHRASE:
        blockers.append("P58_OPERATOR_APPROVAL_PHRASE_INVALID")
    for key in (
        "approved_p6_preflight_sha256",
        "approved_p48_connector_sha256",
        "approved_p49_handoff_sha256",
        "approved_adapter_manifest_sha256",
        "approved_order_intent_sha256",
        "one_time_action_nonce_sha256",
    ):
        if not _is_sha256_hex(payload.get(key)):
            blockers.append(f"P58_OPERATOR_APPROVAL_{key.upper()}_INVALID")
    for key in (
        "real_evidence_acquisition_approved",
        "runtime_network_call_allowed",
        "runtime_authority_granted",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P58_OPERATOR_APPROVAL_{key.upper()}_NOT_FALSE")
    if payload.get("review_only") is not True:
        blockers.append("P58_OPERATOR_APPROVAL_REVIEW_ONLY_NOT_TRUE")
    blockers.extend(_walk_forbidden(payload))
    validation = {
        "approval_valid": not blockers,
        "approval_block_reasons": sorted(dict.fromkeys(blockers)),
        "real_evidence_acquisition_approved": payload.get(
            "real_evidence_acquisition_approved"
        )
        is True,
        "runtime_network_call_allowed": payload.get(
            "runtime_network_call_allowed"
        )
        is True,
    }
    validation["p58_operator_approval_validation_sha256"] = sha256_json(validation)
    return validation


def _valid_p58_source_fixture(
    *, status: str, hash_key: str
) -> dict[str, Any]:
    payload = {
        "status": status,
        "blocked": False,
        "review_only": True,
        "actual_order_submission_performed": False,
        "order_endpoint_called": False,
        "http_request_sent": False,
        "signature_created": False,
        "secret_value_accessed": False,
    }
    payload[hash_key] = sha256_json(payload)
    return payload


def build_valid_p58_self_test_request(
    *, cfg: AppConfig | None = None
) -> P58EvidenceAcquisitionRequest:
    del cfg
    p6 = _valid_p58_source_fixture(
        status="P6_EXTERNAL_RUNTIME_PREFLIGHT_READY_REVIEW_ONLY_NO_SUBMIT",
        hash_key="p6_external_runtime_preflight_report_sha256",
    )
    p48 = _valid_p58_source_fixture(
        status="P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_READY_REVIEW_ONLY_NO_SUBMIT",
        hash_key="p48_local_runtime_adapter_connector_sha256",
    )
    p49 = _valid_p58_source_fixture(
        status="P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_READY_REVIEW_ONLY_NO_SUBMIT",
        hash_key="p49_external_runtime_evidence_handoff_sha256",
    )
    adapter = P58NoNetworkFixtureAdapter()
    manifest = ExternalRuntimeAdapterManifest(
        adapter_id=adapter.adapter_id,
        adapter_version=adapter.adapter_version,
        adapter_module_ref="P58_REVIEW_PACKAGE_NO_NETWORK_FIXTURE_ADAPTER_ONLY",
        adapter_package_sha256=sha256_json(
            {
                "adapter_id": adapter.adapter_id,
                "adapter_version": adapter.adapter_version,
                "fixture_only": True,
                "network_call_capable": False,
            }
        ),
        fixture_only=True,
        real_endpoint_adapter=False,
        network_call_capable_in_external_runtime=False,
    ).to_dict()
    order_intent = {
        "artifact_type": "p58_no_network_self_test_order_intent_metadata",
        "environment": _ALLOWED_ENVIRONMENT,
        "venue": _ALLOWED_VENUE,
        "symbol": _ALLOWED_SYMBOL,
        "side": "BUY",
        "order_type": "MARKET",
        "quantity_mode": "NOTIONAL_METADATA_ONLY",
        "notional_usdt": "LOW_NOTIONAL_SELF_TEST_METADATA_ONLY",
        "client_order_id": "P58_FIXTURE_CLIENT_ORDER_ID_NOT_REAL",
        "fixture_only": True,
        "execute_real_submit_now": False,
        "runtime_authority_granted": False,
    }
    order_intent_sha = sha256_json(order_intent)
    nonce = sha256_json({"scope": _ALLOWED_SELF_TEST_SCOPE, "order": order_intent_sha})
    approval = P58OperatorEvidenceAcquisitionApproval(
        approved_p6_preflight_sha256=str(
            p6.get("p6_external_runtime_preflight_report_sha256") or "0" * 64
        ),
        approved_p48_connector_sha256=str(
            p48.get("p48_local_runtime_adapter_connector_sha256") or "0" * 64
        ),
        approved_p49_handoff_sha256=str(
            p49.get("p49_external_runtime_evidence_handoff_sha256") or "0" * 64
        ),
        approved_adapter_manifest_sha256=str(
            manifest["p58_external_runtime_adapter_manifest_sha256"]
        ),
        approved_order_intent_sha256=order_intent_sha,
        one_time_action_nonce_sha256=nonce,
    ).to_dict()
    return P58EvidenceAcquisitionRequest(
        operation_scope=_ALLOWED_SELF_TEST_SCOPE,
        evidence_origin=_SELF_TEST_EVIDENCE_ORIGIN,
        p6_preflight_report=p6,
        p48_connector_report=p48,
        p49_handoff_report=p49,
        adapter_manifest=manifest,
        operator_approval=approval,
        order_intent_metadata=order_intent,
        secret_reference_id="P58_METADATA_ONLY_TESTNET_SECRET_REFERENCE_SELF_TEST",
        key_fingerprint_sha256=sha256_json(
            {"metadata_only_key_fingerprint": "P58_SELF_TEST_NOT_A_REAL_KEY"}
        ),
        idempotency_key=sha256_json(
            {"p58_self_test_idempotency": order_intent_sha}
        ),
        hot_path_preorder_risk_gate_id="p58_self_test_hot_path_risk_gate",
        hot_path_preorder_risk_gate_sha256=sha256_json(
            {
                "risk_gate_id": "p58_self_test_hot_path_risk_gate",
                "result": "PASS_SELF_TEST_METADATA_ONLY",
                "fixture_only": True,
            }
        ),
    )


def run_p58_no_network_evidence_acquisition_self_test(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    request = build_valid_p58_self_test_request(cfg=cfg)
    adapter = P58NoNetworkFixtureAdapter()
    runner = ExternalRuntimeEvidenceAcquisitionRunner()
    with tempfile.TemporaryDirectory(prefix="cas_p58_evidence_acquisition_") as tmp:
        output = Path(tmp) / "redacted_evidence"
        result = runner.execute_no_network_self_test(
            request, adapter, output_dir=output
        )
        files = sorted(path.name for path in output.glob("*.json"))
        all_files_exist = len(files) == 5
        manifest = read_json(
            output / "p58_redacted_evidence_export_manifest_NO_NETWORK_SELF_TEST.json",
            default={},
        )
        manifest_valid = isinstance(manifest, Mapping) and _verify_embedded_hash(
            manifest, "p58_redacted_evidence_export_manifest_sha256"
        )
        output_dir_existed_during_test = output.exists()
    output_dir_deleted_after_test = not output.exists()

    real_scope_blocked = False
    try:
        runner.execute_real_evidence_acquisition(
            replace(
                request,
                operation_scope=_REAL_ACQUISITION_SCOPE,
                evidence_origin=_REAL_EVIDENCE_ORIGIN,
                self_test_only=False,
                real_evidence_acquisition_requested=True,
            ),
            adapter,
            output_dir="P58_REAL_OUTPUT_DISABLED",
        )
    except ExternalRuntimeEvidenceAcquisitionDisabledError:
        real_scope_blocked = True

    passed = bool(
        result.get("runner_code_path_exercised")
        and result.get("adapter_contract_exercised")
        and result.get("redacted_exporter_code_path_exercised")
        and result.get("no_secret_scan_passed")
        and result.get("real_signed_testnet_evidence") is False
        and result.get("p7_import_eligible") is False
        and all_files_exist
        and manifest_valid
        and output_dir_existed_during_test
        and output_dir_deleted_after_test
        and real_scope_blocked
    )
    report = {
        "artifact_type": "p58_no_network_evidence_acquisition_self_test_report",
        "p58_version": P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION,
        "self_test_passed": passed,
        "runner_code_path_exercised": result.get("runner_code_path_exercised")
        is True,
        "adapter_contract_exercised": result.get("adapter_contract_exercised")
        is True,
        "redacted_exporter_code_path_exercised": result.get(
            "redacted_exporter_code_path_exercised"
        )
        is True,
        "no_network_adapter_used": True,
        "exported_file_count": len(files),
        "exported_files": files,
        "all_expected_files_exist": all_files_exist,
        "manifest_hash_valid": manifest_valid,
        "no_secret_scan_passed": result.get("no_secret_scan_passed") is True,
        "ephemeral_output_directory_used": True,
        "ephemeral_output_directory_deleted_after_test": output_dir_deleted_after_test,
        "real_evidence_acquisition_scope_blocked": real_scope_blocked,
        "real_signed_testnet_evidence_present": False,
        "p7_import_eligible": False,
        "actual_p7_import_ready": False,
        **_execution_false_payload(),
    }
    report["p58_no_network_evidence_acquisition_self_test_report_sha256"] = (
        sha256_json(report)
    )
    return report


def build_p58_negative_fixture_results(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    valid = build_valid_p58_self_test_request(cfg=cfg)
    adapter = P58NoNetworkFixtureAdapter()
    cases: dict[str, tuple[P58EvidenceAcquisitionRequest, ExternalRuntimeEvidenceAdapter, ExternalRuntimeEvidenceAcquisitionConfig]] = {}

    cases["runner_enablement_attempt"] = (
        valid,
        adapter,
        replace(
            ExternalRuntimeEvidenceAcquisitionConfig(),
            external_runtime_runner_enabled=True,
        ),
    )
    cases["real_acquisition_enablement_attempt"] = (
        valid,
        adapter,
        replace(
            ExternalRuntimeEvidenceAcquisitionConfig(),
            real_evidence_acquisition_enabled=True,
        ),
    )

    mainnet = deepcopy(valid.canonical_payload())
    mainnet["adapter_manifest"]["environment"] = "mainnet"
    cases["mainnet_manifest"] = (
        P58EvidenceAcquisitionRequest(**mainnet),
        adapter,
        ExternalRuntimeEvidenceAcquisitionConfig(),
    )

    wrong_symbol = deepcopy(valid.canonical_payload())
    wrong_symbol["adapter_manifest"]["symbol"] = "ETHUSDT"
    cases["wrong_symbol_manifest"] = (
        P58EvidenceAcquisitionRequest(**wrong_symbol),
        adapter,
        ExternalRuntimeEvidenceAcquisitionConfig(),
    )

    submit_default = deepcopy(valid.canonical_payload())
    submit_default["adapter_manifest"]["submit_enabled_by_default"] = True
    cases["submit_enabled_by_default"] = (
        P58EvidenceAcquisitionRequest(**submit_default),
        adapter,
        ExternalRuntimeEvidenceAcquisitionConfig(),
    )

    loaded_review = deepcopy(valid.canonical_payload())
    loaded_review["adapter_manifest"]["loaded_by_review_package"] = True
    cases["real_adapter_loaded_by_review_package"] = (
        P58EvidenceAcquisitionRequest(**loaded_review),
        adapter,
        ExternalRuntimeEvidenceAcquisitionConfig(),
    )

    raw_secret = deepcopy(valid.canonical_payload())
    raw_secret["order_intent_metadata"]["api_secret_value"] = "FORBIDDEN"
    cases["raw_secret_field"] = (
        P58EvidenceAcquisitionRequest(**raw_secret),
        adapter,
        ExternalRuntimeEvidenceAcquisitionConfig(),
    )

    approval_network = deepcopy(valid.canonical_payload())
    approval_network["operator_approval"]["runtime_network_call_allowed"] = True
    cases["operator_network_allowance_attempt"] = (
        P58EvidenceAcquisitionRequest(**approval_network),
        adapter,
        ExternalRuntimeEvidenceAcquisitionConfig(),
    )

    real_request = replace(
        valid,
        operation_scope=_REAL_ACQUISITION_SCOPE,
        evidence_origin=_REAL_EVIDENCE_ORIGIN,
        self_test_only=False,
        real_evidence_acquisition_requested=True,
    )
    cases["real_acquisition_scope_attempt"] = (
        real_request,
        adapter,
        ExternalRuntimeEvidenceAcquisitionConfig(),
    )

    class UnsafeNetworkFixtureAdapter(P58NoNetworkFixtureAdapter):
        network_call_capable = True

    cases["network_capable_fixture_adapter"] = (
        valid,
        UnsafeNetworkFixtureAdapter(),
        ExternalRuntimeEvidenceAcquisitionConfig(),
    )

    results: dict[str, Any] = {}
    for name, (request, case_adapter, config) in cases.items():
        blocked = False
        reasons: list[str] = []
        runner = ExternalRuntimeEvidenceAcquisitionRunner(config=config)
        try:
            validation = runner.validate_request(request, case_adapter)
            if not validation["request_valid"]:
                blocked = True
                reasons = list(validation["request_block_reasons"])
            else:
                with tempfile.TemporaryDirectory(prefix=f"cas_p58_neg_{name}_") as tmp:
                    runner.execute_no_network_self_test(
                        request, case_adapter, output_dir=Path(tmp) / "out"
                    )
        except ExternalRuntimeEvidenceAcquisitionError as exc:
            blocked = True
            reasons = [str(exc)]
        results[name] = {
            "fixture_name": name,
            "blocked_fail_closed": blocked,
            "block_reasons": reasons,
        }

    payload = {
        "artifact_type": "p58_external_runtime_evidence_acquisition_negative_fixture_results",
        "all_negative_fixtures_blocked_fail_closed": all(
            item["blocked_fail_closed"] for item in results.values()
        ),
        "fixture_results": results,
        "real_signed_testnet_evidence_present": False,
        "actual_p7_import_ready": False,
        **_execution_false_payload(),
    }
    payload["p58_negative_fixture_results_sha256"] = sha256_json(payload)
    return payload


def build_p58_external_runtime_evidence_acquisition_report(
    *,
    cfg: AppConfig | None = None,
    self_test_report: Mapping[str, Any] | None = None,
    negative_fixture_results: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    p57 = _read_latest_json(cfg, "p57_transactional_p7_importer_integration_report.json")
    p6 = _read_latest_json(cfg, "p6_external_runtime_preflight_report.json")
    p48 = _read_latest_json(cfg, "p48_local_runtime_adapter_connector_report.json")
    p49 = _read_latest_json(cfg, "p49_external_runtime_evidence_handoff_report.json")
    self_test = dict(
        self_test_report or run_p58_no_network_evidence_acquisition_self_test(cfg=cfg)
    )
    negatives = dict(
        negative_fixture_results or build_p58_negative_fixture_results(cfg=cfg)
    )
    config = ExternalRuntimeEvidenceAcquisitionConfig().to_dict()
    config_validation = validate_p58_config(config)
    blockers: list[str] = []

    source_requirements = (
        (
            p57,
            "P57_TRANSACTIONAL_P7_IMPORTER_INTEGRATION_VALIDATED_REVIEW_ONLY_IMPORTER_DISABLED",
            "P58_P57",
        ),
        (
            p6,
            "P6_EXTERNAL_RUNTIME_PREFLIGHT_READY_REVIEW_ONLY_NO_SUBMIT",
            "P58_P6",
        ),
        (
            p48,
            "P48_LOCAL_RUNTIME_ADAPTER_CONNECTOR_READY_REVIEW_ONLY_NO_SUBMIT",
            "P58_P48",
        ),
        (
            p49,
            "P49_EXTERNAL_RUNTIME_EVIDENCE_HANDOFF_READY_REVIEW_ONLY_NO_SUBMIT",
            "P58_P49",
        ),
    )
    for payload, expected, prefix in source_requirements:
        if not payload:
            blockers.append(f"{prefix}_REPORT_MISSING")
        elif payload.get("status") != expected:
            blockers.append(f"{prefix}_STATUS_INVALID")
        elif payload.get("blocked") is True:
            blockers.append(f"{prefix}_BLOCKED")
    blockers.extend(config_validation["config_block_reasons"])
    if self_test.get("self_test_passed") is not True:
        blockers.append("P58_SELF_TEST_FAILED")
    if self_test.get("real_evidence_acquisition_scope_blocked") is not True:
        blockers.append("P58_REAL_ACQUISITION_SCOPE_NOT_BLOCKED")
    if negatives.get("all_negative_fixtures_blocked_fail_closed") is not True:
        blockers.append("P58_NEGATIVE_FIXTURE_FAILURE")
    blockers.extend(_walk_forbidden(self_test))

    blocked = bool(blockers)
    status = (
        STATUS_BLOCKED_FAIL_CLOSED
        if blocked
        else STATUS_VALIDATED_REVIEW_ONLY_RUNNER_DISABLED
    )
    created_at = utc_now_canonical()
    report = {
        "artifact_type": "p58_external_runtime_signed_testnet_evidence_acquisition_report",
        "p58_version": P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION,
        "status": status,
        "blocked": blocked,
        "fail_closed": blocked,
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "review_only": True,
        "runtime_authority_source": False,
        "external_runtime_runner_implemented": True,
        "external_runtime_adapter_protocol_implemented": True,
        "redacted_evidence_exporter_implemented": True,
        "real_adapter_implementation_included_in_review_package": False,
        "real_endpoint_network_client_implemented_in_review_package": False,
        "no_network_self_test_path_validated": self_test.get("self_test_passed")
        is True,
        "runner_adapter_exporter_code_path_exercised": bool(
            self_test.get("runner_code_path_exercised")
            and self_test.get("adapter_contract_exercised")
            and self_test.get("redacted_exporter_code_path_exercised")
        ),
        "redacted_evidence_artifact_set_exported_in_ephemeral_self_test": True,
        "no_secret_scan_passed": self_test.get("no_secret_scan_passed") is True,
        "real_evidence_acquisition_scope_blocked": self_test.get(
            "real_evidence_acquisition_scope_blocked"
        )
        is True,
        "real_signed_testnet_evidence_present": False,
        "real_signed_testnet_evidence_acquisition_completed": False,
        "actual_p7_import_ready": False,
        "next_progress_requires_external_runtime_adapter_package": True,
        "next_progress_requires_metadata_only_secret_binding_at_operator_runtime": True,
        "next_progress_requires_separate_explicit_operator_submit_approval": True,
        "next_progress_requires_single_real_signed_testnet_order": True,
        "next_progress_requires_real_redacted_evidence_bundle": True,
        "no_additional_p7_review_wrapper_recommended": True,
        "source_p57_report_id": p57.get(
            "p57_transactional_p7_importer_integration_id"
        ),
        "source_p57_report_sha256": p57.get(
            "p57_transactional_p7_importer_integration_sha256"
        ),
        "source_p6_preflight_sha256": p6.get(
            "p6_external_runtime_preflight_report_sha256"
        ),
        "source_p48_connector_sha256": p48.get(
            "p48_local_runtime_adapter_connector_sha256"
        ),
        "source_p49_handoff_sha256": p49.get(
            "p49_external_runtime_evidence_handoff_sha256"
        ),
        "config": config,
        "config_validation": config_validation,
        "self_test_report": self_test,
        "negative_fixture_results": negatives,
        **_execution_false_payload(),
        "created_at_utc": created_at,
    }
    report["p58_external_runtime_evidence_acquisition_id"] = stable_id(
        "p58_external_runtime_evidence_acquisition", report, 24
    )
    report["p58_external_runtime_evidence_acquisition_sha256"] = sha256_json(
        report
    )
    return report


def persist_p58_external_runtime_evidence_acquisition(
    *, cfg: AppConfig | None = None
) -> dict[str, Any]:
    cfg = cfg or load_config()
    self_test = run_p58_no_network_evidence_acquisition_self_test(cfg=cfg)
    negatives = build_p58_negative_fixture_results(cfg=cfg)
    report = build_p58_external_runtime_evidence_acquisition_report(
        cfg=cfg,
        self_test_report=self_test,
        negative_fixture_results=negatives,
    )
    config = ExternalRuntimeEvidenceAcquisitionConfig().to_dict()
    adapter_manifest_template = ExternalRuntimeAdapterManifest().to_dict()

    operator_request_template = {
        "artifact_type": "p58_operator_real_signed_testnet_evidence_acquisition_request_TEMPLATE_DISABLED",
        "p58_version": P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION,
        "review_only": True,
        "external_runtime_only": True,
        "runner_enabled": False,
        "real_evidence_acquisition_enabled": False,
        "real_evidence_acquisition_approved": False,
        "runtime_network_call_allowed": False,
        "execute_real_submit_now": False,
        "environment": _ALLOWED_ENVIRONMENT,
        "venue": _ALLOWED_VENUE,
        "symbol": _ALLOWED_SYMBOL,
        "max_order_count": 1,
        "external_adapter_package_sha256": "EXTERNAL_ADAPTER_PACKAGE_SHA256_REQUIRED",
        "secret_reference_id": "OPERATOR_RUNTIME_METADATA_ONLY_SECRET_REFERENCE_REQUIRED",
        "key_fingerprint_sha256": "KEY_FINGERPRINT_SHA256_REQUIRED",
        "p6_preflight_sha256": "P6_PREFLIGHT_SHA256_REQUIRED",
        "p48_connector_sha256": "P48_CONNECTOR_SHA256_REQUIRED",
        "p49_handoff_sha256": "P49_HANDOFF_SHA256_REQUIRED",
        "hot_path_preorder_risk_gate_id": "FRESH_HOT_PATH_RISK_GATE_ID_REQUIRED",
        "hot_path_preorder_risk_gate_sha256": "FRESH_HOT_PATH_RISK_GATE_SHA256_REQUIRED",
        "idempotency_key": "IDEMPOTENCY_KEY_REQUIRED",
        "one_time_action_nonce_sha256": "FRESH_NONCE_SHA256_REQUIRED",
        "raw_secret_values_allowed": False,
        "raw_request_body_export_allowed": False,
        "raw_signed_payload_export_allowed": False,
        "raw_exchange_payload_export_allowed": False,
        "runtime_authority_source": False,
        **_execution_false_payload(),
    }
    operator_request_template[
        "p58_operator_real_evidence_acquisition_request_template_sha256"
    ] = sha256_json(operator_request_template)

    export_manifest_template = {
        "artifact_type": "p58_redacted_evidence_export_manifest_TEMPLATE_NO_EVIDENCE",
        "p58_version": P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_VERSION,
        "review_only": True,
        "real_signed_testnet_evidence_present": False,
        "p7_import_eligible": False,
        "required_artifacts": [
            "redacted_submit_response_bundle.json",
            "external_runtime_execution_transcript.json",
            "no_secret_log_scan_report.json",
            "status_polling_evidence.json",
            "cancel_boundary_evidence.json",
            "signed_testnet_reconciliation_evidence.json",
            "signed_testnet_session_close_evidence.json",
            "p7_intake_bridge_candidate.json",
        ],
        "raw_secret_values_included": False,
        "raw_request_body_included": False,
        "raw_signed_payload_included": False,
        "raw_exchange_payload_included": False,
        "runtime_authority_source": False,
        **_execution_false_payload(),
    }
    export_manifest_template[
        "p58_redacted_evidence_export_manifest_template_sha256"
    ] = sha256_json(export_manifest_template)

    summary = {
        "artifact_type": "p58_external_runtime_evidence_acquisition_summary",
        "status": report["status"],
        "blocked": report["blocked"],
        "review_only": True,
        "runner_adapter_exporter_implemented": True,
        "no_network_self_test_passed": report[
            "no_network_self_test_path_validated"
        ],
        "real_adapter_implementation_included_in_review_package": False,
        "real_signed_testnet_evidence_present": False,
        "actual_p7_import_ready": False,
        "external_runtime_runner_enabled": False,
        "real_evidence_acquisition_enabled": False,
        "created_at_utc": report["created_at_utc"],
    }
    summary["p58_summary_sha256"] = sha256_json(summary)

    registry_record = {
        "artifact_type": "p58_external_runtime_evidence_acquisition_registry_record",
        "p58_external_runtime_evidence_acquisition_id": report[
            "p58_external_runtime_evidence_acquisition_id"
        ],
        "p58_external_runtime_evidence_acquisition_sha256": report[
            "p58_external_runtime_evidence_acquisition_sha256"
        ],
        "status": report["status"],
        "review_only": True,
        "no_network_self_test_passed": report[
            "no_network_self_test_path_validated"
        ],
        "real_signed_testnet_evidence_present": False,
        "actual_p7_import_ready": False,
        "external_runtime_runner_enabled": False,
        "created_at_utc": report["created_at_utc"],
    }
    registry_record["p58_registry_record_sha256"] = sha256_json(registry_record)
    append_registry_record(
        registry_path(
            cfg, P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_REGISTRY_NAME
        ),
        registry_record,
        registry_name=P58_EXTERNAL_RUNTIME_EVIDENCE_ACQUISITION_REGISTRY_NAME,
    )

    latest = _latest_dir(cfg)
    outputs = {
        "p58_external_runtime_evidence_acquisition_report.json": report,
        "p58_external_runtime_evidence_acquisition_config.json": config,
        "p58_no_network_evidence_acquisition_self_test_report.json": self_test,
        "p58_external_runtime_evidence_acquisition_negative_fixture_results.json": negatives,
        "p58_external_runtime_adapter_manifest_TEMPLATE_EXTERNAL_ONLY.json": adapter_manifest_template,
        "p58_operator_real_signed_testnet_evidence_acquisition_request_TEMPLATE_DISABLED.json": operator_request_template,
        "p58_redacted_evidence_export_manifest_TEMPLATE_NO_EVIDENCE.json": export_manifest_template,
        "p58_external_runtime_evidence_acquisition_summary.json": summary,
        "p58_external_runtime_evidence_acquisition_registry_record.json": registry_record,
    }
    for filename, payload in outputs.items():
        atomic_write_json(latest / filename, payload)
    return report
