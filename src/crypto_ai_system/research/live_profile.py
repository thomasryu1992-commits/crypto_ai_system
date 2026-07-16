"""Operator-approved live-stage profile (L4).

The PreOrderRiskGate requires an *approved* profile whose hash matches the
ResearchSignal's. The paper profile is auto-approved (simulation, no real money);
this live profile is NOT — its approval fields are set only when the operator has
fully configured the live-strategy boundary (enable flags, the distinct
confirmation phrase, hard caps, a daily-loss limit, and live-promotion evidence).
Setting that env IS the operator's approval act; with anything missing the
profile reports unapproved and the gate fails closed at APPROVED_PROFILE.

The identity core (and therefore the profile hash the ResearchSignal carries) is
static and excludes the approval fields, so the hash stays deterministic while
approval is evaluated live at gate time.

This module is also the single source of "is the live stage fully configured":
``live_stage_block_reason`` is used by the pipeline's stage router and by the
signal builder, so they can never disagree.
"""

from __future__ import annotations

from typing import Any

import config.settings as settings
from crypto_ai_system.utils.audit import sha256_json

LIVE_PROFILE_ID = "live_operator_v1"
LIVE_PROFILE_VERSION = "live_operator_v1.0"

# Stable identity core (no timestamps, no approval state) so the hash is
# deterministic and the ResearchSignal can carry the same profile_sha256.
_LIVE_PROFILE_CORE: dict[str, Any] = {
    "profile_id": LIVE_PROFILE_ID,
    "profile_version": LIVE_PROFILE_VERSION,
    "stage": "live",
    "approved_stages": ["live"],
}

LIVE_PROFILE_SHA256 = sha256_json(_LIVE_PROFILE_CORE)

_CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_TRADES_LIVE_FUNDS_AUTONOMOUSLY"


def _confirmation_present() -> bool:
    expected = getattr(settings, "LIVE_STRATEGY_CONFIRMATION_PHRASE", "") or _CONFIRMATION_PHRASE
    given = getattr(settings, "LIVE_STRATEGY_CONFIRMATION", "")
    return bool(given) and given == expected


def live_stage_block_reason() -> str | None:
    """Why the live stage may NOT run, or None when fully configured.

    Single source for the pipeline stage router and the signal builder. The final
    guard re-checks all of this (and more) before anything is signed.
    """
    if not getattr(settings, "LIVE_STRATEGY_ORDER_ENABLED", False):
        return "LIVE_STRATEGY_ORDER_ENABLED is false"
    if not getattr(settings, "LIVE_STRATEGY_PLACE_ORDER_ENABLED", False):
        return "live strategy enabled without LIVE_STRATEGY_PLACE_ORDER_ENABLED — refusing"
    if not _confirmation_present():
        return "live strategy enabled without its confirmation phrase — refusing"
    if getattr(settings, "LIVE_STRATEGY_MANUAL_KILL_SWITCH", False):
        return "live strategy kill switch is engaged — refusing"
    if float(getattr(settings, "LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT", 0.0) or 0.0) <= 0:
        return "LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT not configured — refusing"
    if float(getattr(settings, "LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT", 0.0) or 0.0) <= 0:
        return "LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT not configured — refusing"
    try:
        from crypto_ai_system.execution.live_promotion import live_promotion_ready

        if not live_promotion_ready():
            return "live promotion evidence not ready (clean canary orders) — refusing"
    except Exception:  # noqa: BLE001 - fail closed if evidence can't be read
        return "live promotion evidence unreadable — refusing"
    return None


def live_stage_fully_configured() -> bool:
    return live_stage_block_reason() is None


def get_live_profile() -> dict[str, Any]:
    """Return the live profile; approved only when the operator config is complete."""
    profile = dict(_LIVE_PROFILE_CORE)
    profile["profile_sha256"] = LIVE_PROFILE_SHA256
    profile["profile_hash"] = LIVE_PROFILE_SHA256
    approved = live_stage_fully_configured()
    profile["approved"] = approved
    profile["approval_status"] = "approved" if approved else "unapproved"
    return profile
