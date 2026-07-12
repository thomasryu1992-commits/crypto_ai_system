from external_runtime_packages.extended_read_only_probe import ExtendedPrivateReadOnlyProbe, PrivateReadOnlyProbePolicy
from crypto_ai_system.execution.extended_read_only_connectivity import ExtendedPublicReadOnlyClient, ExtendedPublicReadOnlyPolicy, ExtendedReadOnlyPolicyError, build_p71_complete_evidence, build_p71_public_connectivity_evidence, run_p71_public_probe, validate_p71_private_account_evidence
from external_runtime_packages.extended_read_only_probe.probe import _requests_get


def _market_payload():
    return {"status": "OK", "data": [{"name": "BTC-USD", "status": "ACTIVE", "tradingConfig": {"minOrderSize": "0.001", "minPriceChange": "0.1"}}]}


def _orderbook_payload():
    return {"status": "OK", "data": {"market": "BTC-USD", "bids": [{"price": "100", "qty": "1"}], "asks": [{"price": "101", "qty": "1"}]}}


def test_p71_public_probe_accepts_fresh_rest_and_stream_without_completing_private_gate():
    def rest_get(url, params, headers, timeout):
        assert headers == {"User-Agent": "crypto-ai-system-p71-read-only/1"}
        assert "X-Api-Key" not in headers
        return _market_payload() if url.endswith("/info/markets") else _orderbook_payload()

    def stream_probe(url, headers, timeout):
        return {"received": True, "message": {"type": "SNAPSHOT", "market": "BTC-USD", "bids": [], "asks": []}, "latency_ms": 1.0}

    evidence = run_p71_public_probe(network_enabled=True, rest_get=rest_get, stream_probe=stream_probe)
    assert evidence["public_connectivity_valid"] is True
    assert evidence["private_account_read_evidence_valid"] is False
    assert evidence["p71_complete"] is False
    assert evidence["write_block_probe_valid"] is True
    assert evidence["network_write_call_performed"] is False


def test_p71_network_disabled_fails_closed():
    evidence = run_p71_public_probe(network_enabled=False)
    assert evidence["public_connectivity_valid"] is False
    assert "P71_MARKET_REST_NOT_CALLED" in evidence["block_reasons"]
    assert evidence["write_block_probe_valid"] is True


def test_p71_stream_failure_is_preserved_as_blocking_diagnostic():
    def rest_get(url, params, headers, timeout):
        return _market_payload() if url.endswith("/info/markets") else _orderbook_payload()

    def stream_probe(url, headers, timeout):
        raise RuntimeError("handshake rejected")

    evidence = run_p71_public_probe(network_enabled=True, rest_get=rest_get, stream_probe=stream_probe)
    assert evidence["public_rest_valid"] is True
    assert evidence["public_stream_valid"] is False
    assert evidence["public_stream_error_type"] == "RuntimeError"
    assert "P71_PUBLIC_STREAM_SNAPSHOT_MISSING" in evidence["block_reasons"]


def test_p71_rejects_wrong_venue_market_and_write_policy():
    for policy in (
        ExtendedPublicReadOnlyPolicy(api_base_url="https://api.starknet.extended.exchange/api/v1"),
        ExtendedPublicReadOnlyPolicy(market="ETH-USD"),
        ExtendedPublicReadOnlyPolicy(write_calls_allowed=True),
        ExtendedPublicReadOnlyPolicy(credential_headers_allowed=True),
    ):
        try:
            ExtendedPublicReadOnlyClient(policy)
        except ExtendedReadOnlyPolicyError:
            pass
        else:
            raise AssertionError("unsafe P71 policy must fail closed")


def test_p71_no_secret_scan_blocks_credential_material():
    evidence = build_p71_public_connectivity_evidence(
        market_response={"called": True, "payload": _market_payload()},
        orderbook_response={"called": True, "payload": {**_orderbook_payload(), "api_key": "must-not-appear"}},
        stream_response={"called": True, "received": True, "message": {"market": "BTC-USD"}},
    )
    assert evidence["public_connectivity_valid"] is False
    assert "P71_NO_SECRET_SCAN_FAILED" in evidence["block_reasons"]


