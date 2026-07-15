from __future__ import annotations

from datetime import timedelta

from config.settings import (
    DAILY_MAX_LOSS_R,
    MAX_CONSECUTIVE_LOSSES,
    MAX_DRAWDOWN_PCT,
    PAPER_TRADES_PATH,
    RISK_STATUS_PATH,
    WEEKLY_MAX_LOSS_R,
)
from core.json_io import atomic_write_json, read_json
from core.time_utils import parse_time, utc_now, utc_now_iso
from core.event_log import log_event


def _closed_trades() -> list[dict]:
    # B-4: the canonical paper position kernel is the single source of closed
    # paper outcomes. Read them from the outcome-feedback registry (result_R),
    # not the retired Path A trade file.
    try:
        from crypto_ai_system.config import load_config
        from crypto_ai_system.registry.base_registry import load_registry_records, registry_path

        cfg = load_config(".")
        rows = load_registry_records(registry_path(cfg, "outcome_feedback_registry"))
        trades = [
            {
                "status": "CLOSED",
                "pnl_r": float(r.get("result_R", 0.0) or 0.0),
                "exit_time": r.get("created_at_utc"),
                "result": r.get("win_loss"),
            }
            for r in rows
            if r.get("outcome_closed") is True
        ]
        return trades
    except Exception:  # noqa: BLE001 - fall back to the legacy paper trade file
        data = read_json(PAPER_TRADES_PATH, [])
        if isinstance(data, list):
            return [t for t in data if t.get("status") == "CLOSED" or t.get("result")]
        return []


def _pnl_since(trades: list[dict], start_time) -> float:
    total = 0.0
    for trade in trades:
        t = parse_time(trade.get("exit_time") or trade.get("closed_at") or trade.get("timestamp"))
        if t and t >= start_time:
            total += float(trade.get("pnl_r", trade.get("net_pnl_r", 0.0)))
    return total


def _consecutive_losses(trades: list[dict]) -> int:
    count = 0
    for trade in reversed(trades):
        pnl = float(trade.get("pnl_r", trade.get("net_pnl_r", 0.0)))
        if pnl < 0:
            count += 1
        else:
            break
    return count


def _max_drawdown_r(trades: list[dict]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for trade in trades:
        equity += float(trade.get("pnl_r", trade.get("net_pnl_r", 0.0)))
        peak = max(peak, equity)
        dd = equity - peak
        max_dd = min(max_dd, dd)
    return max_dd


def run_risk_guard() -> dict:
    trades = sorted(_closed_trades(), key=lambda x: str(x.get("exit_time", "")))
    now = utc_now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())

    daily_pnl_r = _pnl_since(trades, day_start)
    weekly_pnl_r = _pnl_since(trades, week_start)
    consecutive_losses = _consecutive_losses(trades)
    drawdown_r = _max_drawdown_r(trades)

    problems = []
    if daily_pnl_r <= DAILY_MAX_LOSS_R:
        problems.append("daily_loss_limit_breached")
    if weekly_pnl_r <= WEEKLY_MAX_LOSS_R:
        problems.append("weekly_loss_limit_breached")
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        problems.append("max_consecutive_losses_breached")
    # MAX_DRAWDOWN_PCT is retained for compatibility; for R-based MVP use negative R drawdown threshold of abs value / 100 mapping.
    if drawdown_r <= -abs(MAX_DRAWDOWN_PCT) / 10:
        problems.append("max_drawdown_proxy_breached")

    status = "NORMAL"
    allow_new_position = True
    if problems:
        status = "BLOCK_NEW_POSITION"
        allow_new_position = False

    result = {
        "created_at": utc_now_iso(),
        "status": status,
        "allow_new_position": allow_new_position,
        "daily_pnl_r": round(daily_pnl_r, 4),
        "weekly_pnl_r": round(weekly_pnl_r, 4),
        "consecutive_losses": consecutive_losses,
        "drawdown_r": round(drawdown_r, 4),
        "problems": problems,
        "calculation_mode": "time_based_exit_time",
    }
    atomic_write_json(RISK_STATUS_PATH, result)
    log_event("risk_guard_checked", {"status": status, "problems": problems})
    return result


def main() -> None:
    result = run_risk_guard()
    print(f"Risk Guard: {result['status']} allow_new_position={result['allow_new_position']}")


if __name__ == "__main__":
    main()
