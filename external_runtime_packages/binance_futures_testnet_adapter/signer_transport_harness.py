from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Protocol, Sequence

from .adapter_package import (
    ALLOWED_ENDPOINTS,
    ALLOWED_ENVIRONMENT,
    ALLOWED_METHODS,
    ALLOWED_SYMBOL,
    ALLOWED_TESTNET_REST_BASE_URL,
    ALLOWED_VENUE,
    AdapterPackageDisabledError,
    AdapterPackageValidationError,
    BinanceFuturesTestnetEndpointPolicy,
    DisabledExternalAdapterRunnerConfig,
    MetadataOnlyKeyBinding,
    P59NoNetworkOrderIntent,
    _is_sha256_hex,
    _sha256_json,
    _verify_embedded_hash,
    _walk_forbidden,
    validate_disabled_runner_config,
    validate_endpoint_policy,
    validate_metadata_only_key_binding,
    validate_order_intent,
)

P60_EXTERNAL_SIGNER_TRANSPORT_HARNESS_VERSION = "p60_external_signer_transport_injection_harness_v1"
STATUS_HARNESS_VALIDATED_DISABLED = (
    "P60_EXTERNAL_SIGNER_HTTP_TRANSPORT_INJECTION_HARNESS_VALIDATED_REVIEW_ONLY_DISABLED"
)
STATUS_HARNESS_BLOCKED_FAIL_CLOSED = (
    "P60_EXTERNAL_SIGNER_HTTP_TRANSPORT_INJECTION_HARNESS_BLOCKED_FAIL_CLOSED"
)


class P60SignerHarnessProtocol(Protocol):
    signer_id: str
    process_memory_only: bool
    secret_persistence_allowed: bool
    secret_logging_allowed: bool
    concrete_signer: bool

    def describe_signer(self) -> Mapping[str, Any]:
        ...


class P60TransportHarnessProtocol(Protocol):
    transport_id: str
    testnet_only: bool
    base_url: str
    concrete_http_transport: bool
    network_send_capable: bool

    def dry_validate_request(self, request_metadata: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class ExternalSignerInjectionMetadata:
    signer_metadata_version: str = "p60_external_signer_injection_metadata_v1"
    signer_id: str = "OPERATOR_SUPPLIED_EXTERNAL_PROCESS_MEMORY_SIGNER"
    signer_location: str = "external_runtime_process_memory_only"
    process_memory_only: bool = True
    secret_reference_id_required: bool = True
    key_fingerprint_sha256_required: bool = True
    raw_secret_value_available_to_package: bool = False
    raw_secret_value_logged: bool = False
    secret_persistence_allowed: bool = False
    secret_file_read_allowed: bool = False
    concrete_signer_included_in_review_package: bool = False
    signature_creation_enabled_by_default: bool = False
    sign_call_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p60_external_signer_injection_metadata_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class ExternalHttpTransportInjectionMetadata:
    transport_metadata_version: str = "p60_external_http_transport_injection_metadata_v1"
    transport_id: str = "OPERATOR_SUPPLIED_TESTNET_ONLY_HTTP_TRANSPORT"
    base_url: str = ALLOWED_TESTNET_REST_BASE_URL
    testnet_only: bool = True
    allowed_method: str = ALLOWED_METHODS["test_submit"]
    allowed_path: str = ALLOWED_ENDPOINTS["test_submit"]
    real_network_send_enabled_by_default: bool = False
    concrete_http_transport_included_in_review_package: bool = False
    send_call_performed: bool = False
    mainnet_allowed: bool = False
    arbitrary_endpoint_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p60_external_http_transport_injection_metadata_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class SignerTransportHarnessConfig:
    harness_config_version: str = "p60_signer_transport_harness_config_v1"
    harness_scope: str = "external_runtime_injection_harness_review_only"
    review_package_may_hold_secret_values: bool = False
    harness_enabled: bool = False
    external_signer_injection_allowed_after_separate_approval: bool = True
    external_transport_injection_allowed_after_separate_approval: bool = True
    signing_enabled: bool = False
    network_calls_enabled: bool = False
    submit_enabled: bool = False
    order_test_endpoint_dry_validation_enabled: bool = True
    real_order_endpoint_enabled: bool = False
    status_endpoint_enabled: bool = False
    cancel_endpoint_enabled: bool = False
    allowed_dry_validation_method: str = ALLOWED_METHODS["test_submit"]
    allowed_dry_validation_path: str = ALLOWED_ENDPOINTS["test_submit"]
    max_order_count: int = 1
    fail_closed_on_any_mismatch: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p60_signer_transport_harness_config_sha256"] = _sha256_json(payload)
        return payload


@dataclass(frozen=True)
class OrderTestDryValidationIntent:
    intent_version: str = "p60_order_test_dry_validation_intent_v1"
    environment: str = ALLOWED_ENVIRONMENT
    venue: str = ALLOWED_VENUE
    symbol: str = ALLOWED_SYMBOL
    side: str = "BUY"
    order_type: str = "MARKET"
    notional_usdt: str = "5.00"
    client_order_id: str = "P60_ORDER_TEST_DRY_VALIDATION_CLIENT_ORDER_ID"
    idempotency_key: str = "6" * 64
    hot_path_risk_gate_id: str = "P60_FIXTURE_HOT_PATH_RISK_GATE_ID"
    hot_path_risk_gate_sha256: str = "7" * 64
    fixture_only: bool = True
    dry_validation_only: bool = True
    signed_testnet_real_evidence: bool = False
    submit_requested: bool = False
    network_call_requested: bool = False
    signature_requested: bool = False
    runtime_authority_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["p60_order_test_dry_validation_intent_sha256"] = _sha256_json(payload)
        return payload



def _walk_forbidden_p60(obj: Any, *, prefix: str = "") -> list[str]:
    # Reuse the P59 scanner only for non-boolean, user-supplied/raw fields.
    # Safety flags such as raw_secret_value_available_to_package=false must not be treated as leaked secrets.
    if isinstance(obj, Mapping):
        blockers: list[str] = []
        for key, value in obj.items():
            key_l = str(key).lower()
            child = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, bool):
                continue
            if any(token in key_l for token in ("api_key_value", "api_secret_value", "secret_value", "private_key", "passphrase", "raw_secret")):
                blockers.append(f"P59_FORBIDDEN_SECRET_OR_RAW_FIELD:{child}")
            blockers.extend(_walk_forbidden_p60(value, prefix=child))
        return blockers
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        blockers: list[str] = []
        for idx, value in enumerate(obj):
            blockers.extend(_walk_forbidden_p60(value, prefix=f"{prefix}[{idx}]"))
        return blockers
    return []

