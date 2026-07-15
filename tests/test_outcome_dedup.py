"""Tests for outcome dedup / no-trade guard (P0-3)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.feedback.outcome_analytics_v2 import outcome_skip_reason


def _closed(**kw):
    base = {
        "outcome_closed": True,
        "outcome_id": "o1",
        "execution_id": "e1",
        "reconciliation_id": "r1",
    }
    base.update(kw)
    return base


def test_fresh_closed_trade_is_appended():
    assert outcome_skip_reason(_closed(), []) is None


def test_open_position_is_skipped():
    assert outcome_skip_reason(_closed(outcome_closed=False), []) == "not_closed"


def test_no_execution_is_skipped():
    payload = _closed(execution_id="", reconciliation_id="")
    assert outcome_skip_reason(payload, []) == "no_execution"


def test_duplicate_outcome_id_is_skipped():
    existing = [{"outcome_id": "o1", "execution_id": "e0", "reconciliation_id": "r0"}]
    assert outcome_skip_reason(_closed(), existing) == "duplicate"


def test_duplicate_execution_id_is_skipped():
    existing = [{"outcome_id": "oX", "execution_id": "e1", "reconciliation_id": "rX"}]
    assert outcome_skip_reason(_closed(), existing) == "duplicate"


def test_duplicate_reconciliation_id_is_skipped():
    existing = [{"outcome_id": "oX", "execution_id": "eX", "reconciliation_id": "r1"}]
    assert outcome_skip_reason(_closed(), existing) == "duplicate"


def test_distinct_trade_is_appended():
    existing = [{"outcome_id": "o0", "execution_id": "e0", "reconciliation_id": "r0"}]
    assert outcome_skip_reason(_closed(), existing) is None
