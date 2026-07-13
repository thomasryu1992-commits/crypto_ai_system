from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from crypto_ai_system.utils.audit import is_canonical_utc_timestamp, sha256_json, sha256_text, utc_now_canonical

P67_VERSION = "p67_real_order_test_redacted_evidence_receipt_v1"
STATUS_P67_READY = "P67_REAL_ORDER_TEST_REDACTED_EVIDENCE_RECEIPT_READY_REVIEW_ONLY_NO_SUBMIT"
STATUS_P67_ACCEPTED = "P67_REAL_ORDER_TEST_REDACTED_EVIDENCE_RECEIPT_ACCEPTED_REVIEW_ONLY_NO_SUBMIT"
STATUS_P67_BLOCKED = "P67_REAL_ORDER_TEST_REDACTED_EVIDENCE_RECEIPT_BLOCKED_FAIL_CLOSED"
P66_SOURCE_STATUS = "P66_OPERATOR_ACTIVATION_INTAKE_FOR_REAL_ORDER_TEST_READY_REVIEW_ONLY_NO_CALL"
P66_ACCEPTED_STATUS = "P66_OPERATOR_ACTIVATION_INTAKE_FOR_REAL_ORDER_TEST_ACCEPTED_REVIEW_ONLY_NO_CALL"
P65_APPROVED_ORDER_TEST_SCOPE = "p65_approved_testnet_order_test_only"
REAL_EVIDENCE_ORIGIN = "real_binance_futures_testnet_order_test_external_runtime"
FIXTURE_EVIDENCE_ORIGIN = "p67_no_network_redacted_receipt_fixture"
ALLOWED_VENUE = "binance_futures_testnet"
ALLOWED_BASE_URL = "https://demo-fapi.binance.com"
ALLOWED_METHOD = "POST"
ALLOWED_PATH = "/fapi/v1/order/test"
ALLOWED_SYMBOL = "BTCUSDT"
MAX_RECEIPT_DELAY_SECONDS = 900
P67_REGISTRY_NAME = "p67_real_order_test_redacted_evidence_receipt_registry"

FORBIDDEN_KEY_TOKENS = (
    "api_key_value",
    "api_secret_value",
    "secret_value",
    "private_key",
    "passphrase",
    "raw_secret",
    "credential_value",
    "secret_file_contents",
    "raw_signed_payload",
    "raw_request_body",
    "raw_response_body",
    "raw_exchange_payload",
    "unredacted_exchange_response",
    "authorization_header",
    "x-mbx-apikey",
)
FORBIDDEN_VALUE_TOKENS = (
    "-----BEGIN PRIVATE KEY-----",
    "api_secret=",
    "api_key=",
    "x-mbx-apikey:",
    "authorization: bearer ",
)


