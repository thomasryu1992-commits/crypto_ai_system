"""Network-free tests for the signed testnet order adapter."""

from __future__ import annotations

import hashlib
import hmac
import sys
from pathlib import Path
from urllib.parse import urlencode

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution.signed_testnet_adapter import (
    SignedTestnetAdapter,
    NonTestnetHostError,
)


def _intent():
    return {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.001,
        "client_order_id": "CAI_BTCUSDT_LONG_abc123",
        "entry_price": 64000.0,
    }


def _capture_transport(status=200, body=None):
    captured = {}

    def transport(method, url, params, headers, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = dict(params)
        captured["headers"] = dict(headers)
        return status, (body if body is not None else {"orderId": 999, "status": "NEW"})

    return transport, captured


def test_rejects_non_testnet_host():
    with pytest.raises(NonTestnetHostError):
        SignedTestnetAdapter("k", "s", base_url="https://fapi.binance.com")


def test_requires_key_and_secret():
    with pytest.raises(ValueError):
        SignedTestnetAdapter("", "", base_url="https://testnet.binancefuture.com")


def test_submit_builds_expected_params_and_signs():
    transport, captured = _capture_transport()
    adapter = SignedTestnetAdapter("mykey", "mysecret", transport=transport)

    result = adapter.submit_order(_intent())

    p = captured["params"]
    assert p["symbol"] == "BTCUSDT"
    assert p["side"] == "BUY"
    assert p["type"] == "MARKET"
    assert p["quantity"] == 0.001
    assert p["newClientOrderId"] == "CAI_BTCUSDT_LONG_abc123"
    assert "timestamp" in p and "recvWindow" in p
    assert captured["headers"]["X-MBX-APIKEY"] == "mykey"

    # Signature must be HMAC-SHA256 over the query string (params minus signature).
    signature = dict(p)
    sent_sig = signature.pop("signature")
    expected = hmac.new(
        b"mysecret", urlencode(signature).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert sent_sig == expected

    assert result["submitted"] is True
    assert result["exchange_order_id"] == 999


def test_reduce_only_adds_reduce_only_param():
    transport, captured = _capture_transport()
    adapter = SignedTestnetAdapter("k", "s", transport=transport)
    intent = _intent()
    intent["reduce_only"] = True
    adapter.submit_order(intent)
    assert captured["params"]["reduceOnly"] == "true"


def test_open_order_has_no_reduce_only_param():
    transport, captured = _capture_transport()
    adapter = SignedTestnetAdapter("k", "s", transport=transport)
    adapter.submit_order(_intent())
    assert "reduceOnly" not in captured["params"]


def test_result_redacts_signature_and_never_exposes_secret():
    transport, _ = _capture_transport()
    adapter = SignedTestnetAdapter("mykey", "supersecret", transport=transport)

    result = adapter.submit_order(_intent())

    assert result["request"]["signature"] == "***redacted***"
    assert "supersecret" not in repr(result)


def test_http_error_is_not_submitted_and_is_classified():
    transport, _ = _capture_transport(status=400, body={"code": -1102, "msg": "bad"})
    adapter = SignedTestnetAdapter("k", "s", transport=transport)

    result = adapter.submit_order(_intent())

    assert result["submitted"] is False
    assert result["ok"] is False
    assert result["http_status"] == 400
    assert result["classification"]["state"] == "REJECTED"


def test_transport_exception_fails_closed():
    def boom(method, url, params, headers, timeout):
        raise TimeoutError("network down")

    adapter = SignedTestnetAdapter("k", "s", transport=boom)
    result = adapter.submit_order(_intent())

    assert result["ok"] is False
    assert result["submitted"] is False
    assert "classification" in result
