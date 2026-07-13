from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from crypto_ai_system.execution.extended_read_only_connectivity import (
    EXTENDED_TESTNET_API_BASE_URL,
    EXTENDED_TESTNET_DOCUMENTED_STREAM_BASE_URL,
    EXTENDED_TESTNET_STREAM_BASE_URL,
    P71_EVIDENCE_MAX_AGE_SECONDS,
    P71_HEARTBEAT_OBSERVATION_SECONDS,
    P71_MARKET_RULE_MAX_AGE_MS,
    P71_MAX_CLOCK_OFFSET_MS,
    P71_ORDERBOOK_MAX_AGE_MS,
    P71_PONG_TIMEOUT_SECONDS,
    P71_SDK_USER_AGENT,
    P71_SERVER_PING_INTERVAL_SECONDS,
    ExtendedPublicReadOnlyClient,
    ExtendedPublicReadOnlyPolicy,
    ExtendedReadOnlyPolicyError,
    build_p71_complete_evidence,
    build_p71_public_connectivity_evidence,
    resolve_extended_stream_endpoints,
    run_p71_public_probe,
    validate_p71_private_account_evidence,
    _websocket_error_diagnostic,
    websocket_public_snapshot_probe,
)
from external_runtime_packages.extended_read_only_probe import (
    ExtendedPrivateReadOnlyProbe,
    PrivateReadOnlyProbePolicy,
    resolve_private_stream_endpoints,
    websocket_private_account_snapshot_probe,
)
from external_runtime_packages.extended_read_only_probe.probe import (
    _requests_get,
    _websocket_error_diagnostic as _private_websocket_error_diagnostic,
)

BASE_EPOCH_MS = 1_783_810_000_000


def _market_payload():
    return {
        "status": "OK",
        "data": [
            {
                "name": "BTC-USD",
                "status": "ACTIVE",
                "tradingConfig": {"minOrderSize": "0.001", "minPriceChange": "0.1"},
            }
        ],
    }


def _orderbook_payload():
    return {
        "status": "OK",
        "data": {
            "market": "BTC-USD",
            "bids": [{"price": "100", "qty": "1"}],
            "asks": [{"price": "101", "qty": "1"}],
        },
    }


def _rate_evidence():
    return {
        "policy_applied": True,
        "attempt_count": 1,
        "retry_count": 0,
        "http_429_count": 0,
        "retry_after_seen": False,
        "retry_delays_seconds": [],
        "max_attempts": 3,
        "exhausted": False,
    }


def _rest_response(payload, *, received_ms=BASE_EPOCH_MS, status=200, blocked=False):
    return {
        "called": True,
        "blocked": blocked,
        "method": "GET",
        "path": "/info/test",
        "http_status": status,
        "payload": payload,
        "received_at_epoch_ms": received_ms,
        "received_at_utc": "2026-07-12T00:00:00Z",
        "redirect_blocked": False,
        "rate_limit_evidence": _rate_evidence(),
    }


def _valid_public_stream_result():
    return {
        "received": True,
        "message": {
            "type": "SNAPSHOT",
            "data": {
                "m": "BTC-USD",
                "b": [{"p": "100", "q": "1"}],
                "a": [{"p": "101", "q": "1"}],
            },
            "ts": BASE_EPOCH_MS,
            "seq": 1,
        },
        "first_message_sha256": "1" * 64,
        "last_message_sha256": "2" * 64,
        "latency_ms": 1.0,
        "session_duration_ms": P71_HEARTBEAT_OBSERVATION_SECONDS * 1000,
        "connection_attempts": 1,
        "reconnect_count": 0,
        "reconnect_reasons": [],
        "resync_performed": False,
        "resync_snapshot_received": False,
        "message_count": 2,
        "initial_snapshot_valid": True,
        "snapshot_received": True,
        "first_sequence": 1,
        "last_sequence": 2,
        "sequence_valid": True,
        "sequence_gap_count": 0,
        "stream_market_valid": True,
        "server_timestamp_present": True,
        "max_abs_clock_offset_ms": 125,
        "clock_offset_within_limit": True,
        "heartbeat_policy_configured": True,
        "server_ping_interval_seconds": P71_SERVER_PING_INTERVAL_SECONDS,
        "pong_timeout_seconds": P71_PONG_TIMEOUT_SECONDS,
        "automatic_control_frame_pong_capability": True,
        "server_ping_observed_directly": False,
        "client_pong_observed_directly": False,
        "heartbeat_evidence_mode": "INFERRED_FROM_CONNECTION_SURVIVAL",
        "heartbeat_observation_required_seconds": P71_HEARTBEAT_OBSERVATION_SECONDS,
        "heartbeat_window_observed": True,
        "connection_survived_heartbeat_window": True,
        "attempt_diagnostics": [],
    }


