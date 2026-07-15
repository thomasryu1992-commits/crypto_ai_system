"""Increment 3: attributed outcome recording + S9/S10 lifecycle feedback."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.json_io import read_jsonl
from crypto_ai_system.strategy_factory.strategy_spec import StrategyStatus
from crypto_ai_system.strategy_factory.active_strategy_pool import add_champion, empty_pool, find_entry, save_pool
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec
from crypto_ai_system.feedback.strategy_feedback_step import (
    record_strategy_outcome,
    run_strategy_lifecycle_feedback,
)

NOW = "2026-07-16T00:00:00Z"


def _spec_dict(sid="S004"):
    return StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1", "strategy_id": sid, "strategy_version": "1.0",
        "generation_id": "GEN-001", "strategy_family": "trend_pullback", "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"], "timeframe": "1h", "direction": "long",
        "entry_rules": {"operator": "AND", "conditions": [{"feature": "rsi", "comparison": "<=", "value": 40}]},
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.0, "target_atr": 2.0, "max_holding_bars": 24},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    }).to_dict()


def _position(strategy_id="S004"):
    return {
        "status": "OPEN", "direction": "LONG", "strategy_id": strategy_id,
        "strategy_rule_hash": f"hash_{strategy_id}", "strategy_generation_id": "GEN-001",
        "supporting_strategy_ids": ["S008"], "strategy_entry_evaluation_id": "eval_1",
        "risk_gate_id": "rg_1", "order_intent_id": "oi_1", "execution_id": "ex_1",
        "reconciliation_id": "rc_1", "decision_id": "dp_1", "entry_regime": "TREND_UP",
        "holding_candles": 3,
    }


# -- 3a: outcome attribution on close -----------------------------------------

def test_records_strategy_driven_close(tmp_path):
    registry = str(tmp_path / "attributed.jsonl")
    settlement = {"result_R": 1.9, "close_reason": "take_profit"}
    record = record_strategy_outcome(_position(), settlement, registry_file=registry, now=NOW)
    assert record is not None
    assert record["strategy_id"] == "S004"
    assert record["r_multiple"] == 1.9
    assert record["supporting_strategy_ids"] == ["S008"]
    assert len(read_jsonl(registry)) == 1


def test_skips_research_driven_close(tmp_path):
    registry = str(tmp_path / "attributed.jsonl")
    pos = _position()
    del pos["strategy_id"]
    assert record_strategy_outcome(pos, {"result_R": 1.0}, registry_file=registry, now=NOW) is None


# -- 3b: lifecycle feedback over real outcomes --------------------------------

def _seed_pool(tmp_path, sid="S004"):
    pool_file = str(tmp_path / "pool.json")
    pool, _ = add_champion(empty_pool(), _spec_dict(sid), 0.7, now=NOW)
    save_pool(pool_file, pool)
    return pool_file


def _record_losses(registry, count, sid="S004"):
    pos = _position(sid)
    for _ in range(count):
        record_strategy_outcome(pos, {"result_R": -1.0, "close_reason": "stop_loss"}, registry_file=registry, now=NOW)


def test_healthy_strategy_stays_active(tmp_path):
    pool_file = _seed_pool(tmp_path)
    registry = str(tmp_path / "attributed.jsonl")
    pos = _position()
    for r in ([2.0, -1.0] * 30):
        record_strategy_outcome(pos, {"result_R": r, "close_reason": "x"}, registry_file=registry, now=NOW)
    summary = run_strategy_lifecycle_feedback(
        pool_file=pool_file, outcome_registry_file=registry,
        lifecycle_registry_file=str(tmp_path / "lc.jsonl"), now=NOW,
    )
    assert summary["evaluated"] == 1
    assert summary["status_changes"] == 0
    from crypto_ai_system.strategy_factory.active_strategy_pool import load_pool
    assert find_entry(load_pool(pool_file), "S004")["status"] == StrategyStatus.PAPER_ACTIVE.value


def test_decayed_strategy_escalates_and_persists(tmp_path):
    pool_file = _seed_pool(tmp_path)
    registry = str(tmp_path / "attributed.jsonl")
    lifecycle = str(tmp_path / "lc.jsonl")
    _record_losses(registry, 50)  # 50 losing paper trades

    from crypto_ai_system.strategy_factory.active_strategy_pool import load_pool
    # Cycle 1: escalates to probation and records a failure.
    s1 = run_strategy_lifecycle_feedback(pool_file=pool_file, outcome_registry_file=registry,
                                         lifecycle_registry_file=lifecycle, now=NOW)
    assert s1["status_changes"] == 1
    entry = find_entry(load_pool(pool_file), "S004")
    assert entry["status"] == StrategyStatus.PROBATION.value
    assert entry["consecutive_failures"] == 1

    # Cycle 2: second consecutive failure -> suspended.
    s2 = run_strategy_lifecycle_feedback(pool_file=pool_file, outcome_registry_file=registry,
                                         lifecycle_registry_file=lifecycle, now=NOW)
    entry2 = find_entry(load_pool(pool_file), "S004")
    assert entry2["status"] == StrategyStatus.SUSPENDED.value
    # Each status change is logged to the lifecycle registry.
    assert len(read_jsonl(lifecycle)) == 2


def test_suspended_strategy_no_longer_routed(tmp_path):
    # After suspension, the router must not route the strategy (loop closed).
    from crypto_ai_system.strategy_factory.active_strategy_pool import load_pool
    from crypto_ai_system.strategy_factory.entry_strategy_router_agent import route_entries
    pool_file = _seed_pool(tmp_path)
    registry = str(tmp_path / "attributed.jsonl")
    _record_losses(registry, 50)
    for _ in range(2):  # drive to suspension
        run_strategy_lifecycle_feedback(pool_file=pool_file, outcome_registry_file=registry,
                                        lifecycle_registry_file=str(tmp_path / "lc.jsonl"), now=NOW)
    pool = load_pool(pool_file)
    result = route_entries(pool, {"rsi": 20}, now=NOW)  # a matching signal
    assert result["status"] == "NO_ENTRY"  # suspended -> not routed
    assert result["strategies_evaluated"] == 0


def test_no_outcomes_leaves_pool_unchanged(tmp_path):
    pool_file = _seed_pool(tmp_path)
    summary = run_strategy_lifecycle_feedback(
        pool_file=pool_file, outcome_registry_file=str(tmp_path / "empty.jsonl"),
        lifecycle_registry_file=str(tmp_path / "lc.jsonl"), now=NOW,
    )
    assert summary["status_changes"] == 0
    assert summary["decisions"][0]["trade_count"] == 0
