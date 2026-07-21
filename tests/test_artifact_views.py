"""Typed artifact views over the storage/latest handoff (modularization pass).

The contract: every view default mirrors the pre-existing consumer semantics,
so adopting a view never changes behavior — and empty/missing artifacts
resolve in the fail-closed direction (blocked / not filled / not reconciled).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.artifacts import (
    SCHEMA_MARKET_SNAPSHOT,
    SCHEMA_RECONCILIATION,
    SCHEMA_TRADE_DECISION,
    MarketSnapshotView,
    OrderResultView,
    ReconciliationView,
    TradeDecisionView,
)


# -- fail-closed defaults on empty artifacts ------------------------------------

def test_empty_snapshot_defaults():
    v = MarketSnapshotView.from_mapping({})
    assert v.symbol is None
    assert v.timeframe == "1h"
    assert v.trend_bias == "unknown"
    assert v.last_close is None
    assert (v.is_synthetic, v.is_fallback, v.is_stale) == (False, False, False)


def test_empty_decision_is_blocked():
    v = TradeDecisionView.from_mapping({})
    assert v.allow_order_intent is False
    assert v.pre_order_risk_gate_approved is False
    assert v.execution_stage == "paper"
    assert v.entry is None


def test_empty_order_result_is_no_trade():
    v = OrderResultView.from_mapping({})
    assert v.filled is False
    assert v.external_order_submission_performed is False
    assert v.intent == {}


def test_empty_reconciliation_is_not_reconciled():
    v = ReconciliationView.from_mapping({})
    assert v.is_reconciled is False
    assert v.mismatches == ()


# -- fallback chains match the consumers ----------------------------------------

def test_decision_entry_price_chain():
    assert TradeDecisionView.from_mapping({"entry": 100.0}).entry == 100.0
    assert TradeDecisionView.from_mapping({"entry_price": 99.0}).entry == 99.0
    assert TradeDecisionView.from_mapping({"price": 98.0}).entry == 98.0
    assert TradeDecisionView.from_mapping({"entry": "garbage"}).entry is None


def test_decision_notional_and_stage_chains():
    v = TradeDecisionView.from_mapping({"notional_usdt": 25.0, "decision_stage": "live"})
    assert v.order_notional_usdt == 25.0
    assert v.execution_stage == "live"


def test_reconciliation_actual_fields():
    v = ReconciliationView.from_mapping({
        "status": "RECONCILED",
        "actual": {"order_status": "FILLED", "avg_fill_price": "60000.5", "executed_qty": "0.001"},
        "mismatches": [],
    })
    assert v.is_reconciled is True
    assert v.actual_order_status == "FILLED"
    assert v.actual_avg_fill_price == pytest.approx(60000.5)
    assert v.actual_executed_qty == pytest.approx(0.001)


def test_snapshot_garbage_close_is_none():
    assert MarketSnapshotView.from_mapping({"last_close": "not-a-number"}).last_close is None


def test_from_file_missing_is_fail_closed(tmp_path):
    v = TradeDecisionView.from_file(tmp_path / "missing.json")
    assert v.allow_order_intent is False


# -- writers stamp schema_version -----------------------------------------------

def test_market_snapshot_builder_stamps_schema(monkeypatch):
    import builders.market_snapshot as ms
    from core.time_utils import utc_now

    candles = [{"timestamp": utc_now().isoformat(), "open": 1.0, "high": 1.0,
                "low": 1.0, "close": 1.0, "volume": 1.0}] * 3
    monkeypatch.setattr(ms, "read_json", lambda p, d: {"symbol": "BTCUSDT", "candles": candles})
    monkeypatch.setattr(ms, "atomic_write_json", lambda p, payload: None)
    monkeypatch.setattr(ms, "log_event", lambda *a, **k: None)
    snap = ms.build_market_snapshot()
    assert snap["schema_version"] == SCHEMA_MARKET_SNAPSHOT


def test_strategy_decision_stamps_schema():
    from crypto_ai_system.strategy_factory.strategy_trade_decision import build_strategy_trade_decision

    d = build_strategy_trade_decision(
        router_result={"status": "NO_ENTRY", "direction": None},
        primary_spec={"exit_rules": {}}, feature_row={}, market_snapshot={},
        research_permission={}, pre_order_risk_gate={}, attribution={},
        data_health={}, risk={}, now="2026-07-21T00:00:00Z",
    )
    assert d["schema_version"] == SCHEMA_TRADE_DECISION


def test_reconciler_fallback_stamps_schema(monkeypatch, tmp_path):
    import crypto_ai_system.execution.reconciler as rec
    from core.json_io import atomic_write_json
    from crypto_ai_system.config import AppConfig

    atomic_write_json(tmp_path / "order_result.json", {"status": "PAPER"})
    monkeypatch.setattr(rec, "ORDER_RESULT_PATH", tmp_path / "order_result.json")
    monkeypatch.setattr(rec, "PAPER_STATE_PATH", tmp_path / "paper_state.json")
    monkeypatch.setattr(rec, "RECONCILIATION_PATH", tmp_path / "recon.json")
    monkeypatch.setattr(rec, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(
        "crypto_ai_system.config.load_config",
        lambda root=".": AppConfig(root=tmp_path, settings={"storage": {"latest_dir": "latest"}}),
    )
    result = rec.run_reconciler()
    assert result["schema_version"] == SCHEMA_RECONCILIATION
    # And the view round-trips it.
    assert ReconciliationView.from_mapping(result).schema_version == SCHEMA_RECONCILIATION


# -- CycleInputs delegates to the typed view ------------------------------------

def test_cycle_inputs_market_delegation():
    from crypto_ai_system.pipeline.contracts import ValidationVerdict
    from crypto_ai_system.pipeline.trading_steps.context import CycleInputs

    snapshot = {"last_close": 60000.0, "timeframe": "4h", "trend_bias": "bullish",
                "is_stale": True, "symbol": "BTCUSDT"}
    inputs = CycleInputs(cfg=None, stage="paper", cycle_id="c1", now=None,
                         snapshot=snapshot, latest_candle=None,
                         verdict=ValidationVerdict.fail_closed(), routing=None)
    assert inputs.last_close == 60000.0
    assert inputs.timeframe == "4h"
    assert inputs.regime == "bullish"
    assert inputs.market.is_stale is True
    assert inputs.market.symbol == "BTCUSDT"
    assert inputs.snapshot is snapshot  # raw mapping preserved for outputs
