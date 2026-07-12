from crypto_ai_system.execution.venue_alignment import BINANCE_REFERENCE_VENUE, EXTENDED_TESTNET_VENUE, VenueAlignmentPolicy, validate_evidence_venue_for_primary_execution, validate_venue_alignment


def test_default_p69_policy_is_aligned_and_frozen():
    result = validate_venue_alignment(VenueAlignmentPolicy())
    assert result["valid"] is True
    assert result["policy"]["primary_execution_venue"] == "extended"
    assert result["policy"]["binance_reference_branch_runtime_enabled"] is False
    assert result["policy"]["cross_venue_evidence_import_allowed"] is False
    assert result["policy"]["extended_alignment_validated"] is False


def test_binance_reference_evidence_cannot_satisfy_extended_gate():
    result = validate_evidence_venue_for_primary_execution(BINANCE_REFERENCE_VENUE)
    assert result["valid"] is False
    assert "CROSS_VENUE_EVIDENCE_IMPORT_BLOCKED" in result["block_reasons"]
    assert "BINANCE_REFERENCE_EVIDENCE_NOT_RUNTIME_ELIGIBLE" in result["block_reasons"]


def test_extended_evidence_matches_primary_testnet_venue():
    assert validate_evidence_venue_for_primary_execution(EXTENDED_TESTNET_VENUE)["valid"] is True


def test_unsafe_route_flags_fail_closed():
    policy = VenueAlignmentPolicy().to_dict()
    policy["runtime_auto_route_allowed"] = True
    policy["binance_reference_branch_runtime_enabled"] = True
    result = validate_venue_alignment(policy)
    assert result["valid"] is False
    assert "RUNTIME_AUTO_ROUTE_ALLOWED_MUST_BE_FALSE" in result["block_reasons"]
    assert "BINANCE_REFERENCE_BRANCH_RUNTIME_ENABLED_MUST_BE_FALSE" in result["block_reasons"]
