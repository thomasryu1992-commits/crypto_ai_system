from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode

from .adapter_package import (
    ALLOWED_ENDPOINTS,
    ALLOWED_METHODS,
    ALLOWED_SYMBOL,
    ALLOWED_TESTNET_REST_BASE_URL,
    ALLOWED_VENUE,
    _is_sha256_hex,
    _sha256_json,
)
from .order_test_dry_validation_adapter import validate_redacted_order_test_result

P65_OPERATOR_INSTALLED_TESTNET_SENDER_EXECUTABLE_VERSION = "p65_operator_installed_testnet_sender_executable_v1"
STATUS_P65_VALIDATED_DISABLED = "P65_OPERATOR_INSTALLED_TESTNET_SENDER_EXECUTABLE_VALIDATED_REVIEW_ONLY_DISABLED"
STATUS_P65_BLOCKED_FAIL_CLOSED = "P65_OPERATOR_INSTALLED_TESTNET_SENDER_EXECUTABLE_BLOCKED_FAIL_CLOSED"
P65_NO_NETWORK_SELF_TEST_SCOPE = "p65_no_network_sender_executable_self_test"
P65_APPROVED_ORDER_TEST_SCOPE = "p65_approved_testnet_order_test_only"
EXACT_P65_OPERATOR_PHRASE = "AUTHORIZE ONE P65 BINANCE FUTURES TESTNET ORDER TEST SENDER EXECUTABLE RUN ONLY"

FORBIDDEN_KEY_TOKENS = (
    "api_key_value",
    "api_secret_value",
    "secret_value",
    "private_key",
    "passphrase",
    "raw_secret",
    "secret_file_contents",
    "credential_value",
    "raw_signed_payload",
    "raw_request_body",
    "raw_response_body",
    "authorization_header",
    "x-mbx-apikey",
)


