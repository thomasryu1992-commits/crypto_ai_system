"""L2: live-strategy order final guard — the strictest fail-closed gate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from crypto_ai_system.execution import live_order_final_guard as guard

CONFIRM = "I_UNDERSTAND_THIS_TRADES_LIVE_FUNDS_AUTONOMOUSLY"


def _intent(notional=50.0):
    return {
        "status": "ORDER_INTENT_CREATED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.001,
        "order_notional_usdt": notional,
        "notional_usdt": notional,
        "connectivity_test": False,
        "risk_gate_id": "rg_live_1",
        "profile_id": "p1",
    }


def _enable_settings(monkeypatch):
    """Satisfy every config gate + the loss/promotion/count runtime checks, but
    leave the risk-gate verification to whatever the test wants."""
    for name, val in {
        "LIVE_STRATEGY_ORDER_ENABLED": True,
        "LIVE_STRATEGY_PLACE_ORDER_ENABLED": True,
        "LIVE_STRATEGY_MANUAL_KILL_SWITCH": False,
        "LIVE_STRATEGY_CONFIRMATION": CONFIRM,
        "LIVE_STRATEGY_CONFIRMATION_PHRASE": CONFIRM,
        "LIVE_STRATEGY_BASE_URL": "https://fapi.binance.com",
        "LIVE_STRATEGY_API_KEY": "k",
        "LIVE_STRATEGY_API_SECRET": "s",
        "LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT": 60.0,
        "LIVE_STRATEGY_ABSOLUTE_MAX_NOTIONAL_USDT": 200.0,
        "LIVE_STRATEGY_MAX_DAILY_ORDER_COUNT": 5,
        "LIVE_STRATEGY_MAX_OPEN_NOTIONAL_USDT": 120.0,
        "LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT": 20.0,
    }.items():
        monkeypatch.setattr(settings, name, val, raising=False)
    monkeypatch.setattr(guard, "count_today", lambda: 0)
    monkeypatch.setattr(guard, "daily_loss_limit_breached", lambda limit: False)
    monkeypatch.setattr(guard, "live_promotion_ready", lambda: True)


@pytest.fixture
def enabled(monkeypatch):
    """Every gate satisfied; risk-gate verification stubbed to pass."""
    _enable_settings(monkeypatch)
    monkeypatch.setattr(guard, "_verify_live_risk_gate", lambda intent: (True, []))


def test_blocked_by_default():
    result = guard.evaluate_live_order_final_guard(_intent())
    assert result["status"] == "BLOCKED"
    assert result["approved"] is False


def test_ready_when_all_gates_pass(enabled):
    result = guard.evaluate_live_order_final_guard(_intent(), current_open_notional_usdt=0.0)
    assert result["status"] == "READY", result["blocks"]


@pytest.mark.parametrize("flag", ["LIVE_STRATEGY_ORDER_ENABLED", "LIVE_STRATEGY_PLACE_ORDER_ENABLED"])
def test_enable_flags_required(enabled, monkeypatch, flag):
    monkeypatch.setattr(settings, flag, False, raising=False)
    assert guard.evaluate_live_order_final_guard(_intent())["approved"] is False


def test_confirmation_required(enabled, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_STRATEGY_CONFIRMATION", "", raising=False)
    assert guard.evaluate_live_order_final_guard(_intent())["approved"] is False


def test_canary_confirmation_does_not_authorize(enabled, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_STRATEGY_CONFIRMATION",
                        "I_UNDERSTAND_THIS_PLACES_A_REAL_LIVE_MAINNET_ORDER", raising=False)
    assert guard.evaluate_live_order_final_guard(_intent())["approved"] is False


def test_kill_switch_blocks(enabled, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_STRATEGY_MANUAL_KILL_SWITCH", True, raising=False)
    r = guard.evaluate_live_order_final_guard(_intent())
    assert r["approved"] is False and any("KILL_SWITCH" in b for b in r["blocks"])


def test_daily_loss_breaker_blocks(enabled, monkeypatch):
    monkeypatch.setattr(guard, "daily_loss_limit_breached", lambda limit: True)
    r = guard.evaluate_live_order_final_guard(_intent())
    assert r["approved"] is False and any("loss" in b.lower() for b in r["blocks"])


def test_promotion_gate_blocks(enabled, monkeypatch):
    monkeypatch.setattr(guard, "live_promotion_ready", lambda: False)
    r = guard.evaluate_live_order_final_guard(_intent())
    assert r["approved"] is False and any("promotion" in b for b in r["blocks"])


def test_connectivity_intent_rejected(enabled):
    intent = _intent()
    intent["connectivity_test"] = True
    r = guard.evaluate_live_order_final_guard(intent)
    assert r["approved"] is False and any("connectivity" in b for b in r["blocks"])


def test_non_live_host_blocks(enabled, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_STRATEGY_BASE_URL", "https://testnet.binancefuture.com", raising=False)
    assert guard.evaluate_live_order_final_guard(_intent())["approved"] is False


def test_notional_over_cap_blocks(enabled):
    assert guard.evaluate_live_order_final_guard(_intent(notional=999.0))["approved"] is False


def test_absolute_ceiling_bounds_cap(enabled, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT", 10_000.0, raising=False)
    r = guard.evaluate_live_order_final_guard(_intent(notional=500.0))
    assert r["approved"] is False and any("ceiling" in b for b in r["blocks"])


def test_daily_count_cap_blocks(enabled, monkeypatch):
    monkeypatch.setattr(guard, "count_today", lambda: 5)
    r = guard.evaluate_live_order_final_guard(_intent())
    assert r["approved"] is False and any("daily order count" in b for b in r["blocks"])


def test_open_exposure_cap_blocks(enabled):
    # 100 already open + 50 new = 150 > 120 cap
    r = guard.evaluate_live_order_final_guard(_intent(notional=50.0), current_open_notional_usdt=100.0)
    assert r["approved"] is False and any("exposure" in b for b in r["blocks"])


def test_testnet_risk_gate_record_rejected_for_live(monkeypatch):
    # P0-2: a stage='testnet' RiskGate record must NOT authorize a live order.
    # Uses the REAL _verify_live_risk_gate (no stub) so the stage check runs.
    _enable_settings(monkeypatch)

    def fake_get(risk_gate_id, **kw):
        return {"risk_gate_id": risk_gate_id, "approved": True, "stage": "testnet",
                "profile_id": "p1", "expires_at_utc": "2999-01-01T00:00:00Z"}

    import crypto_ai_system.registry.risk_gate_registry as rgr
    monkeypatch.setattr(rgr, "get_risk_gate_record", fake_get)
    r = guard.evaluate_live_order_final_guard(_intent())
    assert r["approved"] is False
    assert any("STAGE_MISMATCH" in b for b in r["blocks"])
