from crypto_ai_system.execution.venue_contracts import ExternalVenueRuntimePackage, VenueCredentialReference, VenueEvidenceBundle, VenueOrderIntent, VenueStatusEvent, VenueSubmitReceipt, validate_order_intent, validate_runtime_package


def test_p70_order_intent_is_venue_neutral_and_disabled():
    intent = VenueOrderIntent(order_intent_id="oi_1", venue="extended_starknet_sepolia", environment="testnet", market="BTC-USD", side="BUY", order_type="LIMIT", quantity="0.001", time_in_force="IOC", submit_allowed=False)
    result = validate_order_intent(intent)
    assert result["valid"] is True
    assert "endpoint" not in result["intent"]
    assert "api_key" not in result["intent"]


def test_p70_order_intent_rejects_submit_authority_and_endpoint_fields():
    result = validate_order_intent({"order_intent_id": "oi_2", "venue": "extended_starknet_sepolia", "environment": "testnet", "market": "BTC-USD", "side": "BUY", "order_type": "LIMIT", "quantity": "0.001", "submit_allowed": True, "endpoint_path": "/venue/order"})
    assert result["valid"] is False
    assert "VENUE_ORDER_INTENT_SUBMIT_MUST_REMAIN_DISABLED_P70" in result["block_reasons"]
    assert "VENUE_ORDER_INTENT_FORBIDDEN_CORE_FIELD:endpoint_path" in result["block_reasons"]


def test_p70_runtime_package_fails_closed():
    package = ExternalVenueRuntimePackage(package_id="extended_adapter", venue="extended_starknet_sepolia", environment="testnet", adapter_version="future", package_sha256="a" * 64)
    assert validate_runtime_package(package)["valid"] is True
    unsafe = {**package.to_dict(), "network_enabled": True}
    assert validate_runtime_package(unsafe)["valid"] is False


def test_p70_receipt_status_evidence_and_credential_are_metadata_only():
    credential = VenueCredentialReference(credential_reference_id="cred_1", venue="extended_starknet_sepolia", environment="testnet", secret_value_present=False)
    receipt = VenueSubmitReceipt(submission_id="sub_1", order_intent_id="oi_1", venue="extended_starknet_sepolia", environment="testnet", accepted=False)
    event = VenueStatusEvent(status_event_id="evt_1", order_intent_id="oi_1", venue="extended_starknet_sepolia", status="NOT_SUBMITTED", observed_at_utc="2026-07-12T00:00:00Z")
    evidence = VenueEvidenceBundle(evidence_bundle_id="ev_1", order_intent_id="oi_1", venue="extended_starknet_sepolia", environment="testnet")
    assert credential.to_dict()["secret_value_present"] is False
    assert receipt.to_dict()["accepted"] is False
    assert event.to_dict()["status"] == "NOT_SUBMITTED"
    assert evidence.to_dict()["eligible_for_primary_execution_evidence"] is False
