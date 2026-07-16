"""L2: pre-submit final guard for the autonomous live-strategy order path.

The strictest gate in the system — the last fail-closed check before a real
mainnet strategy order is signed. Unlike the live canary (a connectivity check
that bypasses the strategy RiskGate), a live strategy order MUST resolve to a
persisted, approved, unexpired, tamper-free PreOrderRiskGate record evaluated for
``stage="live"`` and bound to this intent. On top of that it enforces:

* enable flags + a distinct live-strategy confirmation phrase;
* a manual kill switch;
* the L1 daily realized-loss circuit breaker (an unconfigured limit blocks);
* the L5 promotion gate (minimum clean live-canary orders on record);
* a mainnet host allowlist + a separate order-capable live-strategy key;
* a per-order notional cap bounded by an absolute ceiling;
* a daily order-count cap and a total open-exposure cap.

Returns BLOCKED / REPAIR_REQUIRED / READY. Config is read at call time so tests
can override flags. Never signs, submits, or reads secrets.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import config.settings as settings
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now

from crypto_ai_system.execution.live_canary_adapter import ALLOWED_LIVE_HOSTS
from crypto_ai_system.execution.live_pnl_ledger import daily_loss_limit_breached
from crypto_ai_system.execution.live_promotion import live_promotion_ready

STATUS_BLOCKED = "BLOCKED"
STATUS_REPAIR_REQUIRED = "REPAIR_REQUIRED"
STATUS_READY = "READY"

_CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_TRADES_LIVE_FUNDS_AUTONOMOUSLY"


def _counter_path():
    return settings.LATEST_DIR / "live_strategy_order_counter.json"


def _today() -> str:
    return utc_now().strftime("%Y-%m-%d")


def count_today() -> int:
    data = read_json(_counter_path(), {})
    if not isinstance(data, dict):
        return 0
    return int(data.get(_today(), 0))


def record_submission() -> int:
    """Increment today's live-strategy submitted-order counter. Call only after a real submit."""
    path = _counter_path()
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    day = _today()
    data[day] = int(data.get(day, 0)) + 1
    atomic_write_json(path, data)
    return data[day]


def _confirmation_present() -> bool:
    expected = getattr(settings, "LIVE_STRATEGY_CONFIRMATION_PHRASE", "") or _CONFIRMATION_PHRASE
    given = getattr(settings, "LIVE_STRATEGY_CONFIRMATION", "")
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


def _verify_live_risk_gate(intent: dict[str, Any]) -> tuple[bool, list[str]]:
    """A live strategy order needs a verified stage='live' RiskGate record."""
    try:
        from crypto_ai_system.registry.risk_gate_registry import (
            get_risk_gate_record,
            verify_strategy_risk_gate,
        )

        record = get_risk_gate_record(intent.get("risk_gate_id"))
        verdict = verify_strategy_risk_gate(record, intent, execution_stage="live")
    except Exception as exc:  # noqa: BLE001 - fail closed on any lookup error
        return False, [f"risk_gate_lookup_error:{type(exc).__name__}"]
    return bool(verdict.get("approved")), [f"strategy risk gate: {r}" for r in verdict.get("reasons", [])]


def evaluate_live_close_guard(intent: dict[str, Any]) -> dict[str, Any]:
    """Narrower guard for a reduceOnly CLOSE of an existing live position.

    A close reduces risk, so it is exempt from the checks that exist to stop NEW
    risk: the daily-loss breaker (a tripped breaker must still be able to flatten),
    the kill switch (kill switch = no new risk, flatten allowed), the promotion
    gate, the caps, and the RiskGate record (the entry was already gated). What it
    still requires is the structural boundary: the enable flags + confirmation
    (an operator who disabled the live boundary manages the position manually),
    the mainnet host allowlist, the key, and that the intent really is reduceOnly.
    """
    blocks: list[str] = []
    repairs: list[str] = []

    if not getattr(settings, "LIVE_STRATEGY_ORDER_ENABLED", False):
        blocks.append("LIVE_STRATEGY_ORDER_ENABLED is false")
    if not getattr(settings, "LIVE_STRATEGY_PLACE_ORDER_ENABLED", False):
        blocks.append("LIVE_STRATEGY_PLACE_ORDER_ENABLED is false")
    if not _confirmation_present():
        blocks.append("live strategy confirmation phrase not present")

    base_url = getattr(settings, "LIVE_STRATEGY_BASE_URL", "")
    host = (urlparse(base_url).hostname or "").lower()
    if host not in ALLOWED_LIVE_HOSTS:
        blocks.append(f"base url host {host!r} is not an allowed live host")
    if not getattr(settings, "LIVE_STRATEGY_API_KEY", "") or not getattr(settings, "LIVE_STRATEGY_API_SECRET", ""):
        blocks.append("live strategy api key/secret not configured")

    if not intent.get("reduce_only"):
        blocks.append("close guard requires a reduceOnly intent")
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
        "close_guard": True,
    }