def _rest_get(url, _params, headers, _timeout):
    assert headers == {"User-Agent": P71_SDK_USER_AGENT}
    assert "X-Api-Key" not in headers
    return 200, _market_payload() if url.endswith("/info/markets") else _orderbook_payload(), {}


def _valid_private_stream_result(*, balance_present=True, position_count=0, open_order_count=0):
    return {
        "actual_network_read_performed": True,
        "first_message_sha256": "3" * 64,
        "last_message_sha256": "4" * 64,
        "session_duration_ms": P71_HEARTBEAT_OBSERVATION_SECONDS * 1000,
        "connection_attempts": 1,
        "reconnect_count": 0,
        "reconnect_reasons": [],
        "resync_performed": False,
        "resync_snapshot_received": False,
        "message_count": 2,
        "initial_snapshot_valid": True,
        "first_sequence": 1,
        "last_sequence": 2,
        "sequence_valid": True,
        "position_count": position_count,
        "open_order_count": open_order_count,
        "balance_present": balance_present,
        "market_scope_valid": True,
        "server_timestamp_present": True,
        "max_abs_clock_offset_ms": 100,
        "clock_evidence_valid": True,
        "heartbeat_policy_valid": True,
        "server_ping_interval_seconds": P71_SERVER_PING_INTERVAL_SECONDS,
        "pong_timeout_seconds": P71_PONG_TIMEOUT_SECONDS,
        "automatic_control_frame_pong_capability": True,
        "server_ping_observed_directly": False,
        "client_pong_observed_directly": False,
        "heartbeat_evidence_mode": "INFERRED_FROM_CONNECTION_SURVIVAL",
        "heartbeat_observation_required_seconds": P71_HEARTBEAT_OBSERVATION_SECONDS,
        "heartbeat_window_observed": True,
        "connection_survived_heartbeat_window": True,
        "no_secret_scan_passed": True,
        "attempt_diagnostics": [],
    }


def _private_transport(url, _params, headers, _timeout):
    assert headers["X-Api-Key"] == "test-only-api-key"
    if url.endswith("/user/account/info"):
        return 200, {"status": "OK", "data": {"id": 101, "status": "ACTIVE", "l2Vault": 202}}, {}
    if url.endswith("/user/balance"):
        return 200, {
            "status": "OK",
            "data": {"balance": "100", "equity": "100", "availableForTrade": "90"},
        }, {}
    if url.endswith("/user/positions") or url.endswith("/user/orders"):
        return 200, {"status": "OK", "data": []}, {}
    raise AssertionError(url)


def _private_receipt(*, source_is_fixture=False, stream_result=None):
    probe = ExtendedPrivateReadOnlyProbe(
        api_key="test-only-api-key",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
            source_is_fixture=source_is_fixture,
        ),
        transport=_private_transport,
        stream_probe=lambda *_args: stream_result or _valid_private_stream_result(),
        sleep_fn=lambda _seconds: None,
        random_fn=lambda: 0.0,
    )
    return probe.run()


def test_p71_public_probe_accepts_fresh_rest_and_hardened_stream_without_completing_private_gate(monkeypatch):
    monkeypatch.setattr("crypto_ai_system.execution.extended_read_only_connectivity._epoch_ms", lambda: BASE_EPOCH_MS)
    observed = {}

    def stream_probe(url, headers, _timeout):
        observed["url"] = url
        observed["headers"] = headers
        return _valid_public_stream_result()

    evidence = run_p71_public_probe(network_enabled=True, rest_get=_rest_get, stream_probe=stream_probe)
    assert observed["url"] == f"{EXTENDED_TESTNET_STREAM_BASE_URL}/orderbooks/BTC-USD?depth=1"
    assert observed["headers"] == {"User-Agent": P71_SDK_USER_AGENT}
    assert evidence["public_connectivity_valid"] is True
    assert evidence["public_rest_valid"] is True
    assert evidence["market_rules_fresh"] is True
    assert evidence["orderbook_fresh"] is True
    assert evidence["public_rest_rate_limit_policy_valid"] is True
    assert evidence["public_stream_valid"] is True
    assert evidence["public_stream_initial_snapshot_valid"] is True
    assert evidence["public_stream_heartbeat_evidence_mode"] == "INFERRED_FROM_CONNECTION_SURVIVAL"
    assert evidence["public_stream_server_ping_observed_directly"] is False
    assert evidence["public_stream_client_pong_observed_directly"] is False
    assert evidence["public_rest_ws_consistency_valid"] is True
    assert evidence["private_account_read_evidence_valid"] is False
    assert evidence["p71_complete"] is False
    assert evidence["write_block_probe_valid"] is True


