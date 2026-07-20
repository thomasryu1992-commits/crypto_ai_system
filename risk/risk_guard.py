from __future__ import annotations

from datetime import timedelta

from config.settings import (
    DAILY_MAX_LOSS_R,
    MAX_CONSECUTIVE_LOSSES,
    MAX_DRAWDOWN_PCT,
    RISK_PER_TRADE,
    RISK_STATUS_PATH,
    WEEKLY_MAX_LOSS_R,
)
from core.json_io import atomic_write_json
from core.time_utils import parse_time, utc_now, utc_now_iso
from core.event_log import log_event


class RiskHistoryUnreadable(RuntimeError):
    """The canonical outcome registry could not be read — risk limits cannot
    be computed, so the guard must BLOCK, never silently trade on no history."""


def _closed_trades() -> list[dict]:
    # B-4: the canonical paper position kernel is the single source of closed
    # paper outcomes. Read them from the outcome-feedback registry (result_R).
    # There is deliberately NO fallback: a damaged/unreadable registry means the
    # loss limits would be computed over nothing, which is fail-open — the old
    # fallback to the retired paper_trades.json silently reset every limit.
    try:
        from crypto_ai_system.config import load_config
        from crypto_ai_system.registry.base_registry import load_registry_records, registry_path

        cfg = load_config(".")
        rows = load_registry_records(registry_path(cfg, "outcome_feedback_registry"))
    except Exception as exc:  # noqa: BLE001 - surfaced as a blocking verdict by run_risk_guard
        raise RiskHistoryUnreadable(f"{type(exc).__name__}: {exc}") from exc
    return [
        {
            "status": "CLOSED",
            "pnl_r": float(r.get("result_R", 0.0) or 0.0),
            "exit_time": r.get("created_at_utc"),
            "result": r.get("win_loss"),
        }
        for r in rows
        if r.get("outcome_closed") is True
    ]


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


def _drawdowns_r(trades: list[dict]) -> tuple[float, float]:
    """(max historical drawdown, CURRENT drawdown from peak), both <= 0, in R.

    The breaker acts on the CURRENT drawdown so it unlatches when equity
    recovers to a new peak — the historical max is reporting only. (Previously
    the breaker used the all-time max, so one deep dip blocked new positions
    forever until a manual outcome reset.)
    """
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for trade in trades:
        equity += float(trade.get("pnl_r", trade.get("net_pnl_r", 0.0)))
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd, equity - peak


def _drawdown_limit_r() -> float:
    """MAX_DRAWDOWN_PCT (equity %) mapped to R via risk-per-trade.

    Default -10% at 1% risk per trade = 10R of cumulative loss from the peak.
    """
    risk_pct = RISK_PER_TRADE if RISK_PER_TRADE > 0 else 0.01
    return (abs(MAX_DRAWDOWN_PCT) / 100.0) / risk_pct


def run_risk_guard() -> dict:
    try:
        trades = sorted(_closed_trades(), key=lambda x: str(x.get("exit_time", "")))
    except RiskHistoryUnreadable as exc:
        # Fail closed: no risk history means no new positions, loudly.
        result = {
            "created_at": utc_now_iso(),
            "status": "BLOCK_NEW_POSITION",
            "allow_new_position": False,
            "daily_pnl_r": 0.0,
            "weekly_pnl_r": 0.0,
            "consecutive_losses": 0,
            "drawdown_r": 0.0,
            "problems": ["risk_history_unreadable"],
            "risk_history_error": str(exc),
            "calculation_mode": "time_based_exit_time",
        }
        atomic_write_json(RISK_STATUS_PATH, result)
        log_event(
            "risk_guard_history_unreadable",
            {"error": str(exc)},
            severity="ERROR",
        )
        return result
    now = utc_now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())

    daily_pnl_r = _pnl_since(trades, day_start)
    weekly_pnl_r = _pnl_since(trades, week_start)
    consecutive_losses = _consecutive_losses(trades)
    max_drawdown_r, current_drawdown_r = _drawdowns_r(trades)

    problems = []
    if daily_pnl_r <= DAILY_MAX_LOSS_R:
        problems.append("daily_loss_limit_breached")
    if weekly_pnl_r <= WEEKLY_MAX_LOSS_R:
        problems.append("weekly_loss_limit_breached")
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        problems.append("max_consecutive_losses_breached")
    if current_drawdown_r <= -_drawdown_limit_r():
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
        "drawdown_r": round(current_drawdown_r, 4),
        "max_drawdown_r": round(max_drawdown_r, 4),
        "drawdown_limit_r": round(_drawdown_limit_r(), 4),
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