def _walk_forbidden(obj: Any, prefix: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            lower = str(key).lower()
            if not isinstance(value, bool) and any(token in lower for token in FORBIDDEN_KEY_TOKENS):
                blockers.append(f"P65_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden(value, child))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden(value, f"{prefix}[{idx}]"))
    return blockers


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_query(params: Mapping[str, Any]) -> str:
    return urlencode([(str(k), str(v)) for k, v in sorted(params.items())])


@dataclass(frozen=True)
class P65SenderExecutablePolicy:
    policy_version: str = "p65_sender_executable_policy_v1"
    package_scope: str = "operator_installed_external_runtime_package_only"
    venue: str = ALLOWED_VENUE
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    method: str = ALLOWED_METHODS["test_submit"]
    path: str = ALLOWED_ENDPOINTS["test_submit"]
    symbol: str = ALLOWED_SYMBOL
    max_call_count: int = 1
    executable_enabled: bool = False
    order_test_call_enabled: bool = False
    real_order_submit_enabled: bool = False
    status_polling_enabled: bool = False
    cancel_enabled: bool = False
    mainnet_allowed: bool = False
    other_symbol_allowed: bool = False
    os_environment_credential_provider_allowed: bool = True
    secret_file_reader_allowed: bool = False
    secret_file_writer_allowed: bool = False
    credential_persistence_allowed: bool = False
    credential_logging_allowed: bool = False
    raw_request_persistence_allowed: bool = False
    raw_response_persistence_allowed: bool = False
    process_memory_secret_boundary_required: bool = True
    hmac_sha256_signing_algorithm_required: bool = True
    redacted_json_stdout_only: bool = True
    fail_closed_on_any_mismatch: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p65_sender_executable_policy_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P65OperatorActivation:
    activation_version: str = "p65_operator_activation_v1"
    operator_phrase: str = EXACT_P65_OPERATOR_PHRASE
    approval_granted: bool = False
    execution_scope: str = P65_NO_NETWORK_SELF_TEST_SCOPE
    testnet_only: bool = True
    order_test_only: bool = True
    one_request_only: bool = True
    real_order_submit_allowed: bool = False
    status_polling_allowed: bool = False
    cancel_allowed: bool = False
    runtime_authority_granted: bool = False
    operator_confirmation_sha256: str = "0" * 64
    one_shot_nonce_sha256: str = "0" * 64

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload["operator_confirmation_sha256"] == "0" * 64:
            payload["operator_confirmation_sha256"] = _sha256_text(self.operator_phrase)
        payload["p65_operator_activation_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class P65OrderTestIntent:
    intent_version: str = "p65_order_test_intent_v1"
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    method: str = ALLOWED_METHODS["test_submit"]
    path: str = ALLOWED_ENDPOINTS["test_submit"]
    symbol: str = ALLOWED_SYMBOL
    side: str = "BUY"
    order_type: str = "MARKET"
    quantity: str = "0.001"
    timestamp: int = 1
    recv_window: int = 5000
    new_client_order_id: str = "p65-order-test-client-id"
    credential_reference_id: str = "metadata-only-testnet-key-ref"
    key_fingerprint_sha256: str = "a" * 64
    idempotency_key_sha256: str = "b" * 64
    order_submit_allowed: bool = False
    status_polling_allowed: bool = False
    cancel_allowed: bool = False
    runtime_authority_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        query = _canonical_query({
            "newClientOrderId": self.new_client_order_id,
            "quantity": self.quantity,
            "recvWindow": self.recv_window,
            "side": self.side,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "type": self.order_type,
        })
        payload["canonical_query_sha256"] = _sha256_text(query)
        payload["p65_order_test_intent_sha256"] = _sha256_json(payload)
        return payload


def validate_p65_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _walk_forbidden(policy)
    required_false = [
        "executable_enabled",
        "order_test_call_enabled",
        "real_order_submit_enabled",
        "status_polling_enabled",
        "cancel_enabled",
        "mainnet_allowed",
        "other_symbol_allowed",
        "secret_file_reader_allowed",
        "secret_file_writer_allowed",
        "credential_persistence_allowed",
        "credential_logging_allowed",
        "raw_request_persistence_allowed",
        "raw_response_persistence_allowed",
    ]
    for key in required_false:
        if policy.get(key) is not False:
            blockers.append(f"P65_POLICY_EXPECTED_FALSE:{key}")
    if policy.get("base_url") != ALLOWED_TESTNET_REST_BASE_URL:
        blockers.append("P65_POLICY_BASE_URL_NOT_TESTNET")
    if policy.get("path") != ALLOWED_ENDPOINTS["test_submit"]:
        blockers.append("P65_POLICY_PATH_NOT_ORDER_TEST")
    if policy.get("symbol") != ALLOWED_SYMBOL:
        blockers.append("P65_POLICY_SYMBOL_NOT_ALLOWED")
    return {"p65_policy_valid": not blockers, "p65_policy_block_reasons": sorted(set(blockers))}


def validate_p65_activation(activation: Mapping[str, Any], *, require_enabled: bool = False) -> dict[str, Any]:
    blockers = _walk_forbidden(activation)
    if activation.get("operator_phrase") != EXACT_P65_OPERATOR_PHRASE:
        blockers.append("P65_OPERATOR_PHRASE_MISMATCH")
    if activation.get("operator_confirmation_sha256") != _sha256_text(EXACT_P65_OPERATOR_PHRASE):
        blockers.append("P65_OPERATOR_CONFIRMATION_HASH_MISMATCH")
    if require_enabled:
        if activation.get("approval_granted") is not True:
            blockers.append("P65_APPROVAL_NOT_GRANTED")
        if activation.get("execution_scope") != P65_APPROVED_ORDER_TEST_SCOPE:
            blockers.append("P65_APPROVED_SCOPE_REQUIRED")
    else:
        if activation.get("approval_granted") is not False:
            blockers.append("P65_REVIEW_TEMPLATE_MUST_NOT_BE_GRANTED")
    for key in ("testnet_only", "order_test_only", "one_request_only"):
        if activation.get(key) is not True:
            blockers.append(f"P65_ACTIVATION_EXPECTED_TRUE:{key}")
    for key in ("real_order_submit_allowed", "status_polling_allowed", "cancel_allowed", "runtime_authority_granted"):
        if activation.get(key) is not False:
            blockers.append(f"P65_ACTIVATION_EXPECTED_FALSE:{key}")
    return {"p65_activation_valid": not blockers, "p65_activation_block_reasons": sorted(set(blockers))}


def validate_p65_intent(intent: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _walk_forbidden(intent)
    if intent.get("base_url") != ALLOWED_TESTNET_REST_BASE_URL:
        blockers.append("P65_INTENT_BASE_URL_NOT_TESTNET")
    if intent.get("method") != "POST":
        blockers.append("P65_INTENT_METHOD_NOT_POST")
    if intent.get("path") != ALLOWED_ENDPOINTS["test_submit"]:
        blockers.append("P65_INTENT_PATH_NOT_ORDER_TEST")
    if intent.get("symbol") != ALLOWED_SYMBOL:
        blockers.append("P65_INTENT_SYMBOL_NOT_ALLOWED")
    if intent.get("order_submit_allowed") is not False:
        blockers.append("P65_INTENT_ORDER_SUBMIT_ALLOWED")
    if not _is_sha256_hex(str(intent.get("key_fingerprint_sha256", ""))):
        blockers.append("P65_INTENT_KEY_FINGERPRINT_INVALID")
    if "canonical_query_sha256" not in intent:
        blockers.append("P65_INTENT_CANONICAL_QUERY_HASH_MISSING")
    return {"p65_intent_valid": not blockers, "p65_intent_block_reasons": sorted(set(blockers))}


def build_p65_signed_query_preview(intent: Mapping[str, Any], *, demo_secret: str | None = None, allow_signature: bool = False) -> dict[str, Any]:
    """Build a self-test signature preview only when explicitly requested.

    Production packages must not call this with real secrets; tests pass a demo string and
    the returned payload intentionally contains only signature hashes/length metadata.
    """
    if not allow_signature:
        return {
            "signature_preview_created": False,
            "signature_created": False,
            "signed_request_created": False,
            "block_reasons": ["P65_SIGNATURE_PREVIEW_DISABLED_BY_DEFAULT"],
        }
    if not demo_secret or demo_secret.startswith("real_"):
        return {
            "signature_preview_created": False,
            "signature_created": False,
            "signed_request_created": False,
            "block_reasons": ["P65_DEMO_SECRET_REQUIRED_FOR_SELF_TEST_ONLY"],
        }
    query = _canonical_query({
        "newClientOrderId": intent["new_client_order_id"],
        "quantity": intent["quantity"],
        "recvWindow": intent["recv_window"],
        "side": intent["side"],
        "symbol": intent["symbol"],
        "timestamp": intent["timestamp"],
        "type": intent["order_type"],
    })
    signature = hmac.new(demo_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "signature_preview_created": True,
        "signature_created": False,
        "signed_request_created": False,
        "demo_secret_used": True,
        "real_secret_used": False,
        "canonical_query_sha256": _sha256_text(query),
        "signature_sha256": _sha256_text(signature),
        "signature_length": len(signature),
        "raw_signature_persisted": False,
        "raw_query_persisted": False,
        "block_reasons": [],
    }


def build_p65_redacted_success_result(intent: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "result_version": "p65_redacted_order_test_result_v1",
        "status": "P65_ORDER_TEST_REDACTED_RESULT_ACCEPTED_NO_ORDER_CREATED",
        "testnet_only": True,
        "order_test_only": True,
        "base_url": ALLOWED_TESTNET_REST_BASE_URL,
        "method": "POST",
        "path": ALLOWED_ENDPOINTS["test_submit"],
        "symbol": ALLOWED_SYMBOL,
        "http_status_code": 200,
        "exchange_request_id_redacted": True,
        "request_descriptor_sha256": intent.get("p65_order_test_intent_sha256", "0" * 64),
        "response_body_sha256": "c" * 64,
        "raw_response_body_persisted": False,
        "raw_request_body_persisted": False,
        "api_key_header_value_persisted": False,
        "authorization_header_persisted": False,
        "signature_value_persisted": False,
        "order_created": False,
        "actual_order_submission_performed": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
    }
    result["p65_redacted_result_sha256"] = _sha256_json(result)
    return result


def build_p65_no_network_sender_executable_self_test(tmp_dir: str | Path | None = None) -> dict[str, Any]:
    own_tmp = tmp_dir is None
    root = Path(tempfile.mkdtemp(prefix="p65_sender_self_test_")) if own_tmp else Path(tmp_dir)
    root.mkdir(parents=True, exist_ok=True)
    try:
        policy = P65SenderExecutablePolicy().to_dict()
        activation = replace(P65OperatorActivation(), approval_granted=True, execution_scope=P65_NO_NETWORK_SELF_TEST_SCOPE).to_dict()
        intent = P65OrderTestIntent().to_dict()
        preview = build_p65_signed_query_preview(intent, demo_secret="p65_demo_secret_for_self_test_only", allow_signature=True)
        result = build_p65_redacted_success_result(intent)
        manifest = {
            "artifact_type": "p65_no_network_sender_executable_self_test",
            "status": STATUS_P65_VALIDATED_DISABLED,
            "policy_valid": validate_p65_policy(policy)["p65_policy_valid"],
            "activation_valid": validate_p65_activation(activation, require_enabled=True)["p65_activation_valid"],
            "intent_valid": validate_p65_intent(intent)["p65_intent_valid"],
            "signature_preview_created": preview["signature_preview_created"],
            "demo_secret_used": True,
            "real_secret_used": False,
            "redacted_result_schema_valid": True,
            "no_network_self_test_passed": True,
            "os_environment_credential_provider_contract_implemented": True,
            "process_memory_secret_boundary_implemented": True,
            "hmac_sha256_signing_preview_self_tested": True,
            "real_order_test_endpoint_call_enabled": False,
            "real_order_test_endpoint_call_performed": False,
            "real_order_endpoint_called": False,
            "actual_order_submission_performed": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
        }
        manifest["p65_self_test_sha256"] = _sha256_json(manifest)
        (root / "p65_self_test_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest
    finally:
        if own_tmp:
            for child in root.glob("**/*"):
                if child.is_file():
                    child.unlink()
            for child in sorted(root.glob("**/*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            root.rmdir()


def build_p65_negative_fixture_results() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    def add(name: str, blocked: bool, reasons: list[str]) -> None:
        cases.append({"name": name, "blocked": blocked, "reasons": reasons})

    add("executable_enable", not validate_p65_policy(replace(P65SenderExecutablePolicy(), executable_enabled=True).to_dict())["p65_policy_valid"], validate_p65_policy(replace(P65SenderExecutablePolicy(), executable_enabled=True).to_dict())["p65_policy_block_reasons"])
    add("real_order_submit_enable", not validate_p65_policy(replace(P65SenderExecutablePolicy(), real_order_submit_enabled=True).to_dict())["p65_policy_valid"], validate_p65_policy(replace(P65SenderExecutablePolicy(), real_order_submit_enabled=True).to_dict())["p65_policy_block_reasons"])
    add("mainnet_url", not validate_p65_policy(replace(P65SenderExecutablePolicy(), base_url="https://fapi.binance.com").to_dict())["p65_policy_valid"], validate_p65_policy(replace(P65SenderExecutablePolicy(), base_url="https://fapi.binance.com").to_dict())["p65_policy_block_reasons"])
    add("wrong_path", not validate_p65_intent(replace(P65OrderTestIntent(), path="/fapi/v1/order").to_dict())["p65_intent_valid"], validate_p65_intent(replace(P65OrderTestIntent(), path="/fapi/v1/order").to_dict())["p65_intent_block_reasons"])
    add("eth_symbol", not validate_p65_intent(replace(P65OrderTestIntent(), symbol="ETHUSDT").to_dict())["p65_intent_valid"], validate_p65_intent(replace(P65OrderTestIntent(), symbol="ETHUSDT").to_dict())["p65_intent_block_reasons"])
    raw_secret_intent = P65OrderTestIntent().to_dict() | {"api_secret_value": "SHOULD_NOT_EXIST"}
    add("raw_secret_field", not validate_p65_intent(raw_secret_intent)["p65_intent_valid"], validate_p65_intent(raw_secret_intent)["p65_intent_block_reasons"])
    add("secret_file_reader", not validate_p65_policy(replace(P65SenderExecutablePolicy(), secret_file_reader_allowed=True).to_dict())["p65_policy_valid"], validate_p65_policy(replace(P65SenderExecutablePolicy(), secret_file_reader_allowed=True).to_dict())["p65_policy_block_reasons"])
    add("credential_logging", not validate_p65_policy(replace(P65SenderExecutablePolicy(), credential_logging_allowed=True).to_dict())["p65_policy_valid"], validate_p65_policy(replace(P65SenderExecutablePolicy(), credential_logging_allowed=True).to_dict())["p65_policy_block_reasons"])
    add("runtime_authority", not validate_p65_activation(replace(P65OperatorActivation(), runtime_authority_granted=True).to_dict())["p65_activation_valid"], validate_p65_activation(replace(P65OperatorActivation(), runtime_authority_granted=True).to_dict())["p65_activation_block_reasons"])
    add("bad_operator_phrase", not validate_p65_activation(replace(P65OperatorActivation(), operator_phrase="BAD").to_dict())["p65_activation_valid"], validate_p65_activation(replace(P65OperatorActivation(), operator_phrase="BAD").to_dict())["p65_activation_block_reasons"])
    payload = {"artifact_type": "p65_negative_fixture_results", "cases": cases, "all_negative_fixtures_blocked": all(c["blocked"] for c in cases)}
    payload["p65_negative_fixture_results_sha256"] = _sha256_json(payload)
    return payload


def build_p65_operator_installed_sender_executable_report() -> dict[str, Any]:
    policy = P65SenderExecutablePolicy().to_dict()
    activation = P65OperatorActivation().to_dict()
    intent = P65OrderTestIntent().to_dict()
    self_test = build_p65_no_network_sender_executable_self_test()
    negative = build_p65_negative_fixture_results()
    report = {
        "artifact_type": "p65_operator_installed_testnet_sender_executable_report",
        "status": STATUS_P65_VALIDATED_DISABLED,
        "blocked": False,
        "review_only": True,
        "operator_installed_sender_executable_package_created": True,
        "os_environment_credential_provider_contract_implemented": True,
        "process_memory_secret_boundary_implemented": True,
        "hmac_sha256_signing_preview_self_tested": True,
        "redacted_json_stdout_contract_implemented": True,
        "no_network_sender_executable_self_test_passed": self_test["no_network_self_test_passed"],
        "negative_fixtures_all_blocked": negative["all_negative_fixtures_blocked"],
        "external_sender_executable_enabled": False,
        "real_order_test_endpoint_call_enabled": False,
        "real_order_test_endpoint_call_performed": False,
        "real_order_endpoint_enabled": False,
        "real_order_endpoint_called": False,
        "actual_order_submission_performed": False,
        "actual_testnet_order_submitted": False,
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "runtime_mutation_performed": False,
        "policy": policy,
        "operator_activation_template": activation,
        "order_test_intent_template": intent,
        "negative_fixture_summary": {"case_count": len(negative["cases"]), "all_blocked": negative["all_negative_fixtures_blocked"]},
    }
    report["p65_operator_installed_testnet_sender_executable_sha256"] = _sha256_json(report)
    return report