def test_p71_network_disabled_fails_closed():
    evidence = run_p71_public_probe(network_enabled=False)
    assert evidence["public_connectivity_valid"] is False
    assert "P71_MARKET_REST_NOT_CALLED" in evidence["block_reasons"]


def test_p71_rejects_wrong_venue_market_and_write_policy():
    for policy in (
        ExtendedPublicReadOnlyPolicy(api_base_url="https://api.starknet.extended.exchange/api/v1"),
        ExtendedPublicReadOnlyPolicy(stream_base_url="wss://api.starknet.extended.exchange/stream.extended.exchange/v1"),
        ExtendedPublicReadOnlyPolicy(market="ETH-USD"),
        ExtendedPublicReadOnlyPolicy(write_calls_allowed=True),
        ExtendedPublicReadOnlyPolicy(credential_headers_allowed=True),
    ):
        with pytest.raises(ExtendedReadOnlyPolicyError):
            ExtendedPublicReadOnlyClient(policy)


def test_p71_stream_endpoint_resolver_accepts_sdk_documented_and_override_hosts(monkeypatch):
    monkeypatch.delenv("EXTENDED_STREAM_URL_OVERRIDE", raising=False)
    endpoints = resolve_extended_stream_endpoints()
    bases = [item.base_url for item in endpoints]
    assert EXTENDED_TESTNET_STREAM_BASE_URL in bases
    assert EXTENDED_TESTNET_DOCUMENTED_STREAM_BASE_URL in bases

    override = EXTENDED_TESTNET_DOCUMENTED_STREAM_BASE_URL
    overridden = resolve_extended_stream_endpoints(override_base_url=override)
    assert overridden[0].base_url == override
    assert overridden[0].source == "env_override"

    with pytest.raises(ExtendedReadOnlyPolicyError):
        resolve_extended_stream_endpoints(
            override_base_url="wss://example.invalid/stream.extended.exchange/v1"
        )


def test_p71_public_probe_falls_through_stream_endpoint_candidates(monkeypatch):
    monkeypatch.setattr("crypto_ai_system.execution.extended_read_only_connectivity._epoch_ms", lambda: BASE_EPOCH_MS)
    calls = []

    def stream_probe(url, _headers, _timeout):
        calls.append(url)
        if len(calls) == 1:
            raise RuntimeError("server rejected WebSocket connection: HTTP 503")
        return _valid_public_stream_result()

    evidence = run_p71_public_probe(
        network_enabled=True,
        rest_get=_rest_get,
        stream_probe=stream_probe,
        stream_url_override=EXTENDED_TESTNET_STREAM_BASE_URL,
    )
    assert len(calls) == 2
    assert calls[0] == f"{EXTENDED_TESTNET_STREAM_BASE_URL}/orderbooks/BTC-USD?depth=1"
    assert calls[1] == f"{EXTENDED_TESTNET_DOCUMENTED_STREAM_BASE_URL}/orderbooks/BTC-USD?depth=1"
    assert evidence["public_stream_valid"] is True
    assert evidence["public_stream_endpoint_source"] == "documented_testnet"
    assert evidence["public_stream_attempt_diagnostics"][0]["http_status"] == 503


def test_p71_public_stream_handshake_rejection_is_classified_without_rest_fallback_completion(monkeypatch):
    monkeypatch.setattr("crypto_ai_system.execution.extended_read_only_connectivity._epoch_ms", lambda: BASE_EPOCH_MS)

    def stream_probe(url, _headers, _timeout):
        if "api." in url:
            raise RuntimeError("server rejected WebSocket connection: HTTP 503")
        raise RuntimeError("server rejected WebSocket connection: HTTP 403")

    evidence = run_p71_public_probe(
        network_enabled=True,
        rest_get=_rest_get,
        stream_probe=stream_probe,
        stream_url_override=EXTENDED_TESTNET_STREAM_BASE_URL,
    )
    assert evidence["public_rest_valid"] is True
    assert evidence["public_stream_valid"] is False
    assert evidence["rest_market_data_fallback_available"] is True
    assert evidence["rest_market_data_fallback_counts_as_websocket_evidence"] is False
    assert "P71_PUBLIC_STREAM_HANDSHAKE_REJECTED_HTTP_503" in evidence["block_reasons"]
    assert "P71_PUBLIC_STREAM_HANDSHAKE_REJECTED_HTTP_403" in evidence["block_reasons"]
    assert "P71_PUBLIC_STREAM_SNAPSHOT_MISSING" in evidence["block_reasons"]


