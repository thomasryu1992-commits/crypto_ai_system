"""L1: realized live-P&L ledger and the daily-loss circuit breaker.

Autonomous live trading needs a real, live-money view of today's realized P&L so
the daily-loss limit can actually halt the loop — the paper risk guard computes R
from paper outcomes and never sees live USDT. This module is that view:

* ``record_live_outcome`` appends one realized live round-trip (USDT P&L) to an
  append-only registry, with the same integrity guarantees as the rest of the
  audit chain (id, tamper hash, canonical timestamp).
* ``live_daily_realized_pnl_usdt`` sums today's realized P&L.
* ``daily_loss_limit_breached`` is the circuit breaker: an unconfigured limit
  (<= 0) is treated as breached, so live stays fail-closed until the operator sets
  a real limit.
* ``live_risk_snapshot`` writes the derived live risk status for the gate/loop.

Pure and IO-narrow: functions accept an explicit registry/status path so tests
run against a tmp dir. This module never signs, submits, or reads secrets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import config.settings as settings
from core.json_io import atomic_write_json
from core.time_utils import utc_now, utc_now_iso
from crypto_ai_system.registry.base_registry import append_registry_record, load_registry_records

LIVE_OUTCOME_REGISTRY_NAME = "live_outcome_registry"

_ID_FIELD = "live_outcome_record_id"
_HASH_FIELD = "live_outcome_record_sha256"


def _registry_file(registry_file: str | Path | None) -> Path:
    return Path(registry_file) if registry_file is not None else Path(settings.LIVE_OUTCOME_REGISTRY_PATH)


def _today_utc() -> str:
    return utc_now().strftime("%Y-%m-%d")


def record_live_outcome(
    *,
    realized_pnl_usdt: float,
    symbol: str,
    side: str,
    quantity: float,
    open_price: float | None = None,
    close_price: float | None = None,
    open_order_id: Any = None,
    close_order_id: Any = None,
    strategy_id: str | None = None,
    opened_at_utc: str | None = None,
    closed_at_utc: str | None = None,
    registry_file: str | Path | None = None,
) -> dict[str, Any]:
    """Append one realized live round-trip outcome. Returns the persisted record."""
    record = {
        "realized_pnl_usdt": round(float(realized_pnl_usdt), 8),
        "symbol": symbol,
        "side": side,
        "quantity": float(quantity),
        "open_price": open_price,
        "close_price": close_price,
        "open_order_id": open_order_id,
        "close_order_id": close_order_id,
        "strategy_id": strategy_id,
        "opened_at_utc": opened_at_utc,
        "closed_at_utc": closed_at_utc or utc_now_iso(),
        "outcome_closed": True,
    }
    return append_registry_record(
        _registry_file(registry_file),
        record,
        registry_name=LIVE_OUTCOME_REGISTRY_NAME,
        id_field=_ID_FIELD,
        hash_field=_HASH_FIELD,
        id_prefix="live_outcome",
    )


def load_live_outcomes(registry_file: str | Path | None = None) -> list[dict[str, Any]]:
    return load_registry_records(_registry_file(registry_file))


def live_daily_realized_pnl_usdt(
    *, registry_file: str | Path | None = None, day: str | None = None
) -> float:
    """Sum realized live P&L (USDT) for outcomes closed on ``day`` (UTC, default today)."""
    day = day or _today_utc()
    total = 0.0
    for record in load_live_outcomes(registry_file):
        stamp = str(record.get("closed_at_utc") or record.get("created_at_utc") or "")
        if stamp[:10] == day:
            try:
                total += float(record.get("realized_pnl_usdt") or 0.0)
            except (TypeError, ValueError):
                continue
    return round(total, 8)


def daily_loss_limit_breached(
    limit_usdt: float | None,
    *,
    registry_file: str | Path | None = None,
    day: str | None = None,
) -> bool:
    """True when today's realized loss has reached the limit.

    Fail-closed: a missing/non-positive limit is treated as breached, so the live
    path cannot run without an explicit daily-loss limit.
    """
    if limit_usdt is None or float(limit_usdt) <= 0:
        return True
    realized = live_daily_realized_pnl_usdt(registry_file=registry_file, day=day)
    return realized <= -abs(float(limit_usdt))


def live_risk_snapshot(
    *,
    limit_usdt: float | None = None,
    registry_file: str | Path | None = None,
    status_path: str | Path | None = None,
) -> dict[str, Any]:
    """Compute and persist the live risk status (today's realized P&L + breaker)."""
    day = _today_utc()
    limit = settings.LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT if limit_usdt is None else limit_usdt
    pnl = live_daily_realized_pnl_usdt(registry_file=registry_file, day=day)
    breached = daily_loss_limit_breached(limit, registry_file=registry_file, day=day)
    snapshot = {
        "created_at": utc_now_iso(),
        "day_utc": day,
        "live_daily_pnl_usdt": pnl,
        "daily_loss_limit_usdt": float(limit or 0.0),
        "daily_loss_limit_configured": bool(limit and float(limit) > 0),
        "daily_loss_limit_breached": breached,
    }
    atomic_write_json(status_path or settings.LIVE_RISK_STATUS_PATH, snapshot)
    return snapshot
