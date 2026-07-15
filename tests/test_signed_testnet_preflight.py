"""Network-free tests for signed-testnet config preflight."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from crypto_ai_system.execution.signed_testnet_preflight import check_config_readiness

CONFIRM_PHRASE = "I_UNDERSTAND_THIS_PLACES_REAL_ORDERS"


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(settings, "TESTNET_SIGNED_ORDER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "SIGNED_TESTNET_PLACE_ORDER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "SIGNED_TESTNET_MANUAL_APPROVAL_REQUIRED", True, raising=False)
    monkeypatch.setattr(settings, "LIVE_TRADING_CONFIRMATION", CONFIRM_PHRASE, raising=False)
    monkeypatch.setattr(settings, "LIVE_TRADING_CONFIRMATION_PHRASE", CONFIRM_PHRASE, raising=False)
    monkeypatch.setattr(settings, "BINANCE_TESTNET", True, raising=False)
    monkeypatch.setattr(settings, "SIGNED_TESTNET_LIVE_KEY_ALLOWED", False, raising=False)
    monkeypatch.setattr(settings, "BINANCE_TESTNET_BASE_URL", "https://testnet.binancefuture.com", raising=False)
    monkeypatch.setattr(settings, "BINANCE_API_KEY", "k", raising=False)
    monkeypatch.setattr(settings, "BINANCE_API_SECRET", "s", raising=False)


def test_not_ready_by_default(monkeypatch):
    monkeypatch.setattr(settings, "TESTNET_SIGNED_ORDER_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "SIGNED_TESTNET_PLACE_ORDER_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "BINANCE_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "BINANCE_API_SECRET", "", raising=False)
    result = check_config_readiness()
    assert result["ready"] is False
    assert any("TESTNET_SIGNED_ORDER_ENABLED" in b for b in result["blocks"])
    assert any("BINANCE_API_KEY" in b for b in result["blocks"])


def test_ready_when_all_set(ready):
    result = check_config_readiness()
    assert result["ready"] is True, result
    assert result["blocks"] == []


def test_missing_secret_blocks(ready, monkeypatch):
    monkeypatch.setattr(settings, "BINANCE_API_SECRET", "", raising=False)
    result = check_config_readiness()
    assert result["ready"] is False
    assert any("BINANCE_API_SECRET" in b for b in result["blocks"])


def test_mainnet_host_blocks(ready, monkeypatch):
    monkeypatch.setattr(settings, "BINANCE_TESTNET_BASE_URL", "https://fapi.binance.com", raising=False)
    result = check_config_readiness()
    assert result["ready"] is False
    assert any("testnet host" in b for b in result["blocks"])
