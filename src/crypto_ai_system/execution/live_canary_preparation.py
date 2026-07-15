"""Live canary preparation: the read-only gate between signed testnet and live.

Aggregates the evidence required before a live canary order may even be
discussed:

1. Repeated clean signed-testnet sessions (the Phase 10 harness report).
2. A live venue *read-only* probe: key restrictions, account flags, balance,
   open positions/orders, symbol filters (min notional), commission rate.
3. Fail-closed posture: this module never enables anything. Its report always
   records ``live_order_submission_allowed=false``.

The probe client is GET-only by construction — it has no order, cancel, or
transfer method and refuses non-allowlisted hosts — so it is structurally
incapable of mutating the account. Transport is injectable so tests never hit
the network.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

from core.time_utils import utc_now_iso

# The only hosts the probe may ever sign a read-only request against.
ALLOWED_LIVE_FUTURES_HOSTS = frozenset({"fapi.binance.com"})
ALLOWED_LIVE_SPOT_HOSTS = frozenset({"api.binance.com"})

ACCOUNT_PATH = "/fapi/v2/account"
BALANCE_PATH = "/fapi/v2/balance"
POSITION_RISK_PATH = "/fapi/v2/positionRisk"
OPEN_ORDERS_PATH = "/fapi/v1/openOrders"
COMMISSION_RATE_PATH = "/fapi/v1/commissionRate"
EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
API_RESTRICTIONS_PATH = "/sapi/v1/account/apiRestrictions"

# A transport takes (method, url, params, headers, timeout) and returns
# (http_status_code, parsed_json_or_error_dict). Same shape as the testnet
# adapter's so a shared fake works in tests.
Transport = Callable[[str, str, dict, dict, float], "tuple[int, Any]"]


class NonLiveHostError(ValueError):
    """Raised when a non-allowlisted host is configured — never signed against."""


def _requests_transport(
    method: str, url: str, params: dict, headers: dict, timeout: float
) -> tuple[int, Any]:
    import requests  # local import so the module loads without network stack

    response = requests.request(
        method, url, params=params, headers=headers, timeout=timeout
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw_text": response.text}
    return response.status_code, body


def _host_of(base_url: str) -> str:
    return (urlparse(base_url).hostname or "").lower()


def _redact(params: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(params)
    if "signature" in redacted:
        redacted["signature"] = "***redacted***"
    return redacted


class LiveReadOnlyProbe:
    """Signed GET-only client for the live venue.

    Deliberately has no submit/cancel/transfer method: the widest thing this
    class can do is read. Any attempt to point it at a non-allowlisted host
    fails at construction time.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        futures_base_url: str = "https://fapi.binance.com",
        spot_base_url: str = "https://api.binance.com",
        *,
        transport: Transport | None = None,
        timeout: float = 5.0,
        recv_window: int = 5000,
    ) -> None:
        futures_host = _host_of(futures_base_url)
        if futures_host not in ALLOWED_LIVE_FUTURES_HOSTS:
            raise NonLiveHostError(
                f"refusing to sign against futures host {futures_host!r}; "
                f"allowed: {sorted(ALLOWED_LIVE_FUTURES_HOSTS)}"
            )
        spot_host = _host_of(spot_base_url)
        if spot_host not in ALLOWED_LIVE_SPOT_HOSTS:
            raise NonLiveHostError(
                f"refusing to sign against spot host {spot_host!r}; "
                f"allowed: {sorted(ALLOWED_LIVE_SPOT_HOSTS)}"
            )
        if not api_key or not api_secret:
            raise ValueError("api_key and api_secret are required to sign requests")

        self._api_key = api_key
        self._api_secret = api_secret.encode("utf-8")
        self.futures_base_url = futures_base_url.rstrip("/")
        self.spot_base_url = spot_base_url.rstrip("/")
        self.timeout = timeout
        self.recv_window = recv_window
        self._transport: Transport = transport or _requests_transport

    # -- signing ----------------------------------------------------------
    def _sign(self, query_string: str) -> str:
        return hmac.new(self._api_secret, query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    def _signed_params(self, params: dict[str, Any]) -> dict[str, Any]:
        signed = dict(params)
        signed.setdefault("recvWindow", self.recv_window)
        signed["timestamp"] = int(time.time() * 1000)
        signed["signature"] = self._sign(urlencode(signed))
        return signed

    def _get(self, base_url: str, path: str, params: dict[str, Any], *, signed: bool) -> dict[str, Any]:
        request_params = self._signed_params(params) if signed else dict(params)
        headers = {"X-MBX-APIKEY": self._api_key} if signed else {}
        url = f"{base_url}{path}"
        try:
            status_code, body = self._transport(
                "GET", url, request_params, headers, self.timeout
            )
        except Exception as exc:  # noqa: BLE001 - network/transport failure
            return {
                "ok": False,
                "http_status": None,
                "error": f"{type(exc).__name__}: {exc}",
                "request": _redact(request_params),
            }

        ok = 200 <= status_code < 300
        result = {
            "ok": ok,
            "http_status": status_code,
            "response": body if ok else None,
            "request": _redact(request_params),
        }
        if not ok:
            code = body.get("code") if isinstance(body, dict) else None
            msg = body.get("msg") if isinstance(body, dict) else None
            result["error"] = {"code": code, "msg": msg}
        return result

    # -- read-only operations ---------------------------------------------
    def get_api_restrictions(self) -> dict[str, Any]:
        """Key scope: withdrawals/transfers must be disabled on a canary key."""
        return self._get(self.spot_base_url, API_RESTRICTIONS_PATH, {}, signed=True)

    def get_account(self) -> dict[str, Any]:
        return self._get(self.futures_base_url, ACCOUNT_PATH, {}, signed=True)

    def get_balance(self) -> dict[str, Any]:
        return self._get(self.futures_base_url, BALANCE_PATH, {}, signed=True)

    def get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": symbol} if symbol else {}
        return self._get(self.futures_base_url, POSITION_RISK_PATH, params, signed=True)

    def get_open_orders(self, symbol: str) -> dict[str, Any]:
        return self._get(self.futures_base_url, OPEN_ORDERS_PATH, {"symbol": symbol}, signed=True)

    def get_commission_rate(self, symbol: str) -> dict[str, Any]:
        return self._get(self.futures_base_url, COMMISSION_RATE_PATH, {"symbol": symbol}, signed=True)

    def get_exchange_info(self) -> dict[str, Any]:
        # Public endpoint: unsigned, no key header.
        return self._get(self.futures_base_url, EXCHANGE_INFO_PATH, {}, signed=False)


# -- evidence gates ---------------------------------------------------------

def evaluate_testnet_session_evidence(
    report: dict | None, min_clean_sessions: int = 5
) -> dict[str, Any]:
    """Gate 1: the Phase 10 session report must show repeated clean sessions."""
    blockers: list[str] = []
    aggregate = (report or {}).get("aggregate") or {}

    if not report:
        blockers.append(
            "no signed_testnet_session_report.json — run run_testnet_session.py first"
        )
    else:
        sessions_ok = int(aggregate.get("sessions_ok") or 0)
        orders_submitted = int(aggregate.get("orders_submitted") or 0)
        reconcile_rate = aggregate.get("reconcile_rate")
        if sessions_ok < min_clean_sessions:
            blockers.append(
                f"clean testnet sessions {sessions_ok} < required {min_clean_sessions}"
            )
        if orders_submitted == 0:
            blockers.append("session report contains no submitted orders")
        if reconcile_rate != 1.0:
            blockers.append(f"testnet reconcile_rate {reconcile_rate!r} != 1.0")

    return {
        "passed": not blockers,
        "blockers": blockers,
        "min_clean_sessions": min_clean_sessions,
        "sessions_ok": aggregate.get("sessions_ok"),
        "orders_submitted": aggregate.get("orders_submitted"),
        "reconcile_rate": aggregate.get("reconcile_rate"),
        "avg_slippage_bps": aggregate.get("avg_slippage_bps"),
        "avg_latency_ms": aggregate.get("avg_latency_ms"),
        "report_created_at": (report or {}).get("created_at"),
    }


def _symbol_filters(exchange_info: dict, symbol: str) -> dict[str, Any]:
    for entry in (exchange_info.get("symbols") or []):
        if not isinstance(entry, dict) or entry.get("symbol") != symbol:
            continue
        filters = {f.get("filterType"): f for f in entry.get("filters", []) if isinstance(f, dict)}
        notional = filters.get("MIN_NOTIONAL", {})
        lot = filters.get("LOT_SIZE", {})
        price = filters.get("PRICE_FILTER", {})
        return {
            "status": entry.get("status"),
            "min_notional": notional.get("notional"),
            "min_qty": lot.get("minQty"),
            "step_size": lot.get("stepSize"),
            "tick_size": price.get("tickSize"),
        }
    return {}


def run_live_readonly_probe(probe: LiveReadOnlyProbe, symbol: str) -> dict[str, Any]:
    """Gate 2: read the live venue. Never signs anything but GETs."""
    errors: list[str] = []

    def _call(name: str, result: dict) -> Any:
        if not result.get("ok"):
            errors.append(f"{name}: {result.get('error') or result.get('http_status')}")
            return None
        return result.get("response")

    restrictions = _call("api_restrictions", probe.get_api_restrictions()) or {}
    account = _call("account", probe.get_account()) or {}
    positions = _call("positions", probe.get_positions(symbol)) or []
    open_orders = _call("open_orders", probe.get_open_orders(symbol)) or []
    commission = _call("commission_rate", probe.get_commission_rate(symbol)) or {}
    exchange_info = _call("exchange_info", probe.get_exchange_info()) or {}

    open_position_count = sum(
        1
        for p in positions
        if isinstance(p, dict) and abs(float(p.get("positionAmt") or 0.0)) > 0
    )

    return {
        "ok": not errors,
        "errors": errors,
        "symbol": symbol,
        "key_restrictions": {
            "enable_reading": restrictions.get("enableReading"),
            "enable_withdrawals": restrictions.get("enableWithdrawals"),
            "enable_internal_transfer": restrictions.get("enableInternalTransfer"),
            "enable_futures": restrictions.get("enableFutures"),
            "enable_spot_and_margin_trading": restrictions.get("enableSpotAndMarginTrading"),
            "ip_restrict": restrictions.get("ipRestrict"),
        },
        "account": {
            "can_trade": account.get("canTrade"),
            "can_deposit": account.get("canDeposit"),
            "can_withdraw": account.get("canWithdraw"),
            "total_wallet_balance_usdt": account.get("totalWalletBalance"),
            "available_balance_usdt": account.get("availableBalance"),
        },
        "open_position_count": open_position_count,
        "open_order_count": len(open_orders) if isinstance(open_orders, list) else None,
        "commission": {
            "maker": commission.get("makerCommissionRate"),
            "taker": commission.get("takerCommissionRate"),
        },
        "symbol_filters": _symbol_filters(exchange_info, symbol),
    }


def build_live_canary_preparation_report(
    session_evidence: dict[str, Any],
    probe_summary: dict[str, Any] | None,
    *,
    probe_attempted: bool,
) -> dict[str, Any]:
    """Merge the gates into one fail-closed report.

    ``preparation_ready`` may become true; the order-authority flags below it
    never do — enabling a live canary order is a separate, operator-approved
    step outside this module.
    """
    blockers = list(session_evidence.get("blockers") or [])

    if not probe_attempted:
        blockers.append(
            "live read-only probe not run — scripts/check_live_canary_readiness.py --probe"
        )
    elif not probe_summary or not probe_summary.get("ok"):
        for err in (probe_summary or {}).get("errors") or ["probe returned no data"]:
            blockers.append(f"live probe failed: {err}")
    else:
        restrictions = probe_summary.get("key_restrictions") or {}
        if restrictions.get("enable_withdrawals") is not False:
            blockers.append("live key allows withdrawals — use a restricted key")
        if restrictions.get("enable_internal_transfer") is True:
            blockers.append("live key allows internal transfer — use a restricted key")
        if restrictions.get("enable_reading") is not True:
            blockers.append("live key cannot read account data")
        filters = probe_summary.get("symbol_filters") or {}
        if not filters.get("min_notional"):
            blockers.append("symbol min notional could not be determined")
        if filters.get("status") not in (None, "TRADING"):
            blockers.append(f"symbol not in TRADING status (got {filters.get('status')!r})")

    return {
        "created_at": utc_now_iso(),
        "preparation_ready": not blockers,
        "blockers": blockers,
        "testnet_evidence": session_evidence,
        "live_probe": probe_summary,
        # Hard fail-closed: this report is evidence, never authority.
        "live_canary_execution_enabled": False,
        "live_order_submission_allowed": False,
        "external_order_submission_performed": False,
    }
