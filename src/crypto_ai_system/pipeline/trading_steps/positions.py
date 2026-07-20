"""Position counting and canonical position opening (M5).

Opening only happens from a freshly FILLED entry and only when no position is
already open (the gate's max_open_positions enforces the same upstream). Paper
opens from the simulated fill; live opens from the REAL fill via its kernel,
which itself requires a RECONCILED entry — nothing here fabricates a position.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from crypto_ai_system.execution.paper_book_kernel import open_books
from crypto_ai_system.execution.paper_position_kernel import (
    has_open_position,
    open_from_execution,
)
from crypto_ai_system.pipeline.trading_steps.context import CycleInputs


def count_open_positions(inputs: CycleInputs, *, multibook: bool) -> int:
    """Open-position count for the gate (multibook counts open books)."""
    if inputs.is_live:
        from crypto_ai_system.execution.live_position_kernel import has_open_live_position

        return 1 if has_open_live_position(inputs.cfg) else 0
    if multibook:
        return len(open_books(inputs.cfg))
    return 1 if (inputs.is_paper and has_open_position(inputs.cfg)) else 0


@dataclass(frozen=True)
class OpenOutcome:
    opened: dict | None = None
    book_open_refusal: str | None = None


def open_position_if_filled(
    inputs: CycleInputs,
    *,
    multibook: bool,
    multibook_entries: Sequence[Mapping[str, Any]],
    order: Mapping[str, Any],
    reconciliation: Any,
    order_filled: bool,
    externally_submitted: bool,
) -> OpenOutcome:
    """Open the canonical position from this cycle's fill, if any."""
    if multibook:
        # Opens already happened inside the entry walk (the kernel stayed
        # the arbiter there); surface the first for the legacy output shape.
        return OpenOutcome(
            opened=next((e.get("opened") for e in multibook_entries if e.get("opened")), None),
            book_open_refusal=next(
                (e.get("book_refusal") for e in multibook_entries if e.get("book_refusal")), None
            ),
        )
    if inputs.is_paper and order_filled and not has_open_position(inputs.cfg):
        return OpenOutcome(
            opened=open_from_execution(
                order,
                reconciliation if isinstance(reconciliation, dict) else {},
                cycle_id=inputs.cycle_id,
                cfg=inputs.cfg,
            )
        )
    if inputs.is_live and externally_submitted:
        from crypto_ai_system.execution.live_position_kernel import (
            has_open_live_position,
            open_from_live_execution,
        )

        if not has_open_live_position(inputs.cfg):
            return OpenOutcome(
                opened=open_from_live_execution(
                    order,
                    reconciliation if isinstance(reconciliation, dict) else {},
                    cycle_id=inputs.cycle_id,
                    cfg=inputs.cfg,
                )
            )
    return OpenOutcome()
