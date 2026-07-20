"""Bounded retry on the public kline fetch (QA fix): a transient blip must not
cost a whole cycle, but a definitive client error must not be retried."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.data.binance_futures_collector import BinanceFuturesPublicClient


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


def _client(monkeypatch, responses):
    client = BinanceFuturesPublicClient()
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        item = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(client.session, "get", fake_get)
    monkeypatch.setattr("crypto_ai_system.data.binance_futures_collector.time.sleep", lambda s: None)
    return client, calls


def test_transient_connection_error_is_retried(monkeypatch):
    client, calls = _client(monkeypatch, [
        requests.ConnectionError("blip"),
        requests.ConnectionError("blip"),
        _Response(200, {"ok": True}),
    ])
    assert client._get("/fapi/v1/klines") == {"ok": True}
    assert calls["n"] == 3


def test_5xx_is_retried(monkeypatch):
    client, calls = _client(monkeypatch, [_Response(503), _Response(200, {"ok": True})])
    assert client._get("/fapi/v1/klines") == {"ok": True}
    assert calls["n"] == 2


def test_definitive_4xx_is_not_retried(monkeypatch):
    client, calls = _client(monkeypatch, [_Response(400)])
    with pytest.raises(requests.HTTPError):
        client._get("/fapi/v1/klines")
    assert calls["n"] == 1


def test_exhausted_retries_raise(monkeypatch):
    client, calls = _client(monkeypatch, [requests.ConnectionError("down")])
    with pytest.raises(requests.ConnectionError):
        client._get("/fapi/v1/klines")
    assert calls["n"] == BinanceFuturesPublicClient.RETRY_ATTEMPTS
