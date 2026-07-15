"""Signed Binance USD-M Futures **testnet** order adapter.

The one place in the system that signs a request and can POST an order. It is
deliberately narrow and fail-closed:

* Testnet host allowlist only — any mainnet URL is rejected.
* Secrets are read by the caller and passed in at submit time; this module
  never logs or returns the api key, secret, or signature.
* Order submission is never auto-retried; on an ambiguous failure the caller
  should query by ``newClientOrderId`` (see ``classify_exchange_error``).

Transport is injectable so tests never hit the network. The default transport
uses ``requests``.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

from crypto_ai_system.execution.retry_policy import classify_exchange_error

# Only these hosts may ever be signed against. Mainnet is not here by design.
ALLOWED_TESTNET_HOSTS = frozenset({"testnet.binancefuture.com"})

ORDER_PATH = "/fapi/v1/order"
POSITION_RISK_PATH = "/fapi/v2/positionRisk"
BALANCE_PATH = "/fapi/v2/balance"

# A transport takes (method, url, params, headers, timeout) and returns
# (http_status_code, parsed_json_or_error_dict).
Transport = Callable[[str, str, dict, dict, float], "tuple[int, Any]"]


class NonTestnetHostError(ValueError):
    """Raised when a non-testnet host is configured — never signed against."""


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


class SignedTestnetAdapter:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://testnet.binancefuture.com",
        *,
        transport: Transport | None = None,
        timeout: float = 5.0,
        recv_window: int = 5000,
    ) -> None:
        host = _host_of(base_url)
        if host not in ALLOWED_TESTNET_HOSTS:
            raise NonTestnetHostError(
                f"refusing to sign against non-testnet host {host!r}; "
                f"allowed: {sorted(ALLOWED_TESTNET_HOSTS)}"
            )
        if not api_key or not api_secret:
            raise ValueError("api_key and api_secret are required to sign requests")

        self._api_key = api_key
        self._api_secret = api_secret.encode("utf-8")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.recv_window = recv_window
        self._transport: Transport = transport or _requests_transport

    # -- signing ---------------------------------------------------------
    def _sign(self, query_string: str) -> str:
        return hmac.new(self._api_secret, query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    def _signed_params(self, params: dict[str, Any]) -> dict[str, Any]:
        signed = dict(params)
        signed.setdefault("recvWindow", self.recv_window)
        signed["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(signed)
        signed["signature"] = self._sign(query_string)
        return signed

    def _headers(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self._api_key}

    def _send(self, method: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        signed = self._signed_params(params)
        url = f"{self.base_url}{path}"
        try:
            status_code, body = self._transport(
                method, url, signed, self._headers(), self.timeout
            )
        except Exception as exc:  # noqa: BLE001 - network/transport failure
            classification = classify_exchange_error(error_name=type(exc).__name__)
            return {
                "ok": False,
                "http_status": None,
                "error": f"{type(exc).__name__}: {exc}",
                "classification": classification,
                "request": _redact(signed),
            }

        ok = 200 <= status_code < 300
        result = {
            "ok": ok,
            "http_status": status_code,
            "response": body if ok else None,
            "request": _redact(signed),
        }
        if not ok:
            code = body.get("code") if isinstance(body, dict) else None
            msg = body.get("msg") if isinstance(body, dict) else None
            result["error"] = {"code": code, "msg": msg}
            result["classification"] = classify_exchange_error(status_code=status_code)
        return result

    # -- operations ------------------------------------------------------
    def submit_order(self, intent: dict[str, Any]) -> dict[str, Any]:
        """Submit a single order derived from an order intent.

        Never auto-retries. Returns a redacted result dict; the exchange order
        id (if any) is surfaced under ``exchange_order_id``.
        """
        params: dict[str, Any] = {
            "symbol": intent["symbol"],
            "side": intent["side"],
            "type": intent.get("order_type_exchange", "MARKET"),
            "quantity": intent["quantity"],
            "newClientOrderId": intent["client_order_id"],
        }
        if intent.get("reduce_only"):
            # Closing/reducing order: the exchange must not let it flip the
            # position to the opposite side.
            params["reduceOnly"] = "true"
        if params["type"] == "LIMIT":
            params["price"] = intent["entry_price"]
            params["timeInForce"] = intent.get("time_in_force", "GTC")

        result = self._send("POST", ORDER_PATH, params)
        response = result.get("response") or {}
        result["exchange_order_id"] = response.get("orderId") if isinstance(response, dict) else None
        result["client_order_id"] = intent["client_order_id"]
        result["submitted"] = bool(result.get("ok"))
        return result

    def query_order(self, symbol: str, client_order_id: str) -> dict[str, Any]:
        return self._send(
            "GET", ORDER_PATH, {"symbol": symbol, "origClientOrderId": client_order_id}
        )

    def cancel_order(self, symbol: str, client_order_id: str) -> dict[str, Any]:
        return self._send(
            "DELETE", ORDER_PATH, {"symbol": symbol, "origClientOrderId": client_order_id}
        )

    def get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": symbol} if symbol else {}
        return self._send("GET", POSITION_RISK_PATH, params)

    def get_balance(self) -> dict[str, Any]:
        return self._send("GET", BALANCE_PATH, {})


def _redact(params: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of request params with the signature removed.

    The api key/secret are never part of the query params (key is a header,
    secret is never transmitted), and the signature is stripped here so no
    credential-derived value is ever logged or persisted.
    """
    redacted = dict(params)
    if "signature" in redacted:
        redacted["signature"] = "***redacted***"
    return redacted
