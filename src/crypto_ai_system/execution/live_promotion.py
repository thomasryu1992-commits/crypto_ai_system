"""Live promotion evidence: clean live-canary orders gate autonomous live trading.

The live canary proved a single order end to end. Before autonomous live strategy
trading may be enabled, the operator must have placed a minimum number of clean,
fully reconciled live-canary orders — the same shape of evidence the canary itself
required from repeated clean testnet sessions. This module records each canary
order's reconciliation outcome and counts the clean ones.

Fail-closed: with no evidence the count is 0, so ``live_promotion_ready`` is False
until enough clean canary orders exist. IO-narrow; never signs or submits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import config.settings as settings
from core.time_utils import utc_now_iso
from crypto_ai_system.registry.base_registry import append_registry_record, load_registry_records

LIVE_CANARY_ORDER_REGISTRY_NAME = "live_canary_order_registry"

_ID_FIELD = "live_canary_order_record_id"
_HASH_FIELD = "live_canary_order_record_sha256"

_RECONCILED = "RECONCILED"


def _registry_file(registry_file: str | Path | None) -> Path:
    return Path(registry_file) if registry_file is not None else Path(settings.LIVE_CANARY_ORDER_REGISTRY_PATH)


def record_canary_order(
    *,
    reconcile_status: str | None,
    exchange_order_id: Any = None,
    client_order_id: str | None = None,
    symbol: str | None = None,
    mismatches: list | None = None,
    registry_file: str | Path | None = None,
) -> dict[str, Any]:
    """Record one live-canary order's reconciliation outcome (evidence, append-only)."""
    record = {
        "reconcile_status": reconcile_status,
        "clean": reconcile_status == _RECONCILED and not (mismatches or []),
        "exchange_order_id": exchange_order_id,
        "client_order_id": client_order_id,
        "symbol": symbol,
        "mismatches": list(mismatches or []),
        "recorded_at_utc": utc_now_iso(),
    }
    return append_registry_record(
        _registry_file(registry_file),
        record,
        registry_name=LIVE_CANARY_ORDER_REGISTRY_NAME,
        id_field=_ID_FIELD,
        hash_field=_HASH_FIELD,
        id_prefix="live_canary_order",
    )


def clean_canary_order_count(registry_file: str | Path | None = None) -> int:
    """Number of clean (RECONCILED, zero-mismatch) live-canary orders on record."""
    try:
        records = load_registry_records(_registry_file(registry_file))
    except Exception:  # noqa: BLE001 - a damaged/absent registry means no evidence
        return 0
    return sum(1 for r in records if r.get("clean") is True)


def live_promotion_ready(
    min_orders: int | None = None, *, registry_file: str | Path | None = None
) -> bool:
    """True when enough clean live-canary orders exist to allow live strategy trading."""
    required = settings.LIVE_STRATEGY_MIN_CLEAN_CANARY_ORDERS if min_orders is None else int(min_orders)
    if required <= 0:
        # A non-positive requirement would be a promotion with no evidence — refuse.
        return False
    return clean_canary_order_count(registry_file) >= required
