"""Canonical execution port + venue adapters (directive P0-1, Phase B).

Paper and signed-testnet execution used to be two hard-coded branches inside
``order_executor.execute_order_intent``. This module makes the branch an
``ExecutionPort``: the same canonical OrderIntent is handed to whichever adapter
serves the requested stage, and the only difference between paper and testnet is
the adapter. Reconciliation, outcome, and the RiskGate remain shared.

Adapters never lower a safety bar: the signed-testnet adapter still runs the
pre-submit final guard (hard caps, key scope, confirmation, strategy RiskGate
record) before anything is signed.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core.time_utils import utc_now_iso


@runtime_checkable
class ExecutionPort(Protocol):
    """A venue that can execute a canonical OrderIntent for one stage."""

    stage: str

    def submit(self, intent: dict[str, Any], *, readiness: dict[str, Any]) -> dict[str, Any]:
        ...


class PaperExecutionAdapter:
    """Wraps the deterministic paper execution engine (Path B, v2)."""

    stage = "paper"

    def submit(self, intent: dict[str, Any], *, readiness: dict[str, Any]) -> dict[str, Any]:
        from crypto_ai_system.execution.paper_execution_engine_v2 import execute_and_persist_paper_order

        result = execute_and_persist_paper_order(
            intent,
            risk_gate_report=intent.get("risk_gate_report") or {},
            market_state={
                "price": intent.get("entry_price"),
                "fee_bps": intent.get("fee_bps"),
                "slippage_bps": intent.get("slippage_bps"),
            },
        )
        result["mode"] = "PAPER_EXECUTION_ENGINE_V2"
        result["readiness"] = readiness
        result["filled"] = (result.get("simulated_fill") or {}).get("fill_status") in {"FILLED", "PARTIALLY_FILLED"}
        result["exchange_order_id"] = None
        return result


class BinanceTestnetAdapter:
    """Wraps the signed-testnet final guard + HMAC adapter.

    Fails closed: unless the pre-submit final guard returns READY, nothing is
    signed or sent.
    """

    stage = "signed_testnet"

    def submit(self, intent: dict[str, Any], *, readiness: dict[str, Any]) -> dict[str, Any]:
        import config.settings as settings
        from crypto_ai_system.execution.signed_testnet_adapter import SignedTestnetAdapter
        from crypto_ai_system.execution.signed_testnet_final_guard import (
            evaluate_signed_testnet_final_guard,
            record_submission,
        )

        guard = evaluate_signed_testnet_final_guard(intent)
        result = {
            "created_at": utc_now_iso(),
            "intent": intent,
            "readiness": readiness,
            "final_guard": guard,
            # Surfaced so outcome/performance aggregation can exclude non-strategy
            # (connectivity-harness) orders.
            "connectivity_test": bool(intent.get("connectivity_test")),
            "exchange_order_id": None,
            "filled": False,
            "external_order_submission_performed": False,
        }

        if not guard.get("approved"):
            result["state"] = "REJECTED"
            result["status"] = f"SIGNED_TESTNET_{guard.get('status', 'BLOCKED')}"
            result["mode"] = "SIGNED_TESTNET_GUARD_BLOCK"
            return result

        adapter = SignedTestnetAdapter(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
            base_url=settings.BINANCE_TESTNET_BASE_URL,
        )
        submit = adapter.submit_order(intent)
        submitted = bool(submit.get("submitted"))
        if submitted:
            record_submission()

        result["mode"] = "SIGNED_TESTNET_ADAPTER"
        result["state"] = "SUBMITTED" if submitted else "UNKNOWN"
        result["status"] = "SIGNED_TESTNET_ORDER_SUBMITTED" if submitted else "SIGNED_TESTNET_SUBMIT_FAILED"
        result["submit_result"] = submit
        result["exchange_order_id"] = submit.get("exchange_order_id")
        result["client_order_id"] = submit.get("client_order_id")
        result["external_order_submission_performed"] = submitted
        return result


class BinanceLiveStrategyAdapter:
    """Wraps the live-strategy final guard + mainnet HMAC adapter (L3).

    Fails closed: unless the pre-submit final guard returns READY — which itself
    requires a verified stage='live' RiskGate record, the L1 daily-loss breaker
    clear, promotion evidence, and every hard cap satisfied — nothing is signed
    or sent. The live canary stays a separate standalone boundary; this port is
    the pipeline's strategy-driven live path.
    """

    stage = "live"

    def submit(self, intent: dict[str, Any], *, readiness: dict[str, Any]) -> dict[str, Any]:
        from crypto_ai_system.execution.live_strategy_execution import submit_live_strategy_order

        result = submit_live_strategy_order(
            intent,
            current_open_notional_usdt=float(intent.get("current_open_notional_usdt") or 0.0),
        )
        result["readiness"] = readiness
        return result


_SIGNED_TESTNET_STAGES = {"signed_testnet", "testnet"}

_PAPER_ADAPTER = PaperExecutionAdapter()
_TESTNET_ADAPTER = BinanceTestnetAdapter()
_LIVE_STRATEGY_ADAPTER = BinanceLiveStrategyAdapter()


def select_adapter(stage: str | None) -> ExecutionPort | None:
    """Return the ExecutionPort for ``stage`` (paper / signed_testnet / live), else None.

    None means "no adapter serves this stage" — the caller falls back to its
    fail-closed shadow/blocked handling. The ``live`` port exists but is itself
    fail-closed: its final guard blocks unless every live-strategy gate passes."""
    normalized = str(stage or "").strip().lower()
    if normalized == "paper":
        return _PAPER_ADAPTER
    if normalized in _SIGNED_TESTNET_STAGES:
        return _TESTNET_ADAPTER
    if normalized == "live":
        return _LIVE_STRATEGY_ADAPTER
    return None
