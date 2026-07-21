"""Typed views over the ``storage/latest`` JSON handoff artifacts.

The files ARE the inter-module API of this system, but their schemas were
implicit — every consumer re-derived field names, fallback chains, and
defaults by hand, which is exactly how the audit's gate-bypass class happened
(a key one side never wrote, read with a silent default on the other).

These views make each artifact's contract explicit in ONE place:

- Every field's default mirrors the CURRENT consumer semantics (documented
  inline), so adopting a view never changes behavior — the win is typo-proof
  access and a single home for the fallback chains.
- Writers stamp ``schema_version`` so a reader can tell which contract a file
  was written under; views surface it but do not block on it (the handoff
  stays advisory-typed — hard gates live in the guards, not here).
- Adoption is incremental by design: new consumers use views, existing
  ``read_json`` call sites keep working untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

SCHEMA_MARKET_SNAPSHOT = "market_snapshot.v1"
SCHEMA_TRADE_DECISION = "trade_decision.v1"
SCHEMA_ORDER_RESULT = "order_result.v1"
SCHEMA_RECONCILIATION = "reconciliation.v1"


def _num(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None  # drop NaN


def _read(path: str | Path) -> Mapping[str, Any]:
    from core.json_io import read_json

    data = read_json(path, {})
    return data if isinstance(data, Mapping) else {}


@dataclass(frozen=True)
class MarketSnapshotView:
    """``market_snapshot.json`` — the cycle's market view."""

    symbol: str | None
    timeframe: str          # consumers default "1h" (CycleInputs, kernels)
    last_close: float | None
    trend_bias: str         # consumers default "unknown" (regime)
    is_synthetic: bool      # consumers default False
    is_fallback: bool
    is_stale: bool          # False = fresh (the builder writes it since the QA fix)
    last_candle_time: str | None
    candle_count: int
    schema_version: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "MarketSnapshotView":
        m = m or {}
        return cls(
            symbol=(str(m["symbol"]) if m.get("symbol") else None),
            timeframe=str(m.get("timeframe", "1h")),
            last_close=_num(m.get("last_close")),
            trend_bias=str(m.get("trend_bias", "unknown")),
            is_synthetic=bool(m.get("is_synthetic", False)),
            is_fallback=bool(m.get("is_fallback", False)),
            is_stale=bool(m.get("is_stale", False)),
            last_candle_time=m.get("last_candle_time"),
            candle_count=int(m.get("candle_count", 0) or 0),
            schema_version=m.get("schema_version"),
            raw=m,
        )

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "MarketSnapshotView":
        if path is None:
            from config.settings import MARKET_SNAPSHOT_PATH as path  # noqa: PLW0127
        return cls.from_mapping(_read(path))


@dataclass(frozen=True)
class TradeDecisionView:
    """``latest_trade_decision.json`` — research- or strategy-shaped decision."""

    final_decision: str | None
    direction: str | None
    allow_order_intent: bool            # False = blocked (fail-closed default)
    pre_order_risk_gate_approved: bool  # False = not approved
    risk_gate_id: str | None
    symbol: str | None
    entry: float | None                 # entry -> entry_price -> price chain
    stop_loss: float | None
    take_profit: float | None
    order_notional_usdt: float | None   # order_notional_usdt -> notional_usdt
    execution_stage: str                # execution_stage -> decision_stage -> "paper"
    strategy_id: str | None
    decision_id: str | None
    order_intent_consumed_at: str | None  # set = already authorized one intent
    schema_version: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "TradeDecisionView":
        m = m or {}
        return cls(
            final_decision=m.get("final_decision"),
            direction=(str(m["direction"]).upper() if m.get("direction") else None),
            allow_order_intent=bool(m.get("allow_order_intent", False)),
            pre_order_risk_gate_approved=m.get("pre_order_risk_gate_approved") is True,
            risk_gate_id=m.get("risk_gate_id"),
            symbol=m.get("symbol"),
            entry=_num(m.get("entry") or m.get("entry_price") or m.get("price")),
            stop_loss=_num(m.get("stop_loss")),
            take_profit=_num(m.get("take_profit")),
            order_notional_usdt=_num(m.get("order_notional_usdt") or m.get("notional_usdt")),
            execution_stage=str(m.get("execution_stage") or m.get("decision_stage") or "paper"),
            strategy_id=m.get("strategy_id"),
            decision_id=m.get("decision_id"),
            order_intent_consumed_at=m.get("order_intent_consumed_at"),
            schema_version=m.get("schema_version"),
            raw=m,
        )

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "TradeDecisionView":
        if path is None:
            from config.settings import TRADE_DECISION_PATH as path  # noqa: PLW0127
        return cls.from_mapping(_read(path))


@dataclass(frozen=True)
class OrderResultView:
    """``latest_order_result.json`` — what the executor/adapter did."""

    status: str | None
    state: str | None
    filled: bool                              # False = no fill
    external_order_submission_performed: bool  # False = never reached a venue
    client_order_id: str | None
    exchange_order_id: Any
    order_intent_id: str | None
    intent: Mapping[str, Any]
    schema_version: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "OrderResultView":
        m = m or {}
        intent = m.get("intent")
        return cls(
            status=m.get("status"),
            state=m.get("state"),
            filled=bool(m.get("filled", False)),
            external_order_submission_performed=bool(m.get("external_order_submission_performed", False)),
            client_order_id=m.get("client_order_id"),
            exchange_order_id=m.get("exchange_order_id"),
            order_intent_id=m.get("order_intent_id"),
            intent=intent if isinstance(intent, Mapping) else {},
            schema_version=m.get("schema_version"),
            raw=m,
        )

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "OrderResultView":
        if path is None:
            from config.settings import ORDER_RESULT_PATH as path  # noqa: PLW0127
        return cls.from_mapping(_read(path))


@dataclass(frozen=True)
class ReconciliationView:
    """``latest_reconciliation.json`` — did reality match the intent."""

    status: str | None      # only "RECONCILED" opens positions (live kernel)
    mismatches: tuple
    actual_order_status: str | None
    actual_avg_fill_price: float | None
    actual_executed_qty: float | None
    schema_version: str | None
    raw: Mapping[str, Any] = field(repr=False)

    @property
    def is_reconciled(self) -> bool:
        return self.status == "RECONCILED"

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "ReconciliationView":
        m = m or {}
        actual = m.get("actual")
        actual = actual if isinstance(actual, Mapping) else {}
        mismatches = m.get("mismatches")
        return cls(
            status=m.get("status"),
            mismatches=tuple(mismatches) if isinstance(mismatches, (list, tuple)) else (),
            actual_order_status=actual.get("order_status"),
            actual_avg_fill_price=_num(actual.get("avg_fill_price")),
            actual_executed_qty=_num(actual.get("executed_qty")),
            schema_version=m.get("schema_version"),
            raw=m,
        )

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "ReconciliationView":
        if path is None:
            from config.settings import RECONCILIATION_PATH as path  # noqa: PLW0127
        return cls.from_mapping(_read(path))
