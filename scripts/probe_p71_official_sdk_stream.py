from __future__ import annotations

import asyncio
import json
import sys

from x10.clients.stream.stream_client import StreamClient
from x10.config import TESTNET_CONFIG


def _error_summary(exc: Exception) -> dict[str, object]:
    response = getattr(exc, "response", None)
    return {
        "ok": False,
        "error_type": type(exc).__name__,
        "http_status": getattr(response, "status_code", None)
        or getattr(response, "status", None)
        or getattr(exc, "status_code", None),
        "error": str(exc)[:220],
    }


async def _main() -> int:
    stream_url = str(TESTNET_CONFIG.endpoints.stream_url)
    result: dict[str, object] = {
        "redacted": True,
        "write_paths_used": False,
        "mode": "public_official_sdk_orderbook",
        "sdk_stream_url": stream_url,
        "ok": False,
    }
    try:
        client = StreamClient(api_url=stream_url, close_timeout=2)
        async with client.subscribe_to_orderbooks("BTC-USD", depth=1) as stream:
            message = await asyncio.wait_for(stream.recv(), timeout=15)
            result.update({"ok": True, "message": message.model_dump(mode="json")})
    except Exception as exc:
        result.update(_error_summary(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
