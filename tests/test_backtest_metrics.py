"""Phase S4d: performance metrics tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto_ai_system.backtesting.performance_metrics import compute_backtest_metrics


def _t(r, side="LONG", regime="RANGE", fee_r=0.0, slip_r=0.0):
    return {"r_multiple": r, "side": side, "entry_regime": regime,
            "fee_cost_r": fee_r, "slippage_cost_r": slip_r}


def test_empty_ledger():
    m = compute_backtest_metrics([])
    assert m["trade_count"] == 0
    assert m["expectancy_r"] is None
    assert m["profit_factor"] is None
    assert m["max_drawdown_r"] == 0.0


def test_basic_expectancy_and_win_rate():
    m = compute_backtest_metrics([_t(2.0), _t(-1.0), _t(2.0), _t(-1.0)])
    assert m["trade_count"] == 4
    assert m["win_rate"] == 0.5
    assert round(m["expectancy_r"], 6) == 0.5
    assert round(m["average_r"], 6) == 0.5


def test_profit_factor():
    m = compute_backtest_metrics([_t(2.0), _t(2.0), _t(-1.0)])
    # gross profit 4, gross loss 1 -> 4.0
    assert round(m["profit_factor"], 6) == 4.0


def test_profit_factor_none_without_losses():
    m = compute_backtest_metrics([_t(1.0), _t(2.0)])
    assert m["profit_factor"] is None
    assert m["gross_loss_r"] == 0.0


def test_max_drawdown_r():
    # cumulative: 1, -1, 0, -1 ; peak: 1,1,1,1 ; dd: 0,2,1,2 -> 2.0
    m = compute_backtest_metrics([_t(1.0), _t(-2.0), _t(1.0), _t(-1.0)])
    assert round(m["max_drawdown_r"], 6) == 2.0


def test_long_short_split():
    m = compute_backtest_metrics([_t(2.0, side="LONG"), _t(-1.0, side="LONG"), _t(3.0, side="SHORT")])
    assert round(m["long_expectancy_r"], 6) == 0.5
    assert round(m["short_expectancy_r"], 6) == 3.0


def test_regime_consistency():
    # RANGE bucket mean +0.5 (profitable), TREND_UP bucket mean -1 (not) -> 1/2
    trades = [_t(2.0, regime="RANGE"), _t(-1.0, regime="RANGE"), _t(-1.0, regime="TREND_UP")]
    m = compute_backtest_metrics(trades)
    assert m["regime_consistency"] == 0.5


def test_cost_r_aggregation():
    m = compute_backtest_metrics([_t(1.0, fee_r=0.01, slip_r=0.02), _t(-1.0, fee_r=0.01, slip_r=0.02)])
    assert round(m["fee_cost_r"], 6) == 0.02
    assert round(m["slippage_cost_r"], 6) == 0.04


def test_sharpe_and_sortino_none_for_single_trade():
    m = compute_backtest_metrics([_t(2.0)])
    assert m["sharpe_like"] is None
    assert m["sortino_like"] is None


def test_sharpe_and_sortino_computed():
    m = compute_backtest_metrics([_t(2.0), _t(-1.0), _t(1.0), _t(-1.0)])
    assert m["sharpe_like"] is not None
    assert m["sortino_like"] is not None
    # Sortino only penalises downside, so it exceeds Sharpe when there is upside spread.
    assert m["sortino_like"] > m["sharpe_like"]


def test_all_wins_sortino_none():
    m = compute_backtest_metrics([_t(1.0), _t(2.0), _t(1.5)])
    assert m["sortino_like"] is None  # no downside deviation
