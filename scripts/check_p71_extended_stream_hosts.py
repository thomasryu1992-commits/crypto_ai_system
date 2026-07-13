from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_ai_system.execution.extended_read_only_connectivity import (  # noqa: E402
    EXTENDED_STREAM_URL_OVERRIDE_ENV,
    PUBLIC_ORDERBOOK_STREAM_PATH,
    resolve_extended_stream_endpoints,
)


USER_AGENT = "X10PythonTradingClient/2.4.0"

PUBLIC_V2_RPC_PATH = "/stream.extended.exchange/v2/rpc"
PRIVATE_ACCOUNT_STREAM_PATH = "/account"


def _error_summary(exc: Exception) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    return {
        "ok": False,
        "error_type": type(exc).__name__,
        "http_status": getattr(response, "status_code", None)
        or getattr(response, "status", None)
        or getattr(exc, "status_code", None),
        "error": str(exc)[:220],
    }


def _host(url: str) -> str:
    return url.split("/")[2]


def _v2_rpc_url(v1_base_url: str) -> str:
    parsed = urlparse(v1_base_url)
    return f"{parsed.scheme}://{parsed.netloc}{PUBLIC_V2_RPC_PATH}"


def _base_record(mode: str, url: str, source: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "source": source,
        "host": _host(url),
        "url_sha256": __import__("hashlib").sha256(url.encode("utf-8")).hexdigest(),
        "ok": False,
    }


def check_public_v1(url: str, source: str) -> dict[str, Any]:
    result: dict[str, Any] = _base_record("public_v1_path", url, source)
    try:
        with connect(url, user_agent_header=USER_AGENT, open_timeout=15, close_timeout=2) as ws:
            payload = json.loads(ws.recv(timeout=10))
            data = payload.get("data") if isinstance(payload, dict) else {}
            if not isinstance(data, dict):
                data = {}
            result.update(
                {
                    "ok": True,
                    "message_type": payload.get("type"),
                    "seq": payload.get("seq"),
                    "market": data.get("m"),
                    "has_best_bid": bool(data.get("b")),
                    "has_best_ask": bool(data.get("a")),
                }
            )
    except Exception as exc:
        result.update(_error_summary(exc))
    return result


def check_public_v2_rpc(url: str, source: str) -> dict[str, Any]:
    result: dict[str, Any] = _base_record("public_v2_rpc", url, source)
    try:
        with connect(url, user_agent_header=USER_AGENT, open_timeout=15, close_timeout=2) as ws:
            ws.send(
                json.dumps(
                    {
                        "method": "subscribe",
                        "id": 1,
                        "jsonrpc": "2.0",
                        "params": {
                            "scope": "orderbooks",
                            "selector": {"market": "BTC-USD", "depth": "1", "rfqOnly": False},
                        },
                    }
                )
            )
            ack = json.loads(ws.recv(timeout=10))
            payload = json.loads(ws.recv(timeout=10))
            data = payload.get("data") if isinstance(payload, dict) else {}
            if not isinstance(data, dict):
                data = {}
            result.update(
                {
                    "ok": True,
                    "ack_keys": sorted(ack.keys()) if isinstance(ack, dict) else [],
                    "message_type": payload.get("type"),
                    "seq": payload.get("seq"),
                    "subscription": payload.get("subscription"),
                    "market": data.get("m") or data.get("market"),
                    "has_best_bid": bool(data.get("b")),
                    "has_best_ask": bool(data.get("a")),
                }
            )
    except Exception as exc:
        result.update(_error_summary(exc))
    return result


async def _check_public_official_sdk_orderbook_async() -> dict[str, Any]:
    try:
        from x10.clients.stream.stream_client import StreamClient
        from x10.config import TESTNET_CONFIG
    except Exception as exc:
        return {
            "mode": "public_official_sdk_orderbook",
            "host": None,
            "ok": False,
            "sdk_imported": False,
            **_error_summary(exc),
        }

    stream_url = str(TESTNET_CONFIG.endpoints.stream_url)
    result: dict[str, Any] = {
        "mode": "public_official_sdk_orderbook",
        "host": _host(stream_url),
        "ok": False,
        "sdk_imported": True,
        "sdk_stream_url": stream_url,
    }
    try:
        client = StreamClient(api_url=stream_url, close_timeout=2)
        async with client.subscribe_to_orderbooks("BTC-USD", depth=1) as stream:
            message = await asyncio.wait_for(stream.recv(), timeout=15)
            payload = message.model_dump() if hasattr(message, "model_dump") else dict(message)
            data = payload.get("data") if isinstance(payload, dict) else {}
            if not isinstance(data, dict):
                data = {}
            result.update(
                {
                    "ok": True,
                    "message_type": payload.get("type"),
                    "seq": payload.get("seq"),
                    "market": data.get("m") or data.get("market"),
                    "has_best_bid": bool(data.get("b")),
                    "has_best_ask": bool(data.get("a")),
                }
            )
    except Exception as exc:
        result.update(_error_summary(exc))
    return result


def check_public_official_sdk_orderbook() -> dict[str, Any]:
    return asyncio.run(_check_public_official_sdk_orderbook_async())


def check_private_v1(url: str, api_key: str) -> dict[str, Any]:
    result: dict[str, Any] = _base_record("private_v1_account", url, "resolved_v1_candidate")
    try:
        with connect(
            url,
            additional_headers={"X-Api-Key": api_key},
            user_agent_header=USER_AGENT,
            open_timeout=15,
            close_timeout=2,
        ) as ws:
            payload = json.loads(ws.recv(timeout=10))
            data = payload.get("data") if isinstance(payload, dict) else {}
            if not isinstance(data, dict):
                data = {}
            result.update(
                {
                    "ok": True,
                    "message_type": payload.get("type"),
                    "seq": payload.get("seq"),
                    "has_balance": "balance" in data,
                    "has_positions": "positions" in data,
                    "has_orders": "orders" in data,
                    "has_spot_balances": "spotBalances" in data,
                }
            )
    except Exception as exc:
        result.update(_error_summary(exc))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Check P71 Extended testnet WebSocket host/path candidates.")
    parser.add_argument("--credential-target", help="Optional Windows Credential Manager target for private stream checks.")
    parser.add_argument(
        "--stream-url-override",
        help=f"Optional wss:// Extended Starknet Sepolia stream base URL override. Also honors {EXTENDED_STREAM_URL_OVERRIDE_ENV}.",
    )
    args = parser.parse_args()

    endpoints = resolve_extended_stream_endpoints(override_base_url=args.stream_url_override)
    results: list[dict[str, Any]] = []
    for endpoint in endpoints:
        results.append(check_public_v1(endpoint.with_path(PUBLIC_ORDERBOOK_STREAM_PATH), endpoint.source))
    for endpoint in endpoints:
        results.append(check_public_v2_rpc(_v2_rpc_url(endpoint.base_url), endpoint.source))
    results.append(check_public_official_sdk_orderbook())

    if args.credential_target:
        from external_runtime_packages.extended_read_only_probe.windows_credential_provider import (
            read_generic_credential_secret,
        )

        api_key = read_generic_credential_secret(args.credential_target)
        for endpoint in endpoints:
            item = check_private_v1(endpoint.with_path(PRIVATE_ACCOUNT_STREAM_PATH), api_key)
            item["source"] = endpoint.source
            results.append(item)

    print(json.dumps({"redacted": True, "write_paths_used": False, "results": results}, indent=2, sort_keys=True))
    return 0 if any(item.get("ok") is True for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