def test_p71_public_rest_rate_limit_retries_retry_after_then_succeeds(monkeypatch):
    monkeypatch.setattr("crypto_ai_system.execution.extended_read_only_connectivity._epoch_ms", lambda: BASE_EPOCH_MS)
    calls = {}
    delays = []

    def transport(url, _params, _headers, _timeout):
        calls[url] = calls.get(url, 0) + 1
        if calls[url] == 1:
            return 429, {"status": "ERROR"}, {"Retry-After": "2"}
        return 200, _market_payload() if url.endswith("/info/markets") else _orderbook_payload(), {}

    evidence = run_p71_public_probe(
        network_enabled=True,
        rest_get=transport,
        stream_probe=lambda *_args: _valid_public_stream_result(),
        sleep_fn=delays.append,
        random_fn=lambda: 0.0,
    )
    assert evidence["public_rest_valid"] is True
    assert evidence["market_rate_limit_evidence"]["retry_count"] == 1
    assert evidence["orderbook_rate_limit_evidence"]["retry_count"] == 1
    assert delays == [2.0, 2.0]


def test_p71_public_rest_redirect_fails_closed(monkeypatch):
    monkeypatch.setattr("crypto_ai_system.execution.extended_read_only_connectivity._epoch_ms", lambda: BASE_EPOCH_MS)

    def transport(_url, _params, _headers, _timeout):
        return 302, {"status": "REDIRECT"}, {"Location": "https://evil.invalid"}

    evidence = run_p71_public_probe(
        network_enabled=True,
        rest_get=transport,
        stream_probe=lambda *_args: _valid_public_stream_result(),
        sleep_fn=lambda _seconds: None,
    )
    assert evidence["public_rest_valid"] is False
    assert "P71_MARKET_REST_REDIRECT_BLOCKED" in evidence["block_reasons"]


def test_p71_market_and_orderbook_freshness_are_required():
    observed = BASE_EPOCH_MS
    evidence = build_p71_public_connectivity_evidence(
        market_response=_rest_response(_market_payload(), received_ms=observed - P71_MARKET_RULE_MAX_AGE_MS - 1),
        orderbook_response=_rest_response(_orderbook_payload(), received_ms=observed - P71_ORDERBOOK_MAX_AGE_MS - 1),
        stream_response={"called": True, **_valid_public_stream_result()},
        write_block_probe={"called": False, "blocked": True, "reason": "P71_WRITE_CALL_BLOCKED"},
        observed_at_epoch_ms=observed,
    )
    assert evidence["public_rest_valid"] is False
    assert "P71_MARKET_RULES_STALE_OR_UNTIMED" in evidence["block_reasons"]
    assert "P71_ORDERBOOK_STALE_OR_UNTIMED" in evidence["block_reasons"]


def test_p71_public_rest_ws_orderbook_consistency_is_required():
    stream = _valid_public_stream_result()
    stream["message"] = copy.deepcopy(stream["message"])
    stream["message"]["data"]["b"] = [{"p": "150", "q": "1"}]
    stream["message"]["data"]["a"] = [{"p": "151", "q": "1"}]
    evidence = build_p71_public_connectivity_evidence(
        market_response=_rest_response(_market_payload()),
        orderbook_response=_rest_response(_orderbook_payload()),
        stream_response={"called": True, **stream},
        write_block_probe={"called": False, "blocked": True, "reason": "P71_WRITE_CALL_BLOCKED"},
        observed_at_epoch_ms=BASE_EPOCH_MS,
    )
    assert evidence["public_stream_valid"] is False
    assert "P71_PUBLIC_REST_WS_ORDERBOOK_INCONSISTENT" in evidence["block_reasons"]