def read_json(path: str | Path, default: Any = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True, default=str)
            handle.write("\n")
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def append_jsonl(path: str | Path, row: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _is_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _is_nonzero_sha256(value: Any) -> bool:
    return _is_sha256(value) and str(value).lower() != "0" * 64


def _without_hash(payload: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != hash_field}


def _embedded_hash_valid(payload: Mapping[str, Any], hash_field: str) -> bool:
    actual = str(payload.get(hash_field, ""))
    return _is_sha256(actual) and actual == sha256_json(_without_hash(payload, hash_field))


def _walk_forbidden(obj: Any, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            lower = str(key).lower()
            if not isinstance(value, bool) and any(token in lower for token in FORBIDDEN_KEY_TOKENS):
                blockers.append(f"P67_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden(value, child))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, f"{prefix}[{idx}]"))
    elif isinstance(obj, str):
        lower = obj.lower()
        if any(token.lower() in lower for token in FORBIDDEN_VALUE_TOKENS):
            blockers.append(f"P67_FORBIDDEN_SECRET_OR_RAW_VALUE:{prefix or '<root>'}")
    return blockers


def _parse_utc(value: Any) -> datetime | None:
    if not is_canonical_utc_timestamp(value):
        return None
    return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _canonical_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class P67RealOrderTestRedactedEvidenceReceipt:
    receipt_version: str = P67_VERSION
    artifact_type: str = "p67_real_order_test_redacted_evidence_receipt"
    evidence_origin: str = FIXTURE_EVIDENCE_ORIGIN
    fixture_only: bool = True
    actual_external_runtime_execution: bool = False
    operator_request_id: str = "P67_FIXTURE_OPERATOR_REQUEST"
    p66_operator_activation_intake_sha256: str = "0" * 64
    p66_activation_validation_receipt_sha256: str = "0" * 64
    credential_reference_id: str = "metadata-only:operator-os-provider:binance-futures-testnet"
    key_fingerprint_sha256: str = "c" * 64
    one_shot_nonce_sha256: str = "d" * 64
    one_shot_nonce_consumed_by_external_sender: bool = True
    venue: str = ALLOWED_VENUE
    base_url: str = ALLOWED_BASE_URL
    method: str = ALLOWED_METHOD
    path: str = ALLOWED_PATH
    symbol: str = ALLOWED_SYMBOL
    max_call_count: int = 1
    request_descriptor_sha256: str = "e" * 64
    canonical_query_sha256: str = "f" * 64
    redacted_response_sha256: str = "a" * 64
    no_secret_scan_report_sha256: str = "b" * 64
    http_status_code: int = 200
    exchange_response_class: str = "empty_json_object"
    external_sender_executable_used: bool = True
    http_request_sent: bool = True
    signature_created_in_external_process: bool = True
    order_test_endpoint_called: bool = True
    real_order_submit_endpoint_called: bool = False
    order_created: bool = False
    exchange_order_id_present: bool = False
    actual_order_submission_performed: bool = False
    raw_request_persisted: bool = False
    raw_response_persisted: bool = False
    secret_value_exposed_to_crypto_ai_system: bool = False
    secret_value_logged: bool = False
    redacted_evidence_only: bool = True
    testnet_only: bool = True
    order_test_only: bool = True
    one_request_only: bool = True
    runtime_authority_granted: bool = False
    live_execution_allowed: bool = False
    auto_promotion_allowed: bool = False
    executed_at_utc: str = "2026-07-12T04:00:00Z"
    received_at_utc: str = "2026-07-12T04:00:01Z"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p67_real_order_test_redacted_evidence_receipt_sha256"] = sha256_json(payload)
        return payload


def validate_p66_source_report(report: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(report or {})
    blockers = _walk_forbidden(payload)
    if payload.get("status") != P66_SOURCE_STATUS:
        blockers.append("P67_P66_SOURCE_STATUS_INVALID")
    if payload.get("review_only") is not True:
        blockers.append("P67_P66_SOURCE_REVIEW_ONLY_REQUIRED")
    if payload.get("p66_operator_activation_intake_validator_implemented") is not True:
        blockers.append("P67_P66_VALIDATOR_NOT_IMPLEMENTED")
    if payload.get("approved_fixture_validation_passed") is not True:
        blockers.append("P67_P66_FIXTURE_VALIDATION_NOT_PASSED")
    if payload.get("negative_fixtures_all_blocked") is not True:
        blockers.append("P67_P66_NEGATIVE_FIXTURES_NOT_BLOCKED")
    if not _embedded_hash_valid(payload, "p66_operator_activation_intake_for_real_order_test_sha256"):
        blockers.append("P67_P66_SOURCE_HASH_INVALID_OR_MISMATCH")
    for key in (
        "actual_operator_activation_received",
        "actual_operator_activation_accepted",
        "real_order_test_activation_enabled",
        "real_order_test_endpoint_call_enabled",
        "real_order_test_endpoint_call_performed",
        "sender_executable_enabled",
        "one_shot_nonce_consumed",
        "http_request_sent",
        "signature_created",
        "signed_request_created",
        "secret_value_accessed",
        "actual_order_submission_performed",
        "actual_testnet_order_submitted",
        "actual_live_order_submitted",
        "runtime_mutation_performed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P67_P66_SOURCE_EXPECTED_FALSE:{key}")
    return {
        "p66_source_valid": not blockers,
        "p66_source_block_reasons": sorted(dict.fromkeys(blockers)),
        "p66_source_sha256": payload.get("p66_operator_activation_intake_for_real_order_test_sha256"),
    }


def validate_p66_activation_chain(
    intake: Mapping[str, Any] | None,
    validation_receipt: Mapping[str, Any] | None,
    *,
    allow_fixture: bool,
) -> dict[str, Any]:
    intake_payload = dict(intake or {})
    receipt_payload = dict(validation_receipt or {})
    blockers = _walk_forbidden(intake_payload) + _walk_forbidden(receipt_payload)
    if not _embedded_hash_valid(intake_payload, "p66_operator_activation_intake_sha256"):
        blockers.append("P67_P66_INTAKE_HASH_INVALID_OR_MISMATCH")
    if not _embedded_hash_valid(receipt_payload, "p66_activation_validation_receipt_sha256"):
        blockers.append("P67_P66_VALIDATION_RECEIPT_HASH_INVALID_OR_MISMATCH")
    fixture = intake_payload.get("fixture_only") is True
    if fixture and not allow_fixture:
        blockers.append("P67_P66_FIXTURE_ACTIVATION_NOT_ALLOWED")
    if intake_payload.get("approval_granted") is not True:
        blockers.append("P67_P66_APPROVAL_REQUIRED")
    if intake_payload.get("actual_operator_supplied") is not True:
        blockers.append("P67_P66_ACTUAL_OPERATOR_SUPPLIED_REQUIRED")
    if intake_payload.get("execution_scope") != P65_APPROVED_ORDER_TEST_SCOPE:
        blockers.append("P67_P66_EXECUTION_SCOPE_INVALID")
    for key, expected in (
        ("venue", ALLOWED_VENUE),
        ("base_url", ALLOWED_BASE_URL),
        ("method", ALLOWED_METHOD),
        ("path", ALLOWED_PATH),
        ("symbol", ALLOWED_SYMBOL),
    ):
        if intake_payload.get(key) != expected:
            blockers.append(f"P67_P66_INTAKE_SCOPE_INVALID:{key}")
    if intake_payload.get("max_call_count") != 1:
        blockers.append("P67_P66_MAX_CALL_COUNT_MUST_BE_ONE")
    for key in ("testnet_only", "order_test_only", "one_request_only", "redacted_evidence_only", "process_memory_credentials_only"):
        if intake_payload.get(key) is not True:
            blockers.append(f"P67_P66_EXPECTED_TRUE:{key}")
    for key in ("real_order_submit_allowed", "status_polling_allowed", "cancel_allowed", "runtime_authority_granted", "live_execution_allowed", "auto_promotion_allowed"):
        if intake_payload.get(key) is not False:
            blockers.append(f"P67_P66_EXPECTED_FALSE:{key}")
    if not str(intake_payload.get("credential_reference_id", "")).startswith("metadata-only:"):
        blockers.append("P67_P66_METADATA_ONLY_CREDENTIAL_REFERENCE_REQUIRED")
    if not _is_nonzero_sha256(intake_payload.get("key_fingerprint_sha256")):
        blockers.append("P67_P66_KEY_FINGERPRINT_REQUIRED")
    if not _is_nonzero_sha256(intake_payload.get("one_shot_nonce_sha256")):
        blockers.append("P67_P66_NONCE_REQUIRED")
    if receipt_payload.get("status") != P66_ACCEPTED_STATUS:
        blockers.append("P67_P66_VALIDATION_RECEIPT_STATUS_INVALID")
    if receipt_payload.get("accepted") is not True or receipt_payload.get("blocked") is not False:
        blockers.append("P67_P66_VALIDATION_RECEIPT_NOT_ACCEPTED")
    if receipt_payload.get("operator_activation_intake_sha256") != intake_payload.get("p66_operator_activation_intake_sha256"):
        blockers.append("P67_P66_INTAKE_RECEIPT_HASH_CHAIN_MISMATCH")
    if receipt_payload.get("operator_request_id") != intake_payload.get("operator_request_id"):
        blockers.append("P67_P66_OPERATOR_REQUEST_ID_MISMATCH")
    if receipt_payload.get("key_fingerprint_sha256") != intake_payload.get("key_fingerprint_sha256"):
        blockers.append("P67_P66_KEY_FINGERPRINT_MISMATCH")
    if receipt_payload.get("one_shot_nonce_sha256") != intake_payload.get("one_shot_nonce_sha256"):
        blockers.append("P67_P66_NONCE_MISMATCH")
    fixture_receipt = receipt_payload.get("fixture_validation_only") is True
    if fixture_receipt != fixture:
        blockers.append("P67_P66_FIXTURE_MARKER_MISMATCH")
    if fixture_receipt and not allow_fixture:
        blockers.append("P67_P66_FIXTURE_VALIDATION_RECEIPT_NOT_ALLOWED")
    for key in (
        "one_shot_nonce_consumed_by_p66",
        "real_order_test_execution_enabled_by_p66",
        "real_order_test_execution_performed_by_p66",
        "sender_executable_enabled_by_p66",
        "http_request_sent_by_p66",
        "signature_created_by_p66",
        "secret_value_accessed_by_p66",
        "runtime_mutation_performed_by_p66",
        "actual_order_submission_performed_by_p66",
        "activation_intake_recorded_by_p66",
    ):
        if receipt_payload.get(key) is not False:
            blockers.append(f"P67_P66_RECEIPT_EXPECTED_FALSE:{key}")
    return {
        "p66_activation_chain_valid": not blockers,
        "p66_activation_chain_block_reasons": sorted(dict.fromkeys(blockers)),
        "fixture_only": fixture,
        "operator_request_id": intake_payload.get("operator_request_id"),
        "p66_operator_activation_intake_sha256": intake_payload.get("p66_operator_activation_intake_sha256"),
        "p66_activation_validation_receipt_sha256": receipt_payload.get("p66_activation_validation_receipt_sha256"),
    }


def build_p67_receipt_template(p66_report: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    p66_template = p66_report.get("operator_activation_intake_template") if isinstance(p66_report.get("operator_activation_intake_template"), Mapping) else {}
    receipt = P67RealOrderTestRedactedEvidenceReceipt(
        evidence_origin="FILL_REAL_EXTERNAL_RUNTIME_EVIDENCE_ORIGIN",
        fixture_only=False,
        actual_external_runtime_execution=False,
        operator_request_id="FILL_OPERATOR_REQUEST_ID",
        p66_operator_activation_intake_sha256="0" * 64,
        p66_activation_validation_receipt_sha256="0" * 64,
        credential_reference_id="FILL_METADATA_ONLY_CREDENTIAL_REFERENCE",
        key_fingerprint_sha256="0" * 64,
        one_shot_nonce_sha256="0" * 64,
        one_shot_nonce_consumed_by_external_sender=False,
        request_descriptor_sha256="0" * 64,
        canonical_query_sha256="0" * 64,
        redacted_response_sha256="0" * 64,
        no_secret_scan_report_sha256="0" * 64,
        http_status_code=0,
        exchange_response_class="FILL_REDACTED_RESPONSE_CLASS",
        external_sender_executable_used=False,
        http_request_sent=False,
        signature_created_in_external_process=False,
        order_test_endpoint_called=False,
        executed_at_utc=_canonical_utc(current),
        received_at_utc=_canonical_utc(current),
    ).to_dict()
    receipt["source_p66_report_sha256"] = p66_report.get("p66_operator_activation_intake_for_real_order_test_sha256")
    receipt["source_p66_template_sha256"] = p66_template.get("p66_operator_activation_intake_sha256")
    receipt["p67_real_order_test_redacted_evidence_receipt_sha256"] = sha256_json(
        _without_hash(receipt, "p67_real_order_test_redacted_evidence_receipt_sha256")
    )
    return receipt


def build_valid_p67_receipt_fixture(
    p66_intake: Mapping[str, Any],
    p66_validation_receipt: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    payload = P67RealOrderTestRedactedEvidenceReceipt(
        evidence_origin=FIXTURE_EVIDENCE_ORIGIN,
        fixture_only=True,
        actual_external_runtime_execution=False,
        operator_request_id=str(p66_intake.get("operator_request_id")),
        p66_operator_activation_intake_sha256=str(p66_intake.get("p66_operator_activation_intake_sha256")),
        p66_activation_validation_receipt_sha256=str(p66_validation_receipt.get("p66_activation_validation_receipt_sha256")),
        credential_reference_id=str(p66_intake.get("credential_reference_id")),
        key_fingerprint_sha256=str(p66_intake.get("key_fingerprint_sha256")),
        one_shot_nonce_sha256=str(p66_intake.get("one_shot_nonce_sha256")),
        one_shot_nonce_consumed_by_external_sender=True,
        request_descriptor_sha256="e" * 64,
        canonical_query_sha256="f" * 64,
        redacted_response_sha256="a" * 64,
        no_secret_scan_report_sha256="b" * 64,
        executed_at_utc=_canonical_utc(current),
        received_at_utc=_canonical_utc(current + timedelta(seconds=1)),
    ).to_dict()
    return payload


def validate_p67_redacted_evidence_receipt(
    receipt: Mapping[str, Any] | None,
    p66_intake: Mapping[str, Any] | None,
    p66_validation_receipt: Mapping[str, Any] | None,
    *,
    allow_fixture: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = dict(receipt or {})
    intake = dict(p66_intake or {})
    validation_receipt = dict(p66_validation_receipt or {})
    blockers = _walk_forbidden(payload)
    chain = validate_p66_activation_chain(intake, validation_receipt, allow_fixture=allow_fixture)
    blockers.extend(chain["p66_activation_chain_block_reasons"])
    if not _embedded_hash_valid(payload, "p67_real_order_test_redacted_evidence_receipt_sha256"):
        blockers.append("P67_RECEIPT_HASH_INVALID_OR_MISMATCH")
    fixture = payload.get("fixture_only") is True
    if fixture and not allow_fixture:
        blockers.append("P67_FIXTURE_RECEIPT_NOT_ALLOWED_FOR_ACTUAL_EVIDENCE")
    expected_origin = FIXTURE_EVIDENCE_ORIGIN if fixture else REAL_EVIDENCE_ORIGIN
    if payload.get("evidence_origin") != expected_origin:
        blockers.append("P67_EVIDENCE_ORIGIN_INVALID")
    if fixture:
        if payload.get("actual_external_runtime_execution") is not False:
            blockers.append("P67_FIXTURE_MUST_NOT_CLAIM_ACTUAL_EXECUTION")
    elif payload.get("actual_external_runtime_execution") is not True:
        blockers.append("P67_ACTUAL_EXTERNAL_RUNTIME_EXECUTION_REQUIRED")
    for key, expected in (
        ("venue", ALLOWED_VENUE),
        ("base_url", ALLOWED_BASE_URL),
        ("method", ALLOWED_METHOD),
        ("path", ALLOWED_PATH),
        ("symbol", ALLOWED_SYMBOL),
    ):
        if payload.get(key) != expected:
            blockers.append(f"P67_RECEIPT_SCOPE_INVALID:{key}")
    if payload.get("max_call_count") != 1:
        blockers.append("P67_MAX_CALL_COUNT_MUST_BE_ONE")
    for key in (
        "one_shot_nonce_consumed_by_external_sender",
        "external_sender_executable_used",
        "http_request_sent",
        "signature_created_in_external_process",
        "order_test_endpoint_called",
        "redacted_evidence_only",
        "testnet_only",
        "order_test_only",
        "one_request_only",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P67_EXPECTED_TRUE:{key}")
    for key in (
        "real_order_submit_endpoint_called",
        "order_created",
        "exchange_order_id_present",
        "actual_order_submission_performed",
        "raw_request_persisted",
        "raw_response_persisted",
        "secret_value_exposed_to_crypto_ai_system",
        "secret_value_logged",
        "runtime_authority_granted",
        "live_execution_allowed",
        "auto_promotion_allowed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P67_EXPECTED_FALSE:{key}")
    if payload.get("http_status_code") != 200:
        blockers.append("P67_HTTP_STATUS_NOT_200")
    if payload.get("exchange_response_class") != "empty_json_object":
        blockers.append("P67_SUCCESS_RESPONSE_CLASS_INVALID")
    for key in (
        "p66_operator_activation_intake_sha256",
        "p66_activation_validation_receipt_sha256",
        "key_fingerprint_sha256",
        "one_shot_nonce_sha256",
        "request_descriptor_sha256",
        "canonical_query_sha256",
        "redacted_response_sha256",
        "no_secret_scan_report_sha256",
    ):
        if not _is_nonzero_sha256(payload.get(key)):
            blockers.append(f"P67_REQUIRED_SHA256_INVALID:{key}")
    if payload.get("operator_request_id") != intake.get("operator_request_id"):
        blockers.append("P67_OPERATOR_REQUEST_ID_MISMATCH")
    if payload.get("p66_operator_activation_intake_sha256") != intake.get("p66_operator_activation_intake_sha256"):
        blockers.append("P67_P66_INTAKE_HASH_CHAIN_MISMATCH")
    if payload.get("p66_activation_validation_receipt_sha256") != validation_receipt.get("p66_activation_validation_receipt_sha256"):
        blockers.append("P67_P66_VALIDATION_RECEIPT_HASH_CHAIN_MISMATCH")
    if payload.get("credential_reference_id") != intake.get("credential_reference_id"):
        blockers.append("P67_CREDENTIAL_REFERENCE_MISMATCH")
    if payload.get("key_fingerprint_sha256") != intake.get("key_fingerprint_sha256"):
        blockers.append("P67_KEY_FINGERPRINT_MISMATCH")
    if payload.get("one_shot_nonce_sha256") != intake.get("one_shot_nonce_sha256"):
        blockers.append("P67_NONCE_MISMATCH")
    executed = _parse_utc(payload.get("executed_at_utc"))
    received = _parse_utc(payload.get("received_at_utc"))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    if executed is None:
        blockers.append("P67_EXECUTED_AT_INVALID")
    if received is None:
        blockers.append("P67_RECEIVED_AT_INVALID")
    if executed and received:
        if received < executed:
            blockers.append("P67_RECEIVED_BEFORE_EXECUTED")
        if (received - executed).total_seconds() > MAX_RECEIPT_DELAY_SECONDS:
            blockers.append("P67_RECEIPT_DELAY_EXCEEDED")
        if received > current + timedelta(seconds=5):
            blockers.append("P67_RECEIPT_FROM_FUTURE")
    blockers = sorted(dict.fromkeys(blockers))
    accepted = not blockers
    actual_accepted = accepted and not fixture
    return {
        "status": STATUS_P67_ACCEPTED if accepted else STATUS_P67_BLOCKED,
        "p67_redacted_evidence_receipt_valid": accepted,
        "p67_redacted_evidence_receipt_block_reasons": blockers,
        "fixture_only": fixture,
        "actual_real_order_test_evidence_accepted": actual_accepted,
        "order_test_dry_validation_proven": actual_accepted,
        "eligible_for_next_signed_testnet_submit_preflight": actual_accepted,
        "p50_external_evidence_import_eligible": False,
        "p7_post_submit_evidence_import_eligible": False,
        "signed_testnet_submit_evidence": False,
        "actual_order_submission_performed": False,
        "real_order_test_endpoint_call_performed_by_p67": False,
        "secret_value_accessed_by_p67": False,
    }


def build_p67_no_secret_scan_report(receipt: Mapping[str, Any]) -> dict[str, Any]:
    matches = _walk_forbidden(receipt)
    report = {
        "artifact_type": "p67_real_order_test_evidence_no_secret_scan_report",
        "scan_completed": True,
        "scan_passed": not matches,
        "match_count": len(matches),
        "matches": matches,
        "raw_secret_values_present": False if not matches else True,
        "raw_request_or_response_present": False if not matches else True,
        "review_only": True,
    }
    report["p67_no_secret_scan_report_sha256"] = sha256_json(report)
    return report


def build_p67_order_test_validation_bridge(
    receipt: Mapping[str, Any],
    validation: Mapping[str, Any],
    *,
    fixture_validation_only: bool,
) -> dict[str, Any]:
    actual_accepted = validation.get("actual_real_order_test_evidence_accepted") is True
    bridge = {
        "artifact_type": "p67_order_test_dry_validation_bridge",
        "status": STATUS_P67_ACCEPTED if validation.get("p67_redacted_evidence_receipt_valid") is True else STATUS_P67_BLOCKED,
        "review_only": True,
        "fixture_validation_only": fixture_validation_only,
        "receipt_sha256": receipt.get("p67_real_order_test_redacted_evidence_receipt_sha256"),
        "operator_request_id": receipt.get("operator_request_id"),
        "one_shot_nonce_sha256": receipt.get("one_shot_nonce_sha256"),
        "real_order_test_dry_validation_evidence_accepted": actual_accepted,
        "eligible_for_next_signed_testnet_submit_preflight": actual_accepted,
        "p58_real_submit_evidence_acquisition_eligible": False,
        "p50_external_evidence_import_eligible": False,
        "p7_post_submit_evidence_import_eligible": False,
        "signed_testnet_submit_evidence": False,
        "order_created": False,
        "actual_order_submission_performed": False,
        "reason_p50_p7_ineligible": "order_test_endpoint_validates_a_request_but_does_not_create_an_order_or_post_submit_evidence",
        "automatic_stage_promotion_allowed": False,
        "runtime_authority_granted": False,
        "live_execution_allowed": False,
    }
    bridge["p67_order_test_dry_validation_bridge_sha256"] = sha256_json(bridge)
    return bridge


def _fixture_activation_chain(p66_report: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    template = p66_report.get("operator_activation_intake_template") if isinstance(p66_report.get("operator_activation_intake_template"), Mapping) else {}
    receipt = p66_report.get("approved_fixture_receipt") if isinstance(p66_report.get("approved_fixture_receipt"), Mapping) else {}
    intake = dict(template)
    intake.update(
        {
            "operator_request_id": "p67-valid-operator-fixture",
            "approval_granted": True,
            "actual_operator_supplied": True,
            "fixture_only": True,
            "execution_scope": P65_APPROVED_ORDER_TEST_SCOPE,
            "credential_reference_id": "metadata-only:operator-os-provider:binance-futures-testnet",
            "key_fingerprint_sha256": "c" * 64,
            "one_shot_nonce_sha256": "d" * 64,
        }
    )
    intake.pop("p66_operator_activation_intake_sha256", None)
    intake["p66_operator_activation_intake_sha256"] = sha256_json(intake)
    validation_receipt = dict(receipt)
    validation_receipt.update(
        {
            "operator_request_id": intake["operator_request_id"],
            "operator_activation_intake_sha256": intake["p66_operator_activation_intake_sha256"],
            "key_fingerprint_sha256": intake["key_fingerprint_sha256"],
            "one_shot_nonce_sha256": intake["one_shot_nonce_sha256"],
            "fixture_validation_only": True,
        }
    )
    validation_receipt.pop("p66_activation_validation_receipt_sha256", None)
    validation_receipt["p66_activation_validation_receipt_sha256"] = sha256_json(validation_receipt)
    return intake, validation_receipt


def build_p67_negative_fixture_results(p66_report: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    intake, p66_receipt = _fixture_activation_chain(p66_report)
    base = build_valid_p67_receipt_fixture(intake, p66_receipt, now=current)
    cases: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], bool]] = []

    def mutated(name: str, **updates: Any) -> None:
        payload = dict(base)
        payload.update(updates)
        payload.pop("p67_real_order_test_redacted_evidence_receipt_sha256", None)
        payload["p67_real_order_test_redacted_evidence_receipt_sha256"] = sha256_json(payload)
        cases.append((name, payload, intake, p66_receipt, True))

    mutated("mainnet_url", base_url="https://fapi.binance.com")
    mutated("real_submit_path", path="/fapi/v1/order")
    mutated("wrong_symbol", symbol="ETHUSDT")
    mutated("order_created", order_created=True)
    mutated("real_submit_called", real_order_submit_endpoint_called=True)
    mutated("raw_response_persisted", raw_response_persisted=True)
    mutated("runtime_authority", runtime_authority_granted=True)
    mutated("nonce_mismatch", one_shot_nonce_sha256="1" * 64)
    mutated("receipt_delay", received_at_utc=_canonical_utc(current + timedelta(seconds=901)))
    secret_case = dict(base)
    secret_case["api_secret_value"] = "forbidden"
    secret_case.pop("p67_real_order_test_redacted_evidence_receipt_sha256", None)
    secret_case["p67_real_order_test_redacted_evidence_receipt_sha256"] = sha256_json(secret_case)
    cases.append(("raw_secret_field", secret_case, intake, p66_receipt, True))
    nonfixture = dict(base)
    nonfixture.update({"fixture_only": False, "evidence_origin": REAL_EVIDENCE_ORIGIN, "actual_external_runtime_execution": False})
    nonfixture.pop("p67_real_order_test_redacted_evidence_receipt_sha256", None)
    nonfixture["p67_real_order_test_redacted_evidence_receipt_sha256"] = sha256_json(nonfixture)
    cases.append(("actual_receipt_without_actual_execution", nonfixture, intake, p66_receipt, True))
    bad_p66_receipt = dict(p66_receipt)
    bad_p66_receipt["accepted"] = False
    bad_p66_receipt.pop("p66_activation_validation_receipt_sha256", None)
    bad_p66_receipt["p66_activation_validation_receipt_sha256"] = sha256_json(bad_p66_receipt)
    cases.append(("p66_receipt_not_accepted", base, intake, bad_p66_receipt, True))

    results = []
    for name, payload, case_intake, case_receipt, allow_fixture in cases:
        validation = validate_p67_redacted_evidence_receipt(
            payload, case_intake, case_receipt, allow_fixture=allow_fixture, now=current
        )
        results.append(
            {
                "case": name,
                "blocked": validation["p67_redacted_evidence_receipt_valid"] is False,
                "block_reasons": validation["p67_redacted_evidence_receipt_block_reasons"],
            }
        )
    report = {
        "artifact_type": "p67_real_order_test_redacted_evidence_receipt_negative_fixture_results",
        "case_count": len(results),
        "all_negative_fixtures_blocked": all(item["blocked"] for item in results),
        "results": results,
    }
    report["p67_negative_fixture_results_sha256"] = sha256_json(report)
    return report


def build_p67_real_order_test_redacted_evidence_receipt_report(
    p66_report: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    source_validation = validate_p66_source_report(p66_report)
    template = build_p67_receipt_template(p66_report, now=current)
    fixture_intake, fixture_p66_receipt = _fixture_activation_chain(p66_report)
    fixture = build_valid_p67_receipt_fixture(fixture_intake, fixture_p66_receipt, now=current)
    fixture_validation = validate_p67_redacted_evidence_receipt(
        fixture, fixture_intake, fixture_p66_receipt, allow_fixture=True, now=current + timedelta(seconds=2)
    )
    scan = build_p67_no_secret_scan_report(fixture)
    bridge = build_p67_order_test_validation_bridge(fixture, fixture_validation, fixture_validation_only=True)
    negatives = build_p67_negative_fixture_results(p66_report, now=current)
    ready = (
        source_validation["p66_source_valid"] is True
        and fixture_validation["p67_redacted_evidence_receipt_valid"] is True
        and scan["scan_passed"] is True
        and negatives["all_negative_fixtures_blocked"] is True
    )
    report = {
        "artifact_type": "p67_real_order_test_redacted_evidence_receipt_report",
        "status": STATUS_P67_READY if ready else STATUS_P67_BLOCKED,
        "blocked": not ready,
        "review_only": True,
        "runtime_authority_source": False,
        "p67_receipt_validator_implemented": True,
        "p67_no_secret_scan_implemented": True,
        "p67_order_test_dry_validation_bridge_implemented": True,
        "p66_source_validation": source_validation,
        "receipt_template": template,
        "fixture_receipt": fixture,
        "fixture_validation": fixture_validation,
        "fixture_no_secret_scan": scan,
        "fixture_bridge": bridge,
        "negative_fixture_summary": {
            "case_count": negatives["case_count"],
            "all_blocked": negatives["all_negative_fixtures_blocked"],
        },
        "negative_fixtures_all_blocked": negatives["all_negative_fixtures_blocked"],
        "actual_redacted_order_test_receipt_received": False,
        "actual_redacted_order_test_receipt_accepted": False,
        "actual_real_order_test_dry_validation_proven": False,
        "eligible_for_next_signed_testnet_submit_preflight": False,
        "p58_real_submit_evidence_acquisition_eligible": False,
        "p50_external_evidence_import_eligible": False,
        "p7_post_submit_evidence_import_eligible": False,
        "real_signed_testnet_submit_evidence_present": False,
        "real_order_test_endpoint_call_performed_by_p67": False,
        "real_order_submit_endpoint_called": False,
        "actual_order_submission_performed": False,
        "actual_testnet_order_submitted": False,
        "actual_live_order_submitted": False,
        "http_request_sent_by_p67": False,
        "signature_created_by_p67": False,
        "signed_request_created_by_p67": False,
        "secret_value_accessed_by_p67": False,
        "secret_value_logged_by_p67": False,
        "runtime_mutation_performed": False,
        "live_canary_execution_enabled": False,
        "live_scaled_execution_enabled": False,
        "created_at_utc": _canonical_utc(current),
    }
    report["p67_real_order_test_redacted_evidence_receipt_report_sha256"] = sha256_json(report)
    return report


def validate_p67_receipt_files(
    receipt_path: str | Path,
    p66_intake_path: str | Path,
    p66_validation_receipt_path: str | Path,
    *,
    allow_fixture: bool = False,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    receipt = read_json(receipt_path, {})
    intake = read_json(p66_intake_path, {})
    p66_receipt = read_json(p66_validation_receipt_path, {})
    validation = validate_p67_redacted_evidence_receipt(
        receipt, intake, p66_receipt, allow_fixture=allow_fixture, now=now
    )
    scan = build_p67_no_secret_scan_report(receipt if isinstance(receipt, Mapping) else {})
    bridge = build_p67_order_test_validation_bridge(
        receipt if isinstance(receipt, Mapping) else {},
        validation,
        fixture_validation_only=bool(receipt.get("fixture_only")) if isinstance(receipt, Mapping) else False,
    )
    return validation, scan, bridge


def persist_p67_real_order_test_redacted_evidence_receipt(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    latest = root / "storage" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    p66_report = read_json(latest / "p66_operator_activation_intake_for_real_order_test_report.json", {})
    report = build_p67_real_order_test_redacted_evidence_receipt_report(p66_report)
    negatives = build_p67_negative_fixture_results(p66_report)
    fixture_intake, fixture_p66_receipt = _fixture_activation_chain(p66_report)
    outputs = {
        "p67_real_order_test_redacted_evidence_receipt_report.json": report,
        "p67_source_p66_activation_intake_FIXTURE_ONLY.json": fixture_intake,
        "p67_source_p66_validation_receipt_FIXTURE_ONLY.json": fixture_p66_receipt,
        "p67_real_order_test_redacted_evidence_receipt_TEMPLATE_REVIEW_ONLY_NO_SUBMIT.json": report["receipt_template"],
        "p67_real_order_test_redacted_evidence_receipt_ACCEPTED_FIXTURE_ONLY.json": report["fixture_receipt"],
        "p67_real_order_test_redacted_evidence_receipt_validation_FIXTURE_ONLY.json": report["fixture_validation"],
        "p67_real_order_test_no_secret_scan_FIXTURE_ONLY.json": report["fixture_no_secret_scan"],
        "p67_order_test_dry_validation_bridge_FIXTURE_ONLY.json": report["fixture_bridge"],
        "p67_real_order_test_redacted_evidence_receipt_negative_fixture_results.json": negatives,
        "p67_real_order_test_redacted_evidence_receipt_summary.json": {
            "status": report["status"],
            "review_only": True,
            "actual_redacted_order_test_receipt_received": False,
            "actual_real_order_test_dry_validation_proven": False,
            "p50_external_evidence_import_eligible": False,
            "p7_post_submit_evidence_import_eligible": False,
            "actual_order_submission_performed": False,
        },
    }
    phase_dir = root / "storage" / "p67_real_order_test_redacted_evidence_receipt"
    for name, payload in outputs.items():
        atomic_write_json(latest / name, payload)
        atomic_write_json(phase_dir / name, payload)
    registry_row = {
        "registry_name": P67_REGISTRY_NAME,
        "status": report["status"],
        "report_sha256": report["p67_real_order_test_redacted_evidence_receipt_report_sha256"],
        "review_only": True,
        "actual_receipt_received": False,
        "actual_order_submission_performed": False,
        "created_at_utc": report["created_at_utc"],
    }
    registry_row["registry_record_sha256"] = sha256_json(registry_row)
    append_jsonl(root / "storage" / "registries" / f"{P67_REGISTRY_NAME}.jsonl", registry_row)
    atomic_write_json(latest / "p67_real_order_test_redacted_evidence_receipt_registry_record.json", registry_row)
    atomic_write_json(phase_dir / "p67_real_order_test_redacted_evidence_receipt_registry_record.json", registry_row)
    (root / "P67_REAL_ORDER_TEST_REDACTED_EVIDENCE_RECEIPT_REPORT.md").write_text(_markdown_report(report), encoding="utf-8")
    return report


def _markdown_report(report: Mapping[str, Any]) -> str:
    return f"""# P67 Real `/order/test` Redacted Evidence Receipt Report

## Status

`{report.get('status')}`

## Implemented

- P66 activation-chain binding validator
- redacted real `/fapi/v1/order/test` evidence receipt schema
- receipt hash, nonce, key fingerprint, operator request, scope, timestamp, and no-secret validation
- explicit dry-validation bridge for the next signed-testnet submit preflight
- explicit P50/P7 ineligibility because `/order/test` creates no order and no post-submit evidence
- review-only persistence and audit registry

## Current truth

- actual redacted receipt received: `{str(report.get('actual_redacted_order_test_receipt_received')).lower()}`
- actual real order-test dry validation proven: `{str(report.get('actual_real_order_test_dry_validation_proven')).lower()}`
- eligible for next signed-testnet submit preflight: `{str(report.get('eligible_for_next_signed_testnet_submit_preflight')).lower()}`
- P50 external evidence import eligible: `{str(report.get('p50_external_evidence_import_eligible')).lower()}`
- P7 post-submit evidence import eligible: `{str(report.get('p7_post_submit_evidence_import_eligible')).lower()}`
- actual order submission performed: `{str(report.get('actual_order_submission_performed')).lower()}`

## Boundary correction

A successful Binance Futures `/fapi/v1/order/test` response validates request construction and authentication but does not create an order. Therefore P67 must not manufacture `exchange_order_id`, fill, reconciliation, or session-close evidence and must not feed P50/P7 post-submit import. The next eligible stage after accepted real P67 evidence is a separately approved signed-testnet submit preflight.

## Safety

All execution, submit, live, runtime mutation, and secret-access flags remain false.
"""


__all__ = [
    "P67_VERSION",
    "STATUS_P67_READY",
    "STATUS_P67_ACCEPTED",
    "STATUS_P67_BLOCKED",
    "REAL_EVIDENCE_ORIGIN",
    "FIXTURE_EVIDENCE_ORIGIN",
    "P67RealOrderTestRedactedEvidenceReceipt",
    "build_p67_receipt_template",
    "build_valid_p67_receipt_fixture",
    "validate_p66_source_report",
    "validate_p66_activation_chain",
    "validate_p67_redacted_evidence_receipt",
    "build_p67_no_secret_scan_report",
    "build_p67_order_test_validation_bridge",
    "build_p67_negative_fixture_results",
    "build_p67_real_order_test_redacted_evidence_receipt_report",
    "validate_p67_receipt_files",
    "persist_p67_real_order_test_redacted_evidence_receipt",
]
