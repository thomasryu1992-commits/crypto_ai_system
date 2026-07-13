from __future__ import annotations

import argparse
import json
from typing import Any

from websockets.sync.client import connect


USER_AGENT = "X10PythonTradingClient/2.4.0"

PUBLIC_V1_URLS = (
    "wss://api.starknet.sepolia.extended.exchange/stream.extended.exchange/v1/orderbooks/BTC-USD?depth=1",
    "wss://starknet.sepolia.extended.exchange/stream.extended.exchange/v1/orderbooks/BTC-USD?depth=1",
)
PUBLIC_V2_RPC_URLS = (
    "wss://api.starknet.sepolia.extended.exchange/stream.extended.exchange/v2/rpc",
    "wss://starknet.sepolia.extended.exchange/stream.extended.exchange/v2/rpc",
)
PRIVATE_V1_URLS = (
    "wss://api.starknet.sepolia.extended.exchange/stream.extended.exchange/v1/account",
    "wss://starknet.sepolia.extended.exchange/stream.extended.exchange/v1/account",
)


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


def check_public_v1(url: str) -> dict[str, Any]:
    result: dict[str, Any] = {"mode": "public_v1_path", "host": _host(url), "ok": False}
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


def check_public_v2_rpc(url: str) -> dict[str, Any]:
    result: dict[str, Any] = {"mode": "public_v2_rpc", "host": _host(url), "ok": False}
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


def check_private_v1(url: str, api_key: str) -> dict[str, Any]:
    result: dict[str, Any] = {"mode": "private_v1_account", "host": _host(url), "ok": False}
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
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    results.extend(check_public_v1(url) for url in PUBLIC_V1_URLS)
    results.extend(check_public_v2_rpc(url) for url in PUBLIC_V2_RPC_URLS)

    if args.credential_target:
        from external_runtime_packages.extended_read_only_probe.windows_credential_provider import (
            read_generic_credential_secret,
        )

        api_key = read_generic_credential_secret(args.credential_target)
        results.extend(check_private_v1(url, api_key) for url in PRIVATE_V1_URLS)

    print(json.dumps({"redacted": True, "write_paths_used": False, "results": results}, indent=2, sort_keys=True))
    return 0 if any(item.get("ok") is True for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
