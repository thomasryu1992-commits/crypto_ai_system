"""Phase S4c: single-pass execution simulator for one StrategySpec.

Walks a feature frame once and produces a trade ledger in R terms. The timing
rule is strict to avoid look-ahead: the spec is evaluated on bar *i* (whose
features are known only at its close), and the position is entered at bar *i+1*'s
open. The stop/target are sized from the entry fill using the ATR at the signal
bar; each subsequent bar is checked intrabar (high/low) for a stop or target hit,
then for the max-holding time exit. One position at a time; any position still
open at the end is force-closed at the last close.

Pure over its inputs: given the same frame, spec, and cost model it produces the
same ledger. No IO, no config, no network.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from crypto_ai_system.backtesting.cost_model import (
    CostModel,
    settle_trade,
    size_position,
    stop_price,
    target_price,
)
from crypto_ai_system.strategy_factory.strategy_evaluator import evaluate_spec
from crypto_ai_system.strategy_factory.strategy_spec import StrategySpec

REQUIRED_COLUMNS = ("open", "high", "low", "close", "atr")

EXIT_TARGET = "TARGET"
EXIT_STOP = "STOP"
EXIT_MAX_HOLDING = "MAX_HOLDING"
EXIT_FORCE_CLOSE = "FORCE_CLOSE"


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # drop NaN


def _hit_stop(side: str, low: float | None, high: float | None, stop: float) -> bool:
    if side == "LONG":
        return low is not None and low <= stop
    return high is not None and high >= stop


def _hit_target(side: str, low: float | None, high: float | None, target: float) -> bool:
    if side == "LONG":
        return high is not None and high >= target
    return low is not None and low <= target


def simulate_strategy(
    spec: StrategySpec,
    frame: pd.DataFrame,
    *,
    cost: CostModel | None = None,
    equity: float = 10000.0,
    risk_pct: float = 0.01,
) -> dict[str, Any]:
    """Simulate ``spec`` over ``frame`` and return the trade ledger + summary."""
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"feature frame is missing required columns: {missing}")
    cost = cost or CostModel()

    records = frame.to_dict("records")
    n = len(records)
    trades: list[dict[str, Any]] = []
    entries = 0
    position: dict[str, Any] | None = None

    i = 0
    while i < n:
        if position is None:
            if i + 1 >= n:
                break  # no next bar to enter on
            signal_row = records[i]
            atr = _num(signal_row.get("atr"))
            result = evaluate_spec(spec, signal_row)
            entered = False
            if result.matched and atr and atr > 0:
                side = result.direction or "LONG"
                entry_bar = i + 1
                entry_intended = _num(records[entry_bar].get("open"))
                if entry_intended and entry_intended > 0:
                    entry_fill = cost.fill_price(entry_intended, side, "entry")
                    stop = stop_price(entry_fill, atr, side, spec.exit_rules.stop_atr)
                    target = target_price(entry_fill, atr, side, spec.exit_rules.target_atr)
                    qty, risk_amount, _ = size_position(equity, risk_pct, entry_fill, stop)
                    if qty > 0:
                        position = {
                            "entry_bar": entry_bar,
                            "side": side,
                            "entry_intended": entry_intended,
                            "entry_fill": entry_fill,
                            "stop": stop,
                            "target": target,
                            "qty": qty,
                            "risk_amount": risk_amount,
                            "entry_regime": signal_row.get("market_regime"),
                            "entry_timestamp": records[entry_bar].get("timestamp"),
                        }
                        entries += 1
                        i = entry_bar
                        entered = True
            if not entered:
                i += 1
                continue

        # Manage the open position on bar i.
        row = records[i]
        side = position["side"]
        low, high, close = _num(row.get("low")), _num(row.get("high")), _num(row.get("close"))
        bars_held = i - position["entry_bar"] + 1

        exit_reason: str | None = None
        exit_intended: float | None = None
        # Stop takes priority over target when both trigger in one bar (conservative).
        if _hit_stop(side, low, high, position["stop"]):
            exit_reason, exit_intended = EXIT_STOP, position["stop"]
        elif _hit_target(side, low, high, position["target"]):
            exit_reason, exit_intended = EXIT_TARGET, position["target"]
        elif bars_held >= spec.exit_rules.max_holding_bars and close is not None:
            exit_reason, exit_intended = EXIT_MAX_HOLDING, close

        if exit_reason is not None and exit_intended is not None:
            trades.append(_close(position, i, row, exit_reason, exit_intended, bars_held, cost))
            position = None
        i += 1

    if position is not None:
        last = records[-1]
        close = _num(last.get("close"))
        if close is not None:
            bars_held = (n - 1) - position["entry_bar"] + 1
            trades.append(_close(position, n - 1, last, EXIT_FORCE_CLOSE, close, bars_held, cost))
        position = None

    return {
        "strategy_id": spec.strategy_id,
        "strategy_rule_hash": spec.strategy_rule_hash,
        "bars": n,
        "entries": entries,
        "closed_trades": len(trades),
        "trades": trades,
    }


def _close(
    position: dict[str, Any],
    exit_bar: int,
    exit_row: dict[str, Any],
    exit_reason: str,
    exit_intended: float,
    bars_held: int,
    cost: CostModel,
) -> dict[str, Any]:
    side = position["side"]
    settlement = settle_trade(
        side, position["entry_intended"], exit_intended, position["qty"], position["risk_amount"], cost
    )
    return {
        "side": side,
        "entry_bar": position["entry_bar"],
        "exit_bar": exit_bar,
        "entry_timestamp": position.get("entry_timestamp"),
        "exit_timestamp": exit_row.get("timestamp"),
        "entry_price": position["entry_fill"],
        "exit_price": cost.fill_price(exit_intended, side, "exit"),
        "stop": position["stop"],
        "target": position["target"],
        "qty": position["qty"],
        "bars_held": bars_held,
        "exit_reason": exit_reason,
        "entry_regime": position.get("entry_regime"),
        "r_multiple": settlement.r_multiple,
        "net_pnl": settlement.net_pnl,
        "fees": settlement.fees,
        "slippage_cost": settlement.slippage_cost,
        "fee_cost_r": settlement.fee_cost_r,
        "slippage_cost_r": settlement.slippage_cost_r,
    }
