"""Network-free tests for the Phase 10 testnet session harness."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.execution.testnet_session_harness import (
    run_one_session,
    run_sessions,
)


class FakeVenue:
    """A coordinated fake: submit_fn and reconcile_fn share this state."""

    def __init__(self, fill_price=64000.0, balance=5000.0, block_after=None, fee=0.05):
        self.fill_price = fill_price
        self.balance = balance
        self.block_after = block_after
        self.fee = fee
        self.submitted = 0
        self._last_side = None

    def submit(self, intent):
        if self.block_after is not None and self.submitted >= self.block_after:
            return {
                "status": "SIGNED_TESTNET_BLOCKED",
                "state": "REJECTED",
                "external_order_submission_performed": False,
                "exchange_order_id": None,
            }
        self.submitted += 1
        self.balance -= self.fee
        self._last_side = intent["side"]
        return {
            "status": "SIGNED_TESTNET_ORDER_SUBMITTED",
            "state": "SUBMITTED",
            "external_order_submission_performed": True,
            "exchange_order_id": 1000 + self.submitted,
        }

    def reconcile(self):
        if self._last_side is None:
            return {"status": "NO_SUBMISSION", "actual": {}}
        return {
            "status": "RECONCILED",
            "filled": True,
            "mismatches": [],
            "actual": {
                "avg_fill_price": self.fill_price,
                "wallet_balance_usdt": self.balance,
                "position_amt": 0.0,
            },
        }


def _price_fn(p=64000.0):
    return lambda: p


def test_one_clean_session_ok():
    venue = FakeVenue()
    rec = run_one_session(
        "BTCUSDT", 150.0, _price_fn(),
        submit_fn=venue.submit, reconcile_fn=venue.reconcile, session_id="s1",
    )
    assert rec["status"] == "OK"
    assert rec["open"]["submitted"] is True
    assert rec["close"]["submitted"] is True
    assert rec["open"]["reconcile_status"] == "RECONCILED"
    assert rec["close"]["reconcile_status"] == "RECONCILED"


def test_open_block_skips_close():
    venue = FakeVenue(block_after=0)  # block immediately
    rec = run_one_session(
        "BTCUSDT", 150.0, _price_fn(),
        submit_fn=venue.submit, reconcile_fn=venue.reconcile, session_id="s1",
    )
    assert rec["status"] == "BLOCKED"
    assert rec["open"]["submitted"] is False
    assert rec["close"] is None


def test_run_sessions_stops_on_block():
    # Allow 3 successful order legs, then block: session1 (2 legs) ok,
    # session2 opens (leg 3) then close blocked -> PARTIAL, no session3.
    venue = FakeVenue(block_after=3)
    result = run_sessions(
        5, "BTCUSDT", 150.0, _price_fn(),
        submit_fn=venue.submit, reconcile_fn=venue.reconcile,
    )
    # session2's close is blocked, but the session itself opened, so the loop
    # continues only if a whole session is BLOCKED. Here session3's open blocks.
    statuses = [s["status"] for s in result["sessions"]]
    assert statuses[0] == "OK"
    assert "BLOCKED" in statuses
    assert result["sessions"][-1]["status"] == "BLOCKED"
    assert len(result["sessions"]) < 5  # stopped early


def test_slippage_sign_on_buy():
    # Fill 10 bps above expected -> positive (worse) slippage on a BUY.
    venue = FakeVenue(fill_price=64064.0)
    rec = run_one_session(
        "BTCUSDT", 150.0, _price_fn(64000.0),
        submit_fn=venue.submit, reconcile_fn=venue.reconcile, session_id="s1",
    )
    assert abs(rec["open"]["slippage_bps"] - 10.0) < 0.5
    # SELL close at a higher fill than expected is favorable -> negative.
    assert rec["close"]["slippage_bps"] < 0


def test_aggregate_cost_and_rates():
    venue = FakeVenue(balance=5000.0, fee=0.05)
    result = run_sessions(
        2, "BTCUSDT", 150.0, _price_fn(),
        submit_fn=venue.submit, reconcile_fn=venue.reconcile,
        balance_fn=lambda: venue.balance,
    )
    agg = result["aggregate"]
    assert agg["sessions_run"] == 2
    assert agg["orders_submitted"] == 4
    assert agg["reconcile_rate"] == 1.0
    # 4 legs * 0.05 fee = 0.20 total cost.
    assert abs(agg["total_round_trip_cost_usdt"] - 0.20) < 1e-6