class _FakeClock:
    def __init__(self):
        self.monotonic_value = 0.0
        self.wall_value = BASE_EPOCH_MS / 1000

    def monotonic(self):
        return self.monotonic_value

    def wall(self):
        return self.wall_value

    def advance(self, seconds):
        self.monotonic_value += seconds
        self.wall_value += seconds


class _FakeWs:
    def __init__(self, clock, messages):
        self.clock = clock
        self.messages = list(messages)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def recv(self, timeout):
        if self.messages:
            self.clock.advance(0.1)
            return json.dumps(self.messages.pop(0))
        self.clock.advance(timeout)
        raise TimeoutError


def _public_snapshot(seq=1):
    return {
        "type": "SNAPSHOT",
        "data": {"m": "BTC-USD", "b": [{"p": "100", "q": "1"}], "a": [{"p": "101", "q": "1"}]},
        "ts": BASE_EPOCH_MS + 100,
        "seq": seq,
    }


def _public_delta(seq):
    return {
        "type": "DELTA",
        "data": {"m": "BTC-USD", "b": [{"p": "100", "q": "1"}], "a": [{"p": "101", "q": "1"}]},
        "ts": BASE_EPOCH_MS + 200,
        "seq": seq,
    }


def test_p71_public_sequence_gap_reconnects_and_requires_new_snapshot():
    clock = _FakeClock()
    connections = [
        _FakeWs(clock, [_public_snapshot(1), _public_delta(3)]),
        _FakeWs(clock, [_public_snapshot(1), _public_delta(2)]),
    ]

    def connect_fn(*_args, **_kwargs):
        return connections.pop(0)

    result = websocket_public_snapshot_probe(
        f"{EXTENDED_TESTNET_STREAM_BASE_URL}/orderbooks/BTC-USD?depth=1",
        {"User-Agent": P71_SDK_USER_AGENT},
        30,
        connect_fn=connect_fn,
        monotonic_fn=clock.monotonic,
        wall_time_fn=clock.wall,
        sleep_fn=lambda _seconds: None,
        observation_seconds=P71_HEARTBEAT_OBSERVATION_SECONDS,
    )
    assert result["connection_attempts"] == 2
    assert result["reconnect_count"] == 1
    assert result["reconnect_reasons"] == ["SEQUENCE_GAP"]
    assert result["resync_performed"] is True
    assert result["resync_snapshot_received"] is True
    assert result["initial_snapshot_valid"] is True
    assert result["sequence_valid"] is True


def test_p71_public_first_message_must_be_snapshot():
    clock = _FakeClock()

    def connect_fn(*_args, **_kwargs):
        return _FakeWs(clock, [_public_delta(1)])

    with pytest.raises(RuntimeError):
        websocket_public_snapshot_probe(
            f"{EXTENDED_TESTNET_STREAM_BASE_URL}/orderbooks/BTC-USD?depth=1",
            {"User-Agent": P71_SDK_USER_AGENT},
            30,
            connect_fn=connect_fn,
            monotonic_fn=clock.monotonic,
            wall_time_fn=clock.wall,
            sleep_fn=lambda _seconds: None,
            observation_seconds=P71_HEARTBEAT_OBSERVATION_SECONDS,
        )


def test_p71_heartbeat_evidence_is_inferred_not_direct():
    stream = _valid_public_stream_result()
    assert stream["heartbeat_evidence_mode"] == "INFERRED_FROM_CONNECTION_SURVIVAL"
    assert stream["server_ping_observed_directly"] is False
    assert stream["client_pong_observed_directly"] is False
    assert stream["session_duration_ms"] >= (P71_SERVER_PING_INTERVAL_SECONDS + P71_PONG_TIMEOUT_SECONDS + 2) * 1000


def test_p71_no_secret_scan_is_recursive():
    evidence = build_p71_public_connectivity_evidence(
        market_response=_rest_response(_market_payload()),
        orderbook_response=_rest_response({**_orderbook_payload(), "nested": {"api_key": "must-not-appear"}}),
        stream_response={"called": True, **_valid_public_stream_result()},
        write_block_probe={"called": False, "blocked": True, "reason": "P71_WRITE_CALL_BLOCKED"},
        observed_at_epoch_ms=BASE_EPOCH_MS,
    )
    assert evidence["public_connectivity_valid"] is False
    assert "P71_NO_SECRET_SCAN_FAILED" in evidence["block_reasons"]


