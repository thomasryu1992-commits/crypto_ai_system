"""Pure order-lifecycle derivation (M2).

Turns the executor/walk results into the cycle's lifecycle booleans. A
non-empty result dict is NOT a trade (a REJECTED/NO_ORDER result is also a
dict): a trade counts only when the executor actually filled (paper) or
submitted (testnet/live). Multibook aggregates across the cycle's entry
attempts. Pure over its inputs — no IO, no config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

_EXTERNAL_SUBMIT_STATUSES = {"SIGNED_TESTNET_ORDER_SUBMITTED", "LIVE_STRATEGY_ORDER_SUBMITTED"}


@dataclass(frozen=True)
class Lifecycle:
    order_status: Any
    order_intent_created: bool
    order_submitted: bool
    order_filled: bool
    trade_executed: bool


def _intent_created(order: Mapping[str, Any]) -> bool:
    return bool((order.get("intent") or {}).get("order_intent_created")) or bool(
        order.get("order_intent_id")
    )


def derive_lifecycle(
    order: Mapping[str, Any],
    multibook_entries: Sequence[Mapping[str, Any]],
    *,
    multibook: bool,
) -> Lifecycle:
    """Derive the cycle's order lifecycle from the representative order (and,
    in multibook mode, the whole entry walk)."""
    order_status = order.get("status")
    if multibook:
        orders = [e.get("order") or {} for e in multibook_entries]
        order_filled = any(bool(o.get("filled")) for o in orders)
        return Lifecycle(
            order_status=order_status,
            order_intent_created=any(_intent_created(o) for o in orders),
            order_submitted=False,  # multibook is paper-only; nothing external
            order_filled=order_filled,
            trade_executed=order_filled,
        )

    order_filled = bool(order.get("filled"))
    order_submitted = bool(order.get("external_order_submission_performed")) or (
        order_status in _EXTERNAL_SUBMIT_STATUSES
    )
    return Lifecycle(
        order_status=order_status,
        order_intent_created=_intent_created(order),
        order_submitted=order_submitted,
        order_filled=order_filled,
        trade_executed=order_filled or order_status in _EXTERNAL_SUBMIT_STATUSES,
    )
