from __future__ import annotations

import csv
from typing import Any

from config.settings import MARKET_DATA_PATH, PAPER_STATE_PATH, PAPER_TRADES_CSV_PATH, PAPER_TRADES_PATH, RISK_PER_TRADE
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event
from crypto_ai_system.trading.atr import stop_distance_bps_from_atr
from crypto_ai_system.trading.position_sizing import calculate_position_size


PAPER_ENGINE_MODE = "PAPER_ONLY"
LIVE_TRADING_ALLOWED_BY_THIS_MODULE = False
EXTERNAL_ORDER_SUBMISSION_PERFORMED = False

# B-4: the canonical paper position lifecycle now lives in
# execution.paper_position_kernel. This legacy Path A book no longer opens or
# closes positions in the active runtime (single paper path). The exit math
# (evaluate_open_position / close_trade / update_position_conservative) is kept
# for reuse and regression tests; set False to exercise the legacy path directly.
KERNEL_OWNS_POSITIONS = True

# Max bars to hold an open paper position before a time-based exit. Without this
# a position that neither hits SL nor TP stays open forever, so no closed trade
# is ever collected and performance can't be measured (directive P0-4). Values
# mirror the backtest matrix so paper and backtest agree on holding horizon.
PAPER_MAX_HOLD_BARS = {"15m": 96, "1h": 48, "4h": 30}
DEFAULT_MAX_HOLD_BARS = 48


def _default_state() -> dict[str, Any]:
    return {"active_position": None, "last_update": None, "closed_trades": []}


def load_paper_state() -> dict[str, Any]:
    state = read_json(PAPER_STATE_PATH, None)
    if not isinstance(state, dict):
        state = _default_state()
    state.setdefault("active_position", None)
    state.setdefault("closed_trades", [])
    return state


def save_paper_state(state: dict[str, Any]) -> None:
    state["last_update"] = utc_now_iso()
    atomic_write_json(PAPER_STATE_PATH, state)


def _save_trade(trade: dict[str, Any]) -> None:
    trades = read_json(PAPER_TRADES_PATH, [])
    if not isinstance(trades, list):
        trades = []
    trades.append(trade)
    atomic_write_json(PAPER_TRADES_PATH, trades)
    PAPER_TRADES_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({k for row in trades for k in row.keys()})
    with PAPER_TRADES_CSV_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        writer.writerows(trades)


def build_paper_position(
    signal: str,
    entry_price: float,
    reason: str = "",
    position_size_multiplier: float = 1.0,
    risk_level: str = "normal",
    research_signal_id: str | None = None,
    permission_gate_applied: bool = False,
) -> dict[str, Any]:
    market_data = read_json(MARKET_DATA_PATH, {})
    candles = market_data.get("candles", [])
    atr_info = stop_distance_bps_from_atr(entry_price, candles)
    stop_distance_pct = float(atr_info["final_stop_distance_bps"]) / 10000
    reward_r = 2.0

    if signal == "LONG":
        stop_loss = entry_price * (1 - stop_distance_pct)
        take_profit = entry_price + (entry_price - stop_loss) * reward_r
    elif signal == "SHORT":
        stop_loss = entry_price * (1 + stop_distance_pct)
        take_profit = entry_price - (stop_loss - entry_price) * reward_r
    else:
        raise ValueError("signal must be LONG or SHORT")

    risk = abs(entry_price - stop_loss)
    sizing = calculate_position_size(entry_price, stop_loss)
    multiplier = max(0.0, min(1.0, float(position_size_multiplier or 0.0)))
    quantity = float(sizing["quantity"]) * multiplier
    notional_usdt = float(sizing["notional_usdt"]) * multiplier

    return {
        "trade_id": f"paper_{utc_now_iso()}_{signal}",
        "status": "OPEN",
        "direction": signal,
        "entry_time": utc_now_iso(),
        "entry_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "risk": round(risk, 2),
        "risk_per_trade": RISK_PER_TRADE,
        "quantity": round(quantity, 8),
        "notional_usdt": round(notional_usdt, 4),
        "position_size_multiplier": multiplier,
        "risk_level": risk_level,
        "research_signal_id": research_signal_id,
        "permission_gate_applied": permission_gate_applied,
        "position_sizing_reason": sizing["reason"],
        "atr_info": atr_info,
        "entry_reason": reason,
        "exit_reason": None,
        "holding_candles": 0,
        "max_favorable_excursion": 0.0,
        "max_adverse_excursion": 0.0,
        "intrabar_policy": "pessimistic_sl_first",
    }


