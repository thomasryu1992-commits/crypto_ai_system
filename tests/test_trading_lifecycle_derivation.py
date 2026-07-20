"""M2: pure order-lifecycle derivation — first direct unit tests for the
single-book / multibook matrix that was previously buried in execute()."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.pipeline.trading_steps.lifecycle import derive_lifecycle


# -- single-book ----------------------------------------------------------------

def test_rejected_result_dict_is_not_a_trade():
    life = derive_lifecycle({"status": "NO_ORDER_INTENT", "state": "REJECTED"}, [], multibook=False)
    assert life.trade_executed is False
    assert life.order_filled is False
    assert life.order_intent_created is False


def test_paper_fill_counts_as_trade():
    order = {"status": "PAPER_FILLED", "filled": True, "order_intent_id": "oi1"}
    life = derive_lifecycle(order, [], multibook=False)
    assert life.trade_executed is True
    assert life.order_filled is True
    assert life.order_intent_created is True
    assert life.order_submitted is False


def test_external_submit_counts_as_trade_even_unfilled():
    order = {"status": "LIVE_STRATEGY_ORDER_SUBMITTED", "filled": False,
             "external_order_submission_performed": True, "order_intent_id": "oi1"}
    life = derive_lifecycle(order, [], multibook=False)
    assert life.trade_executed is True
    assert life.order_submitted is True
    assert life.order_filled is False


def test_unresolved_submit_is_submitted_but_not_a_trade_status():
    # QA fix interplay: an UNRESOLVED submit is performed=True (accounting) but
    # its status is not in the submit set — order_submitted must still be True.
    order = {"status": "LIVE_STRATEGY_SUBMIT_UNRESOLVED", "filled": False,
             "external_order_submission_performed": True}
    life = derive_lifecycle(order, [], multibook=False)
    assert life.order_submitted is True


def test_intent_created_via_nested_intent():
    order = {"status": "SHADOW_ONLY", "intent": {"order_intent_created": True}}
    assert derive_lifecycle(order, [], multibook=False).order_intent_created is True


# -- multibook ------------------------------------------------------------------

def _entry(filled, intent_id=None):
    order = {"filled": filled}
    if intent_id:
        order["order_intent_id"] = intent_id
    return {"order": order, "filled": filled}


def test_multibook_any_fill_counts():
    entries = [_entry(False, "oi1"), _entry(True, "oi2"), _entry(False)]
    life = derive_lifecycle({"status": "X"}, entries, multibook=True)
    assert life.trade_executed is True
    assert life.order_filled is True
    assert life.order_intent_created is True
    assert life.order_submitted is False  # multibook is paper-only


def test_multibook_no_fills_no_trade():
    entries = [_entry(False), _entry(False)]
    life = derive_lifecycle({"status": "NO_ORDER_INTENT"}, entries, multibook=True)
    assert life.trade_executed is False
    assert life.order_status == "NO_ORDER_INTENT"  # representative order's status


def test_multibook_empty_walk():
    life = derive_lifecycle({}, [], multibook=True)
    assert life.trade_executed is False
    assert life.order_intent_created is False