def test_p71_private_probe_outputs_fresh_hashed_rest_and_stream_evidence():
    receipt = _private_receipt()
    serialized = str(receipt)
    assert "test-only-api-key" not in serialized
    assert receipt["credential_value_included"] is False
    assert receipt["write_call_performed"] is False
    assert receipt["signature_created"] is False
    assert receipt["account_id"] == 101
    assert receipt["account_status"] == "ACTIVE"
    assert receipt["account_stream_receipt"]["initial_snapshot_valid"] is True
    assert receipt["rest_ws_consistency_valid"] is True
    assert set(receipt["endpoint_receipts"]) == {"account_info", "balance", "positions", "open_orders"}
    assert validate_p71_private_account_evidence(receipt)["valid"] is True


def test_p71_private_probe_strips_credential_whitespace():
    observed = []

    def transport(url, params, headers, timeout):
        observed.append(headers["X-Api-Key"])
        return _private_transport(url, params, {**headers, "X-Api-Key": "test-only-api-key"}, timeout)

    probe = ExtendedPrivateReadOnlyProbe(
        api_key="  test-only-api-key\r\n",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
        ),
        transport=transport,
        stream_probe=lambda *_args: _valid_private_stream_result(),
    )
    probe.run()
    assert set(observed) == {"test-only-api-key"}


def test_p71_private_stream_endpoint_resolver_accepts_documented_host_and_rejects_mainnet():
    endpoints = resolve_private_stream_endpoints(override_base_url=EXTENDED_TESTNET_DOCUMENTED_STREAM_BASE_URL)
    assert endpoints[0].base_url == EXTENDED_TESTNET_DOCUMENTED_STREAM_BASE_URL
    assert endpoints[0].source == "env_override"

    with pytest.raises(ValueError):
        resolve_private_stream_endpoints(
            override_base_url="wss://api.starknet.extended.exchange/stream.extended.exchange/v1"
        )


def test_p71_private_stream_failure_returns_redacted_blocked_receipt():
    def failing_stream_probe(url, headers, _timeout):
        assert headers["X-Api-Key"] == "test-only-api-key"
        if "api." in url:
            raise RuntimeError("server rejected WebSocket connection: HTTP 503")
        raise RuntimeError("server rejected WebSocket connection: HTTP 403")

    receipt = ExtendedPrivateReadOnlyProbe(
        api_key="test-only-api-key",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
            stream_url_override=EXTENDED_TESTNET_STREAM_BASE_URL,
        ),
        transport=_private_transport,
        stream_probe=failing_stream_probe,
    ).run()
    serialized = str(receipt)
    stream_receipt = receipt["account_stream_receipt"]
    assert "test-only-api-key" not in serialized
    assert receipt["actual_network_read_performed"] is False
    assert receipt["rest_ws_consistency_valid"] is False
    assert stream_receipt["blocked"] is True
    assert stream_receipt["stream_failure_reason"] == "stream_handshake_forbidden_http_403"
    assert [item["http_status"] for item in stream_receipt["stream_attempt_diagnostics"]] == [503, 403]
    assert validate_p71_private_account_evidence(receipt)["valid"] is False


def test_p71_private_rate_limit_retries_and_records_evidence():
    calls = {}
    delays = []

    def transport(url, params, headers, timeout):
        calls[url] = calls.get(url, 0) + 1
        if calls[url] == 1:
            return 429, {"status": "ERROR"}, {"Retry-After": "1"}
        return _private_transport(url, params, headers, timeout)

    receipt = ExtendedPrivateReadOnlyProbe(
        api_key="test-only-api-key",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
        ),
        transport=transport,
        stream_probe=lambda *_args: _valid_private_stream_result(),
        sleep_fn=delays.append,
        random_fn=lambda: 0.0,
    ).run()
    assert all(item["rate_limit_evidence"]["retry_count"] == 1 for item in receipt["endpoint_receipts"].values())
    assert validate_p71_private_account_evidence(receipt)["valid"] is True
    assert delays == [1.0, 1.0, 1.0, 1.0]


def test_p71_private_zero_balance_404_requires_active_account_auth():
    def transport(url, params, headers, timeout):
        if url.endswith("/user/balance"):
            return 404, {"status": "ERROR", "error": {"code": 404, "message": "balance not found"}}, {}
        return _private_transport(url, params, headers, timeout)

    receipt = ExtendedPrivateReadOnlyProbe(
        api_key="test-only-api-key",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
        ),
        transport=transport,
        stream_probe=lambda *_args: _valid_private_stream_result(balance_present=False),
    ).run()
    balance = receipt["endpoint_receipts"]["balance"]
    assert balance["zero_balance_confirmed"] is True
    assert balance["zero_balance_basis"] == "DOCUMENTED_BALANCE_404_AFTER_ACTIVE_ACCOUNT_AUTH"
    assert validate_p71_private_account_evidence(receipt)["valid"] is True


