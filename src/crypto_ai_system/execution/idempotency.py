from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def make_idempotency_key(
    payload_or_symbol: Dict[str, Any] | str,
    direction: str | None = None,
    strategy_id: str | None = None,
    candle_time: str | None = None,
    signal_id: str | None = None,
) -> str:
    """Build a stable idempotency key.

    Step241 keeps backward compatibility with the legacy root execution.idempotency
    signature while preserving the canonical dict-payload signature.
    """
    if isinstance(payload_or_symbol, dict) and direction is None and strategy_id is None and candle_time is None and signal_id is None:
        raw = json.dumps(payload_or_symbol, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:24]

    symbol = str(payload_or_symbol)
    raw = f"{symbol}|{direction or ''}|{strategy_id or ''}|{candle_time or ''}|{signal_id or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_client_order_id(symbol: str, direction: str, idempotency_key: str) -> str:
    """Create a compact client order id compatible with legacy callers."""
    prefix = f"CAI_{symbol}_{direction}_"
    return (prefix + str(idempotency_key)[:18])[:36]


def enrich_order_identity(intent: dict[str, Any]) -> dict[str, Any]:
    """Populate idempotency fields on an order intent without side effects."""
    symbol = intent.get("symbol", "BTCUSDT")
    direction = intent.get("direction", "NONE")
    candle_time = intent.get("candle_time") or intent.get("created_at", "")
    signal_id = intent.get("signal_id") or intent.get("source_decision", "")
    strategy_id = intent.get("strategy_id", "research_bridge_v2")
    key = make_idempotency_key(symbol, direction, strategy_id, candle_time, signal_id)
    intent["idempotency_key"] = key
    intent["client_order_id"] = make_client_order_id(symbol, direction, key)
    intent["intent_id"] = f"intent_{key[:16]}"
    return intent
