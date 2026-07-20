"""Position settlement step (M3): the three variants + S8 attribution.

Settle-first is the trading stage's first act: SL/TP/time exits may close an
open position and produce a CLOSED outcome before the cycle considers a new
entry. Paper settles by simulation; live submits a REAL reduceOnly close
through the narrow close guard (fail-open-position: a blocked/unconfirmed
close stays OPEN). A closed strategy-driven position is attributed to its
strategy here (S8) — attribution is a settlement concern and stays
best-effort: its failure must never disturb the trade result that already
happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import config.settings as settings
from core.event_log import log_event

from crypto_ai_system.execution.paper_book_kernel import settle_books
from crypto_ai_system.execution.paper_position_kernel import (
    load_open_position,
    settle_open_position,
)
from crypto_ai_system.pipeline.trading_steps.context import CycleInputs
from crypto_ai_system.pipeline.trading_steps.stage_router import _flag


@dataclass(frozen=True)
class SettlementOutcome:
    settlement: dict | None = None
    book_settlements: list[dict] = field(default_factory=list)


def record_strategy_outcome_best_effort(
    position: Mapping[str, Any], settlement: Mapping[str, Any], now: str | None
) -> None:
    """Attribute a closed strategy-driven position to its strategy (S8).

    Isolated and best-effort: an attribution failure must not affect the
    trade result that already happened."""
    try:
        from crypto_ai_system.feedback.strategy_feedback_step import record_strategy_outcome

        record_strategy_outcome(
            position, settlement,
            registry_file=str(settings.STRATEGY_ATTRIBUTED_OUTCOME_REGISTRY_PATH), now=now,
        )
    except Exception as exc:  # noqa: BLE001 - attribution is best-effort, but never silent
        log_event(
            "strategy_outcome_attribution_failed",
            {"error": repr(exc)},
            severity="WARNING",
        )


def settle_positions(inputs: CycleInputs, *, multibook: bool) -> SettlementOutcome:
    """Settle any open position(s) for this cycle. Same order and semantics as
    the pre-split agent branches (multibook books / paper single / live)."""
    if multibook:
        # Every open book settles independently on the same candle; each
        # closed summary carries its own position for S8/S9 attribution.
        book_settlements = settle_books(
            inputs.latest_candle,
            last_close=inputs.last_close,
            timeframe=inputs.timeframe,
            regime=inputs.regime,
            cfg=inputs.cfg,
            enabled=True,
        )
        if _flag("STRATEGY_FACTORY_ROUTING_ENABLED"):
            for closed in book_settlements:
                position = closed.get("position")
                if isinstance(position, dict) and position.get("strategy_id"):
                    record_strategy_outcome_best_effort(position, closed, inputs.now)
        return SettlementOutcome(
            settlement=book_settlements[0] if book_settlements else None,
            book_settlements=book_settlements,
        )

    if inputs.is_paper:
        # Capture the position before settling — settle clears it, and a
        # strategy-driven close must be attributed to its strategy (S8/S9).
        open_before = load_open_position(inputs.cfg)
        settlement = settle_open_position(
            inputs.latest_candle,
            last_close=inputs.last_close,
            timeframe=inputs.timeframe,
            regime=inputs.regime,
            cfg=inputs.cfg,
        )
        if (
            settlement is not None
            and isinstance(open_before, dict)
            and open_before.get("strategy_id")
            and _flag("STRATEGY_FACTORY_ROUTING_ENABLED")
        ):
            record_strategy_outcome_best_effort(open_before, settlement, inputs.now)
        return SettlementOutcome(settlement=settlement)

    if inputs.is_live:
        from crypto_ai_system.execution.live_pnl_ledger import live_risk_snapshot
        from crypto_ai_system.execution.live_position_kernel import (
            load_open_live_position,
            settle_open_live_position,
        )

        # Persist today's realized live P&L + breaker state each cycle so the
        # operator (and dashboard) can watch it and the daily-loss circuit
        # breaker's input is fresh.
        live_risk_snapshot()
        open_before = load_open_live_position(inputs.cfg)
        settlement = settle_open_live_position(
            inputs.latest_candle,
            last_close=inputs.last_close,
            timeframe=inputs.timeframe,
            regime=inputs.regime,
            cfg=inputs.cfg,
        )
        if (
            isinstance(settlement, dict)
            and settlement.get("status") == "CLOSED"
            and isinstance(open_before, dict)
            and open_before.get("strategy_id")
            and _flag("STRATEGY_FACTORY_ROUTING_ENABLED")
        ):
            record_strategy_outcome_best_effort(open_before, settlement, inputs.now)
        return SettlementOutcome(settlement=settlement)

    # signed_testnet (and any other stage): no kernel settlement here — the
    # testnet harness settles its own sessions. Same as the pre-split behavior
    # (none of the three branches matched).
    return SettlementOutcome()
