"""Multi-book paper position kernel (multibook M1).

A *book* is an independent paper ledger keyed by the strategy that drove the
entry (research-driven entries share the ``default`` book): its own position,
its own settlement, its own outcome attribution. Held simultaneously, the
pool's diversity becomes an actual portfolio effect instead of strategies
queuing for one slot.

M1 is kernel-only: callers still run the single-book
``paper_position_kernel`` until M2 wires the trading path through here.
With ``MULTIBOOK_PAPER_ENABLED`` off (the default) every entry point of this
module delegates to the single-book kernel, so behavior is unchanged.

Two caps are structural backstops enforced at open (the operator's 2026-07-19
decision; M3 moves the *reporting* of them into the validation agent):
``MULTIBOOK_MAX_OPEN_BOOKS`` total, ``MULTIBOOK_MAX_SAME_DIRECTION`` per side
- every underlying here is crypto, and three same-direction books are one bet
three times, not three bets.

No exchange side effects: purely simulated fills and settlement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.json_io import atomic_write_json, read_json
from crypto_ai_system.config import AppConfig, load_config
from crypto_ai_system.execution.paper_position_kernel import (
    DEFAULT_MAX_HOLD_BARS,
    MAX_HOLD_BARS,
    build_position,
    open_from_execution as _single_open,
    settle_open_position as _single_settle,
    settle_trade_plan,
)
from crypto_ai_system.feedback.outcome_analytics_v2 import analyze_and_persist_paper_outcome

PAPER_BOOKS_VERSION = "paper_books.v1"
DEFAULT_BOOK_ID = "default"

REFUSED_BOOK_ALREADY_OPEN = "BOOK_ALREADY_OPEN"
REFUSED_MAX_OPEN_BOOKS = "MAX_OPEN_BOOKS"
REFUSED_MAX_SAME_DIRECTION = "MAX_SAME_DIRECTION"
REFUSED_NOT_A_FILL = "NOT_A_FILL"


def multibook_enabled(enabled: bool | None = None) -> bool:
    if enabled is not None:
        return bool(enabled)
    import config.settings as settings

    return bool(getattr(settings, "MULTIBOOK_PAPER_ENABLED", False))


def _caps() -> tuple[int, int]:
    import config.settings as settings

    return (
        int(getattr(settings, "MULTIBOOK_MAX_OPEN_BOOKS", 5)),
        int(getattr(settings, "MULTIBOOK_MAX_SAME_DIRECTION", 3)),
    )


def _books_path(cfg: AppConfig) -> Path:
    raw = cfg.get("storage.latest_dir", "storage/latest")
    base = Path(raw)
    if not base.is_absolute():
        base = cfg.root / base
    base.mkdir(parents=True, exist_ok=True)
    return base / "paper_books.json"


def book_id_for(execution_record: Mapping[str, Any]) -> str:
    """The book an entry belongs to: its driving strategy, else ``default``.

    Mirrors the single kernel's attribution rule - the research bridge's
    pseudo-strategy id is not a strategy, so it lands in the default book.
    """
    intent = dict(execution_record.get("expected_order_intent") or {})
    strategy_id = intent.get("strategy_id")
    if strategy_id and strategy_id != "research_bridge_v2":
        return str(strategy_id)
    return DEFAULT_BOOK_ID


def load_books(cfg: AppConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config(".")
    data = read_json(_books_path(cfg), None)
    if not isinstance(data, dict) or not isinstance(data.get("books"), dict):
        return {"books_version": PAPER_BOOKS_VERSION, "books": {}}
    return data


def _save_books(cfg: AppConfig, data: Mapping[str, Any]) -> None:
    atomic_write_json(_books_path(cfg), dict(data))


def open_books(cfg: AppConfig | None = None) -> dict[str, dict[str, Any]]:
    books = load_books(cfg)["books"]
    return {bid: pos for bid, pos in books.items() if isinstance(pos, dict) and pos.get("status") == "OPEN"}


def has_open_book(cfg: AppConfig | None = None, *, enabled: bool | None = None) -> bool:
    if not multibook_enabled(enabled):
        from crypto_ai_system.execution.paper_position_kernel import has_open_position

        return has_open_position(cfg)
    return bool(open_books(cfg))


def open_in_book(
    execution_record: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    *,
    cycle_id: str | None = None,
    cfg: AppConfig | None = None,
    enabled: bool | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Open a paper position in its book. Returns ``(position, refusal_reason)``.

    Disabled -> delegates to the single-book kernel (one slot, unchanged).
    Enabled -> one position per book, capped globally and per direction; a
    refusal returns ``(None, reason)`` and touches nothing.
    """
    cfg = cfg or load_config(".")
    if not multibook_enabled(enabled):
        position = _single_open(execution_record, reconciliation, cycle_id=cycle_id, cfg=cfg)
        return position, (None if position is not None else REFUSED_NOT_A_FILL)

    position = build_position(execution_record, reconciliation, cycle_id=cycle_id)
    if position is None:
        return None, REFUSED_NOT_A_FILL

    book_id = book_id_for(execution_record)
    data = load_books(cfg)
    books = data["books"]
    currently_open = {bid: pos for bid, pos in books.items()
                     if isinstance(pos, dict) and pos.get("status") == "OPEN"}

    if book_id in currently_open:
        return None, REFUSED_BOOK_ALREADY_OPEN
    max_books, max_same_direction = _caps()
    if len(currently_open) >= max_books:
        return None, REFUSED_MAX_OPEN_BOOKS
    same_direction = sum(1 for pos in currently_open.values()
                         if pos.get("direction") == position["direction"])
    if same_direction >= max_same_direction:
        return None, REFUSED_MAX_SAME_DIRECTION

    position["book_id"] = book_id
    books[book_id] = position
    data["books_version"] = PAPER_BOOKS_VERSION
    _save_books(cfg, data)
    return position, None


