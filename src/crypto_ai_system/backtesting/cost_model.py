"""Phase S4b: cost, slippage, and position sizing for the factory backtest.

Every strategy in a generation batch is scored under the *same* cost assumptions
so their metrics are comparable — that is the whole point of a unified engine. A
taker always fills at an adverse price (buys higher, sells lower) and pays a fee
on both legs. Position size comes from a fixed fractional-risk model shared with
the runtime path (``strategy.risk.calculate_position_size``), so a backtested R
means the same thing as a live R.

All pure functions and frozen dataclasses; no IO, no config reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_ai_system.strategy.risk import calculate_position_size


@dataclass(frozen=True)
class CostModel:
    taker_fee_bps: float = 2.5
    slippage_bps: float = 3.0

    def fill_price(self, mid: float, side: str, action: str) -> float:
        """Adverse-slippage fill: a taker buys above and sells below the mid."""
        adverse_up = (side == "LONG" and action == "entry") or (side == "SHORT" and action == "exit")
        factor = 1.0 + self.slippage_bps / 10000.0 if adverse_up else 1.0 - self.slippage_bps / 10000.0
        return mid * factor

    def fee(self, price: float, qty: float) -> float:
        return abs(price * qty) * self.taker_fee_bps / 10000.0


def stop_price(entry: float, atr: float, side: str, stop_atr: float) -> float:
    """Stop level ``stop_atr`` ATRs adverse to the entry."""
    if side == "LONG":
        return entry - stop_atr * atr
    return entry + stop_atr * atr


def target_price(entry: float, atr: float, side: str, target_atr: float) -> float:
    """Target level ``target_atr`` ATRs favourable to the entry."""
    if side == "LONG":
        return entry + target_atr * atr
    return entry - target_atr * atr


def size_position(equity: float, risk_pct: float, entry: float, stop: float) -> tuple[float, float, float]:
    """(qty, risk_amount, risk_per_unit) from fractional-risk sizing."""
    return calculate_position_size(equity, risk_pct, entry, stop)


@dataclass(frozen=True)
class TradeSettlement:
    gross_pnl: float          # on intended (mid) prices, no costs
    net_pnl: float            # on fills, after fees
    fees: float
    slippage_cost: float      # gross - on-fill pnl (>= 0)
    r_multiple: float         # net / initial risk amount
    fee_cost_r: float
    slippage_cost_r: float


def settle_trade(
    side: str,
    entry_intended: float,
    exit_intended: float,
    qty: float,
    risk_amount: float,
    cost: CostModel,
) -> TradeSettlement:
    """Settle one round-trip in R terms, decomposing fee and slippage drag.

    ``entry_intended`` / ``exit_intended`` are the pre-slippage price levels (the
    bar open for entry, the stop/target/close level for exit). Slippage is
    applied here once per leg, so a caller that sized off ``fill_price(entry)``
    stays consistent — the same single slip is reproduced.
    """
    entry_fill = cost.fill_price(entry_intended, side, "entry")
    exit_fill = cost.fill_price(exit_intended, side, "exit")

    def _pnl(e: float, x: float) -> float:
        return (x - e) * qty if side == "LONG" else (e - x) * qty

    gross = _pnl(entry_intended, exit_intended)
    on_fills = _pnl(entry_fill, exit_fill)
    fees = cost.fee(entry_fill, qty) + cost.fee(exit_fill, qty)
    net = on_fills - fees
    slippage_cost = gross - on_fills

    r = net / risk_amount if risk_amount else 0.0
    fee_r = fees / risk_amount if risk_amount else 0.0
    slip_r = slippage_cost / risk_amount if risk_amount else 0.0
    return TradeSettlement(
        gross_pnl=gross,
        net_pnl=net,
        fees=fees,
        slippage_cost=slippage_cost,
        r_multiple=r,
        fee_cost_r=fee_r,
        slippage_cost_r=slip_r,
    )
