"""Operator preflight for the signed-testnet path.

Config-only readiness (no intent, no order) plus an optional signed *read-only*
balance probe to confirm the keys actually authenticate against the testnet.
Used by ``scripts/check_testnet_readiness.py`` and ``run_testnet_order.py``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import config.settings as settings

from crypto_ai_system.execution.signed_testnet_adapter import (
    ALLOWED_TESTNET_HOSTS,
    SignedTestnetAdapter,
)

_CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_PLACES_REAL_ORDERS"


def _confirmation_present() -> bool:
    expected = getattr(settings, "LIVE_TRADING_CONFIRMATION_PHRASE", "") or _CONFIRMATION_PHRASE
    given = getattr(settings, "LIVE_TRADING_CONFIRMATION", "")
    return bool(given) and given == expected


def check_config_readiness() -> dict[str, Any]:
    """Return ``{ready, blocks}`` from config alone. Never touches the network."""
    blocks: list[str] = []

    if not getattr(settings, "TESTNET_SIGNED_ORDER_ENABLED", False):
        blocks.append("TESTNET_SIGNED_ORDER_ENABLED is false")
    if not getattr(settings, "SIGNED_TESTNET_PLACE_ORDER_ENABLED", False):
        blocks.append("SIGNED_TESTNET_PLACE_ORDER_ENABLED is false")
    if getattr(settings, "SIGNED_TESTNET_MANUAL_APPROVAL_REQUIRED", True) and not _confirmation_present():
        blocks.append("LIVE_TRADING_CONFIRMATION phrase not set correctly")

    if not getattr(settings, "BINANCE_TESTNET", True):
        blocks.append("BINANCE_TESTNET is false (mainnet key scope not allowed)")
    if getattr(settings, "SIGNED_TESTNET_LIVE_KEY_ALLOWED", False):
        blocks.append("SIGNED_TESTNET_LIVE_KEY_ALLOWED is true (must be false)")

    base_url = getattr(settings, "BINANCE_TESTNET_BASE_URL", "")
    host = (urlparse(base_url).hostname or "").lower()
    if host not in ALLOWED_TESTNET_HOSTS:
        blocks.append(f"BINANCE_TESTNET_BASE_URL host {host!r} is not an allowed testnet host")

    if not getattr(settings, "BINANCE_API_KEY", ""):
        blocks.append("BINANCE_API_KEY is not set")
    if not getattr(settings, "BINANCE_API_SECRET", ""):
        blocks.append("BINANCE_API_SECRET is not set")

    return {
        "ready": not blocks,
        "blocks": blocks,
        "notional_cap_usdt": float(getattr(settings, "SIGNED_TESTNET_MAX_ORDER_NOTIONAL_USDT", 5.0)),
        "max_daily_order_count": int(getattr(settings, "SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT", 3)),
    }


def probe_auth() -> dict[str, Any]:
    """Signed read-only balance call to confirm the keys authenticate.

    Read-only: no order is placed. Returns a redacted summary.
    """
    try:
        adapter = SignedTestnetAdapter(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
            base_url=settings.BINANCE_TESTNET_BASE_URL,
        )
        result = adapter.get_balance()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if not result.get("ok"):
        return {
            "ok": False,
            "http_status": result.get("http_status"),
            "error": result.get("error"),
        }

    balances = result.get("response") or []
    usdt = next(
        (b for b in balances if isinstance(b, dict) and b.get("asset") == "USDT"), {}
    )
    return {
        "ok": True,
        "assets_returned": len(balances) if isinstance(balances, list) else 0,
        "usdt_balance": usdt.get("balance"),
    }
