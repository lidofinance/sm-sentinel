import asyncio
from types import TracebackType

from web3 import AsyncWeb3


class ConnectOnDemand:
    """Share Web3 websocket connection lifecycle across short chain reads."""

    def __init__(self, w3: AsyncWeb3) -> None:
        self.w3 = w3
        self._lock = asyncio.Lock()
        self._connected_clients = 0

    async def __aenter__(self) -> AsyncWeb3:
        async with self._lock:
            self._connected_clients += 1
            if not await self.w3.provider.is_connected():
                await self.w3.provider.connect()
            return self.w3

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        async with self._lock:
            self._connected_clients -= 1
            if await self.w3.provider.is_connected() and self._connected_clients == 0:
                await self.w3.provider.disconnect()
