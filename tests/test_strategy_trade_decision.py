"""Increment 2: strategy trade decision builder tests (directive §2.2 gating)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.strategy_factory import strategy_trade_decision as std
from crypto_ai_system.strategy_factory.strategy_trade_decision import build_strategy_trade_decision

NOW = "2026-07-16T00:00:00Z"


def _candidate(direction="LONG"):
    return {"status": "ENTRY_CANDIDATE", "direction": direction, "order_candidate_count": 1,
            "matched_strategy_ids": ["S004", "S008"], "matched_strategy_count": 2,
            "primary_strategy_id": "S004", "primary_strategy_rule_hash": "hash_S004",
            "strategy_pool_version": "active_strategy_pool.v1"}


def _spec(stop_atr=1.0, target_atr=2.0):
    return {"strategy_id": "S004", "strategy_version": "1.0", "generation_id": "GEN-001",
            "strategy_rule_hash": "hash_S004",
            "exit_rules": {"stop_model": "atr", "stop_atr": stop_atr, "target_atr": target_atr, "max_holding_bars": 24}}


def _attr():
    return {"strategy_id": "S004", "strategy_version": "1.0", "strategy_generation_id": "GEN-001",
            "strategy_rule_hash": "hash_S004", "supporting_strategy_ids": ["S008"],
            "matched_strategy_ids": ["S004", "S008"], "strategy_entry_evaluation_id": "strategy_entry_evaluation_x",
            "strategy_pool_version": "active_strategy_pool.v1"}


def _perm(allow_long=True, allow_short=True, allow_new=True):
    return {"allow_long": allow_long, "allow_short": allow_short, "allow_new_position": allow_new}


def _gate(approved=True):
    return {"approved": approved, "status": "PASS_PAPER" if approved else "BLOCK", "risk_gate_id": "rg_1"}


def _build(**over):
    kwargs = dict(
        router_result=over.get("router_result", _candidate()),
        primary_spec=over.get("primary_spec", _spec()),
        feature_row=over.get("feature_row", {"close": 100.0, "atr": 2.0}),
        market_snapshot=over.get("market_snapshot", {"last_close": 100.0}),
        research_permission=over.get("research_permission", _perm()),
        pre_order_risk_gate=over.get("pre_order_risk_gate", _gate()),
        attribution=over.get("attribution", _attr()),
        data_health=over.get("data_health", {"allow_trading": True}),
        risk=over.get("risk", {"allow_new_position": True}),
        now=NOW,
    )
    return build_strategy_trade_decision(**kwargs)


# -- happy path ---------------------------------------------------------------

def test_full_approval_creates_order_intent_permission():
    d = _build()
    assert d["allow_order_intent"] is True
    assert d["final_decision"] == "STRATEGY_LONG_ENTRY"
    assert d["direction"] == "LONG"
    assert d["entry"] == 100.0
    # stop 1 ATR below, target 2 ATR above (long).
    assert d["stop_loss"] == 98.0
    assert d["take_profit"] == 104.0
    assert d["risk_reward"] == 2.0
    assert d["risk_gate_id"] == "rg_1"


def test_short_direction_levels():
    d = _build(router_result=_candidate("SHORT"))
    assert d["direction"] == "SHORT"
    assert d["stop_loss"] == 102.0   # 1 ATR above
    assert d["take_profit"] == 96.0  # 2 ATR below


def test_attribution_carried_onto_decision():
    d = _build()
    assert d["strategy_id"] == "S004"
    assert d["supporting_strategy_ids"] == ["S008"]
    assert d["strategy_entry_evaluation_id"] == "strategy_entry_evaluation_x"
    assert d["strategy_generation_id"] == "GEN-001"


# -- fail-closed gates --------------------------------------------------------

def test_not_a_candidate_blocked():
    d = _build(router_result={"status": "NO_ENTRY", "direction": None})
    assert d["allow_order_intent"] is False
    assert std.BLOCK_NOT_A_CANDIDATE in d["block_reasons"]


def test_direction_not_permitted_blocked():
    d = _build(research_permission=_perm(allow_long=False))
    assert d["allow_order_intent"] is False
    assert std.BLOCK_DIRECTION_NOT_PERMITTED in d["block_reasons"]


def test_new_position_disallowed_blocked():
    d = _build(research_permission=_perm(allow_new=False))
    assert d["allow_order_intent"] is False
    assert std.BLOCK_NEW_POSITION_DISALLOWED in d["block_reasons"]


def test_data_health_disallows_trading_blocked():
    d = _build(data_health={"allow_trading": False})
    assert d["allow_order_intent"] is False
    assert std.BLOCK_DATA_HEALTH in d["block_reasons"]


def test_risk_guard_disallows_new_position_blocked():
    d = _build(risk={"allow_new_position": False})
    assert d["allow_order_intent"] is False
    assert std.BLOCK_RISK_GUARD in d["block_reasons"]


def test_empty_validation_verdicts_fail_closed():
    # A missing/empty verdict must block, never default to allowed.
    d = _build(data_health={}, risk={})
    assert d["allow_order_intent"] is False
    assert std.BLOCK_DATA_HEALTH in d["block_reasons"]
    assert std.BLOCK_RISK_GUARD in d["block_reasons"]


def test_risk_gate_not_approved_blocked():
    d = _build(pre_order_risk_gate=_gate(approved=False))
    assert d["allow_order_intent"] is False
    assert std.BLOCK_RISK_GATE in d["block_reasons"]
    assert d["pre_order_risk_gate_approved"] is False


def test_no_price_blocked():
    d = _build(market_snapshot={}, feature_row={"atr": 2.0})
    assert d["allow_order_intent"] is False
    assert std.BLOCK_NO_PRICE in d["block_reasons"]


def test_no_atr_blocked():
    d = _build(feature_row={"close": 100.0})
    assert d["allow_order_intent"] is False
    assert std.BLOCK_NO_ATR in d["block_reasons"]
    assert d["stop_loss"] is None


def test_blocked_decision_has_no_order_authority():
    d = _build(pre_order_risk_gate=_gate(approved=False))
    assert d["allow_order_intent"] is False
    assert d["order_intent_created"] is False
    assert d["external_order_submission_performed"] is False


def test_decision_id_deterministic():
    a = _build()
    b = _build()
    assert a["trading_decision_agent_id"] == b["trading_decision_agent_id"]


def test_carries_paper_engine_lineage_ids():
    # The paper execution engine rejects an intent missing decision/signal/profile
    # ids, so the strategy decision must carry them (found by the integration run).
    d = build_strategy_trade_decision(
        router_result=_candidate(), primary_spec=_spec(), feature_row={"close": 100.0, "atr": 2.0},
        market_snapshot={"last_close": 100.0}, research_permission=_perm(), pre_order_risk_gate=_gate(),
        attribution=_attr(), data_health={"allow_trading": True}, risk={"allow_new_position": True},
        research_signal_id="rs_1", profile_id="paper_1",
        data_snapshot_id="ds_1", feature_snapshot_id="fs_1", now=NOW,
    )
    assert d["decision_id"] == "strategy_entry_evaluation_x"  # the strategy's eval id
    assert d["research_signal_id"] == "rs_1"
    assert d["profile_id"] == "paper_1"
    assert d["data_snapshot_id"] == "ds_1"
    assert d["feature_snapshot_id"] == "fs_1"