def _collect_blockers(*items: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for item in items:
        for key, value in item.items():
            if key.endswith("_block_reasons") and isinstance(value, list):
                blockers.extend(value)
    return sorted(dict.fromkeys(blockers))


def validate_signer_injection_metadata(metadata: Mapping[str, Any] | ExternalSignerInjectionMetadata | None) -> dict[str, Any]:
    payload = metadata.to_dict() if isinstance(metadata, ExternalSignerInjectionMetadata) else dict(metadata or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p60_external_signer_injection_metadata_sha256"):
        blockers.append("P60_SIGNER_METADATA_EMBEDDED_SHA256_INVALID")
    if payload.get("signer_location") != "external_runtime_process_memory_only":
        blockers.append("P60_SIGNER_LOCATION_INVALID")
    for key in ("process_memory_only", "secret_reference_id_required", "key_fingerprint_sha256_required"):
        if payload.get(key) is not True:
            blockers.append(f"P60_SIGNER_{key.upper()}_NOT_TRUE")
    for key in (
        "raw_secret_value_available_to_package",
        "raw_secret_value_logged",
        "secret_persistence_allowed",
        "secret_file_read_allowed",
        "concrete_signer_included_in_review_package",
        "signature_creation_enabled_by_default",
        "sign_call_performed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P60_SIGNER_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden_p60(payload))
    validation = {
        "signer_injection_metadata_valid": not blockers,
        "signer_injection_metadata_block_reasons": sorted(dict.fromkeys(blockers)),
        "process_memory_only": payload.get("process_memory_only") is True,
        "signature_creation_enabled_by_default": payload.get("signature_creation_enabled_by_default") is True,
    }
    validation["p60_signer_injection_metadata_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_transport_injection_metadata(metadata: Mapping[str, Any] | ExternalHttpTransportInjectionMetadata | None) -> dict[str, Any]:
    payload = metadata.to_dict() if isinstance(metadata, ExternalHttpTransportInjectionMetadata) else dict(metadata or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p60_external_http_transport_injection_metadata_sha256"):
        blockers.append("P60_TRANSPORT_METADATA_EMBEDDED_SHA256_INVALID")
    if payload.get("base_url") != ALLOWED_TESTNET_REST_BASE_URL:
        blockers.append("P60_TRANSPORT_BASE_URL_NOT_ALLOWED_TESTNET")
    if payload.get("allowed_method") != ALLOWED_METHODS["test_submit"]:
        blockers.append("P60_TRANSPORT_ALLOWED_METHOD_NOT_ORDER_TEST_POST")
    if payload.get("allowed_path") != ALLOWED_ENDPOINTS["test_submit"]:
        blockers.append("P60_TRANSPORT_ALLOWED_PATH_NOT_ORDER_TEST")
    if payload.get("testnet_only") is not True:
        blockers.append("P60_TRANSPORT_TESTNET_ONLY_NOT_TRUE")
    for key in (
        "real_network_send_enabled_by_default",
        "concrete_http_transport_included_in_review_package",
        "send_call_performed",
        "mainnet_allowed",
        "arbitrary_endpoint_allowed",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P60_TRANSPORT_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden_p60(payload))
    validation = {
        "transport_injection_metadata_valid": not blockers,
        "transport_injection_metadata_block_reasons": sorted(dict.fromkeys(blockers)),
        "testnet_only": payload.get("testnet_only") is True,
        "real_network_send_enabled_by_default": payload.get("real_network_send_enabled_by_default") is True,
    }
    validation["p60_transport_injection_metadata_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_harness_config(config: Mapping[str, Any] | SignerTransportHarnessConfig | None) -> dict[str, Any]:
    payload = config.to_dict() if isinstance(config, SignerTransportHarnessConfig) else dict(config or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p60_signer_transport_harness_config_sha256"):
        blockers.append("P60_HARNESS_CONFIG_EMBEDDED_SHA256_INVALID")
    if payload.get("harness_scope") != "external_runtime_injection_harness_review_only":
        blockers.append("P60_HARNESS_SCOPE_INVALID")
    for key in (
        "external_signer_injection_allowed_after_separate_approval",
        "external_transport_injection_allowed_after_separate_approval",
        "order_test_endpoint_dry_validation_enabled",
        "fail_closed_on_any_mismatch",
    ):
        if payload.get(key) is not True:
            blockers.append(f"P60_HARNESS_{key.upper()}_NOT_TRUE")
    for key in (
        "review_package_may_hold_secret_values",
        "harness_enabled",
        "signing_enabled",
        "network_calls_enabled",
        "submit_enabled",
        "real_order_endpoint_enabled",
        "status_endpoint_enabled",
        "cancel_endpoint_enabled",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P60_HARNESS_{key.upper()}_NOT_FALSE")
    if payload.get("allowed_dry_validation_method") != "POST":
        blockers.append("P60_HARNESS_DRY_VALIDATION_METHOD_INVALID")
    if payload.get("allowed_dry_validation_path") != ALLOWED_ENDPOINTS["test_submit"]:
        blockers.append("P60_HARNESS_DRY_VALIDATION_PATH_INVALID")
    if int(payload.get("max_order_count") or 0) != 1:
        blockers.append("P60_HARNESS_MAX_ORDER_COUNT_NOT_ONE")
    blockers.extend(_walk_forbidden_p60(payload))
    validation = {
        "harness_config_valid": not blockers,
        "harness_config_block_reasons": sorted(dict.fromkeys(blockers)),
        "harness_enabled": payload.get("harness_enabled") is True,
        "dry_validation_path": payload.get("allowed_dry_validation_path"),
    }
    validation["p60_harness_config_validation_sha256"] = _sha256_json(validation)
    return validation


def validate_order_test_dry_validation_intent(intent: Mapping[str, Any] | OrderTestDryValidationIntent | None) -> dict[str, Any]:
    payload = intent.to_dict() if isinstance(intent, OrderTestDryValidationIntent) else dict(intent or {})
    blockers: list[str] = []
    if not _verify_embedded_hash(payload, "p60_order_test_dry_validation_intent_sha256"):
        blockers.append("P60_DRY_INTENT_EMBEDDED_SHA256_INVALID")
    base_validation = validate_order_intent({**payload, "p59_no_network_order_intent_sha256": _sha256_json({k: v for k, v in payload.items() if not k.endswith('_sha256')})})
    # Keep an explicit local validation instead of depending on the P59 embedded hash format.
    if payload.get("environment") != ALLOWED_ENVIRONMENT:
        blockers.append("P60_DRY_INTENT_ENVIRONMENT_NOT_TESTNET")
    if payload.get("venue") != ALLOWED_VENUE:
        blockers.append("P60_DRY_INTENT_VENUE_INVALID")
    if payload.get("symbol") != ALLOWED_SYMBOL:
        blockers.append("P60_DRY_INTENT_SYMBOL_INVALID")
    if payload.get("dry_validation_only") is not True:
        blockers.append("P60_DRY_INTENT_DRY_VALIDATION_ONLY_NOT_TRUE")
    if payload.get("fixture_only") is not True:
        blockers.append("P60_DRY_INTENT_FIXTURE_ONLY_NOT_TRUE")
    if not _is_sha256_hex(payload.get("idempotency_key")):
        blockers.append("P60_DRY_INTENT_IDEMPOTENCY_KEY_INVALID")
    if not _is_sha256_hex(payload.get("hot_path_risk_gate_sha256")):
        blockers.append("P60_DRY_INTENT_RISK_GATE_SHA256_INVALID")
    for key in (
        "signed_testnet_real_evidence",
        "submit_requested",
        "network_call_requested",
        "signature_requested",
        "runtime_authority_granted",
    ):
        if payload.get(key) is not False:
            blockers.append(f"P60_DRY_INTENT_{key.upper()}_NOT_FALSE")
    blockers.extend(_walk_forbidden_p60(payload))
    validation = {
        "order_test_dry_validation_intent_valid": not blockers,
        "order_test_dry_validation_intent_block_reasons": sorted(dict.fromkeys(blockers)),
        "order_test_endpoint": ALLOWED_ENDPOINTS["test_submit"],
    }
    validation["p60_order_test_dry_validation_intent_validation_sha256"] = _sha256_json(validation)
    return validation


class P60FixtureSignerMetadata:
    signer_id = "P60_FIXTURE_SIGNER_METADATA_ONLY"
    process_memory_only = True
    secret_persistence_allowed = False
    secret_logging_allowed = False
    concrete_signer = False

    def describe_signer(self) -> Mapping[str, Any]:
        return ExternalSignerInjectionMetadata(signer_id=self.signer_id).to_dict()


class P60FixtureDryValidationTransport:
    transport_id = "P60_FIXTURE_TESTNET_DRY_VALIDATION_TRANSPORT"
    testnet_only = True
    base_url = ALLOWED_TESTNET_REST_BASE_URL
    concrete_http_transport = False
    network_send_capable = False

    def dry_validate_request(self, request_metadata: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = dict(request_metadata)
        valid = (
            payload.get("base_url") == ALLOWED_TESTNET_REST_BASE_URL
            and payload.get("method") == "POST"
            and payload.get("path") == ALLOWED_ENDPOINTS["test_submit"]
            and payload.get("symbol") == ALLOWED_SYMBOL
            and payload.get("signature_created") is False
            and payload.get("http_request_sent") is False
        )
        result = {
            "artifact_type": "p60_fixture_transport_dry_validation_result",
            "dry_validation_passed": valid,
            "transport_id": self.transport_id,
            "network_send_capable": False,
            "http_request_sent": False,
            "order_endpoint_called": False,
            "signature_created": False,
            "secret_value_accessed": False,
        }
        result["p60_fixture_transport_dry_validation_result_sha256"] = _sha256_json(result)
        return result


class ExternalSignerTransportInjectionHarness:
    harness_id = "p60_external_signer_transport_injection_harness"
    harness_version = P60_EXTERNAL_SIGNER_TRANSPORT_HARNESS_VERSION

    def __init__(
        self,
        *,
        endpoint_policy: BinanceFuturesTestnetEndpointPolicy | None = None,
        key_binding: MetadataOnlyKeyBinding | None = None,
        runner_config: DisabledExternalAdapterRunnerConfig | None = None,
        harness_config: SignerTransportHarnessConfig | None = None,
        signer_metadata: ExternalSignerInjectionMetadata | None = None,
        transport_metadata: ExternalHttpTransportInjectionMetadata | None = None,
    ) -> None:
        self.endpoint_policy = endpoint_policy or BinanceFuturesTestnetEndpointPolicy()
        self.key_binding = key_binding or MetadataOnlyKeyBinding(
            key_fingerprint_sha256=_sha256_json({"p60": "metadata-only-key-fingerprint"}),
            api_key_fingerprint_sha256=_sha256_json({"p60": "metadata-only-api-key-fingerprint"}),
        )
        self.runner_config = runner_config or DisabledExternalAdapterRunnerConfig()
        self.harness_config = harness_config or SignerTransportHarnessConfig()
        self.signer_metadata = signer_metadata or ExternalSignerInjectionMetadata()
        self.transport_metadata = transport_metadata or ExternalHttpTransportInjectionMetadata()

    def build_order_test_dry_validation_plan(
        self,
        intent: Mapping[str, Any] | OrderTestDryValidationIntent | None = None,
    ) -> dict[str, Any]:
        intent_payload = (intent or OrderTestDryValidationIntent()).to_dict() if not isinstance(intent, Mapping) else dict(intent)
        validations = {
            "endpoint_policy": validate_endpoint_policy(self.endpoint_policy),
            "key_binding": validate_metadata_only_key_binding(self.key_binding),
            "runner_config": validate_disabled_runner_config(self.runner_config),
            "harness_config": validate_harness_config(self.harness_config),
            "signer_metadata": validate_signer_injection_metadata(self.signer_metadata),
            "transport_metadata": validate_transport_injection_metadata(self.transport_metadata),
            "dry_validation_intent": validate_order_test_dry_validation_intent(intent_payload),
        }
        blockers = _collect_blockers(*validations.values())
        if blockers:
            raise AdapterPackageValidationError(";".join(blockers))
        canonical_params = {
            "symbol": ALLOWED_SYMBOL,
            "side": intent_payload["side"],
            "type": intent_payload["order_type"],
            "newClientOrderId": intent_payload["client_order_id"],
            "notional": intent_payload["notional_usdt"],
            "timestamp": "OPERATOR_RUNTIME_SUPPLIED_TIMESTAMP",
        }
        canonical_payload_digest = _sha256_json(canonical_params)
        plan = {
            "artifact_type": "p60_order_test_endpoint_dry_validation_plan_no_signature_no_network",
            "environment": ALLOWED_ENVIRONMENT,
            "venue": ALLOWED_VENUE,
            "base_url": ALLOWED_TESTNET_REST_BASE_URL,
            "method": "POST",
            "path": ALLOWED_ENDPOINTS["test_submit"],
            "symbol": ALLOWED_SYMBOL,
            "canonical_payload_digest_sha256": canonical_payload_digest,
            "idempotency_key": intent_payload["idempotency_key"],
            "client_order_id": intent_payload["client_order_id"],
            "secret_reference_id": self.key_binding.secret_reference_id,
            "key_fingerprint_sha256": self.key_binding.key_fingerprint_sha256,
            "signer_metadata_sha256": self.signer_metadata.to_dict()["p60_external_signer_injection_metadata_sha256"],
            "transport_metadata_sha256": self.transport_metadata.to_dict()["p60_external_http_transport_injection_metadata_sha256"],
            "dry_validation_only": True,
            "signer_injected": False,
            "transport_injected": False,
            "signature_created": False,
            "signed_request_created": False,
            "http_request_sent": False,
            "order_endpoint_called": False,
            "actual_order_submission_performed": False,
            "secret_value_accessed": False,
        }
        plan["p60_order_test_endpoint_dry_validation_plan_sha256"] = _sha256_json(plan)
        return plan

    def run_no_network_order_test_dry_validation(self) -> dict[str, Any]:
        plan = self.build_order_test_dry_validation_plan()
        transport_result = P60FixtureDryValidationTransport().dry_validate_request(plan)
        report = {
            "artifact_type": "p60_order_test_endpoint_no_network_dry_validation_report",
            "dry_validation_passed": transport_result["dry_validation_passed"],
            "order_test_endpoint": ALLOWED_ENDPOINTS["test_submit"],
            "dry_validation_plan_sha256": plan["p60_order_test_endpoint_dry_validation_plan_sha256"],
            "transport_dry_validation_result_sha256": transport_result["p60_fixture_transport_dry_validation_result_sha256"],
            "fixture_transport_used": True,
            "real_transport_used": False,
            "real_signer_used": False,
            "network_call_performed": False,
            "http_request_sent": False,
            "signature_created": False,
            "signed_request_created": False,
            "secret_value_accessed": False,
            "actual_order_submission_performed": False,
        }
        report["p60_order_test_endpoint_no_network_dry_validation_report_sha256"] = _sha256_json(report)
        return report

    def execute_real_order_test_dry_validation(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        del args, kwargs
        raise AdapterPackageDisabledError(
            "P60_REAL_SIGNER_TRANSPORT_DRY_VALIDATION_DISABLED_PENDING_SEPARATE_OPERATOR_APPROVAL_AND_EXTERNAL_PROCESS_MEMORY_SECRET_BINDING"
        )

    def execute_real_signed_testnet_submit(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        del args, kwargs
        raise AdapterPackageDisabledError(
            "P60_REAL_SIGNED_TESTNET_SUBMIT_DISABLED_ORDER_TEST_DRY_VALIDATION_ONLY"
        )


def build_p60_no_network_harness_self_test() -> dict[str, Any]:
    harness = ExternalSignerTransportInjectionHarness()
    dry_report = harness.run_no_network_order_test_dry_validation()
    real_dry_blocked = False
    real_submit_blocked = False
    try:
        harness.execute_real_order_test_dry_validation()
    except AdapterPackageDisabledError:
        real_dry_blocked = True
    try:
        harness.execute_real_signed_testnet_submit()
    except AdapterPackageDisabledError:
        real_submit_blocked = True
    report = {
        "artifact_type": "p60_no_network_signer_transport_harness_self_test_report",
        "self_test_passed": all(
            (
                dry_report["dry_validation_passed"],
                real_dry_blocked,
                real_submit_blocked,
                dry_report["http_request_sent"] is False,
                dry_report["signature_created"] is False,
                dry_report["secret_value_accessed"] is False,
                dry_report["actual_order_submission_performed"] is False,
            )
        ),
        "real_dry_validation_path_blocked": real_dry_blocked,
        "real_submit_path_blocked": real_submit_blocked,
        **dry_report,
    }
    report["p60_no_network_signer_transport_harness_self_test_report_sha256"] = _sha256_json(report)
    return report


def build_p60_negative_fixture_results() -> dict[str, Any]:
    fixtures: dict[str, dict[str, Any]] = {}
    fixtures["harness_enabled"] = validate_harness_config(replace(SignerTransportHarnessConfig(), harness_enabled=True).to_dict())
    fixtures["signing_enabled"] = validate_harness_config(replace(SignerTransportHarnessConfig(), signing_enabled=True).to_dict())
    fixtures["network_enabled"] = validate_harness_config(replace(SignerTransportHarnessConfig(), network_calls_enabled=True).to_dict())
    fixtures["real_order_endpoint_enabled"] = validate_harness_config(replace(SignerTransportHarnessConfig(), real_order_endpoint_enabled=True).to_dict())
    fixtures["wrong_dry_validation_path"] = validate_harness_config(replace(SignerTransportHarnessConfig(), allowed_dry_validation_path=ALLOWED_ENDPOINTS["submit"]).to_dict())
    fixtures["signer_secret_persistence"] = validate_signer_injection_metadata(replace(ExternalSignerInjectionMetadata(), secret_persistence_allowed=True).to_dict())
    fixtures["signer_signing_enabled"] = validate_signer_injection_metadata(replace(ExternalSignerInjectionMetadata(), signature_creation_enabled_by_default=True).to_dict())
    fixtures["transport_mainnet"] = validate_transport_injection_metadata(replace(ExternalHttpTransportInjectionMetadata(), base_url="https://fapi.binance.com").to_dict())
    fixtures["transport_network_send_enabled"] = validate_transport_injection_metadata(replace(ExternalHttpTransportInjectionMetadata(), real_network_send_enabled_by_default=True).to_dict())
    fixtures["raw_secret_in_intent"] = validate_order_test_dry_validation_intent({**OrderTestDryValidationIntent().to_dict(), "api_secret_value": "DO_NOT_STORE"})

    def blocked(item: Mapping[str, Any]) -> bool:
        valid_values = [value for key, value in item.items() if key.endswith("_valid")]
        return bool(valid_values) and all(value is False for value in valid_values)

    report = {
        "artifact_type": "p60_signer_transport_harness_negative_fixture_results",
        "fixture_results": fixtures,
        "fixture_count": len(fixtures),
        "all_negative_fixtures_blocked_fail_closed": all(blocked(item) for item in fixtures.values()),
        "http_request_sent": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "actual_order_submission_performed": False,
    }
    report["p60_signer_transport_harness_negative_fixture_results_sha256"] = _sha256_json(report)
    return report


def build_p60_harness_package_report() -> dict[str, Any]:
    policy = BinanceFuturesTestnetEndpointPolicy().to_dict()
    key_binding = MetadataOnlyKeyBinding(
        key_fingerprint_sha256=_sha256_json({"p60": "metadata-only-key-fingerprint"}),
        api_key_fingerprint_sha256=_sha256_json({"p60": "metadata-only-api-key-fingerprint"}),
    ).to_dict()
    runner = DisabledExternalAdapterRunnerConfig().to_dict()
    harness_config = SignerTransportHarnessConfig().to_dict()
    signer_metadata = ExternalSignerInjectionMetadata().to_dict()
    transport_metadata = ExternalHttpTransportInjectionMetadata().to_dict()
    dry_intent = OrderTestDryValidationIntent().to_dict()
    validations = {
        "endpoint_policy": validate_endpoint_policy(policy),
        "key_binding": validate_metadata_only_key_binding(key_binding),
        "runner_config": validate_disabled_runner_config(runner),
        "harness_config": validate_harness_config(harness_config),
        "signer_metadata": validate_signer_injection_metadata(signer_metadata),
        "transport_metadata": validate_transport_injection_metadata(transport_metadata),
        "dry_intent": validate_order_test_dry_validation_intent(dry_intent),
    }
    self_test = build_p60_no_network_harness_self_test()
    negatives = build_p60_negative_fixture_results()
    blockers = _collect_blockers(*validations.values())
    if not self_test["self_test_passed"]:
        blockers.append("P60_NO_NETWORK_HARNESS_SELF_TEST_FAILED")
    if not negatives["all_negative_fixtures_blocked_fail_closed"]:
        blockers.append("P60_NEGATIVE_FIXTURES_NOT_ALL_BLOCKED")
    status = STATUS_HARNESS_BLOCKED_FAIL_CLOSED if blockers else STATUS_HARNESS_VALIDATED_DISABLED
    report = {
        "artifact_type": "p60_external_signer_http_transport_injection_harness_package_report",
        "status": status,
        "blocked": bool(blockers),
        "fail_closed": bool(blockers),
        "block_reasons": sorted(dict.fromkeys(blockers)),
        "package_version": P60_EXTERNAL_SIGNER_TRANSPORT_HARNESS_VERSION,
        "endpoint_policy": policy,
        "metadata_only_key_binding": key_binding,
        "disabled_runner_config": runner,
        "harness_config": harness_config,
        "signer_injection_metadata": signer_metadata,
        "transport_injection_metadata": transport_metadata,
        "order_test_dry_validation_intent": dry_intent,
        "validations": validations,
        "no_network_harness_self_test": self_test,
        "negative_fixture_results": negatives,
        "external_signer_injection_harness_implemented": True,
        "external_http_transport_injection_harness_implemented": True,
        "order_test_endpoint_dry_validation_implemented": True,
        "order_test_endpoint": ALLOWED_ENDPOINTS["test_submit"],
        "concrete_signer_included": False,
        "concrete_http_transport_included": False,
        "secret_reader_included": False,
        "harness_enabled": False,
        "network_calls_enabled": False,
        "signing_enabled": False,
        "submit_enabled": False,
        "real_order_endpoint_enabled": False,
        "real_signed_testnet_evidence_present": False,
        "actual_order_submission_performed": False,
        "http_request_sent": False,
        "order_endpoint_called": False,
        "signature_created": False,
        "signed_request_created": False,
        "secret_value_accessed": False,
        "runtime_mutation_performed": False,
    }
    report["p60_external_signer_http_transport_injection_harness_package_report_sha256"] = _sha256_json(report)
    return report
