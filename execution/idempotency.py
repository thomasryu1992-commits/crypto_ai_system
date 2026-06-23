from __future__ import annotations

import hashlib
from typing import Any


def make_idempotency_key(symbol: str, direction: str, strategy_id: str, candle_time: str, signal_id: str) -> str:
    raw = f"{symbol}|{direction}|{strategy_id}|{candle_time}|{signal_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_client_order_id(symbol: str, direction: str, idempotency_key: str) -> str:
    # Binance client order IDs have length/charset limits; keep compact.
    prefix = f"CAI_{symbol}_{direction}_"
    return (prefix + idempotency_key[:18])[:36]


def enrich_order_identity(intent: dict[str, Any]) -> dict[str, Any]:
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
