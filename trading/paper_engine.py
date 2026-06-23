from __future__ import annotations

import csv
from typing import Any

from config.settings import MARKET_DATA_PATH, PAPER_STATE_PATH, PAPER_TRADES_CSV_PATH, PAPER_TRADES_PATH, RISK_PER_TRADE
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from core.event_log import log_event
from trading.atr import stop_distance_bps_from_atr
from trading.position_sizing import calculate_position_size


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


def build_paper_position(signal: str, entry_price: float, reason: str = "") -> dict[str, Any]:
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
        "quantity": sizing["quantity"],
        "notional_usdt": sizing["notional_usdt"],
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
    if result == "WIN":
        pnl_r = abs(exit_price - entry) / risk
    elif result == "LOSS":
        pnl_r = -1.0
    else:
        pnl_r = 0.0

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


def run_paper_cycle(signal_payload: dict[str, Any], snapshot: dict[str, Any], allow_new_position: bool = True) -> dict[str, Any]:
    state = load_paper_state()
    active = state.get("active_position")
    signal = signal_payload.get("signal", "NONE")
    reasons = signal_payload.get("reasons", [])

    if active:
        active["last_seen_price"] = snapshot.get("last_close")
        state["active_position"] = active
        save_paper_state(state)
        return {"status": "ACTIVE_POSITION_UPDATED", "active_position": active}

    if not allow_new_position:
        save_paper_state(state)
        return {"status": "BLOCKED_BY_GUARD", "active_position": None}

    if signal not in {"LONG", "SHORT"}:
        save_paper_state(state)
        return {"status": "NO_SIGNAL", "active_position": None}

    entry_price = float(snapshot["last_close"])
    position = build_paper_position(signal, entry_price, ",".join(reasons))
    state["active_position"] = position
    save_paper_state(state)
    log_event("paper_position_opened", {"direction": signal, "entry_price": entry_price, "notional": position.get("notional_usdt")})
    return {"status": "POSITION_OPENED", "active_position": position}
