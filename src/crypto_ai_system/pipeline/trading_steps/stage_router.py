"""Fail-closed execution-stage resolution (paper / signed_testnet / live).

Moved verbatim from ``trading_agent`` (M1). The trading agent re-exports
``resolve_execution_stage`` for compatibility until M5.
"""

from __future__ import annotations

import config.settings as settings

_CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_PLACES_REAL_ORDERS"


def _flag(name: str, default: bool = False) -> bool:
    return bool(getattr(settings, name, default))


def _live_requested() -> bool:
    return _flag("LIVE_TRADING_ENABLED") or _flag("ALLOW_LIVE_TRADING")


def _testnet_requested() -> bool:
    return _flag("ENABLE_TESTNET_ORDERS") or _flag("TESTNET_SIGNED_ORDER_ENABLED")


def _confirmation_present() -> bool:
    phrase = getattr(settings, "LIVE_TRADING_CONFIRMATION_PHRASE", "")
    given = getattr(settings, "LIVE_TRADING_CONFIRMATION", "")
    expected = phrase or _CONFIRMATION_PHRASE
    return bool(given) and given == expected


def _live_strategy_requested() -> bool:
    return _flag("LIVE_STRATEGY_ORDER_ENABLED")


def _live_strategy_block_reason() -> str | None:
    """Every condition for routing the pipeline to the live stage, or why not.

    A partially-configured live request refuses loudly rather than silently
    downgrading to paper — an operator who flipped the live flag must know it is
    not live. Delegates to the single source (live_profile) shared with the
    signal builder; the final guard re-checks all of this before signing.
    """
    from crypto_ai_system.research.live_profile import live_stage_block_reason

    return live_stage_block_reason()


def resolve_execution_stage() -> tuple[str | None, str | None]:
    """Decide the execution stage from config, fail-closed.

    Returns ``(stage, block_reason)``. When ``block_reason`` is set the caller
    must refuse execution. ``stage`` is ``"paper"``, ``"signed_testnet"``, or
    ``"live"`` (all enable flags + confirmation + promotion evidence required).
    """
    if _live_requested():
        # The legacy live flags never route anywhere; the only live path is the
        # explicit LIVE_STRATEGY_* set below.
        return None, "legacy live trading flags are not a live path - refusing (fail-closed)"
    if _live_strategy_requested():
        reason = _live_strategy_block_reason()
        if reason:
            return None, reason
        return "live", None
    if _testnet_requested() and not _confirmation_present():
        return None, "testnet order flag enabled without confirmation phrase - refusing"
    if _testnet_requested() and _confirmation_present():
        return "signed_testnet", None
    return "paper", None