def test_p71_private_zero_balance_404_does_not_pass_when_account_auth_invalid():
    def transport(url, params, headers, timeout):
        if url.endswith("/user/account/info"):
            return 403, {"status": "ERROR"}, {}
        if url.endswith("/user/balance"):
            return 404, {"status": "ERROR"}, {}
        return _private_transport(url, params, headers, timeout)

    receipt = ExtendedPrivateReadOnlyProbe(
        api_key="test-only-api-key",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
        ),
        transport=transport,
        stream_probe=lambda *_args: _valid_private_stream_result(balance_present=False),
    ).run()
    assert receipt["endpoint_receipts"]["balance"]["zero_balance_confirmed"] is False
    assert validate_p71_private_account_evidence(receipt)["valid"] is False


def test_p71_private_response_schema_and_market_scope_are_enforced():
    def transport(url, params, headers, timeout):
        if url.endswith("/user/positions"):
            return 200, {"status": "OK", "data": [{"market": "ETH-USD"}]}, {}
        return _private_transport(url, params, headers, timeout)

    receipt = ExtendedPrivateReadOnlyProbe(
        api_key="test-only-api-key",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
        ),
        transport=transport,
        stream_probe=lambda *_args: _valid_private_stream_result(position_count=1),
    ).run()
    validation = validate_p71_private_account_evidence(receipt)
    assert validation["valid"] is False
    assert "P71_PRIVATE_ENDPOINT_SCHEMA_INVALID:positions" in validation["block_reasons"]


def test_p71_private_rest_ws_consistency_is_required():
    receipt = _private_receipt(stream_result=_valid_private_stream_result(position_count=1))
    assert receipt["rest_ws_consistency_valid"] is False
    assert "P71_PRIVATE_REST_WS_CONSISTENCY_INVALID" in validate_p71_private_account_evidence(receipt)["block_reasons"]


def _private_snapshot(seq=1):
    return {
        "type": "SNAPSHOT",
        "data": {"positions": [], "orders": [], "balance": {"balance": "100", "equity": "100", "availableForTrade": "90"}},
        "ts": BASE_EPOCH_MS + 100,
        "seq": seq,
    }


def _private_delta(seq):
    return {
        "type": "BALANCE",
        "data": {"positions": [], "orders": [], "balance": {"balance": "100", "equity": "100", "availableForTrade": "90"}},
        "ts": BASE_EPOCH_MS + 200,
        "seq": seq,
    }


def test_p71_private_sequence_gap_reconnects_and_resyncs_snapshot():
    clock = _FakeClock()
    connections = [
        _FakeWs(clock, [_private_snapshot(1), _private_delta(3)]),
        _FakeWs(clock, [_private_snapshot(1), _private_delta(2)]),
    ]

    def connect_fn(*_args, **_kwargs):
        return connections.pop(0)

    result = websocket_private_account_snapshot_probe(
        f"{EXTENDED_TESTNET_STREAM_BASE_URL}/account",
        {"User-Agent": "test", "X-Api-Key": "test-only-api-key"},
        30,
        connect_fn=connect_fn,
        monotonic_fn=clock.monotonic,
        wall_time_fn=clock.wall,
        sleep_fn=lambda _seconds: None,
        observation_seconds=P71_HEARTBEAT_OBSERVATION_SECONDS,
    )
    assert result["connection_attempts"] == 2
    assert result["reconnect_reasons"] == ["SEQUENCE_GAP"]
    assert result["resync_snapshot_received"] is True
    assert result["initial_snapshot_valid"] is True
    assert result["sequence_valid"] is True


def test_p71_private_fixture_cannot_be_real_evidence():
    validation = validate_p71_private_account_evidence(_private_receipt(source_is_fixture=True))
    assert validation["valid"] is False
    assert "P71_PRIVATE_FIXTURE_NOT_REAL_EVIDENCE" in validation["block_reasons"]


def test_p71_private_receipt_hash_tamper_is_blocked():
    receipt = _private_receipt()
    receipt["account_status"] = "SUSPENDED"
    validation = validate_p71_private_account_evidence(receipt)
    assert validation["valid"] is False
    assert "P71_PRIVATE_RECEIPT_HASH_MISMATCH" in validation["block_reasons"]


