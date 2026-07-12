from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

import requests

from crypto_ai_system.utils.audit import sha256_json, stable_id, utc_now_canonical

P71_VERSION = "p71_extended_testnet_read_only_connectivity_v1"
P71_PRIVATE_RECEIPT_VERSION = "p71_extended_private_read_only_receipt_v1"
EXTENDED_TESTNET_API_BASE_URL = "https://api.starknet.sepolia.extended.exchange/api/v1"
EXTENDED_TESTNET_STREAM_BASE_URL = "wss://api.starknet.sepolia.extended.exchange/stream.extended.exchange/v1"
EXTENDED_TESTNET_MARKET = "BTC-USD"
PUBLIC_MARKET_PATH = "/info/markets"
PUBLIC_ORDERBOOK_PATH = "/info/markets/BTC-USD/orderbook"
PUBLIC_ORDERBOOK_STREAM_PATH = "/orderbooks/BTC-USD"

RestGet = Callable[[str, Mapping[str, Any], Mapping[str, str], float], Mapping[str, Any]]


class PublicStreamProbe(Protocol):
    def __call__(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> Mapping[str, Any]: ...


class ExtendedReadOnlyPolicyError(RuntimeError):
    pass


def _requests_get(url: str, params: Mapping[str, Any], headers: Mapping[str, str], timeout: float) -> Mapping[str, Any]:
    response = requests.get(url, params=dict(params), headers=dict(headers), timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise ValueError("Extended REST response must be an object")
    return dict(payload)


def websocket_public_snapshot_probe(url: str, headers: Mapping[str, str], timeout_seconds: float) -> Mapping[str, Any]:
    from websockets.sync.client import connect

    started = time.monotonic()
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with connect(
                url,
                user_agent_header=str(headers.get("User-Agent") or "crypto-ai-system-p71-read-only/1"),
                open_timeout=timeout_seconds,
                ping_interval=15,
                ping_timeout=10,
                close_timeout=2,
            ) as ws:
                raw = ws.recv(timeout=timeout_seconds)
            latency_ms = round((time.monotonic() - started) * 1000, 3)
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(str(raw))
            return {"message": payload, "latency_ms": latency_ms, "received": True, "connection_attempts": attempt}
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(attempt)
    raise RuntimeError(f"Extended public stream unavailable after 3 attempts: {last_error}") from last_error


@dataclass(frozen=True)
class ExtendedPublicReadOnlyPolicy:
    api_base_url: str = EXTENDED_TESTNET_API_BASE_URL
    stream_base_url: str = EXTENDED_TESTNET_STREAM_BASE_URL
    market: str = EXTENDED_TESTNET_MARKET
    network_enabled: bool = False
    write_calls_allowed: bool = False
    credential_headers_allowed: bool = False
    timeout_seconds: float = 10.0
    user_agent: str = "crypto-ai-system-p71-read-only/1"


class ExtendedPublicReadOnlyClient:
    def __init__(self, policy: ExtendedPublicReadOnlyPolicy, *, rest_get: RestGet | None = None, stream_probe: PublicStreamProbe | None = None) -> None:
        self.policy = policy
        self.rest_get = rest_get or _requests_get
        self.stream_probe = stream_probe or websocket_public_snapshot_probe
        if "sepolia.extended.exchange" not in policy.api_base_url.lower():
            raise ExtendedReadOnlyPolicyError("P71 API base URL must be Extended Starknet Sepolia")
        if not policy.stream_base_url.lower().startswith("wss://api.starknet.sepolia.extended.exchange/"):
            raise ExtendedReadOnlyPolicyError("P71 stream URL must be Extended Starknet Sepolia WSS")
        if policy.market != EXTENDED_TESTNET_MARKET:
            raise ExtendedReadOnlyPolicyError("P71 market must be BTC-USD")
        if policy.write_calls_allowed:
            raise ExtendedReadOnlyPolicyError("P71 write calls must remain disabled")
        if policy.credential_headers_allowed:
            raise ExtendedReadOnlyPolicyError("P71 public client must not accept credential headers")

    @property
    def headers(self) -> dict[str, str]:
        return {"User-Agent": self.policy.user_agent}

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not self.policy.network_enabled:
            return {"called": False, "blocked": True, "reason": "P71_NETWORK_DISABLED", "path": path, "params": dict(params or {})}
        if not path.startswith("/info/"):
            raise ExtendedReadOnlyPolicyError("P71 public REST allowlist permits only /info/* GET paths")
        started = time.monotonic()
        payload = dict(self.rest_get(f"{self.policy.api_base_url}{path}", dict(params or {}), self.headers, self.policy.timeout_seconds))
        return {"called": True, "blocked": False, "method": "GET", "path": path, "payload": payload, "latency_ms": round((time.monotonic() - started) * 1000, 3)}

    def get_market(self) -> dict[str, Any]:
        return self._get(PUBLIC_MARKET_PATH, {"market": self.policy.market})

    def get_orderbook(self) -> dict[str, Any]:
        return self._get(PUBLIC_ORDERBOOK_PATH)

    def get_orderbook_stream_snapshot(self) -> dict[str, Any]:
        path = PUBLIC_ORDERBOOK_STREAM_PATH
        if not self.policy.network_enabled:
            return {"called": False, "blocked": True, "reason": "P71_NETWORK_DISABLED", "path": path}
        try:
            result = dict(self.stream_probe(f"{self.policy.stream_base_url}{path}", self.headers, self.policy.timeout_seconds))
            return {"called": True, "blocked": False, "path": path, **result}
        except Exception as exc:
            return {
                "called": True,
                "blocked": True,
                "received": False,
                "path": path,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }

    def post(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"called": False, "blocked": True, "reason": "P71_WRITE_CALL_BLOCKED", "http_method": "POST"}


def _unwrap_data(response: Mapping[str, Any]) -> Any:
    payload = response.get("payload") or {}
    if isinstance(payload, Mapping) and "data" in payload:
        return payload.get("data")
    return payload


def _first_market(data: Any) -> Mapping[str, Any]:
    if isinstance(data, list):
        for item in data:
            if isinstance(item, Mapping) and str(item.get("name") or item.get("market") or "") == EXTENDED_TESTNET_MARKET:
                return item
        return data[0] if data and isinstance(data[0], Mapping) else {}
    return data if isinstance(data, Mapping) else {}


def build_p71_public_connectivity_evidence(*, market_response: Mapping[str, Any], orderbook_response: Mapping[str, Any], stream_response: Mapping[str, Any], observed_at_utc: str | None = None) -> dict[str, Any]:
    observed_at = observed_at_utc or utc_now_canonical()
    blockers: list[str] = []
    market = _first_market(_unwrap_data(market_response))
    orderbook = _unwrap_data(orderbook_response)
    stream_message = stream_response.get("message")
    market_name = str(market.get("name") or market.get("market") or "")
    market_status = str(market.get("status") or "").upper()
    trading_config = market.get("tradingConfig") or market.get("trading_config")
    if market_response.get("called") is not True:
        blockers.append("P71_MARKET_REST_NOT_CALLED")
    if market_name != EXTENDED_TESTNET_MARKET:
        blockers.append("P71_BTC_USD_MARKET_NOT_CONFIRMED")
    if market_status not in {"ACTIVE", "TRADING"}:
        blockers.append("P71_MARKET_NOT_ACTIVE")
    if not isinstance(trading_config, Mapping) or not trading_config:
        blockers.append("P71_TRADING_RULES_MISSING")
    if orderbook_response.get("called") is not True:
        blockers.append("P71_ORDERBOOK_REST_NOT_CALLED")
    if not isinstance(orderbook, Mapping) or not (orderbook.get("bids") or orderbook.get("bid")) or not (orderbook.get("asks") or orderbook.get("ask")):
        blockers.append("P71_ORDERBOOK_LEVELS_MISSING")
    if stream_response.get("called") is not True or not stream_response.get("received") or stream_message is None:
        blockers.append("P71_PUBLIC_STREAM_SNAPSHOT_MISSING")

    safe_projection = {
        "market": market,
        "orderbook": orderbook,
        "stream_message": stream_message,
        "raw_market_response": dict(market_response),
        "raw_orderbook_response": dict(orderbook_response),
        "raw_stream_response": dict(stream_response),
        "observed_at_utc": observed_at,
    }
    serialized = json.dumps(safe_projection, ensure_ascii=False, sort_keys=True, default=str).lower()
    forbidden_secret_tokens = ("api_key", "api-secret", "api_secret", "private_key", "stark_private", "x-api-key")
    secret_matches = [token for token in forbidden_secret_tokens if token in serialized]
    if secret_matches:
        blockers.append("P71_NO_SECRET_SCAN_FAILED")

    public_valid = not blockers
    evidence = {
        "version": P71_VERSION,
        "evidence_id": stable_id("p71_extended_public_read_only", {"observed_at_utc": observed_at, "market": market_name, "status": market_status}),
        "venue": "extended_starknet_sepolia",
        "environment": "testnet",
        "market": EXTENDED_TESTNET_MARKET,
        "observed_at_utc": observed_at,
        "public_rest_valid": market_response.get("called") is True and orderbook_response.get("called") is True,
        "public_stream_valid": stream_response.get("called") is True and stream_response.get("received") is True,
        "public_stream_error_type": stream_response.get("error_type"),
        "public_stream_error": stream_response.get("error"),
        "market_status": market_status or None,
        "trading_rules_present": isinstance(trading_config, Mapping) and bool(trading_config),
        "no_secret_scan_passed": not secret_matches,
        "no_secret_scan_matches": secret_matches,
        "public_connectivity_valid": public_valid,
        "private_account_read_evidence_valid": False,
        "p71_complete": False,
        "status": "P71_PUBLIC_READ_ONLY_VALID_PRIVATE_ACCOUNT_EVIDENCE_PENDING" if public_valid else "P71_PUBLIC_READ_ONLY_BLOCKED",
        "block_reasons": sorted(set(blockers + ["P71_PRIVATE_ACCOUNT_READ_EVIDENCE_PENDING"])),
        "network_write_call_performed": False,
        "order_endpoint_called": False,
        "signature_created": False,
        "testnet_order_submission_allowed": False,
        "market_response_hash": sha256_json(dict(market_response)),
        "orderbook_response_hash": sha256_json(dict(orderbook_response)),
        "stream_response_hash": sha256_json(dict(stream_response)),
    }
    evidence["evidence_sha256"] = sha256_json(evidence)
    return evidence


def run_p71_public_probe(*, network_enabled: bool, rest_get: RestGet | None = None, stream_probe: PublicStreamProbe | None = None, timeout_seconds: float = 10.0) -> dict[str, Any]:
    client = ExtendedPublicReadOnlyClient(ExtendedPublicReadOnlyPolicy(network_enabled=network_enabled, timeout_seconds=timeout_seconds), rest_get=rest_get, stream_probe=stream_probe)
    market = client.get_market()
    orderbook = client.get_orderbook()
    stream = client.get_orderbook_stream_snapshot()
    write_block = client.post("/user/order", {})
    evidence = build_p71_public_connectivity_evidence(market_response=market, orderbook_response=orderbook, stream_response=stream)
    evidence["write_block_probe"] = write_block
    evidence["write_block_probe_valid"] = write_block.get("called") is False and write_block.get("blocked") is True
    return evidence


def validate_p71_private_account_evidence(receipt: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(receipt or {})
    blockers: list[str] = []
    if data.get("version") != P71_PRIVATE_RECEIPT_VERSION:
        blockers.append("P71_PRIVATE_RECEIPT_VERSION_INVALID")
    if data.get("venue") != "extended_starknet_sepolia" or data.get("environment") != "testnet" or data.get("market") != "BTC-USD":
        blockers.append("P71_PRIVATE_RECEIPT_SCOPE_INVALID")
    if not str(data.get("credential_reference_id") or "").strip():
        blockers.append("P71_PRIVATE_CREDENTIAL_REFERENCE_MISSING")
    fingerprint = str(data.get("api_key_fingerprint_sha256") or "")
    if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint.lower()):
        blockers.append("P71_PRIVATE_API_KEY_FINGERPRINT_INVALID")
    endpoints = data.get("endpoint_receipts") or {}
    required = {"account_info", "balance", "positions", "open_orders"}
    if not isinstance(endpoints, Mapping) or set(endpoints) != required:
        blockers.append("P71_PRIVATE_REQUIRED_ENDPOINT_EVIDENCE_MISSING")
    else:
        for name, item in endpoints.items():
            zero_balance_valid = (
                name == "balance"
                and isinstance(item, Mapping)
                and item.get("http_status") == 404
                and item.get("zero_balance_confirmed") is True
            )
            normal_read_valid = (
                isinstance(item, Mapping)
                and item.get("http_status") == 200
                and item.get("data_present") is True
            )
            if not isinstance(item, Mapping) or item.get("http_method") != "GET" or not (normal_read_valid or zero_balance_valid):
                blockers.append(f"P71_PRIVATE_ENDPOINT_INVALID:{name}")
            if not str((item or {}).get("response_sha256") or ""):
                blockers.append(f"P71_PRIVATE_ENDPOINT_HASH_MISSING:{name}")
    if data.get("actual_network_read_performed") is not True:
        blockers.append("P71_PRIVATE_ACTUAL_NETWORK_READ_NOT_PROVEN")
    if data.get("source_is_fixture") is not False:
        blockers.append("P71_PRIVATE_FIXTURE_NOT_REAL_EVIDENCE")
    for field in ("all_requests_get", "no_secret_scan_passed"):
        if data.get(field) is not True:
            blockers.append(f"P71_PRIVATE_{field.upper()}_NOT_TRUE")
    for field in ("write_call_performed", "order_endpoint_called", "signature_created", "stark_private_key_accessed", "credential_value_included"):
        if data.get(field) is not False:
            blockers.append(f"P71_PRIVATE_UNSAFE_FLAG:{field}")
    forbidden_fields = {"api_key", "api_secret", "private_key", "secret_value", "raw_response"}
    present = sorted(forbidden_fields.intersection(data))
    blockers.extend(f"P71_PRIVATE_FORBIDDEN_FIELD:{name}" for name in present)
    return {"valid": not blockers, "block_reasons": sorted(set(blockers)), "receipt": data}


def build_p71_complete_evidence(*, public_evidence: Mapping[str, Any], private_receipt: Mapping[str, Any]) -> dict[str, Any]:
    public = dict(public_evidence or {})
    private_validation = validate_p71_private_account_evidence(private_receipt)
    blockers: list[str] = []
    if public.get("public_rest_valid") is not True:
        blockers.append("P71_PUBLIC_REST_INVALID")
    if public.get("public_stream_valid") is not True:
        blockers.append("P71_PUBLIC_STREAM_INVALID")
    if public.get("no_secret_scan_passed") is not True:
        blockers.append("P71_PUBLIC_NO_SECRET_SCAN_INVALID")
    blockers.extend(private_validation["block_reasons"])
    complete = not blockers
    result = {
        "version": P71_VERSION,
        "venue": "extended_starknet_sepolia",
        "environment": "testnet",
        "market": "BTC-USD",
        "public_evidence_sha256": public.get("evidence_sha256"),
        "private_receipt_sha256": private_receipt.get("receipt_sha256"),
        "public_rest_valid": public.get("public_rest_valid") is True,
        "public_stream_valid": public.get("public_stream_valid") is True,
        "private_account_read_evidence_valid": private_validation["valid"],
        "p71_complete": complete,
        "status": "P71_EXTENDED_TESTNET_READ_ONLY_COMPLETE" if complete else "P71_EXTENDED_TESTNET_READ_ONLY_BLOCKED",
        "block_reasons": sorted(set(blockers)),
        "network_write_call_performed": False,
        "order_endpoint_called": False,
        "signature_created": False,
        "testnet_order_submission_allowed": False,
        "created_at_utc": utc_now_canonical(),
    }
    result["evidence_sha256"] = sha256_json(result)
    return result
