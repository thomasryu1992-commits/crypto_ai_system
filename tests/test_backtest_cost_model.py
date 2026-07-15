"""Phase S4b: cost / slippage / sizing model tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.backtesting.cost_model import (
    CostModel,
    settle_trade,
    size_position,
    stop_price,
    target_price,
)


COST = CostModel(taker_fee_bps=2.5, slippage_bps=3.0)


# -- fills / fees -------------------------------------------------------------

def test_taker_fills_are_adverse():
    # Long entry buys above mid; long exit sells below mid.
    assert COST.fill_price(100.0, "LONG", "entry") > 100.0
    assert COST.fill_price(100.0, "LONG", "exit") < 100.0
    # Short entry sells below mid; short exit buys above mid.
    assert COST.fill_price(100.0, "SHORT", "entry") < 100.0
    assert COST.fill_price(100.0, "SHORT", "exit") > 100.0


def test_fee_is_bps_of_notional():
    assert COST.fee(100.0, 2.0) == 200.0 * 2.5 / 10000.0


def test_zero_cost_model_is_frictionless():
    free = CostModel(taker_fee_bps=0.0, slippage_bps=0.0)
    assert free.fill_price(100.0, "LONG", "entry") == 100.0
    assert free.fee(100.0, 5.0) == 0.0


# -- stop / target ------------------------------------------------------------

def test_stop_target_long():
    assert stop_price(100.0, 2.0, "LONG", 1.5) == 97.0
    assert target_price(100.0, 2.0, "LONG", 2.5) == 105.0


def test_stop_target_short():
    assert stop_price(100.0, 2.0, "SHORT", 1.5) == 103.0
    assert target_price(100.0, 2.0, "SHORT", 2.5) == 95.0


# -- sizing -------------------------------------------------------------------

def test_size_position_risk_fraction():
    qty, risk_amount, risk_per_unit = size_position(10000.0, 0.01, 100.0, 98.0)
    assert risk_amount == 100.0
    assert risk_per_unit == 2.0
    assert qty == 50.0


def test_size_position_zero_distance_is_zero_qty():
    qty, _, _ = size_position(10000.0, 0.01, 100.0, 100.0)
    assert qty == 0.0


# -- settlement / R decomposition ---------------------------------------------

def test_frictionless_target_hit_is_positive_r():
    free = CostModel(0.0, 0.0)
    # entry 100, stop 98 -> risk/unit 2, qty 50, risk_amount 100. Target 105 -> +5*50=250 -> +2.5R
    qty, risk_amount, _ = size_position(10000.0, 0.01, 100.0, 98.0)
    s = settle_trade("LONG", 100.0, 105.0, qty, risk_amount, free)
    assert s.fees == 0.0 and s.slippage_cost == 0.0
    assert round(s.r_multiple, 6) == 2.5


def test_frictionless_stop_hit_is_minus_one_r():
    free = CostModel(0.0, 0.0)
    qty, risk_amount, _ = size_position(10000.0, 0.01, 100.0, 98.0)
    s = settle_trade("LONG", 100.0, 98.0, qty, risk_amount, free)
    assert round(s.r_multiple, 6) == -1.0


def test_costs_reduce_r_and_are_decomposed():
    qty, risk_amount, _ = size_position(10000.0, 0.01, 100.0, 98.0)
    gross = settle_trade("LONG", 100.0, 105.0, qty, risk_amount, CostModel(0.0, 0.0))
    net = settle_trade("LONG", 100.0, 105.0, qty, risk_amount, COST)
    assert net.fees > 0.0
    assert net.slippage_cost > 0.0
    assert net.r_multiple < gross.r_multiple
    # net R = gross R - fee_cost_R - slippage_cost_R (all in R units).
    assert round(net.r_multiple, 9) == round(gross.r_multiple - net.fee_cost_r - net.slippage_cost_r, 9)


def test_short_direction_pnl_sign():
    free = CostModel(0.0, 0.0)
    qty, risk_amount, _ = size_position(10000.0, 0.01, 100.0, 102.0)  # short stop above
    # Short from 100 to 95 is a win.
    s = settle_trade("SHORT", 100.0, 95.0, qty, risk_amount, free)
    assert s.r_multiple > 0