def test_p71_private_stale_and_replayed_receipts_are_blocked():
    receipt = _private_receipt()
    created = receipt["created_at_utc"]
    from datetime import datetime, timezone

    created_ms = int(datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
    stale = validate_p71_private_account_evidence(receipt, now_epoch_ms=created_ms + (P71_EVIDENCE_MAX_AGE_SECONDS + 1) * 1000)
    assert "P71_PRIVATE_EVIDENCE_STALE" in stale["block_reasons"]
    replay = validate_p71_private_account_evidence(receipt, seen_session_ids={receipt["read_session_id"]})
    assert "P71_PRIVATE_SESSION_REPLAY_DETECTED" in replay["block_reasons"]


def test_p71_private_recursive_secret_scan_catches_nested_material():
    receipt = _private_receipt()
    receipt["account_stream_receipt"]["debug"] = {"api_key": "redacted-but-forbidden-field"}
    receipt["receipt_sha256"] = "0" * 64
    validation = validate_p71_private_account_evidence(receipt)
    assert "P71_PRIVATE_RECURSIVE_NO_SECRET_SCAN_FAILED" in validation["block_reasons"]


def test_p71_complete_gate_revalidates_scope_hash_ttl_and_all_safety_invariants(monkeypatch):
    monkeypatch.setattr("crypto_ai_system.execution.extended_read_only_connectivity._epoch_ms", lambda: BASE_EPOCH_MS)
    public = run_p71_public_probe(
        network_enabled=True,
        rest_get=_rest_get,
        stream_probe=lambda *_args: _valid_public_stream_result(),
    )
    private = _private_receipt()
    # Align validation time with the private receipt's actual creation time.
    result = build_p71_complete_evidence(public_evidence=public, private_receipt=private)
    assert result["p71_complete"] is False  # public fixed test timestamp is stale relative to actual private receipt time

    # Rebuild public with current time and validate completion.
    monkeypatch.undo()
    public = run_p71_public_probe(
        network_enabled=True,
        rest_get=_rest_get,
        stream_probe=lambda *_args: _valid_public_stream_result(),
    )
    result = build_p71_complete_evidence(public_evidence=public, private_receipt=private)
    assert result["p71_complete"] is True
    assert result["ready_for_signed_testnet_execution"] is False
    assert result["testnet_order_submission_allowed"] is False

    tampered = copy.deepcopy(public)
    tampered["order_endpoint_called"] = True
    blocked = build_p71_complete_evidence(public_evidence=tampered, private_receipt=private)
    assert blocked["p71_complete"] is False
    assert any("P71_PUBLIC_UNSAFE_FLAG:order_endpoint_called" == item for item in blocked["block_reasons"])
    assert "P71_PUBLIC_EVIDENCE_HASH_MISMATCH" in blocked["block_reasons"]


def test_p71_windows_probe_cli_never_accepts_secret_value_argument():
    source = Path("external_runtime_packages/extended_read_only_probe/run_windows_probe.py").read_text(encoding="utf-8")
    assert "--api-key" not in source
    assert "--private-key" not in source
    assert "read_generic_credential_secret" in source
    assert "private_account_stream_valid" in source


def test_p71_private_transport_disables_redirect_and_sanitizes_non_json(monkeypatch):
    class Response:
        status_code = 403
        content = b"opaque intermediary response"
        headers = {"Content-Type": "text/html"}

        def json(self):
            import requests

            raise requests.exceptions.JSONDecodeError("invalid", "", 0)

    observed = {}

    def fake_get(*_args, **kwargs):
        observed.update(kwargs)
        return Response()

    monkeypatch.setattr("requests.get", fake_get)
    status, payload, headers = _requests_get("https://example.invalid", {}, {}, 1.0)
    assert status == 403
    assert observed["allow_redirects"] is False
    assert payload["status"] == "NON_JSON_RESPONSE"
    assert payload["content_type"] == "text/html"
    assert payload["body_length"] == len(Response.content)
    assert "opaque intermediary response" not in str(payload)
    assert headers["content-type"] == "text/html"


def test_p71_websocket_diagnostic_parses_http_status_from_invalid_status_message():
    exc = RuntimeError("server rejected WebSocket connection: HTTP 503")

    assert _websocket_error_diagnostic(exc)["http_status"] == 503
    assert _private_websocket_error_diagnostic(exc)["http_status"] == 503
