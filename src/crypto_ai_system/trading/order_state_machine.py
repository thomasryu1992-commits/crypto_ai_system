from __future__ import annotations

VALID_TRANSITIONS = {
    'NEW': {'SUBMITTED', 'CANCELLED', 'REJECTED'},
    'SUBMITTED': {'PARTIALLY_FILLED', 'FILLED', 'CANCELLED', 'REJECTED', 'TIMEOUT'},
    'PARTIALLY_FILLED': {'FILLED', 'CANCELLED', 'TIMEOUT'},
    'FILLED': {'CLOSED'},
    'CANCELLED': set(),
    'REJECTED': set(),
    'TIMEOUT': {'CANCELLED'},
    'CLOSED': set(),
}


def can_transition(current: str, new: str) -> bool:
    return new in VALID_TRANSITIONS.get(current, set())
