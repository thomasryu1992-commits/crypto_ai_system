"""Multibook entry walk (M4): ranked candidates first, then the research
decision into the default book, bounded by the per-cycle entry budget.

Every attempt runs the full unchanged chain — persist decision, order
executor, paper reconciler, book kernel — so each entry is gated and audited
exactly like a single-book entry, and the kernel remains the arbiter of the
book/global/direction caps. The representative outcome of the walk is the
entry that actually FILLED (first fill wins), and its post-executor decision
(carrying the consumption marker) is re-persisted so the on-disk artifacts
describe the executed trade, never last-writer-wins.

``executor`` / ``reconciler`` / ``persist`` / ``read`` are injected by the
agent from its own module surface so existing monkeypatches keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import config.settings as settings
from config.settings import TRADE_DECISION_PATH

from core.event_log import log_event
from crypto_ai_system.execution.paper_book_kernel import open_books, open_in_book
from crypto_ai_system.pipeline.trading_steps.context import CycleInputs
from crypto_ai_system.pipeline.trading_steps.entry import build_candidate_decision
from crypto_ai_system.pipeline.trading_steps.stage_router import _flag


@dataclass(frozen=True)
class MultibookOutcome:
    entries: list[dict] = field(default_factory=list)
    strategy_drive: dict | None = None
    # The representative (first-filled, else last-attempted) entry's view:
    order: dict = field(default_factory=dict)
    reconciliation: dict = field(default_factory=dict)
    executed_decision: dict | None = None


def run_multibook_entries(
    inputs: CycleInputs,
    *,
    research_decision: Mapping[str, Any],
    open_count: int,
    executor: Callable[[str], dict],
    reconciler: Callable[[], dict],
    persist: Callable[..., None],
    read: Callable[..., dict],
) -> MultibookOutcome:
    from crypto_ai_system.execution.paper_book_kernel import DEFAULT_BOOK_ID

    entries: list[dict] = []
    opened_count = 0
    budget = max(0, int(getattr(settings, "MULTIBOOK_MAX_ENTRIES_PER_CYCLE", 2)))
    taken_books = set(open_books(inputs.cfg))

    def _attempt(decision: Mapping[str, Any], kind: str, book_hint: str) -> None:
        nonlocal opened_count
        persist(TRADE_DECISION_PATH, decision)
        order = executor(inputs.stage)
        order = order if isinstance(order, dict) else {}
        reconciliation = reconciler()
        opened, refusal = None, None
        if order.get("filled"):
            # enabled is passed explicitly: the caller decided the mode for
            # this cycle, and a mid-cycle settings flip must not split it.
            opened, refusal = open_in_book(
                order, reconciliation if isinstance(reconciliation, dict) else {},
                cycle_id=inputs.cycle_id, cfg=inputs.cfg, enabled=True,
            )
            if refusal:
                log_event(
                    "multibook_open_refused",
                    {"reason": refusal, "book": book_hint, "cycle_id": inputs.cycle_id},
                    severity="WARNING",
                )
            elif opened is not None:
                opened_count += 1
                taken_books.add(str(opened.get("book_id")))
        entries.append({
            "decision_kind": kind,
            "book": book_hint,
            "order": order,
            "reconciliation": reconciliation,
            "opened": opened,
            "book_refusal": refusal,
            "filled": bool(order.get("filled")),
            # The post-executor on-disk decision (carries the consumption
            # marker) so the walk can re-persist the EXECUTED entry's
            # decision at the end instead of last-writer-wins.
            "decision": read(TRADE_DECISION_PATH, {}),
        })

    strategy_drive = None
    routing = inputs.routing
    drive_on = _flag("STRATEGY_FACTORY_ROUTING_ENABLED") and _flag("STRATEGY_FACTORY_ROUTING_DRIVE_ENABLED")
    candidates = []
    if drive_on and isinstance(routing, dict):
        candidates = [
            c for c in (routing.get("ranked_candidates") or [])
            if c.get("strategy_id") and c["strategy_id"] not in taken_books
        ]

    for candidate in candidates:
        if len(entries) >= budget:
            break
        decision = build_candidate_decision(
            routing, inputs.verdict, candidate,
            execution_stage=inputs.stage, open_positions=open_count + opened_count,
            cycle_id=inputs.cycle_id, now=inputs.now,
        )
        # No executor churn on a candidate the bridge already refused.
        if decision is None or not decision.get("allow_order_intent"):
            continue
        if strategy_drive is None:
            strategy_drive = decision
        _attempt(decision, "strategy", str(candidate["strategy_id"]))

    # The research decision drives the shared default book, last: the pool's
    # strategies are the point of multibook, research keeps its one slot.
    if len(entries) < budget and DEFAULT_BOOK_ID not in taken_books and isinstance(research_decision, dict):
        _attempt(research_decision, "research", DEFAULT_BOOK_ID)

    # Representative: first fill wins; falls back to the last attempt when
    # nothing filled. Re-persist ITS decision so decision/order/reconciliation
    # all describe the same executed trade.
    representative = next(
        (e for e in entries if e.get("filled")),
        entries[-1] if entries else {},
    )
    executed_decision = representative.get("decision")
    if isinstance(executed_decision, dict) and executed_decision:
        persist(TRADE_DECISION_PATH, executed_decision)
    else:
        executed_decision = None

    return MultibookOutcome(
        entries=entries,
        strategy_drive=strategy_drive,
        order=representative.get("order") or {},
        reconciliation=representative.get("reconciliation") or {},
        executed_decision=executed_decision,
    )
