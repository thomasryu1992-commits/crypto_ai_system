"""Pre-submit final guard for the live-canary order path.

The last fail-closed check before the live adapter signs a real mainnet order.
It is the signed-testnet guard's stricter sibling and adds live-money hardening:

* the read-only preparation gate must already be READY
  (``live_canary_preparation.json`` with ``preparation_ready == true``);
* a distinct live confirmation phrase (a testnet confirmation cannot authorize it);
* a manual kill switch that blocks unconditionally;
* a hard absolute notional ceiling the configurable cap can never exceed;
* a single-order daily cap (a canary is one order), counted in its own file;
* a mainnet host allowlist and a separate order-capable live key.

Returns ``BLOCKED`` / ``REPAIR_REQUIRED`` / ``READY``. ``READY`` means every guard
passed for ONE order within the caps — never standing permission to trade live.
Config is read through ``settings`` at call time so tests can override flags.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import config.settings as settings
from core.json_io import atomic_write_json, read_json
from core.time_utils import utc_now

from crypto_ai_system.execution.live_canary_adapter import ALLOWED_LIVE_HOSTS

STATUS_BLOCKED = "BLOCKED"
STATUS_REPAIR_REQUIRED = "REPAIR_REQUIRED"
STATUS_READY = "READY"

_CONFIRMATION_PHRASE = "I_UNDERSTAND_THIS_PLACES_A_REAL_LIVE_MAINNET_ORDER"


def _counter_path():
    return settings.LATEST_DIR / "live_canary_order_counter.json"


def _preparation_report_path():
    return settings.LATEST_DIR / "live_canary_preparation.json"


def _today() -> str:
    return utc_now().strftime("%Y-%m-%d")


def count_today() -> int:
    data = read_json(_counter_path(), {})
    if not isinstance(data, dict):
        return 0
    return int(data.get(_today(), 0))


def record_submission() -> int:
    """Increment today's live-canary submitted-order counter. Call only after a real submit."""
    path = _counter_path()
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    day = _today()
    data[day] = int(data.get(day, 0)) + 1
    atomic_write_json(path, data)
    return data[day]


def _confirmation_present() -> bool:
    expected = getattr(settings, "LIVE_CANARY_CONFIRMATION_PHRASE", "") or _CONFIRMATION_PHRASE
    given = getattr(settings, "LIVE_CANARY_CONFIRMATION", "")
    return bool(given) and given == expected


def _preparation_ready() -> bool:
    report = read_json(_preparation_report_path(), {})
    return isinstance(report, dict) and report.get("preparation_ready") is True


def _notional_of(intent: dict[str, Any]) -> float:
    for key in ("order_notional_usdt", "notional_usdt"):
        try:
            value = float(intent.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0.0


def evaluate_live_canary_final_guard(intent: dict[str, Any]) -> dict[str, Any]:
    blocks: list[str] = []
    repairs: list[str] = []

    # -- enable flags (fail-closed) --------------------------------------
    if not getattr(settings, "LIVE_CANARY_ENABLED", False):
        blocks.append("LIVE_CANARY_ENABLED is false")
    if not getattr(settings, "LIVE_CANARY_PLACE_ORDER_ENABLED", False):
        blocks.append("LIVE_CANARY_PLACE_ORDER_ENABLED is false")
    if getattr(settings, "LIVE_CANARY_MANUAL_APPROVAL_REQUIRED", True) and not _confirmation_present():
        blocks.append("live canary confirmation phrase not present")
    if getattr(settings, "LIVE_CANARY_MANUAL_KILL_SWITCH", False):
        blocks.append("LIVE_CANARY_MANUAL_KILL_SWITCH is engaged")

    # -- preparation gate must already be READY (testnet evidence + probe) -
    if not _preparation_ready():
        blocks.append(
            "live_canary_preparation.json not READY — run scripts/check_live_canary_readiness.py --probe"
        )

    # -- key scope + host (live mainnet, order-capable key) --------------
    base_url = getattr(settings, "LIVE_CANARY_BASE_URL", "")
    host = (urlparse(base_url).hostname or "").lower()
    if host not in ALLOWED_LIVE_HOSTS:
        blocks.append(f"base url host {host!r} is not an allowed live host")
    if not getattr(settings, "LIVE_CANARY_API_KEY", "") or not getattr(settings, "LIVE_CANARY_API_SECRET", ""):
        blocks.append("live canary api key/secret not configured")

    # -- hard caps (configurable cap bounded by an absolute ceiling) -----
    notional = _notional_of(intent)
    cap = float(getattr(settings, "LIVE_CANARY_MAX_ORDER_NOTIONAL_USDT", 5.0))
    ceiling = float(getattr(settings, "LIVE_CANARY_ABSOLUTE_MAX_NOTIONAL_USDT", 200.0))
    effective_cap = min(cap, ceiling)
    if cap > ceiling:
        blocks.append(f"configured cap {cap} exceeds absolute ceiling {ceiling}")
    if notional <= 0:
        repairs.append("order notional missing or non-positive")
    elif notional > effective_cap:
        blocks.append(f"order notional {notional} exceeds cap {effective_cap}")

    max_daily = int(getattr(settings, "LIVE_CANARY_MAX_DAILY_ORDER_COUNT", 1))
    submitted_today = count_today()
    if submitted_today >= max_daily:
        blocks.append(f"daily canary order count {submitted_today} reached cap {max_daily}")

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
        "notional_absolute_ceiling_usdt": ceiling,
        "effective_cap_usdt": effective_cap,
        "submitted_today": submitted_today,
        "max_daily_order_count": max_daily,
        "preparation_ready": _preparation_ready(),
    }
