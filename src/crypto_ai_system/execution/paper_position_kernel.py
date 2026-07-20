"""Canonical paper position lifecycle (B-4).

Unifies paper execution onto one path: the PaperExecutionAdapter fills an *entry*
(open), this kernel tracks the single open position, and on a later cycle it
settles the position (SL / TP / time / manual exit) and produces a CLOSED outcome
with a real ``result_R`` tied to the full lineage chain (the entry's
reconciliation). This retires the legacy Path A position book — `paper_engine`'s
open/close no longer runs; its exit math is reproduced here so the kernel is the
single source of paper position truth.

No exchange side effects: purely simulated fills and settlement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.feedback.outcome_analytics_v2 import analyze_and_persist_paper_outcome
from crypto_ai_system.utils.audit import stable_id, utc_now_canonical

PAPER_POSITION_KERNEL_VERSION = "paper_position_kernel.v1"

# Max bars to hold before a time exit, per timeframe (mirrors A-1 / backtest).
MAX_HOLD_BARS = {"15m": 96, "1h": 48, "4h": 30}
DEFAULT_MAX_HOLD_BARS = 48

_FILLED = {"FILLED", "PARTIALLY_FILLED"}


def _latest_path(cfg: AppConfig, name: str) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _pos_path(cfg: AppConfig) -> Path:
    return _latest_path(cfg, "paper_position_v2.json")


def load_open_position(cfg: AppConfig | None = None) -> dict[str, Any] | None:
    cfg = cfg or load_config(".")
    pos = read_json(_pos_path(cfg), None)
    if isinstance(pos, dict) and pos.get("status") == "OPEN":
        return pos
    return None


def has_open_position(cfg: AppConfig | None = None) -> bool:
    return load_open_position(cfg) is not None


def _save_position(cfg: AppConfig, pos: Mapping[str, Any]) -> None:
    atomic_write_json(_pos_path(cfg), dict(pos))


def _clear_position(cfg: AppConfig) -> None:
    atomic_write_json(_pos_path(cfg), {"status": "CLOSED"})


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value not in {None, ""} else default
    except (TypeError, ValueError):
        return default


def _result_r(direction: str, entry: float, exit_price: float, risk: float) -> float:
    if risk <= 0:
        return 0.0
    signed = (exit_price - entry) if direction == "LONG" else (entry - exit_price)
    return signed / risk


def build_position(
    execution_record: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    *,
    cycle_id: str | None = None,
) -> dict[str, Any] | None:
    """The position dict a filled entry opens — pure, no IO.

    Split out so the multi-book kernel opens positions with byte-identical
    field logic; ``open_from_execution`` stays the single-book persistence
    wrapper around it."""
    fill = dict(execution_record.get("simulated_fill") or {})
    if fill.get("fill_status") not in _FILLED:
        return None
    intent = dict(execution_record.get("expected_order_intent") or {})
    entry = _f(fill.get("avg_fill_price") or intent.get("entry_price"))
    qty = _f(fill.get("filled_quantity") or intent.get("quantity"))
    sl = _f(intent.get("stop_loss"))
    tp = _f(intent.get("take_profit"))
    side = str(intent.get("side") or "").upper()
    direction = str(intent.get("direction") or ("LONG" if side == "BUY" else "SHORT")).upper()
    if entry <= 0 or qty <= 0:
        return None
    risk = abs(entry - sl) if sl > 0 else 0.0
    position = {
        "position_kernel_version": PAPER_POSITION_KERNEL_VERSION,
        "status": "OPEN",
        "direction": direction,
        "entry_price": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "quantity": qty,
        "risk": risk,
        "holding_candles": 0,
        "intrabar_policy": "pessimistic_sl_first",
        "opened_at_utc": utc_now_canonical(),
        "cycle_id": cycle_id,
        "research_signal_id": execution_record.get("research_signal_id") or reconciliation.get("research_signal_id"),
        "decision_id": execution_record.get("decision_id") or reconciliation.get("decision_id"),
        "risk_gate_id": execution_record.get("risk_gate_id") or reconciliation.get("risk_gate_id"),
        "order_intent_id": execution_record.get("order_intent_id") or reconciliation.get("order_intent_id"),
        "execution_id": execution_record.get("execution_id") or reconciliation.get("execution_id"),
        "reconciliation_id": reconciliation.get("reconciliation_id"),
        # Strategy-factory attribution (S8) when a strategy drove this entry; None
        # for research-driven entries. Rides through to the CLOSED outcome.
        "strategy_id": intent.get("strategy_id") if intent.get("strategy_id") != "research_bridge_v2" else None,
        "supporting_strategy_ids": intent.get("supporting_strategy_ids") or [],
        "strategy_entry_evaluation_id": intent.get("strategy_entry_evaluation_id"),
        "strategy_rule_hash": intent.get("strategy_rule_hash"),
        "strategy_generation_id": intent.get("strategy_generation_id"),
        # The entry reconciliation is what the outcome is computed from on close.
        "entry_reconciliation": dict(reconciliation),
    }
    position["position_id"] = stable_id(
        "paper_position",
        {"execution_id": position["execution_id"], "entry": entry, "opened_at": position["opened_at_utc"]},
        24,
    )
    return position


def open_from_execution(
    execution_record: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    *,
    cycle_id: str | None = None,
    cfg: AppConfig | None = None,
) -> dict[str, Any] | None:
    """Open a paper position from a filled entry execution. Returns the position
    (or None if the fill did not open a position)."""
    cfg = cfg or load_config(".")
    position = build_position(execution_record, reconciliation, cycle_id=cycle_id)
    if position is None:
        return None
    _save_position(cfg, position)
    return position


def _advance_holding(position: dict[str, Any], candle: Mapping[str, Any] | None) -> None:
    """Advance holding_candles once per DISTINCT candle.

    Settle used to count invocations, so extra manual pipeline runs within one
    interval accelerated time_exit. A candle without a timestamp keeps the old
    per-invocation behavior (nothing to dedupe on)."""
    ts = candle.get("timestamp") if isinstance(candle, Mapping) else None
    if ts is not None and str(ts) == str(position.get("last_counted_candle_ts") or ""):
        return
    position["holding_candles"] = int(position.get("holding_candles", 0)) + 1
    if ts is not None:
        position["last_counted_candle_ts"] = str(ts)


def settle_trade_plan(
    position: dict[str, Any],
    candle: Mapping[str, Any] | None,
    last_close: float | None,
    max_hold: int,
    manual_exit: bool,
) -> tuple[str | None, float | None, float | None]:
    """Return (close_reason, exit_price, result_R) or (None, None, None) if still open.

    Precedence: manual exit -> intrabar SL/TP (pessimistic SL-first) -> time exit.

    Public because the counterfactual tracker settles shadow (blocked) trade plans
    with it: a blocked signal's hypothetical result is only comparable to a real
    paper outcome if both are produced by this exact math. ``position`` needs only
    the plan fields (direction/entry_price/stop_loss/take_profit/risk) and is
    mutated in place to advance ``holding_candles``."""
    direction = position["direction"]
    entry = _f(position["entry_price"])
    sl = _f(position["stop_loss"])
    tp = _f(position["take_profit"])
    risk = _f(position["risk"])

    if manual_exit and last_close is not None:
        return "manual_exit", last_close, _result_r(direction, entry, last_close, risk)

    _advance_holding(position, candle)
    if candle is not None and risk > 0:
        high = _f(candle.get("high"))
        low = _f(candle.get("low"))
        if direction == "LONG":
            if low <= sl:
                return "stop_loss", sl, -1.0
            if high >= tp:
                return "take_profit", tp, (tp - entry) / risk
        else:
            if high >= sl:
                return "stop_loss", sl, -1.0
            if low <= tp:
                return "take_profit", tp, (entry - tp) / risk

    if last_close is not None and int(position.get("holding_candles", 0)) >= int(max_hold):
        return "time_exit", last_close, _result_r(direction, entry, last_close, risk)

    return None, None, None


def settle_open_position(
    candle: Mapping[str, Any] | None,
    *,
    last_close: float | None = None,
    manual_exit: bool = False,
    timeframe: str = "1h",
    regime: str | None = None,
    cfg: AppConfig | None = None,
) -> dict[str, Any] | None:
    """Evaluate the open position for exit; on close, produce a CLOSED outcome.

    Returns a summary dict on close, else None (no open position or still open)."""
    cfg = cfg or load_config(".")
    position = load_open_position(cfg)
    if not position:
        return None

    max_hold = MAX_HOLD_BARS.get(timeframe, DEFAULT_MAX_HOLD_BARS)
    reason, exit_price, result_r = settle_trade_plan(position, candle, last_close, max_hold, manual_exit)
    if reason is None:
        position["last_seen_price"] = last_close
        _save_position(cfg, position)
        return None

    context = {
        "exit_price": exit_price,
        "result_R": round(float(result_r), 8),
        "close_reason": reason,
        "regime": regime or "unknown",
    }
    outcome = analyze_and_persist_paper_outcome(
        position.get("entry_reconciliation") or {},
        outcome_context=context,
        cfg=cfg,
    )
    _clear_position(cfg)
    return {
        "position_id": position.get("position_id"),
        "close_reason": reason,
        "exit_price": exit_price,
        "result_R": round(float(result_r), 8),
        "execution_id": position.get("execution_id"),
        "outcome_id": outcome.get("outcome_id"),
        "outcome_status": outcome.get("status"),
    }