def _private_receipt(*, source_is_fixture=False):
    def transport(url, params, headers, timeout):
        assert headers["X-Api-Key"] == "test-only-api-key"
        assert url.split("/api/v1", 1)[1] in {"/user/account/info", "/user/balance", "/user/positions", "/user/orders"}
        return 200, {"status": "OK", "data": [] if not url.endswith("/info") else {"status": "ACTIVE"}}

    probe = ExtendedPrivateReadOnlyProbe(
        api_key="test-only-api-key",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
            source_is_fixture=source_is_fixture,
        ),
        transport=transport,
    )
    return probe.run()


def test_p71_external_private_probe_outputs_hashes_not_api_key():
    receipt = _private_receipt()
    serialized = str(receipt)
    assert "test-only-api-key" not in serialized
    assert receipt["credential_value_included"] is False
    assert receipt["write_call_performed"] is False
    assert set(receipt["endpoint_receipts"]) == {"account_info", "balance", "positions", "open_orders"}
    assert validate_p71_private_account_evidence(receipt)["valid"] is True


def test_p71_private_probe_strips_credential_paste_whitespace():
    observed = {}

    def transport(_url, _params, headers, _timeout):
        observed["header"] = headers["X-Api-Key"]
        return 200, {"status": "OK", "data": {}}

    probe = ExtendedPrivateReadOnlyProbe(
        api_key="  test-only-api-key\r\n",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
        ),
        transport=transport,
    )
    probe.run()
    assert observed["header"] == "test-only-api-key"


def test_p71_private_fixture_cannot_be_real_evidence():
    validation = validate_p71_private_account_evidence(_private_receipt(source_is_fixture=True))
    assert validation["valid"] is False
    assert "P71_PRIVATE_FIXTURE_NOT_REAL_EVIDENCE" in validation["block_reasons"]


def test_p71_private_zero_balance_404_is_valid_read_evidence():
    def transport(url, _params, _headers, _timeout):
        if url.endswith("/user/balance"):
            return 404, {"status": "NON_JSON_RESPONSE", "body_sha256": "0" * 64}
        return 200, {"status": "OK", "data": []}

    receipt = ExtendedPrivateReadOnlyProbe(
        api_key="test-only-api-key",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
        ),
        transport=transport,
    ).run()
    assert receipt["endpoint_receipts"]["balance"]["zero_balance_confirmed"] is True
    assert validate_p71_private_account_evidence(receipt)["valid"] is True


def test_p71_complete_gate_requires_public_stream_and_real_private_receipt():
    def rest_get(url, params, headers, timeout):
        return _market_payload() if url.endswith("/info/markets") else _orderbook_payload()

    public = run_p71_public_probe(
        network_enabled=True,
        rest_get=rest_get,
        stream_probe=lambda *_args: {"received": True, "message": {"type": "SNAPSHOT", "data": {"m": "BTC-USD"}}},
    )
    result = build_p71_complete_evidence(public_evidence=public, private_receipt=_private_receipt())
    assert result["p71_complete"] is True
    blocked = build_p71_complete_evidence(public_evidence={**public, "public_stream_valid": False}, private_receipt=_private_receipt())
    assert blocked["p71_complete"] is False
    assert "P71_PUBLIC_STREAM_INVALID" in blocked["block_reasons"]


def test_p71_windows_probe_cli_never_accepts_secret_value_argument():
    from pathlib import Path

    source = Path("external_runtime_packages/extended_read_only_probe/run_windows_probe.py").read_text(encoding="utf-8")
    assert "--api-key" not in source
    assert "--private-key" not in source
    assert "read_generic_credential_secret" in source


def test_p71_private_transport_sanitizes_non_json_response(monkeypatch):
    import requests

    class Response:
        status_code = 403
        content = b"opaque intermediary response"
        headers = {"Content-Type": "text/html"}

        def json(self):
            raise requests.exceptions.JSONDecodeError("invalid", "", 0)

    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: Response())
    status, payload = _requests_get("https://example.invalid", {}, {}, 1.0)
    assert status == 403
    assert payload["status"] == "NON_JSON_RESPONSE"
    assert payload["content_type"] == "text/html"
    assert payload["body_length"] == len(Response.content)
    assert "opaque intermediary response" not in str(payload)