def close_trade(position: dict[str, Any], result: str, exit_price: float, exit_reason: str) -> dict[str, Any]:
    entry = float(position["entry_price"])
    risk = float(position["risk"])
    direction = str(position.get("direction", "LONG")).upper()
    if result == "WIN":
        pnl_r = abs(exit_price - entry) / risk if risk else 0.0
    elif result == "LOSS":
        pnl_r = -1.0
    else:
        # TIME_EXIT / MANUAL_EXIT close at market: realized signed R, not a
        # capped -1R (SL) or fixed +reward (TP). A long that time-exits above
        # entry is a partial win; below entry, a partial loss.
        signed = (exit_price - entry) if direction == "LONG" else (entry - exit_price)
        pnl_r = signed / risk if risk else 0.0

    trade = {
        **position,
        "status": "CLOSED",
        "exit_time": utc_now_iso(),
        "exit_price": round(exit_price, 2),
        "result": result,
        "pnl_r": round(pnl_r, 4),
        "exit_reason": exit_reason,
    }
    _save_trade(trade)
    return trade


def update_position_conservative(position: dict[str, Any], candle: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    high = float(candle["high"])
    low = float(candle["low"])
    direction = position["direction"]
    entry = float(position["entry_price"])
    sl = float(position["stop_loss"])
    tp = float(position["take_profit"])
    risk = float(position["risk"])

    position["holding_candles"] = int(position.get("holding_candles", 0)) + 1

    if direction == "LONG":
        position["max_favorable_excursion"] = max(float(position.get("max_favorable_excursion", 0)), (high - entry) / risk)
        position["max_adverse_excursion"] = max(float(position.get("max_adverse_excursion", 0)), (entry - low) / risk)
        if low <= sl:
            return close_trade(position, "LOSS", sl, "stop_loss_pessimistic_first"), None
        if high >= tp:
            return close_trade(position, "WIN", tp, "take_profit"), None
    else:
        position["max_favorable_excursion"] = max(float(position.get("max_favorable_excursion", 0)), (entry - low) / risk)
        position["max_adverse_excursion"] = max(float(position.get("max_adverse_excursion", 0)), (high - entry) / risk)
        if high >= sl:
            return close_trade(position, "LOSS", sl, "stop_loss_pessimistic_first"), None
        if low <= tp:
            return close_trade(position, "WIN", tp, "take_profit"), None

    return None, position


def _latest_candle() -> dict[str, Any] | None:
    data = read_json(MARKET_DATA_PATH, {})
    candles = data.get("candles", [])
    if not candles:
        return None
    last = candles[-1]
    if not isinstance(last, dict) or "high" not in last or "low" not in last:
        return None
    return last


def evaluate_open_position(
    position: dict[str, Any],
    candle: dict[str, Any] | None,
    *,
    last_close: float | None = None,
    manual_exit: bool = False,
    max_hold_bars: int = DEFAULT_MAX_HOLD_BARS,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Evaluate whether an open paper position should close this cycle.

    Order of precedence: manual override -> intrabar SL/TP (pessimistic SL-first
    on the same candle) -> time exit. Returns ``(closed_trade, None)`` when the
    position closed, else ``(None, still_open_position)``. Pure w.r.t. state
    files except that ``close_trade`` records the closed trade.
    """
    if manual_exit:
        exit_price = float(last_close if last_close is not None else position.get("entry_price", 0.0))
        return close_trade(position, "MANUAL_EXIT", exit_price, "manual_exit"), None

    if candle is not None:
        closed, still_open = update_position_conservative(position, candle)
        if closed is not None:
            return closed, None
        position = still_open or position

    if last_close is not None and int(position.get("holding_candles", 0)) >= int(max_hold_bars):
        return close_trade(position, "TIME_EXIT", float(last_close), "time_exit"), None

    return None, position


def run_paper_cycle(signal_payload: dict[str, Any], snapshot: dict[str, Any], allow_new_position: bool = True) -> dict[str, Any]:
    if KERNEL_OWNS_POSITIONS:
        # Positions are owned by execution.paper_position_kernel; this legacy
        # book is inert in the active runtime (retired Path A).
        return {"status": "DELEGATED_TO_KERNEL", "active_position": None}
    state = load_paper_state()
    active = state.get("active_position")
    signal = signal_payload.get("signal", "NONE")
    reasons = signal_payload.get("reasons", [])

    if active:
        # An open position is evaluated for exit BEFORE any new-entry logic.
        # Previously this branch only stamped last_seen_price and returned, so
        # positions never closed and no closed outcome was ever produced (P0-4).
        last_close = snapshot.get("last_close")
        last_close_f = None if last_close in {None, ""} else float(last_close)
        timeframe = str(snapshot.get("timeframe", "1h"))
        max_hold = PAPER_MAX_HOLD_BARS.get(timeframe, DEFAULT_MAX_HOLD_BARS)
        closed, still_open = evaluate_open_position(
            active,
            _latest_candle(),
            last_close=last_close_f,
            manual_exit=bool(signal_payload.get("manual_exit", False)),
            max_hold_bars=max_hold,
        )
        if closed is not None:
            state["active_position"] = None
            state.setdefault("closed_trades", []).append(closed)
            save_paper_state(state)
            log_event(
                "paper_position_closed",
                {
                    "direction": closed.get("direction"),
                    "exit_reason": closed.get("exit_reason"),
                    "result": closed.get("result"),
                    "pnl_r": closed.get("pnl_r"),
                },
            )
            return {"status": "POSITION_CLOSED", "closed_trade": closed, "active_position": None}

        still_open["last_seen_price"] = last_close
        state["active_position"] = still_open
        save_paper_state(state)
        return {"status": "ACTIVE_POSITION_UPDATED", "active_position": still_open}

    permission_allow_new = bool(signal_payload.get("allow_new_position", True))
    risk_level = str(signal_payload.get("risk_level", "normal"))
    position_size_multiplier = float(signal_payload.get("position_size_multiplier", 1.0) or 0.0)

    if not allow_new_position or not permission_allow_new or risk_level == "blocked" or position_size_multiplier <= 0:
        save_paper_state(state)
        return {
            "status": "BLOCKED_BY_PERMISSION_GATE",
            "active_position": None,
            "risk_level": risk_level,
            "position_size_multiplier": position_size_multiplier,
            "reasons": reasons + signal_payload.get("block_reasons", []),
        }

    if signal not in {"LONG", "SHORT"}:
        save_paper_state(state)
        return {"status": "NO_SIGNAL", "active_position": None}

    entry_price = float(snapshot["last_close"])
    position = build_paper_position(
        signal,
        entry_price,
        ",".join(reasons),
        position_size_multiplier=position_size_multiplier,
        risk_level=risk_level,
        research_signal_id=signal_payload.get("research_signal_id"),
        permission_gate_applied=bool(signal_payload.get("permission_gate_applied", False)),
    )
    state["active_position"] = position
    save_paper_state(state)
    log_event("paper_position_opened", {"direction": signal, "entry_price": entry_price, "notional": position.get("notional_usdt")})
    return {"status": "POSITION_OPENED", "active_position": position}


def run_paper_engine(sample: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper for legacy regression tests."""
    signal = sample.get("signal", "NONE")
    snapshot = sample.get("snapshot", {}) or {}
    if "last_close" not in snapshot:
        snapshot["last_close"] = snapshot.get("close", 0) or 0
    payload = {"signal": signal, "reasons": sample.get("reasons", [])}
    result = run_paper_cycle(payload, snapshot, allow_new_position=True)
    state = load_paper_state()
    state["last_result"] = result
    return state
