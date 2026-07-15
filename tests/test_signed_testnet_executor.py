"""Executor-branch tests for the signed-testnet path (mocked adapter)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution import order_executor
from crypto_ai_system.execution import signed_testnet_adapter as _adapter_mod
from crypto_ai_system.execution import signed_testnet_final_guard as _guard_mod


def _intent():
    return {
        "status": "ORDER_INTENT_CREATED",
        "execution_stage": "signed_testnet",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 0.001,
        "client_order_id": "CAI_BTCUSDT_LONG_abc",
        "order_notional_usdt": 4.0,
        "pre_order_risk_gate_approved": True,
        "risk_gate_id": "rg_1",
    }


class _FakeAdapter:
    last_submitted = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def submit_order(self, intent):
        _FakeAdapter.last_submitted = intent
        return {
            "ok": True,
            "submitted": True,
            "exchange_order_id": 555,
            "client_order_id": intent["client_order_id"],
        }


def test_executor_submits_when_guard_ready(monkeypatch):
    monkeypatch.setattr(
        _guard_mod,
        "evaluate_signed_testnet_final_guard",
        lambda i: {"status": "READY", "approved": True, "blocks": [], "repairs": []},
    )
    monkeypatch.setattr(_adapter_mod, "SignedTestnetAdapter", _FakeAdapter)
    monkeypatch.setattr(_guard_mod, "record_submission", lambda: 1)

    result = order_executor.execute_order_intent(_intent())

    assert result["status"] == "SIGNED_TESTNET_ORDER_SUBMITTED"
    assert result["state"] == "SUBMITTED"
    assert result["exchange_order_id"] == 555
    assert result["external_order_submission_performed"] is True
    assert _FakeAdapter.last_submitted["client_order_id"] == "CAI_BTCUSDT_LONG_abc"


def test_executor_blocks_when_guard_not_ready(monkeypatch):
    submitted = {"called": False}

    class _NoAdapter:
        def __init__(self, **kwargs):
            submitted["called"] = True

        def submit_order(self, intent):  # pragma: no cover - must not run
            submitted["called"] = True
            return {}

    monkeypatch.setattr(
        _guard_mod,
        "evaluate_signed_testnet_final_guard",
        lambda i: {"status": "BLOCKED", "approved": False, "blocks": ["nope"], "repairs": []},
    )
    monkeypatch.setattr(_adapter_mod, "SignedTestnetAdapter", _NoAdapter)

    result = order_executor.execute_order_intent(_intent())

    assert result["status"] == "SIGNED_TESTNET_BLOCKED"
    assert result["state"] == "REJECTED"
    assert result["external_order_submission_performed"] is False
    assert submitted["called"] is False  # nothing was signed or sent
