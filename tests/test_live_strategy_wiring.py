"""L3: live-strategy execution wiring — stage routing, port selection, submit glue."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from crypto_ai_system.pipeline import trading_agent
from crypto_ai_system.execution.execution_port import select_adapter
from crypto_ai_system.execution import live_strategy_execution as lse
from crypto_ai_system.execution.live_canary_adapter import LiveCanaryAdapter

CONFIRM = "I_UNDERSTAND_THIS_TRADES_LIVE_FUNDS_AUTONOMOUSLY"


def _live_env(monkeypatch, **overrides):
    values = {
        "LIVE_STRATEGY_ORDER_ENABLED": True,
        "LIVE_STRATEGY_PLACE_ORDER_ENABLED": True,
        "LIVE_STRATEGY_MANUAL_KILL_SWITCH": False,
        "LIVE_STRATEGY_CONFIRMATION": CONFIRM,
        "LIVE_STRATEGY_CONFIRMATION_PHRASE": CONFIRM,
        # L4: the stage router also requires configured caps + a daily-loss limit.
        "LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT": 60.0,
        "LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT": 20.0,
    }
    values.update(overrides)
    for name, val in values.items():
        monkeypatch.setattr(settings, name, val, raising=False)


# -- stage routing --------------------------------------------------------------

def test_default_stage_is_paper():
    stage, reason = trading_agent.resolve_execution_stage()
    assert (stage, reason) == ("paper", None)


def test_legacy_live_flags_still_refuse(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_TRADING_ENABLED", True, raising=False)
    stage, reason = trading_agent.resolve_execution_stage()
    assert stage is None and "legacy" in reason


def test_live_without_place_flag_refuses(monkeypatch):
    _live_env(monkeypatch, LIVE_STRATEGY_PLACE_ORDER_ENABLED=False)
    stage, reason = trading_agent.resolve_execution_stage()
    assert stage is None and "PLACE_ORDER" in reason


def test_live_without_confirmation_refuses(monkeypatch):
    _live_env(monkeypatch, LIVE_STRATEGY_CONFIRMATION="")
    stage, reason = trading_agent.resolve_execution_stage()
    assert stage is None and "confirmation" in reason


def test_live_with_kill_switch_refuses(monkeypatch):
    _live_env(monkeypatch, LIVE_STRATEGY_MANUAL_KILL_SWITCH=True)
    stage, reason = trading_agent.resolve_execution_stage()
    assert stage is None and "kill switch" in reason


def test_live_without_promotion_refuses(monkeypatch):
    _live_env(monkeypatch)
    import crypto_ai_system.execution.live_promotion as promo
    monkeypatch.setattr(promo, "live_promotion_ready", lambda *a, **k: False)
    stage, reason = trading_agent.resolve_execution_stage()
    assert stage is None and "promotion" in reason


def test_live_fully_configured_routes_live(monkeypatch):
    _live_env(monkeypatch)
    import crypto_ai_system.execution.live_promotion as promo
    monkeypatch.setattr(promo, "live_promotion_ready", lambda *a, **k: True)
    stage, reason = trading_agent.resolve_execution_stage()
    assert (stage, reason) == ("live", None)


# -- port selection ---------------------------------------------------------------

def test_select_adapter_live_returns_strategy_port():
    port = select_adapter("live")
    assert port is not None and port.stage == "live"


# -- submit glue ------------------------------------------------------------------

def _intent(notional=50.0):
    return {
        "status": "ORDER_INTENT_CREATED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.001,
        "order_notional_usdt": notional,
        "notional_usdt": notional,
        "client_order_id": "live_strategy_test_1",
        "order_type_exchange": "MARKET",
        "risk_gate_id": "rg_live_1",
        "profile_id": "p1",
    }


def test_submit_blocked_by_default():
    result = lse.submit_live_strategy_order(_intent())
    assert result["external_order_submission_performed"] is False
    assert result["state"] == "REJECTED"
    assert result["mode"] == "LIVE_STRATEGY_GUARD_BLOCK"


def test_submit_and_reconcile_when_guard_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ORDER_RESULT_PATH", tmp_path / "order_result.json", raising=False)
    monkeypatch.setattr(settings, "RECONCILIATION_PATH", tmp_path / "recon.json", raising=False)
    monkeypatch.setattr(lse, "ORDER_RESULT_PATH", tmp_path / "order_result.json", raising=False)
    monkeypatch.setattr(lse, "RECONCILIATION_PATH", tmp_path / "recon.json", raising=False)

    monkeypatch.setattr(
        lse, "evaluate_live_order_final_guard",
        lambda intent, **kw: {"status": "READY", "approved": True, "blocks": [], "repairs": []},
    )
    recorded = {"n": 0}
    monkeypatch.setattr(lse, "record_submission", lambda: recorded.__setitem__("n", recorded["n"] + 1))

    def fake_transport(method, url, params, headers, timeout):
        if method == "POST":
            return 200, {"orderId": 9, "status": "FILLED", "executedQty": "0.001", "avgPrice": "60000"}
        if "positionRisk" in url:
            return 200, [{"symbol": "BTCUSDT", "positionAmt": "0.001", "entryPrice": "60000"}]
        if "balance" in url:
            return 200, [{"asset": "USDT", "balance": "100"}]
        return 200, {"orderId": 9, "status": "FILLED", "executedQty": "0.001", "avgPrice": "60000"}

    monkeypatch.setattr(
        lse, "_strategy_adapter",
        lambda: LiveCanaryAdapter("k", "s", base_url="https://fapi.binance.com", transport=fake_transport),
    )

    result = lse.submit_live_strategy_order(_intent())
    assert result["status"] == "LIVE_STRATEGY_ORDER_SUBMITTED"
    assert result["external_order_submission_performed"] is True
    assert recorded["n"] == 1

    # Persist the order result the way execute_order_intent would, then reconcile.
    from core.json_io import atomic_write_json
    atomic_write_json(tmp_path / "order_result.json", result)
    recon = lse.run_live_strategy_reconciliation()
    assert recon["mode"] == "LIVE_STRATEGY_RECONCILIATION"
    assert recon["status"] == "RECONCILED", recon.get("mismatches")


def test_reconciliation_no_submission(monkeypatch, tmp_path):
    monkeypatch.setattr(lse, "ORDER_RESULT_PATH", tmp_path / "order_result.json", raising=False)
    monkeypatch.setattr(lse, "RECONCILIATION_PATH", tmp_path / "recon.json", raising=False)
    recon = lse.run_live_strategy_reconciliation()
    assert recon["status"] == "NO_SUBMISSION"
