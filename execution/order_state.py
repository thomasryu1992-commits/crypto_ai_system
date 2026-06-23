from __future__ import annotations

ORDER_STATES = [
    "CREATED",
    "VALIDATED",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_REQUESTED",
    "CANCELLED",
    "REJECTED",
    "UNKNOWN",
    "RECONCILED",
]


def transition(current: str, target: str) -> str:
    if target not in ORDER_STATES:
        raise ValueError(f"Unknown order state: {target}")
    return target
