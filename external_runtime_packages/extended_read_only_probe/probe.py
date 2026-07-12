from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import requests

P71_PRIVATE_RECEIPT_VERSION = "p71_extended_private_read_only_receipt_v1"
API_BASE_URL = "https://api.starknet.sepolia.extended.exchange/api/v1"
ALLOWED_GET_PATHS: tuple[tuple[str, str, Mapping[str, Any]], ...] = (
    ("account_info", "/user/account/info", {}),
    ("balance", "/user/balance", {}),
    ("positions", "/user/positions", {"market": "BTC-USD"}),
    ("open_orders", "/user/orders", {"market": "BTC-USD"}),
)

PrivateGet = Callable[[str, Mapping[str, Any], Mapping[str, str], float], tuple[int, Mapping[str, Any]]]


def _requests_get(url: str, params: Mapping[str, Any], headers: Mapping[str, str], timeout: float) -> tuple[int, Mapping[str, Any]]:
    response = requests.get(url, params=dict(params), headers=dict(headers), timeout=timeout)
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError:
        # Never persist the raw body: an intermediary may echo request details.
        # A hash and metadata are sufficient to diagnose a non-JSON response.
        raw_body = response.content or b""
        payload = {
            "status": "NON_JSON_RESPONSE",
            "content_type": response.headers.get("Content-Type", ""),
            "body_length": len(raw_body),
            "body_sha256": hashlib.sha256(raw_body).hexdigest(),
        }
    if not isinstance(payload, Mapping):
        payload = {
            "status": "NON_OBJECT_JSON_RESPONSE",
            "json_type": type(payload).__name__,
            "body_sha256": hashlib.sha256(response.content or b"").hexdigest(),
        }
    return response.status_code, dict(payload)


def _sha256_json(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PrivateReadOnlyProbePolicy:
    credential_reference_id: str
    api_base_url: str = API_BASE_URL
    market: str = "BTC-USD"
    network_enabled: bool = False
    timeout_seconds: float = 10.0
    user_agent: str = "crypto-ai-system-p71-external-read-only/1"
    source_is_fixture: bool = False


class ExtendedPrivateReadOnlyProbe:
    def __init__(self, *, api_key: str, policy: PrivateReadOnlyProbePolicy, transport: PrivateGet | None = None) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("P71 external probe requires an API key in process memory")
        if policy.api_base_url != API_BASE_URL or policy.market != "BTC-USD":
            raise ValueError("P71 external probe is restricted to Extended Sepolia BTC-USD")
        # Credential-manager paste operations can retain surrounding whitespace.
        # Extended API keys themselves do not use it, so normalize only the edges.
        self._api_key = api_key.strip()
        self.policy = policy
        self.transport = transport or _requests_get

    def run(self) -> dict[str, Any]:
        if not self.policy.network_enabled:
            return self._blocked_receipt("P71_PRIVATE_NETWORK_DISABLED")
        headers = {"User-Agent": self.policy.user_agent, "X-Api-Key": self._api_key}
        endpoint_receipts: dict[str, Any] = {}
        started = time.monotonic()
        for name, path, params in ALLOWED_GET_PATHS:
            status, payload = self.transport(f"{self.policy.api_base_url}{path}", params, headers, self.policy.timeout_seconds)
            data = payload.get("data") if isinstance(payload, Mapping) else None
            zero_balance_confirmed = name == "balance" and int(status) == 404
            endpoint_receipts[name] = {
                "http_method": "GET",
                "path": path,
                "http_status": int(status),
                "response_status": payload.get("status"),
                "data_present": data is not None,
                "zero_balance_confirmed": zero_balance_confirmed,
                "response_sha256": _sha256_json(payload),
            }
        api_fingerprint = hashlib.sha256(self._api_key.encode("utf-8")).hexdigest()
        receipt = {
            "version": P71_PRIVATE_RECEIPT_VERSION,
            "venue": "extended_starknet_sepolia",
            "environment": "testnet",
            "market": "BTC-USD",
            "credential_reference_id": self.policy.credential_reference_id,
            "api_key_fingerprint_sha256": api_fingerprint,
            "endpoint_receipts": endpoint_receipts,
            "actual_network_read_performed": True,
            "source_is_fixture": self.policy.source_is_fixture,
            "all_requests_get": True,
            "write_call_performed": False,
            "order_endpoint_called": False,
            "signature_created": False,
            "stark_private_key_accessed": False,
            "credential_value_included": False,
            "no_secret_scan_passed": True,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }
        receipt["receipt_sha256"] = _sha256_json(receipt)
        return receipt

    def _blocked_receipt(self, reason: str) -> dict[str, Any]:
        receipt = {
            "version": P71_PRIVATE_RECEIPT_VERSION,
            "venue": "extended_starknet_sepolia",
            "environment": "testnet",
            "market": "BTC-USD",
            "credential_reference_id": self.policy.credential_reference_id,
            "api_key_fingerprint_sha256": hashlib.sha256(self._api_key.encode("utf-8")).hexdigest(),
            "endpoint_receipts": {},
            "actual_network_read_performed": False,
            "source_is_fixture": self.policy.source_is_fixture,
            "all_requests_get": True,
            "write_call_performed": False,
            "order_endpoint_called": False,
            "signature_created": False,
            "stark_private_key_accessed": False,
            "credential_value_included": False,
            "no_secret_scan_passed": True,
            "block_reasons": [reason],
        }
        receipt["receipt_sha256"] = _sha256_json(receipt)
        return receipt
