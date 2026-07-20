"""Order-intent boundary guards (QA fixes): malformed inputs must block, and
one persisted decision authorizes at most one intent."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import crypto_ai_system.execution.order_executor as oe
from core.json_io import atomic_write_json, read_json


def _approved_decision(**over):
    decision = {
        "allow_order_intent": True,
        "pre_order_risk_gate_approved": True,
        "risk_gate_id": "rg_1",
        "direction": "LONG",
        "entry": 100.0,
        "order_notional_usdt": 10.0,
        "final_decision": "TEST_LONG",
        # No adapter serves this stage -> execute path stops at SHADOW_ONLY.
        "execution_stage": "review",
        "decision_stage": "review",
    }
    decision.update(over)
    return decision


# -- build_order_intent input guards -------------------------------------------

def test_malformed_direction_is_rejected_not_mapped_to_sell():
    for bad in (None, "", "SIDEWAYS", 42):
        intent = oe.build_order_intent(_approved_decision(direction=bad))
        assert intent["status"] == "NO_ORDER_INTENT", bad
        assert intent["order_intent_block_reason"] == "MALFORMED_DIRECTION"
        assert "side" not in intent


def test_lowercase_direction_is_normalized():
    intent = oe.build_order_intent(_approved_decision(direction="long"))
    assert intent["status"] == "ORDER_INTENT_CREATED"
    assert intent["side"] == "BUY"


def test_missing_notional_blocks_instead_of_defaulting_to_cap():
    for bad in (None, "", 0, -5, "garbage"):
        intent = oe.build_order_intent(_approved_decision(order_notional_usdt=bad))
        assert intent["status"] == "NO_ORDER_INTENT", bad
        assert intent["order_intent_block_reason"] == "MISSING_ORDER_NOTIONAL"


def test_valid_decision_still_creates_intent():
    intent = oe.build_order_intent(_approved_decision())
    assert intent["status"] == "ORDER_INTENT_CREATED"
    assert intent["notional_usdt"] == 10.0


# -- decision consumption: no replay within the RiskGate TTL --------------------

def _isolate_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(oe, "TRADE_DECISION_PATH", tmp_path / "trade_decision.json")
    monkeypatch.setattr(oe, "ORDER_INTENT_PATH", tmp_path / "order_intent.json")
    monkeypatch.setattr(oe, "ORDER_RESULT_PATH", tmp_path / "order_result.json")
    monkeypatch.setattr(oe, "log_event", lambda *a, **k: None)


def test_decision_is_consumed_after_first_intent(monkeypatch, tmp_path):
    _isolate_paths(monkeypatch, tmp_path)
    atomic_write_json(oe.TRADE_DECISION_PATH, _approved_decision())

    first = oe.run_order_executor()
    assert (read_json(oe.ORDER_INTENT_PATH, {})).get("status") == "ORDER_INTENT_CREATED"
    persisted = read_json(oe.TRADE_DECISION_PATH, {})
    assert persisted.get("order_intent_consumed_at")

    # A re-run against the same persisted decision must refuse, even though the
    # RiskGate record would still verify inside its TTL.
    second = oe.run_order_executor()
    assert second["status"] == "NO_ORDER"
    intent2 = read_json(oe.ORDER_INTENT_PATH, {})
    assert intent2["order_intent_block_reason"] == "TRADE_DECISION_ALREADY_CONSUMED"


def test_fresh_decision_resets_consumption(monkeypatch, tmp_path):
    _isolate_paths(monkeypatch, tmp_path)
    atomic_write_json(oe.TRADE_DECISION_PATH, _approved_decision())
    oe.run_order_executor()

    # The next cycle writes a NEW decision (no marker) -> a new intent is allowed.
    atomic_write_json(oe.TRADE_DECISION_PATH, _approved_decision(final_decision="TEST_LONG_2"))
    oe.run_order_executor()
    assert read_json(oe.ORDER_INTENT_PATH, {}).get("status") == "ORDER_INTENT_CREATED"


def test_blocked_decision_is_not_marked_consumed(monkeypatch, tmp_path):
    _isolate_paths(monkeypatch, tmp_path)
    atomic_write_json(oe.TRADE_DECISION_PATH, _approved_decision(allow_order_intent=False))
    oe.run_order_executor()
    assert not read_json(oe.TRADE_DECISION_PATH, {}).get("order_intent_consumed_at")
