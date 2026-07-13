from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

VENUE_CONTRACT_VERSION = "p70_venue_neutral_execution_contract_v1"


def _contract_dict(value: Any, *, hash_field: str) -> dict[str, Any]:
    payload = asdict(value)
    payload[hash_field] = sha256_json(payload)
    return payload


@dataclass(frozen=True)
class ExternalVenueRuntimePackage:
    package_id: str
    venue: str
    environment: str
    adapter_version: str
    package_sha256: str
    runtime_enabled: bool = False
    submit_enabled: bool = False
    network_enabled: bool = False
    contract_version: str = VENUE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _contract_dict(self, hash_field="runtime_package_contract_sha256")


@dataclass(frozen=True)
class VenueCredentialReference:
    credential_reference_id: str
    venue: str
    environment: str
    api_key_fingerprint_sha256: str | None = None
    signing_key_fingerprint_sha256: str | None = None
    account_id: str | None = None
    subaccount_id: str | None = None
    signing_domain: str | None = None
    chain_id: str | None = None
    secret_value_present: bool = False
    contract_version: str = VENUE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _contract_dict(self, hash_field="credential_reference_contract_sha256")


@dataclass(frozen=True)
class VenueOrderIntent:
    order_intent_id: str
    venue: str
    environment: str
    market: str
    side: str
    order_type: str
    quantity: str
    time_in_force: str | None = None
    limit_price: str | None = None
    reduce_only: bool = False
    idempotency_key: str | None = None
    decision_id: str | None = None
    risk_gate_id: str | None = None
    research_signal_id: str | None = None
    profile_id: str | None = None
    venue_parameters: Mapping[str, Any] = field(default_factory=dict)
    submit_allowed: bool = False
    contract_version: str = VENUE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _contract_dict(self, hash_field="order_intent_contract_sha256")


@dataclass(frozen=True)
class VenueSubmitReceipt:
    submission_id: str
    order_intent_id: str
    venue: str
    environment: str
    accepted: bool
    exchange_order_id: str | None = None
    client_order_id: str | None = None
    request_hash: str | None = None
    response_hash: str | None = None
    submitted_at_utc: str | None = None
    raw_response_included: bool = False
    contract_version: str = VENUE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _contract_dict(self, hash_field="submit_receipt_contract_sha256")


@dataclass(frozen=True)
class VenueStatusEvent:
    status_event_id: str
    order_intent_id: str
    venue: str
    status: str
    observed_at_utc: str
    exchange_order_id: str | None = None
    filled_quantity: str | None = None
    average_fill_price: str | None = None
    event_sequence: int | None = None
    source: str = "venue_stream_or_read_api"
    contract_version: str = VENUE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _contract_dict(self, hash_field="status_event_contract_sha256")


@dataclass(frozen=True)
class VenueEvidenceBundle:
    evidence_bundle_id: str
    order_intent_id: str
    venue: str
    environment: str
    submit_receipt_hash: str | None = None
    status_event_hashes: tuple[str, ...] = ()
    reconciliation_hash: str | None = None
    no_secret_scan_hash: str | None = None
    complete: bool = False
    eligible_for_primary_execution_evidence: bool = False
    contract_version: str = VENUE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _contract_dict(self, hash_field="evidence_bundle_contract_sha256")


@runtime_checkable
class VenueSignerProtocol(Protocol):
    def sign(self, *, intent: VenueOrderIntent, credential: VenueCredentialReference) -> Mapping[str, Any]: ...


@runtime_checkable
class VenueSubmitTransport(Protocol):
    def submit(self, *, signed_request: Mapping[str, Any], runtime_package: ExternalVenueRuntimePackage) -> VenueSubmitReceipt: ...


def validate_order_intent(intent: VenueOrderIntent | Mapping[str, Any]) -> dict[str, Any]:
    data = intent.to_dict() if isinstance(intent, VenueOrderIntent) else dict(intent or {})
    blockers: list[str] = []
    for field_name in ("order_intent_id", "venue", "environment", "market", "side", "order_type", "quantity"):
        if not str(data.get(field_name) or "").strip():
            blockers.append(f"VENUE_ORDER_INTENT_{field_name.upper()}_MISSING")
    if data.get("submit_allowed") is not False:
        blockers.append("VENUE_ORDER_INTENT_SUBMIT_MUST_REMAIN_DISABLED_P70")
    forbidden_keys = {"endpoint", "endpoint_path", "base_url", "api_key", "api_secret", "private_key", "signature"}
    present = sorted(forbidden_keys.intersection(data))
    blockers.extend(f"VENUE_ORDER_INTENT_FORBIDDEN_CORE_FIELD:{name}" for name in present)
    return {
        "validation_id": stable_id("p70_venue_order_intent_validation", {"intent": data, "blockers": blockers}),
        "valid": not blockers,
        "block_reasons": sorted(blockers),
        "intent": data,
        "created_at_utc": utc_now_canonical(),
    }


def validate_runtime_package(package: ExternalVenueRuntimePackage | Mapping[str, Any]) -> dict[str, Any]:
    data = package.to_dict() if isinstance(package, ExternalVenueRuntimePackage) else dict(package or {})
    blockers: list[str] = []
    for field_name in ("package_id", "venue", "environment", "adapter_version", "package_sha256"):
        if not str(data.get(field_name) or "").strip():
            blockers.append(f"EXTERNAL_VENUE_RUNTIME_PACKAGE_{field_name.upper()}_MISSING")
    for flag in ("runtime_enabled", "submit_enabled", "network_enabled"):
        if data.get(flag) is not False:
            blockers.append(f"EXTERNAL_VENUE_RUNTIME_PACKAGE_{flag.upper()}_MUST_BE_FALSE_P70")
    return {"valid": not blockers, "block_reasons": sorted(blockers), "package": data}
