"""Factory runner: builds the backtest frame, populates the pool, persists state."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.json_io import read_json
from crypto_ai_system.backtesting.backtest_agent import AbsoluteGate
from crypto_ai_system.backtesting.cost_model import CostModel
from crypto_ai_system.config import load_config
from crypto_ai_system.registry.base_registry import load_registry_records
from crypto_ai_system.strategy_factory.active_strategy_pool import load_pool, occupying_entries
from crypto_ai_system.strategy_factory.factory_runner import load_counters, run_factory, run_generation
from crypto_ai_system.strategy_factory.runtime_feature_adapter import build_backtest_frame

NOW = "2026-07-16T00:00:00Z"
FREE = CostModel(0.0, 0.0)
# Lenient gate suited to a short synthetic history.
GATE = AbsoluteGate(min_trade_count=3, min_expectancy_r=0.05, min_profit_factor=1.05,
                    min_walk_forward_pass_rate=0.5, max_drawdown_r=15.0, min_temporal_stability=0.15)


def _uptrend_candles(n=240):
    # Rising base with a deep oscillation so RSI swings wide (pullbacks + rallies)
    # and a trend-pullback strategy can actually fire and win.
    rows, base = [], 60000.0
    for i in range(n):
        base *= 1.003
        c = base * (1 + 0.05 * math.sin(2 * math.pi * i / 16))
        rows.append({"timestamp": f"2026-07-01 {i // 24:02d}:{i % 24:02d}:00+00:00",
                     "open": c * 0.999, "high": c * 1.006, "low": c * 0.994, "close": c, "volume": 1000 + i})
    return rows


# -- backtest frame -----------------------------------------------------------

def test_build_backtest_frame_full():
    frame = build_backtest_frame(_uptrend_candles(120), cfg=load_config("."))
    assert isinstance(frame, pd.DataFrame)
    assert len(frame) == 120
    for col in ("ma20", "ma50", "rsi", "adx", "atr", "market_regime"):
        assert col in frame.columns


def test_build_backtest_frame_too_few():
    assert build_backtest_frame([], cfg=load_config(".")).empty


# -- run_generation persistence -----------------------------------------------

def test_run_generation_persists_pool_and_counters(tmp_path):
    pool_file = str(tmp_path / "pool.json")
    state_file = str(tmp_path / "state.json")
    frame = build_backtest_frame(_uptrend_candles(), cfg=load_config("."))

    report = run_generation(frame, pool_file=pool_file, state_file=state_file,
                            cost=FREE, gate=GATE, now=NOW)
    assert report["generation_id"] == "GEN-001"
    # Counters advanced and persisted.
    counters = load_counters(state_file)
    assert counters["generation_seq"] == 2
    assert counters["strategy_seq"] >= 1
    assert Path(pool_file).exists()


def test_counters_advance_across_generations(tmp_path):
    pool_file = str(tmp_path / "pool.json")
    state_file = str(tmp_path / "state.json")
    frame = build_backtest_frame(_uptrend_candles(), cfg=load_config("."))

    ids = []
    for expected_gen in ("GEN-001", "GEN-002", "GEN-003"):
        report = run_generation(frame, pool_file=pool_file, state_file=state_file,
                                cost=FREE, gate=GATE, now=NOW)
        assert report["generation_id"] == expected_gen
        ids.append(report.get("selected_strategy_id"))
    assert load_counters(state_file)["generation_seq"] == 4
    # No duplicate strategy ids in the resulting pool.
    pool = load_pool(pool_file)
    pool_ids = [e["strategy_id"] for e in pool["active_strategies"]]
    assert len(pool_ids) == len(set(pool_ids))


# -- run_factory end to end ---------------------------------------------------

def test_run_factory_populates_pool(tmp_path):
    pool_file = str(tmp_path / "pool.json")
    state_file = str(tmp_path / "state.json")
    result = run_factory(_uptrend_candles(), pool_file=pool_file, state_file=state_file,
                         cycles=3, cost=FREE, gate=GATE, now=NOW)
    assert result["cycles_run"] == 3
    assert result["bars"] == 240
    # On this oscillating uptrend a trend-pullback champion qualifies and lands.
    assert result["active_pool_size"] >= 1
    # The written pool is what the runtime router would read.
    assert occupying_entries(load_pool(pool_file))


def test_run_generation_audits_pool_decision(tmp_path):
    # With a registry_file, every pool decision is appended to the append-only
    # active-strategy registry (the §10 audit trail) — not just applied silently.
    pool_file = str(tmp_path / "pool.json")
    state_file = str(tmp_path / "state.json")
    registry_file = str(tmp_path / "active_strategy_registry.jsonl")
    frame = build_backtest_frame(_uptrend_candles(), cfg=load_config("."))

    report = run_generation(frame, pool_file=pool_file, state_file=state_file,
                            cost=FREE, gate=GATE, registry_file=registry_file, now=NOW)

    records = load_registry_records(registry_file)
    if report.get("pool_decision"):
        assert len(records) == 1
        assert records[0]["decision"]["action"] == report["pool_decision"]["action"]
        assert records[0]["registry_name"] == "active_strategy_registry"
    else:
        assert records == []


def test_run_generation_without_registry_writes_no_audit(tmp_path):
    # Backward-compatible: omitting registry_file skips the audit (no crash).
    pool_file = str(tmp_path / "pool.json")
    state_file = str(tmp_path / "state.json")
    frame = build_backtest_frame(_uptrend_candles(), cfg=load_config("."))
    run_generation(frame, pool_file=pool_file, state_file=state_file,
                   cost=FREE, gate=GATE, now=NOW)
    assert not (tmp_path / "active_strategy_registry.jsonl").exists()


def test_run_factory_insufficient_candles(tmp_path):
    result = run_factory([{"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "timestamp": "t"}],
                         pool_file=str(tmp_path / "p.json"), state_file=str(tmp_path / "s.json"),
                         cycles=1, cost=FREE, gate=GATE, now=NOW)
    assert result.get("error") == "insufficient_candles_for_backtest_frame"


def test_shared_pool_survives_external_edit(tmp_path):
    # The feedback lifecycle edits the pool between runs; the runner must load the
    # current pool (not overwrite it) and add to it.
    pool_file = str(tmp_path / "pool.json")
    state_file = str(tmp_path / "state.json")
    frame = build_backtest_frame(_uptrend_candles(), cfg=load_config("."))
    run_generation(frame, pool_file=pool_file, state_file=state_file, cost=FREE, gate=GATE, now=NOW)

    pool = load_pool(pool_file)
    first_count = len(pool["active_strategies"])
    # Simulate an external status edit (e.g. a suspension) persisted to the pool.
    if pool["active_strategies"]:
        pool["active_strategies"][0]["status"] = "SUSPENDED"
        from crypto_ai_system.strategy_factory.active_strategy_pool import save_pool
        save_pool(pool_file, pool)

    run_generation(frame, pool_file=pool_file, state_file=state_file, cost=FREE, gate=GATE, now=NOW)
    after = load_pool(pool_file)
    # The externally-set SUSPENDED entry is preserved (not clobbered).
    assert any(e.get("status") == "SUSPENDED" for e in after["active_strategies"]) or first_count == 0
