"""Phase S7: multi-strategy entry router tests (directive §18 / §19)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.strategy_factory.active_strategy_pool import add_champion, empty_pool, set_status
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec, StrategyStatus
from crypto_ai_system.strategy_factory.entry_strategy_router_agent import (
    BLOCK_DIRECTION_CONFLICT,
    STATUS_BLOCKED,
    STATUS_ENTRY_CANDIDATE,
    STATUS_NO_ENTRY,
    route_entries,
)

NOW = "2026-07-16T00:00:00Z"


def _spec(strategy_id, direction, conditions):
    # Return the canonical dict (with strategy_rule_hash) a real caller stores.
    return StrategySpec.from_dict({
        "schema_version": "strategy_spec.v1",
        "strategy_id": strategy_id,
        "strategy_version": "1.0",
        "generation_id": "GEN-001",
        "strategy_family": "trend_pullback",
        "status": "GENERATED",
        "symbol_scope": ["BTCUSDT"],
        "timeframe": "1h",
        "direction": direction,
        "entry_rules": {"operator": "AND", "conditions": conditions},
        "exit_rules": {"stop_model": "atr", "stop_atr": 1.0, "target_atr": 2.0, "max_holding_bars": 24},
        "risk_constraints": {"max_risk_per_trade_R": 1.0},
    }).to_dict()


def _long_when_rsi_below(sid, thresh, score=0.7):
    return _spec(sid, "long", [{"feature": "rsi", "comparison": "<=", "value": thresh}]), score


def _short_when_rsi_above(sid, thresh, score=0.7):
    return _spec(sid, "short", [{"feature": "rsi", "comparison": ">=", "value": thresh}]), score


def _pool(*spec_score_pairs):
    pool = empty_pool()
    for spec, score in spec_score_pairs:
        pool, _ = add_champion(pool, spec, score, now=NOW)
    return pool


# -- no match / single match --------------------------------------------------

def test_no_match_no_entry():
    pool = _pool(_long_when_rsi_below("S001", 30))
    result = route_entries(pool, {"rsi": 80}, now=NOW)
    assert result["status"] == STATUS_NO_ENTRY
    assert result["order_candidate_count"] == 0
    assert result["matched_strategy_ids"] == []


def test_single_match_one_candidate():
    pool = _pool(_long_when_rsi_below("S001", 40))
    result = route_entries(pool, {"rsi": 25}, now=NOW)
    assert result["status"] == STATUS_ENTRY_CANDIDATE
    assert result["order_candidate_count"] == 1
    assert result["direction"] == "LONG"
    assert result["primary_strategy_id"] == "S001"
    assert result["matched_strategy_ids"] == ["S001"]


# -- §18: same direction merges to ONE order ----------------------------------

def test_two_same_direction_still_one_order():
    pool = _pool(
        _long_when_rsi_below("S001", 40, score=0.6),
        _long_when_rsi_below("S006", 50, score=0.9),
    )
    result = route_entries(pool, {"rsi": 35}, now=NOW)
    assert result["status"] == STATUS_ENTRY_CANDIDATE
    assert result["direction"] == "LONG"
    assert result["matched_strategy_count"] == 2
    assert result["matched_strategy_ids"] == ["S001", "S006"]
    # Two strategies agreeing does NOT double the position.
    assert result["order_candidate_count"] == 1
    # Primary is the higher-scored strategy.
    assert result["primary_strategy_id"] == "S006"


# -- §18: opposite direction blocks -------------------------------------------

def test_opposite_direction_blocks():
    pool = _pool(
        _long_when_rsi_below("S001", 40),
        _short_when_rsi_above("S006", 30),
    )
    # rsi 35 satisfies both the long (<=40) and short (>=30) legs.
    result = route_entries(pool, {"rsi": 35}, now=NOW)
    assert result["status"] == STATUS_BLOCKED
    assert result["block_reason"] == BLOCK_DIRECTION_CONFLICT
    assert result["order_candidate_count"] == 0
    assert set(result["conflicting_directions"]) == {"LONG", "SHORT"}
    assert result["direction"] is None


# -- routing scope ------------------------------------------------------------

def test_flagged_strategies_still_routed():
    # WARNING/PROBATION keep trading so their rolling window can recover or
    # escalate; only SUSPENDED/ARCHIVED are removed from routing. Distinct
    # thresholds give the two strategies distinct rule hashes so both enter.
    pool = _pool(
        _long_when_rsi_below("S001", 40),
        _long_when_rsi_below("S006", 45),
    )
    pool, _ = set_status(pool, "S006", StrategyStatus.PROBATION, now=NOW)
    result = route_entries(pool, {"rsi": 20}, now=NOW)
    assert result["matched_strategy_ids"] == ["S001", "S006"]
    assert result["strategies_evaluated"] == 2


def test_suspended_and_archived_not_routed():
    pool = _pool(
        _long_when_rsi_below("S001", 40),
        _long_when_rsi_below("S006", 45),
    )
    pool, _ = set_status(pool, "S006", StrategyStatus.SUSPENDED, now=NOW)
    result = route_entries(pool, {"rsi": 20}, now=NOW)
    # Suspended cannot create an OrderIntent (§19); only S001 routes.
    assert result["matched_strategy_ids"] == ["S001"]
    assert result["strategies_evaluated"] == 1


def test_empty_pool_no_entry():
    result = route_entries(empty_pool(), {"rsi": 20}, now=NOW)
    assert result["status"] == STATUS_NO_ENTRY
    assert result["strategies_evaluated"] == 0


def test_indeterminate_feature_no_match():
    pool = _pool(_long_when_rsi_below("S001", 40))
    # rsi missing -> evaluator indeterminate -> no entry (fail-closed).
    result = route_entries(pool, {}, now=NOW)
    assert result["status"] == STATUS_NO_ENTRY


# -- §19 safety: router only proposes -----------------------------------------

def test_router_output_has_no_execution_authority():
    pool = _pool(_long_when_rsi_below("S001", 40))
    result = route_entries(pool, {"rsi": 20}, now=NOW)
    # It is a candidate, not an order. No submission/authority flags leak in.
    assert result["status"] == STATUS_ENTRY_CANDIDATE
    assert result["order_candidate_count"] == 1
    for forbidden in ("submitted", "order_submitted", "can_submit_orders", "external_order_submission_performed"):
        assert forbidden not in result


def test_router_does_not_mutate_pool():
    pool = _pool(_long_when_rsi_below("S001", 40))
    before = [dict(e) for e in pool["active_strategies"]]
    route_entries(pool, {"rsi": 20}, now=NOW)
    assert pool["active_strategies"] == before


def test_evaluations_report_each_strategy():
    pool = _pool(
        _long_when_rsi_below("S001", 40),
        _long_when_rsi_below("S006", 20),
    )
    result = route_entries(pool, {"rsi": 30}, now=NOW)
    by_id = {e["strategy_id"]: e for e in result["evaluations"]}
    assert by_id["S001"]["matched"] is True    # 30 <= 40
    assert by_id["S006"]["matched"] is False   # 30 <= 20 is false
