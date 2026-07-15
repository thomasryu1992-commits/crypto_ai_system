"""P0-1 / Phase B: paper and testnet execution go through one ExecutionPort;
the only difference between stages is the selected adapter."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution import execution_port
from crypto_ai_system.execution.execution_port import (
    BinanceTestnetAdapter,
    ExecutionPort,
    PaperExecutionAdapter,
    select_adapter,
)


def test_select_adapter_routes_by_stage():
    assert isinstance(select_adapter("paper"), PaperExecutionAdapter)
    assert isinstance(select_adapter("signed_testnet"), BinanceTestnetAdapter)
    assert isinstance(select_adapter("testnet"), BinanceTestnetAdapter)
    assert select_adapter("live") is None
    assert select_adapter("") is None
    assert select_adapter(None) is None


def test_adapters_conform_to_protocol():
    assert isinstance(PaperExecutionAdapter(), ExecutionPort)
    assert isinstance(BinanceTestnetAdapter(), ExecutionPort)


def test_paper_adapter_delegates_to_engine(monkeypatch):
    captured = {}

    def fake_engine(intent, *, risk_gate_report, market_state):
        captured["intent"] = intent
        captured["market_state"] = market_state
        return {"simulated_fill": {"fill_status": "FILLED"}, "execution_id": "e1"}

    monkeypatch.setattr(
        "crypto_ai_system.execution.paper_execution_engine_v2.execute_and_persist_paper_order",
        fake_engine,
    )
    intent = {"status": "ORDER_INTENT_CREATED", "entry_price": 100.0, "execution_stage": "paper"}
    result = PaperExecutionAdapter().submit(intent, readiness={"ready": False})

    assert captured["intent"] is intent
    assert result["mode"] == "PAPER_EXECUTION_ENGINE_V2"
    assert result["filled"] is True
    assert result["exchange_order_id"] is None


def test_testnet_adapter_blocks_when_guard_not_ready():
    # Shipped defaults: testnet order path disabled -> guard blocks, nothing signed.
    intent = {"status": "ORDER_INTENT_CREATED", "symbol": "BTCUSDT", "quantity": 0.001, "order_notional_usdt": 4.0}
    result = BinanceTestnetAdapter().submit(intent, readiness={"ready": False})

    assert result["external_order_submission_performed"] is False
    assert result["mode"] == "SIGNED_TESTNET_GUARD_BLOCK"
    assert result["state"] == "REJECTED"
