"""L5: canonical live position lifecycle.

The live sibling of the paper position kernel: a filled live ENTRY opens the
single tracked live position; each later cycle evaluates it for exit (manual /
intrabar SL-TP, pessimistic SL-first / time exit) using the same math as paper —
but where paper *simulates* the close, this kernel submits a REAL reduceOnly
close order through the narrow live close guard, reads the actual close fill
back from the exchange, computes realized USDT P&L from the two real fills, and
feeds the L1 live P&L ledger (which drives the daily-loss circuit breaker) plus
the S8 strategy attribution summary.

Fail-open-position semantics: when the close order is blocked or rejected, the
position STAYS OPEN and the failure is logged loudly — the kernel never
fabricates a close. The next cycle retries; the operator can always flatten
manually on the venue (that path never depends on this code).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.event_log import log_event
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now_iso
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.idempotency import enrich_order_identity
from crypto_ai_system.execution.live_pnl_ledger import record_live_outcome
from crypto_ai_system.utils.audit import stable_id, utc_now_canonical

LIVE_POSITION_KERNEL_VERSION = "live_position_kernel.v1"

# Same hold policy as the paper kernel / backtest.
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
    return _latest_path(cfg, "live_position_v1.json")


def load_open_live_position(cfg: AppConfig | None = None) -> dict[str, Any] | None:
    cfg = cfg or load_config(".")
    pos = read_json(_pos_path(cfg), None)
    if isinstance(pos, dict) and pos.get("status") == "OPEN":
        return pos
    return None


def has_open_live_position(cfg: AppConfig | None = None) -> bool:
    return load_open_live_position(cfg) is not None


def open_live_notional_usdt(cfg: AppConfig | None = None) -> float:
    """Current open live exposure (entry price x quantity), 0.0 when flat."""
    pos = load_open_live_position(cfg)
    if not pos:
        return 0.0
    return _f(pos.get("entry_price")) * _f(pos.get("quantity"))


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


def _realized_pnl_usdt(direction: str, entry: float, exit_price: float, qty: float) -> float:
    """Realized P&L from the two fills. Fees are not modelled here — the ledger
    records fill-to-fill P&L; commission shows up in the venue balance."""
    signed = (exit_price - entry) if direction == "LONG" else (entry - exit_price)
    return signed * qty


def open_from_live_execution(
    order_result: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    *,
    cycle_id: str | None = None,
    cfg: AppConfig | None = None,
) -> dict[str, Any] | None:
    """Open the tracked live position from a filled live entry. Returns it, or None.

    The entry price/quantity come from the exchange's actual fill (via the
    reconciliation), not from the intent — the position tracks reality.
    """
    cfg = cfg or load_config(".")
    if not order_result.get("external_order_submission_performed"):
        return None
    if str(reconciliation.get("status") or "") not in {"RECONCILED"}:
        # An entry we cannot reconcile is not silently trusted; the operator
        # resolves it manually. Loud, fail-closed for position tracking.
        log_event(
            "live_position_open_skipped_unreconciled",
            {"reconciliation_status": reconciliation.get("status")},
            severity="WARNING",
        )
        return None
    actual = dict(reconciliation.get("actual") or {})
    if actual.get("order_status") not in _FILLED:
        return None
    intent = dict(order_result.get("intent") or {})
    entry = _f(actual.get("avg_fill_price") or intent.get("entry_price"))
    qty = _f(actual.get("executed_qty") or intent.get("quantity"))
    sl = _f(intent.get("stop_loss"))
    tp = _f(intent.get("take_profit"))
    side = str(intent.get("side") or "").upper()
    direction = str(intent.get("direction") or ("LONG" if side == "BUY" else "SHORT")).upper()
    if entry <= 0 or qty <= 0:
        return None
    risk = abs(entry - sl) if sl > 0 else 0.0
    position = {
        "position_kernel_version": LIVE_POSITION_KERNEL_VERSION,
        "status": "OPEN",
        "stage": "live",
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
        "symbol": intent.get("symbol"),
        "entry_client_order_id": order_result.get("client_order_id"),
        "entry_exchange_order_id": order_result.get("exchange_order_id"),
        "research_signal_id": intent.get("research_signal_id"),
        "decision_id": intent.get("decision_id"),
        "risk_gate_id": intent.get("risk_gate_id"),
        "order_intent_id": intent.get("order_intent_id"),
        # S8 attribution rides through to the outcome (same as paper).
        "strategy_id": intent.get("strategy_id") if intent.get("strategy_id") != "research_bridge_v2" else None,
        "supporting_strategy_ids": intent.get("supporting_strategy_ids") or [],
        "strategy_entry_evaluation_id": intent.get("strategy_entry_evaluation_id"),
        "strategy_rule_hash": intent.get("strategy_rule_hash"),
        "strategy_generation_id": intent.get("strategy_generation_id"),
    }
    position["position_id"] = stable_id(
        "live_position",
        {"entry_order": position["entry_exchange_order_id"], "entry": entry, "opened_at": position["opened_at_utc"]},
        24,
    )
    _save_position(cfg, position)
    log_event("live_position_opened", {"position_id": position["position_id"], "entry": entry, "qty": qty})
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


def _exit_signal(
    position: dict[str, Any],
    candle: Mapping[str, Any] | None,
    last_close: float | None,
    max_hold: int,
    manual_exit: bool,
) -> str | None:
    """Exit reason for this cycle, or None while the position should stay open.

    Same precedence as the paper kernel: manual -> intrabar SL/TP (pessimistic
    SL-first) -> time exit. The actual exit PRICE comes from the real close fill,
    so only the reason is decided here.
    """
    direction = position["direction"]
    sl = _f(position["stop_loss"])
    tp = _f(position["take_profit"])
    risk = _f(position["risk"])

    if manual_exit and last_close is not None:
        return "manual_exit"

    _advance_holding(position, candle)
    if candle is not None and risk > 0:
        high = _f(candle.get("high"))
        low = _f(candle.get("low"))
        if direction == "LONG":
            if low <= sl:
                return "stop_loss"
            if high >= tp:
                return "take_profit"
        else:
            if high >= sl:
                return "stop_loss"
            if low <= tp:
                return "take_profit"

    if last_close is not None and int(position.get("holding_candles", 0)) >= int(max_hold):
        return "time_exit"
    return None


def _close_intent(
    position: Mapping[str, Any],
    close_reason: str,
    last_close: float | None,
    *,
    client_order_id: str | None = None,
) -> dict[str, Any]:
    direction = str(position.get("direction") or "LONG").upper()
    side = "SELL" if direction == "LONG" else "BUY"
    qty = _f(position.get("quantity"))
    price = _f(last_close or position.get("entry_price"))
    intent = {
        "created_at": utc_now_iso(),
        "status": "ORDER_INTENT_CREATED",
        "execution_stage": "live",
        "decision_stage": "live",
        "symbol": position.get("symbol"),
        "direction": "SHORT" if direction == "LONG" else "LONG",
        "side": side,
        "order_type": "MARKET_LIVE_CLOSE",
        "order_type_exchange": "MARKET",
        "entry_price": price,
        "quantity": qty,
        "order_notional_usdt": round(qty * price, 2) if price > 0 else 0.0,
        "notional_usdt": round(qty * price, 2) if price > 0 else 0.0,
        "reduce_only": True,
        "close_reason": close_reason,
        "position_id": position.get("position_id"),
        "risk_gate_id": position.get("risk_gate_id"),
        "order_intent_created": True,
    }
    intent = enrich_order_identity(intent)
    if client_order_id:
        # Retrying an earlier unconfirmed close MUST reuse its client order id —
        # a fresh id would race a second reduceOnly close against a fill the
        # first one may already have produced.
        intent["client_order_id"] = client_order_id
    return intent


# Venue order states that prove a close order will never fill (safe to retire
# its client order id and submit a fresh close).
_CLOSE_DEAD = {"CANCELED", "REJECTED", "EXPIRED"}


def _settle_from_fill(
    cfg: AppConfig,
    position: dict[str, Any],
    reason: str,
    exit_price: float,
    filled_qty: float,
    close_exchange_order_id: Any,
    regime: str | None,
) -> dict[str, Any]:
    """Record the realized outcome from a REAL close fill and clear the position."""
    direction = str(position.get("direction") or "LONG").upper()
    entry = _f(position.get("entry_price"))
    qty = filled_qty or _f(position.get("quantity"))
    risk = _f(position.get("risk"))
    realized = _realized_pnl_usdt(direction, entry, exit_price, qty)
    result_r = _result_r(direction, entry, exit_price, risk)

    # Feed the L1 ledger — this is what the daily-loss circuit breaker reads.
    ledger_record = record_live_outcome(
        realized_pnl_usdt=realized,
        symbol=str(position.get("symbol")),
        side="BUY" if direction == "LONG" else "SELL",
        quantity=qty,
        open_price=entry,
        close_price=exit_price,
        open_order_id=position.get("entry_exchange_order_id"),
        close_order_id=close_exchange_order_id,
        strategy_id=position.get("strategy_id"),
        opened_at_utc=position.get("opened_at_utc"),
    )
    _clear_position(cfg)
    log_event(
        "live_position_closed",
        {"position_id": position.get("position_id"), "close_reason": reason,
         "realized_pnl_usdt": round(realized, 8), "result_R": round(result_r, 8)},
    )
    return {
        "status": "CLOSED",
        "position_id": position.get("position_id"),
        "close_reason": reason,
        "exit_price": exit_price,
        "quantity": qty,
        "realized_pnl_usdt": round(realized, 8),
        "result_R": round(result_r, 8),
        "regime": regime or "unknown",
        "live_outcome_record_id": ledger_record.get("live_outcome_record_id"),
        "close_exchange_order_id": close_exchange_order_id,
    }


def _resolve_pending_close(
    cfg: AppConfig,
    position: dict[str, Any],
    query_order: Callable[[str, str], dict],
    regime: str | None,
) -> dict[str, Any] | None:
    """Settle/track an earlier close attempt whose fill was never confirmed.

    Returns a settlement/hold dict when the pending close decides this cycle, or
    None when the pending id is proven dead (the caller may submit a fresh
    close). The pending id was persisted BEFORE the original submit, so even a
    crash mid-submit is re-queried here rather than double-closed.
    """
    pending_id = position.get("close_client_order_id")
    if not pending_id:
        return None
    reason = str(position.get("close_reason_pending") or "manual_exit")
    query = query_order(str(position.get("symbol")), str(pending_id))
    query = query if isinstance(query, dict) else {}
    if query.get("ok"):
        response = query.get("response") if isinstance(query.get("response"), dict) else {}
        order_status = response.get("status")
        exit_price = _f(response.get("avgPrice"))
        filled_qty = _f(response.get("executedQty"))
        if order_status in _FILLED and exit_price > 0:
            # The earlier close DID fill — realize it now, so the loss reaches
            # the L1 ledger the daily-loss breaker reads.
            return _settle_from_fill(
                cfg, position, reason, exit_price, filled_qty, response.get("orderId"), regime
            )
        if order_status in _CLOSE_DEAD:
            position.pop("close_client_order_id", None)
            position.pop("close_reason_pending", None)
            position["close_attempt_status"] = f"PENDING_CLOSE_DEAD:{order_status}"
            _save_position(cfg, position)
            return None  # safe to submit a fresh close this cycle
        # Still working at the venue (NEW / partially filled without price yet).
        position["close_attempt_status"] = f"CLOSE_PENDING:{order_status}"
        _save_position(cfg, position)
        return {"status": "CLOSE_PENDING", "close_reason": reason,
                "order_status": order_status, "position_id": position.get("position_id")}
    error = query.get("error") if isinstance(query.get("error"), dict) else {}
    if error.get("code") in {-2013}:
        # Venue says the order never existed — the original submit truly failed.
        position.pop("close_client_order_id", None)
        position.pop("close_reason_pending", None)
        _save_position(cfg, position)
        return None
    # Query failed: the pending close may be live — do NOT race a second one.
    position["close_attempt_status"] = "CLOSE_PENDING_QUERY_FAILED"
    _save_position(cfg, position)
    log_event(
        "live_position_pending_close_query_failed",
        {"position_id": position.get("position_id")},
        severity="WARNING",
    )
    return {"status": "CLOSE_UNCONFIRMED", "close_reason": reason,
            "order_status": None, "position_id": position.get("position_id")}


def settle_open_live_position(
    candle: Mapping[str, Any] | None,
    *,
    last_close: float | None = None,
    manual_exit: bool = False,
    timeframe: str = "1h",
    regime: str | None = None,
    cfg: AppConfig | None = None,
    submit_close: Callable[[dict], dict] | None = None,
    query_order: Callable[[str, str], dict] | None = None,
) -> dict[str, Any] | None:
    """Evaluate the open live position; on an exit signal, CLOSE IT FOR REAL.

    Returns a settlement summary on a confirmed close, a loud failure dict when a
    close was attempted but not confirmed (position stays OPEN), or None when
    there is no open position / no exit signal. ``submit_close`` / ``query_order``
    are injectable for tests; the real ones sign against the live venue.
    """
    cfg = cfg or load_config(".")
    position = load_open_live_position(cfg)
    if not position:
        return None

    if submit_close is None or query_order is None:
        from crypto_ai_system.execution.live_strategy_execution import (
            query_live_order,
            submit_live_close_order,
        )

        submit_close = submit_close or submit_live_close_order
        query_order = query_order or query_live_order

    # An unconfirmed earlier close is resolved BEFORE any new exit decision —
    # its fill (if any) is the position's real outcome.
    pending = _resolve_pending_close(cfg, position, query_order, regime)
    if pending is not None:
        return pending

    max_hold = MAX_HOLD_BARS.get(timeframe, DEFAULT_MAX_HOLD_BARS)
    reason = _exit_signal(position, candle, last_close, max_hold, manual_exit)
    if reason is None:
        position["last_seen_price"] = last_close
        _save_position(cfg, position)
        return None

    intent = _close_intent(position, reason, last_close)
    # Write-ahead: persist the close id BEFORE submitting, so a crash between
    # POST and response still re-queries THIS id instead of double-closing.
    position["close_client_order_id"] = intent.get("client_order_id")
    position["close_reason_pending"] = reason
    _save_position(cfg, position)

    close_result = submit_close(intent)
    if not close_result.get("external_order_submission_performed"):
        # Close blocked/rejected before reaching the venue: the position STAYS
        # OPEN and the never-submitted id is retired. Loud, retried next cycle.
        position.pop("close_client_order_id", None)
        position.pop("close_reason_pending", None)
        position["close_attempt_failed_at_utc"] = utc_now_iso()
        position["close_attempt_status"] = close_result.get("status")
        _save_position(cfg, position)
        log_event(
            "live_position_close_failed",
            {"position_id": position.get("position_id"), "status": close_result.get("status"),
             "blocks": (close_result.get("final_guard") or {}).get("blocks")},
            severity="WARNING",
        )
        return {"status": "CLOSE_FAILED", "close_reason": reason,
                "close_result_status": close_result.get("status"),
                "position_id": position.get("position_id")}

    # Read the actual close fill back from the exchange.
    query = query_order(str(position.get("symbol")), str(close_result.get("client_order_id")))
    response = query.get("response") if isinstance(query, dict) else None
    response = response if isinstance(response, dict) else {}
    exit_price = _f(response.get("avgPrice"))
    filled_qty = _f(response.get("executedQty"))
    order_status = response.get("status")
    if order_status not in _FILLED or exit_price <= 0:
        # Submitted but not (yet) filled/readable: keep the position OPEN with
        # the SAME pending close id — the next cycle re-queries it; never
        # fabricate an exit price, never race a second close.
        position["close_attempt_failed_at_utc"] = utc_now_iso()
        position["close_attempt_status"] = f"CLOSE_FILL_UNCONFIRMED:{order_status}"
        _save_position(cfg, position)
        log_event(
            "live_position_close_unconfirmed",
            {"position_id": position.get("position_id"), "order_status": order_status},
            severity="WARNING",
        )
        return {"status": "CLOSE_UNCONFIRMED", "close_reason": reason,
                "order_status": order_status, "position_id": position.get("position_id")}

    return _settle_from_fill(
        cfg, position, reason, exit_price, filled_qty,
        close_result.get("exchange_order_id"), regime,
    )
