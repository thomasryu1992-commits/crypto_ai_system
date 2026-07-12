from __future__ import annotations

import asyncio

from x10.clients.streamrpc.streamrpc_client import StreamRpcClient
from x10.clients.streamrpc.subscription_params import OrderbooksParams
from x10.config import TESTNET_CONFIG


async def _main() -> None:
    received = asyncio.Event()
    holder: dict[str, str] = {}

    async def handler(message) -> None:
        holder["message"] = message.model_dump_json()
        received.set()

    async with StreamRpcClient(api_url=TESTNET_CONFIG.endpoints.stream_rpc_url) as client:
        await client.subscribe(params=OrderbooksParams(market="BTC-USD", depth="1"), handler=handler)
        await asyncio.wait_for(received.wait(), timeout=15)
        print(holder["message"])


if __name__ == "__main__":
    asyncio.run(_main())