def evaluate_live_order_final_guard(
    intent: dict[str, Any], *, current_open_notional_usdt: float = 0.0
) -> dict[str, Any]:
    blocks: list[str] = []
    repairs: list[str] = []

    # -- enable flags (fail-closed) --------------------------------------
    if not getattr(settings, "LIVE_STRATEGY_ORDER_ENABLED", False):
        blocks.append("LIVE_STRATEGY_ORDER_ENABLED is false")
    if not getattr(settings, "LIVE_STRATEGY_PLACE_ORDER_ENABLED", False):
        blocks.append("LIVE_STRATEGY_PLACE_ORDER_ENABLED is false")
    if not _confirmation_present():
        blocks.append("live strategy confirmation phrase not present")
    if getattr(settings, "LIVE_STRATEGY_MANUAL_KILL_SWITCH", False):
        blocks.append("LIVE_STRATEGY_MANUAL_KILL_SWITCH is engaged")

    # -- daily realized-loss circuit breaker (L1) ------------------------
    loss_limit = float(getattr(settings, "LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT", 0.0) or 0.0)
    if daily_loss_limit_breached(loss_limit):
        if loss_limit <= 0:
            blocks.append("LIVE_STRATEGY_DAILY_LOSS_LIMIT_USDT not configured (must be > 0)")
        else:
            blocks.append(f"daily realized-loss limit {loss_limit} USDT reached — halted for today")

    # -- promotion gate (L5): clean live-canary evidence -----------------
    if not live_promotion_ready():
        blocks.append(
            f"live promotion not ready — need >= "
            f"{getattr(settings, 'LIVE_STRATEGY_MIN_CLEAN_CANARY_ORDERS', 3)} clean canary orders"
        )

    # -- connectivity orders are never strategy-live --------------------
    if intent.get("connectivity_test"):
        blocks.append("connectivity_test intent cannot use the live strategy path")

    # -- key scope + host (mainnet, order-capable strategy key) ---------
    base_url = getattr(settings, "LIVE_STRATEGY_BASE_URL", "")
    host = (urlparse(base_url).hostname or "").lower()
    if host not in ALLOWED_LIVE_HOSTS:
        blocks.append(f"base url host {host!r} is not an allowed live host")
    if not getattr(settings, "LIVE_STRATEGY_API_KEY", "") or not getattr(settings, "LIVE_STRATEGY_API_SECRET", ""):
        blocks.append("live strategy api key/secret not configured")

    # -- hard caps -------------------------------------------------------
    notional = _notional_of(intent)
    cap = float(getattr(settings, "LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT", 0.0))
    ceiling = float(getattr(settings, "LIVE_STRATEGY_ABSOLUTE_MAX_NOTIONAL_USDT", 200.0))
    effective_cap = min(cap, ceiling)
    if cap <= 0:
        blocks.append("LIVE_STRATEGY_MAX_ORDER_NOTIONAL_USDT not configured (must be > 0)")
    if cap > ceiling:
        blocks.append(f"configured cap {cap} exceeds absolute ceiling {ceiling}")
    if notional <= 0:
        repairs.append("order notional missing or non-positive")
    elif notional > effective_cap:
        blocks.append(f"order notional {notional} exceeds cap {effective_cap}")

    max_daily = int(getattr(settings, "LIVE_STRATEGY_MAX_DAILY_ORDER_COUNT", 0))
    submitted_today = count_today()
    if max_daily <= 0:
        blocks.append("LIVE_STRATEGY_MAX_DAILY_ORDER_COUNT not configured (must be > 0)")
    elif submitted_today >= max_daily:
        blocks.append(f"daily order count {submitted_today} reached cap {max_daily}")

    exposure_cap = float(getattr(settings, "LIVE_STRATEGY_MAX_OPEN_NOTIONAL_USDT", 0.0))
    if exposure_cap <= 0:
        blocks.append("LIVE_STRATEGY_MAX_OPEN_NOTIONAL_USDT not configured (must be > 0)")
    elif float(current_open_notional_usdt) + notional > exposure_cap:
        blocks.append(
            f"open exposure {current_open_notional_usdt} + {notional} exceeds cap {exposure_cap}"
        )

    # -- verified stage='live' strategy RiskGate record ------------------
    gate_ok, gate_reasons = _verify_live_risk_gate(intent)
    if not gate_ok:
        blocks.extend(gate_reasons or ["strategy risk gate not approved"])

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
        "effective_cap_usdt": effective_cap,
        "open_exposure_cap_usdt": exposure_cap,
        "current_open_notional_usdt": float(current_open_notional_usdt),
        "submitted_today": submitted_today,
        "max_daily_order_count": max_daily,
        "daily_loss_limit_usdt": loss_limit,
        "risk_gate_verified": gate_ok,
        "promotion_ready": live_promotion_ready(),
    }