def settle_books(
    candle: Mapping[str, Any] | None,
    *,
    last_close: float | None = None,
    manual_exit: bool = False,
    timeframe: str = "1h",
    regime: str | None = None,
    cfg: AppConfig | None = None,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    """Settle every open book against the candle; return the close summaries.

    Disabled -> delegates to the single-book kernel (a list of at most one).
    Enabled -> each book settles independently with the same exit math
    (``settle_trade_plan``); a stop in one book leaves the others open, and
    each CLOSED outcome carries its ``book_id``.
    """
    cfg = cfg or load_config(".")
    if not multibook_enabled(enabled):
        summary = _single_settle(
            candle, last_close=last_close, manual_exit=manual_exit,
            timeframe=timeframe, regime=regime, cfg=cfg,
        )
        return [summary] if summary else []

    data = load_books(cfg)
    books = data["books"]
    max_hold = MAX_HOLD_BARS.get(timeframe, DEFAULT_MAX_HOLD_BARS)
    summaries: list[dict[str, Any]] = []

    for book_id, position in list(books.items()):
        if not isinstance(position, dict) or position.get("status") != "OPEN":
            continue
        reason, exit_price, result_r = settle_trade_plan(position, candle, last_close, max_hold, manual_exit)
        if reason is None:
            position["last_seen_price"] = last_close
            continue
        context = {
            "exit_price": exit_price,
            "result_R": round(float(result_r), 8),
            "close_reason": reason,
            "regime": regime or "unknown",
            "book_id": book_id,
        }
        outcome = analyze_and_persist_paper_outcome(
            position.get("entry_reconciliation") or {},
            outcome_context=context,
            cfg=cfg,
        )
        books[book_id] = {"status": "CLOSED"}
        summaries.append({
            "book_id": book_id,
            "position_id": position.get("position_id"),
            "strategy_id": position.get("strategy_id"),
            "close_reason": reason,
            "exit_price": exit_price,
            "result_R": round(float(result_r), 8),
            "execution_id": position.get("execution_id"),
            "outcome_id": outcome.get("outcome_id"),
            "outcome_status": outcome.get("status"),
        })

    _save_books(cfg, data)
    return summaries
