"""Tests for the signed-testnet final guard and trading-agent stage routing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from crypto_ai_system.execution import signed_testnet_final_guard as guard
from crypto_ai_system.pipeline import trading_agent

CONFIRM_PHRASE = "I_UNDERSTAND_THIS_PLACES_REAL_ORDERS"


def _ready_intent():
    # A connectivity-harness intent: exercises the hard caps (notional/daily/key
    # scope/host) without requiring a strategy RiskGate record (P0-2 split).
    return {
        "status": "ORDER_INTENT_CREATED",
        "symbol": "BTCUSDT",
        "quantity": 0.001,
        "order_notional_usdt": 4.0,
        "connectivity_test": True,
        "pre_order_risk_gate_approved": True,
        "risk_gate_id": "connectivity_test_123",
    }


@pytest.fixture
def enabled(monkeypatch):
    """All config gates satisfied; daily count at zero."""
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
    monkeypatch.setattr(settings, "SIGNED_TESTNET_MAX_ORDER_NOTIONAL_USDT", 5.0, raising=False)
    monkeypatch.setattr(settings, "SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT", 3, raising=False)
    monkeypatch.setattr(guard, "count_today", lambda: 0)


def test_guard_blocked_by_default():
    # No monkeypatching: shipped defaults must block.
    result = guard.evaluate_signed_testnet_final_guard(_ready_intent())
    assert result["status"] == "BLOCKED"
    assert result["approved"] is False


def test_guard_ready_when_all_satisfied(enabled):
    result = guard.evaluate_signed_testnet_final_guard(_ready_intent())
    assert result["status"] == "READY", result
    assert result["approved"] is True


def test_guard_blocks_over_notional_cap(enabled):
    intent = _ready_intent()
    intent["order_notional_usdt"] = 10.0  # cap is 5
    result = guard.evaluate_signed_testnet_final_guard(intent)
    assert result["status"] == "BLOCKED"
    assert any("notional" in b for b in result["blocks"])


def test_guard_blocks_when_daily_cap_reached(enabled, monkeypatch):
    monkeypatch.setattr(guard, "count_today", lambda: 3)
    result = guard.evaluate_signed_testnet_final_guard(_ready_intent())
    assert result["status"] == "BLOCKED"
    assert any("daily order count" in b for b in result["blocks"])


def test_connectivity_intent_is_ready_but_not_strategy(enabled):
    result = guard.evaluate_signed_testnet_final_guard(_ready_intent())
    assert result["status"] == "READY"
    assert result["strategy_execution"] is False
    assert result["risk_gate_verified"] is False


def test_strategy_intent_without_record_is_blocked(enabled, monkeypatch):
    # A strategy order (no connectivity flag) with a risk_gate_id that has no
    # persisted record must be BLOCKED, not merely repairable (P0-2).
    import crypto_ai_system.registry.risk_gate_registry as reg

    monkeypatch.setattr(reg, "get_risk_gate_record", lambda rid, cfg=None: None)
    intent = _ready_intent()
    intent.pop("connectivity_test")
    intent["risk_gate_id"] = "rg_no_record"
    result = guard.evaluate_signed_testnet_final_guard(intent)
    assert result["status"] == "BLOCKED"
    assert result["strategy_execution"] is True
    assert result["risk_gate_verified"] is False
    assert any("strategy risk gate" in b for b in result["blocks"])


# -- stage routing ------------------------------------------------------

def test_routing_defaults_to_paper(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "ALLOW_LIVE_TRADING", False, raising=False)
    monkeypatch.setattr(settings, "ENABLE_TESTNET_ORDERS", False, raising=False)
    monkeypatch.setattr(settings, "TESTNET_SIGNED_ORDER_ENABLED", False, raising=False)
    stage, block = trading_agent.resolve_execution_stage()
    assert stage == "paper"
    assert block is None


def test_routing_blocks_live(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", True, raising=False)
    stage, block = trading_agent.resolve_execution_stage()
    assert stage is None
    assert block and "live" in block.lower()


def test_routing_testnet_requires_confirmation(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "ALLOW_LIVE_TRADING", False, raising=False)
    monkeypatch.setattr(settings, "TESTNET_SIGNED_ORDER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ENABLE_TESTNET_ORDERS", False, raising=False)
    monkeypatch.setattr(settings, "LIVE_TRADING_CONFIRMATION", "", raising=False)
    stage, block = trading_agent.resolve_execution_stage()
    assert stage is None
    assert block and "confirmation" in block.lower()


def test_routing_signed_testnet_when_confirmed(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "ALLOW_LIVE_TRADING", False, raising=False)
    monkeypatch.setattr(settings, "TESTNET_SIGNED_ORDER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ENABLE_TESTNET_ORDERS", False, raising=False)
    monkeypatch.setattr(settings, "LIVE_TRADING_CONFIRMATION", CONFIRM_PHRASE, raising=False)
    monkeypatch.setattr(settings, "LIVE_TRADING_CONFIRMATION_PHRASE", CONFIRM_PHRASE, raising=False)
    stage, block = trading_agent.resolve_execution_stage()
    assert stage == "signed_testnet"
    assert block is None
