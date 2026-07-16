"""Tests for the live-canary ORDER boundary: final guard, adapter, submit/reconcile.

The canary places a real mainnet order, so every test here asserts a fail-closed
property: shipped defaults block, each individual gate blocks, the adapter refuses
non-live hosts, secrets are redacted, and the pipeline never routes to it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config.settings as settings
from crypto_ai_system.execution import live_canary_final_guard as guard
from crypto_ai_system.execution.live_canary_adapter import LiveCanaryAdapter, NonLiveHostError

CONFIRM = "I_UNDERSTAND_THIS_PLACES_A_REAL_LIVE_MAINNET_ORDER"


def _intent(notional=4.0):
    return {
        "status": "ORDER_INTENT_CREATED",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.001,
        "order_notional_usdt": notional,
        "notional_usdt": notional,
        "connectivity_test": True,
        "client_order_id": "live_canary_test_1",
        "order_type_exchange": "MARKET",
    }


@pytest.fixture
def enabled(monkeypatch):
    """All config gates satisfied; preparation READY; daily count at zero."""
    monkeypatch.setattr(settings, "LIVE_CANARY_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_PLACE_ORDER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_MANUAL_APPROVAL_REQUIRED", True, raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_MANUAL_KILL_SWITCH", False, raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_CONFIRMATION", CONFIRM, raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_CONFIRMATION_PHRASE", CONFIRM, raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_BASE_URL", "https://fapi.binance.com", raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_API_KEY", "k", raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_API_SECRET", "s", raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_MAX_ORDER_NOTIONAL_USDT", 5.0, raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_ABSOLUTE_MAX_NOTIONAL_USDT", 200.0, raising=False)
    monkeypatch.setattr(settings, "LIVE_CANARY_MAX_DAILY_ORDER_COUNT", 1, raising=False)
    monkeypatch.setattr(guard, "count_today", lambda: 0)
    monkeypatch.setattr(guard, "_preparation_ready", lambda: True)


# -- final guard --------------------------------------------------------------

def test_guard_blocked_by_default():
    # Shipped defaults must block (no env overrides).
    result = guard.evaluate_live_canary_final_guard(_intent())
    assert result["status"] == "BLOCKED"
    assert result["approved"] is False


def test_guard_ready_when_all_gates_satisfied(enabled):
    result = guard.evaluate_live_canary_final_guard(_intent())
    assert result["status"] == "READY", result["blocks"]
    assert result["approved"] is True


@pytest.mark.parametrize("flag", ["LIVE_CANARY_ENABLED", "LIVE_CANARY_PLACE_ORDER_ENABLED"])
def test_guard_blocks_when_enable_flag_off(enabled, monkeypatch, flag):
    monkeypatch.setattr(settings, flag, False, raising=False)
    result = guard.evaluate_live_canary_final_guard(_intent())
    assert result["approved"] is False


def test_guard_blocks_without_confirmation(enabled, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_CANARY_CONFIRMATION", "", raising=False)
    result = guard.evaluate_live_canary_final_guard(_intent())
    assert result["approved"] is False
    assert any("confirmation" in b for b in result["blocks"])


def test_guard_blocks_with_testnet_confirmation_phrase(enabled, monkeypatch):
    # A testnet confirmation must NOT authorize a live order.
    monkeypatch.setattr(settings, "LIVE_CANARY_CONFIRMATION", "I_UNDERSTAND_THIS_PLACES_REAL_ORDERS", raising=False)
    result = guard.evaluate_live_canary_final_guard(_intent())
    assert result["approved"] is False


def test_guard_blocks_on_kill_switch(enabled, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_CANARY_MANUAL_KILL_SWITCH", True, raising=False)
    result = guard.evaluate_live_canary_final_guard(_intent())
    assert result["approved"] is False
    assert any("KILL_SWITCH" in b for b in result["blocks"])


def test_guard_blocks_when_preparation_not_ready(enabled, monkeypatch):
    monkeypatch.setattr(guard, "_preparation_ready", lambda: False)
    result = guard.evaluate_live_canary_final_guard(_intent())
    assert result["approved"] is False
    assert any("preparation" in b for b in result["blocks"])


def test_guard_blocks_non_live_host(enabled, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_CANARY_BASE_URL", "https://testnet.binancefuture.com", raising=False)
    result = guard.evaluate_live_canary_final_guard(_intent())
    assert result["approved"] is False
    assert any("host" in b for b in result["blocks"])


def test_guard_blocks_without_key(enabled, monkeypatch):
    monkeypatch.setattr(settings, "LIVE_CANARY_API_KEY", "", raising=False)
    result = guard.evaluate_live_canary_final_guard(_intent())
    assert result["approved"] is False


def test_guard_blocks_notional_over_cap(enabled):
    result = guard.evaluate_live_canary_final_guard(_intent(notional=999.0))
    assert result["approved"] is False
    assert any("exceeds cap" in b for b in result["blocks"])


def test_guard_absolute_ceiling_bounds_cap(enabled, monkeypatch):
    # Even if the operator sets a huge cap, the absolute ceiling wins.
    monkeypatch.setattr(settings, "LIVE_CANARY_MAX_ORDER_NOTIONAL_USDT", 10_000.0, raising=False)
    result = guard.evaluate_live_canary_final_guard(_intent(notional=500.0))
    assert result["approved"] is False
    assert any("ceiling" in b for b in result["blocks"])


def test_guard_blocks_when_daily_count_reached(enabled, monkeypatch):
    monkeypatch.setattr(guard, "count_today", lambda: 1)
    result = guard.evaluate_live_canary_final_guard(_intent())
    assert result["approved"] is False
    assert any("daily" in b for b in result["blocks"])


# -- adapter ------------------------------------------------------------------

def test_adapter_rejects_non_live_host():
    with pytest.raises(NonLiveHostError):
        LiveCanaryAdapter("k", "s", base_url="https://testnet.binancefuture.com")


def test_adapter_requires_credentials():
    with pytest.raises(ValueError):
        LiveCanaryAdapter("", "", base_url="https://fapi.binance.com")


def test_adapter_signs_submits_and_redacts():
    seen = {}

    def fake_transport(method, url, params, headers, timeout):
        seen["method"] = method
        seen["params"] = params
        seen["headers"] = headers
        return 200, {"orderId": 55, "status": "NEW"}

    adapter = LiveCanaryAdapter("k", "s", base_url="https://fapi.binance.com", transport=fake_transport)
    result = adapter.submit_order(_intent())
    assert result["submitted"] is True
    assert result["exchange_order_id"] == 55
    # Signature present on the wire but redacted in the returned request echo.
    assert "signature" in seen["params"]
    assert result["request"]["signature"] == "***redacted***"
    assert seen["headers"]["X-MBX-APIKEY"] == "k"


# -- submit glue --------------------------------------------------------------

def test_submit_blocks_without_submission_when_guard_fails(monkeypatch, tmp_path):
    # Shipped defaults -> guard blocks -> nothing submitted, no counter increment.
    monkeypatch.setattr(settings, "ORDER_RESULT_PATH", tmp_path / "order_result.json", raising=False)
    from crypto_ai_system.execution import live_canary_execution as exec_mod

    result = exec_mod.submit_live_canary_order(_intent())
    assert result["external_order_submission_performed"] is False
    assert result["state"] == "REJECTED"
    assert result["mode"] == "LIVE_CANARY_GUARD_BLOCK"


def test_submit_records_and_reconciles_when_ready(enabled, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ORDER_RESULT_PATH", tmp_path / "order_result.json", raising=False)
    monkeypatch.setattr(settings, "RECONCILIATION_PATH", tmp_path / "recon.json", raising=False)
    from crypto_ai_system.execution import live_canary_execution as exec_mod

    recorded = {"n": 0}
    monkeypatch.setattr(exec_mod, "record_submission", lambda: recorded.__setitem__("n", recorded["n"] + 1))

    def fake_transport(method, url, params, headers, timeout):
        if method == "POST":
            return 200, {"orderId": 7, "status": "FILLED", "executedQty": "0.001", "avgPrice": "60000"}
        if "positionRisk" in url:
            return 200, [{"symbol": "BTCUSDT", "positionAmt": "0.001", "entryPrice": "60000"}]
        if "balance" in url:
            return 200, [{"asset": "USDT", "balance": "100"}]
        return 200, {"orderId": 7, "status": "FILLED", "executedQty": "0.001", "avgPrice": "60000"}

    monkeypatch.setattr(
        exec_mod, "LiveCanaryAdapter",
        lambda **kw: LiveCanaryAdapter("k", "s", base_url="https://fapi.binance.com", transport=fake_transport),
    )

    result = exec_mod.submit_live_canary_order(_intent())
    assert result["status"] == "LIVE_CANARY_ORDER_SUBMITTED"
    assert result["external_order_submission_performed"] is True
    assert recorded["n"] == 1

    recon = exec_mod.run_live_canary_reconciliation()
    assert recon["mode"] == "LIVE_CANARY_RECONCILIATION"
    assert recon["status"] == "RECONCILED", recon.get("mismatches")


# -- pipeline isolation -------------------------------------------------------

def test_pipeline_adapter_router_never_serves_live_canary():
    # The canary is a standalone boundary; the pipeline's adapter selector must
    # not resolve the live_canary stage. (The "live" stage now resolves to the
    # separate live-STRATEGY port — itself fail-closed behind its final guard.)
    from crypto_ai_system.execution.execution_port import select_adapter

    assert select_adapter("live_canary") is None
    assert select_adapter("paper") is not None
