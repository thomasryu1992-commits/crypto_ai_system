from __future__ import annotations

import asyncio

from x10.clients.stream.stream_client import StreamClient
from x10.config import TESTNET_CONFIG


async def _main() -> None:
    client = StreamClient(api_url=TESTNET_CONFIG.endpoints.stream_url, close_timeout=2)
    async with client.subscribe_to_orderbooks("BTC-USD", depth=1) as stream:
        message = await asyncio.wait_for(stream.recv(), timeout=15)
        print(message.model_dump_json())


if __name__ == "__main__":
    asyncio.run(_main())
