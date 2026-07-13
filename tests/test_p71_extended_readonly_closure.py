from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_ai_system.execution.extended_read_only_connectivity import (
    P71_HEARTBEAT_OBSERVATION_SECONDS,
    P71_PONG_TIMEOUT_SECONDS,
    P71_SDK_USER_AGENT,
    P71_SERVER_PING_INTERVAL_SECONDS,
    run_p71_public_probe,
)
from crypto_ai_system.validation.p71_extended_readonly_closure import (
    P71ClosureError,
    build_p71_closure_report,
    build_p71_redacted_attestation,
    load_registry_records,
    persist_p71_closure_outputs,
)
from external_runtime_packages.extended_read_only_probe import ExtendedPrivateReadOnlyProbe, PrivateReadOnlyProbePolicy

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


def _public_stream_result():
    return {
        "received": True,
        "message": {
            "type": "SNAPSHOT",
            "data": {"m": "BTC-USD", "b": [{"p": "100", "q": "1"}], "a": [{"p": "101", "q": "1"}]},
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
        "max_abs_clock_offset_ms": 100,
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


def _public_evidence(monkeypatch):
    monkeypatch.setattr("crypto_ai_system.execution.extended_read_only_connectivity._epoch_ms", lambda: BASE_EPOCH_MS)

    def rest_get(url, _params, headers, _timeout):
        assert headers == {"User-Agent": P71_SDK_USER_AGENT}
        return 200, _market_payload() if url.endswith("/info/markets") else _orderbook_payload(), {}

    return run_p71_public_probe(
        network_enabled=True,
        rest_get=rest_get,
        stream_probe=lambda *_args: _public_stream_result(),
        sleep_fn=lambda _seconds: None,
        random_fn=lambda: 0.0,
    )


def _private_stream_result():
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
        "position_count": 0,
        "open_order_count": 0,
        "balance_present": True,
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


def _private_receipt(monkeypatch):
    monkeypatch.setattr("external_runtime_packages.extended_read_only_probe.probe._epoch_ms", lambda: BASE_EPOCH_MS)

    def transport(url, _params, headers, _timeout):
        assert headers["X-Api-Key"] == "test-only-api-key"
        if url.endswith("/user/account/info"):
            return 200, {"status": "OK", "data": {"id": 101, "status": "ACTIVE", "l2Vault": 202}}, {}
        if url.endswith("/user/balance"):
            return 200, {"status": "OK", "data": {"balance": "100", "equity": "100", "availableForTrade": "90"}}, {}
        if url.endswith("/user/positions") or url.endswith("/user/orders"):
            return 200, {"status": "OK", "data": []}, {}
        raise AssertionError(url)

    return ExtendedPrivateReadOnlyProbe(
        api_key="test-only-api-key",
        policy=PrivateReadOnlyProbePolicy(
            credential_reference_id="os_credential_ref:p71/extended/read_only",
            network_enabled=True,
            source_is_fixture=False,
        ),
        transport=transport,
        stream_probe=lambda *_args: _private_stream_result(),
        sleep_fn=lambda _seconds: None,
        random_fn=lambda: 0.0,
    ).run()


def test_p71_closure_completes_and_attestation_is_redacted(monkeypatch):
    public = _public_evidence(monkeypatch)
    private = _private_receipt(monkeypatch)
    report = build_p71_closure_report(
        public_evidence=public,
        private_receipt=private,
        operator_session_id="p71_operator_session_test",
        now_epoch_ms=BASE_EPOCH_MS,
    )
    assert report["p71_complete"] is True
    assert report["public_websocket_valid"] is True
    assert report["private_account_websocket_valid"] is True
    assert report["ready_for_signed_testnet_execution"] is False
    assert report["testnet_order_submission_allowed"] is False
    serialized = json.dumps(report, sort_keys=True)
    assert "test-only-api-key" not in serialized
    assert "endpoint_receipts" not in serialized
    attestation = build_p71_redacted_attestation(report)
    assert attestation["p71_complete"] is True
    assert "api_key_fingerprint_sha256" not in json.dumps(attestation, sort_keys=True)


def test_p71_closure_persists_and_consumes_evidence_once(monkeypatch, tmp_path: Path):
    public = _public_evidence(monkeypatch)
    private = _private_receipt(monkeypatch)
    report = persist_p71_closure_outputs(
        project_root=tmp_path,
        public_evidence=public,
        private_receipt=private,
        operator_session_id="p71_operator_session_test_once",
        now_epoch_ms=BASE_EPOCH_MS,
    )
    assert report["p71_complete"] is True
    assert report["closure_evidence_consumed"] is True
    registry = tmp_path / "storage/registries/p71_consumed_evidence_registry.jsonl"
    records = load_registry_records(registry)
    assert len(records) == 1
    assert records[0]["public_evidence_id"] == public["evidence_id"]
    assert (tmp_path / "storage/latest/p71_extended_readonly_closure_report.json").exists()
    assert (tmp_path / "storage/latest/p71_extended_readonly_attestation.json").exists()
    assert (tmp_path / "storage/latest/P71_EXTENDED_READONLY_CLOSURE_HANDOFF.md").exists()

    replay = persist_p71_closure_outputs(
        project_root=tmp_path,
        public_evidence=public,
        private_receipt=private,
        operator_session_id="p71_operator_session_test_replay",
        now_epoch_ms=BASE_EPOCH_MS,
    )
    assert replay["p71_complete"] is False
    assert "P71_PUBLIC_EVIDENCE_REPLAY_DETECTED" in replay["block_reasons"]
    assert "P71_PRIVATE_SESSION_REPLAY_DETECTED" in replay["block_reasons"]
    assert len(load_registry_records(registry)) == 1
    canonical = json.loads((tmp_path / "storage/latest/p71_extended_readonly_closure_report.json").read_text(encoding="utf-8"))
    assert canonical["p71_complete"] is True
    attempt = json.loads((tmp_path / "storage/latest/p71_extended_readonly_closure_attempt_report.json").read_text(encoding="utf-8"))
    assert attempt["p71_complete"] is False


def test_p71_closure_blocks_mixed_session_time_skew(monkeypatch):
    public = _public_evidence(monkeypatch)
    private = _private_receipt(monkeypatch)
    private["created_at_utc"] = "2026-07-12T00:04:00Z"
    private["expires_at_utc"] = "2026-07-12T00:14:00Z"
    from crypto_ai_system.utils.audit import sha256_json

    private["receipt_sha256"] = sha256_json({key: value for key, value in private.items() if key != "receipt_sha256"})
    report = build_p71_closure_report(
        public_evidence=public,
        private_receipt=private,
        operator_session_id="p71_operator_session_skew",
        now_epoch_ms=BASE_EPOCH_MS + 240_000,
    )
    assert report["p71_complete"] is False
    assert "P71_CLOSURE_SOURCE_TIME_SKEW_EXCEEDED" in report["block_reasons"]


def test_p71_closure_blocks_tampered_source_hash(monkeypatch):
    public = _public_evidence(monkeypatch)
    private = _private_receipt(monkeypatch)
    public["market_status"] = "SUSPENDED"
    report = build_p71_closure_report(
        public_evidence=public,
        private_receipt=private,
        operator_session_id="p71_operator_session_tamper",
        now_epoch_ms=BASE_EPOCH_MS,
    )
    assert report["p71_complete"] is False
    assert "P71_PUBLIC_EVIDENCE_HASH_MISMATCH" in report["block_reasons"]


def test_p71_registry_hash_tamper_fails_closed(tmp_path: Path):
    registry = tmp_path / "registry.jsonl"
    registry.write_text('{"public_evidence_id":"x","registry_record_sha256":"' + "0" * 64 + '"}\n', encoding="utf-8")
    with pytest.raises(P71ClosureError):
        load_registry_records(registry)
