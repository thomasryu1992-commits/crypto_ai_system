"""Pre-submit final guard for the signed-testnet path.

Runs immediately before the adapter signs anything. It is the last fail-closed
check: hard caps, key scope, confirmation, and daily count. Returns one of
``BLOCKED`` / ``REPAIR_REQUIRED`` / ``READY``.

``READY`` means "all guards pass"; it still is not permission to trade beyond a
single testnet order within the configured caps. Config is read through the
``settings`` module at call time so tests can override individual flags.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import config.settings as settings
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now

from crypto_ai_system.execution.signed_testnet_adapter import ALLOWED_TESTNET_HOSTS

STATUS_BLOCKED = "BLOCKED"
STATUS_REPAIR_REQUIRED = "REPAIR_REQUIRED"
STATUS_READY = "READY"

_CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_PLACES_REAL_ORDERS"


def _counter_path():
    return settings.LATEST_DIR / "signed_testnet_order_counter.json"


def _today() -> str:
    return utc_now().strftime("%Y-%m-%d")


def count_today() -> int:
    data = read_json(_counter_path(), {})
    if not isinstance(data, dict):
        return 0
    return int(data.get(_today(), 0))


def record_submission() -> int:
    """Increment today's submitted-order counter. Call only after a real submit."""
    path = _counter_path()
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    day = _today()
    data[day] = int(data.get(day, 0)) + 1
    atomic_write_json(path, data)
    return data[day]


def _confirmation_present() -> bool:
    expected = getattr(settings, "LIVE_TRADING_CONFIRMATION_PHRASE", "") or _CONFIRMATION_PHRASE
    given = getattr(settings, "LIVE_TRADING_CONFIRMATION", "")
    return bool(given) and given == expected


def _notional_of(intent: dict[str, Any]) -> float:
    for key in ("order_notional_usdt", "notional_usdt"):
        try:
            value = float(intent.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0.0


def evaluate_signed_testnet_final_guard(intent: dict[str, Any]) -> dict[str, Any]:
    blocks: list[str] = []
    repairs: list[str] = []

    # -- enable flags (fail-closed) --------------------------------------
    if not getattr(settings, "TESTNET_SIGNED_ORDER_ENABLED", False):
        blocks.append("TESTNET_SIGNED_ORDER_ENABLED is false")
    if not getattr(settings, "SIGNED_TESTNET_PLACE_ORDER_ENABLED", False):
        blocks.append("SIGNED_TESTNET_PLACE_ORDER_ENABLED is false")
    if getattr(settings, "SIGNED_TESTNET_MANUAL_APPROVAL_REQUIRED", True) and not _confirmation_present():
        blocks.append("manual approval confirmation phrase not present")

    # -- key scope (testnet only) ----------------------------------------
    if not getattr(settings, "BINANCE_TESTNET", True):
        blocks.append("BINANCE_TESTNET is false (mainnet key scope not allowed)")
    if getattr(settings, "SIGNED_TESTNET_LIVE_KEY_ALLOWED", False):
        blocks.append("SIGNED_TESTNET_LIVE_KEY_ALLOWED is true (must be false)")
    base_url = getattr(settings, "BINANCE_TESTNET_BASE_URL", "")
    host = (urlparse(base_url).hostname or "").lower()
    if host not in ALLOWED_TESTNET_HOSTS:
        blocks.append(f"base url host {host!r} is not an allowed testnet host")
    if not getattr(settings, "BINANCE_API_KEY", "") or not getattr(settings, "BINANCE_API_SECRET", ""):
        blocks.append("testnet api key/secret not configured")

    # -- hard caps -------------------------------------------------------
    notional = _notional_of(intent)
    cap = float(getattr(settings, "SIGNED_TESTNET_MAX_ORDER_NOTIONAL_USDT", 5.0))
    if notional <= 0:
        repairs.append("order notional missing or non-positive")
    elif notional > cap:
        blocks.append(f"order notional {notional} exceeds cap {cap}")

    max_daily = int(getattr(settings, "SIGNED_TESTNET_MAX_DAILY_ORDER_COUNT", 3))
    submitted_today = count_today()
    if submitted_today >= max_daily:
        blocks.append(f"daily order count {submitted_today} reached cap {max_daily}")

    # -- upstream risk gate: strategy vs connectivity (P0-2) -------------
    # Connectivity-harness orders verify auth/signing/submission/reconciliation
    # only. They intentionally bypass the strategy PreOrderRiskGate and MUST NOT
    # be aggregated as strategy performance. A *strategy* order, by contrast, may
    # not rely on a bare boolean + free-form id: it must resolve to a persisted,
    # approved, unexpired, tamper-free RiskGate record for this stage/profile.
    is_connectivity = bool(intent.get("connectivity_test"))
    strategy_execution = not is_connectivity
    risk_gate_verified = False
    if strategy_execution:
        try:
            from crypto_ai_system.registry.risk_gate_registry import (
                get_risk_gate_record,
                verify_strategy_risk_gate,
            )

            record = get_risk_gate_record(intent.get("risk_gate_id"))
            verdict = verify_strategy_risk_gate(record, intent, execution_stage="signed_testnet")
        except Exception as exc:  # fail closed on any registry/lookup error
            verdict = {"approved": False, "reasons": [f"risk_gate_lookup_error:{type(exc).__name__}"]}
        risk_gate_verified = bool(verdict.get("approved"))
        if not risk_gate_verified:
            blocks.extend(f"strategy risk gate: {r}" for r in verdict.get("reasons", []))

    # -- intent shape ----------------------------------------------------
    if intent.get("status") != "ORDER_INTENT_CREATED":
        repairs.append("intent is not in ORDER_INTENT_CREATED state")
    if not intent.get("symbol"):
        repairs.append("intent missing symbol")
    try:
        if float(intent.get("quantity") or 0) <= 0:
            repairs.append("intent quantity missing or non-positive")
    except (TypeError, ValueError):
        repairs.append("intent quantity not numeric")

    if blocks:
        status = STATUS_BLOCKED
    elif repairs:
        status = STATUS_REPAIR_REQUIRED
    else:
        status = STATUS_READY

    return {
        "status": status,
        "approved": status == STATUS_READY,
        "blocks": blocks,
        "repairs": repairs,
        "notional_usdt": notional,
        "notional_cap_usdt": cap,
        "submitted_today": submitted_today,
        "max_daily_order_count": max_daily,
        # Connectivity orders are not strategy performance; a strategy order is
        # only ready when its RiskGate record verified (P0-2).
        "strategy_execution": strategy_execution,
        "risk_gate_verified": risk_gate_verified,
    }
