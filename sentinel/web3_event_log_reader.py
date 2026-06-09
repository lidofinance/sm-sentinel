import asyncio
import logging
from typing import Any

import web3.exceptions
from web3 import AsyncWeb3
from web3.types import FilterParams

from sentinel.models import Event
from sentinel.modules.base import EventSource
from sentinel.web3_events import decode_event, log_filter_for_source

logger = logging.getLogger(__name__)

GET_LOGS_RETRY_INITIAL_DELAY_SECONDS = 2.0
GET_LOGS_RETRY_MAX_DELAY_SECONDS = 60.0


class Web3EventLogReader:
    """Shared Web3 log reader for backfill streams and random-access history."""

    def __init__(
        self,
        w3: AsyncWeb3,
        *,
        event_sources: tuple[EventSource, ...] = (),
        abi_by_topics: dict | None = None,
        request_interval_seconds: float | None,
        stop_event: asyncio.Event | None = None,
        provider_connected_message: str = "Web3 event log reader provider connected",
    ) -> None:
        self._w3 = w3
        self._event_sources = event_sources
        self._abi_by_topics = abi_by_topics or {}
        self._request_interval_seconds = request_interval_seconds
        self._last_request_ts: float | None = None
        self._stop_event = stop_event
        self._provider_connected_message = provider_connected_message

    async def connected_w3(self) -> AsyncWeb3:
        if not await self._w3.provider.is_connected():
            await self._w3.provider.connect()
            logger.info(self._provider_connected_message)
        return self._w3

    async def fetch_events(
        self,
        *,
        start_block: int,
        end_block: int,
    ) -> list[Event] | None:
        w3 = await self.connected_w3()

        events: list[Event] = []
        for source in self._event_sources:
            filter_params = log_filter_for_source(source, self._abi_by_topics)
            if filter_params is None:
                continue
            filter_params["fromBlock"] = start_block
            filter_params["toBlock"] = end_block

            logs = await self.get_logs_with_retry(
                w3=w3,
                filter_params=filter_params,
                contract=source.address,
                batch_start=start_block,
                batch_end=end_block,
            )
            if logs is None:
                return None

            for log in logs:
                event_topic = log["topics"][0]
                event_abi = self._abi_by_topics.get(event_topic)
                if event_abi is None:
                    continue
                if source.event_names is not None and event_abi["name"] not in source.event_names:
                    continue
                event = decode_event(w3, event_abi, log)
                if source.predicate is not None and not source.predicate(event):
                    continue
                events.append(event)

        return sorted(
            events,
            key=lambda event: (event.block, event.transaction_index, event.log_index),
        )

    async def get_logs_with_retry(
        self,
        *,
        w3: AsyncWeb3,
        filter_params: FilterParams,
        contract: str,
        batch_start: int,
        batch_end: int,
    ) -> list[Any] | None:
        attempt = 1
        delay_seconds = GET_LOGS_RETRY_INITIAL_DELAY_SECONDS

        while True:
            if self._is_stopped():
                return None

            if await self.throttle():
                return None
            try:
                return await w3.eth.get_logs(filter_params)
            except web3.exceptions.Web3Exception as exc:
                if not is_retryable_get_logs_error(exc):
                    raise

                logger.warning(
                    "Rate-limited while fetching logs for %s blocks %s-%s (attempt %s). "
                    "Retrying in %.1fs. Error: %s",
                    contract,
                    batch_start,
                    batch_end,
                    attempt,
                    delay_seconds,
                    exc,
                )
                if await self._sleep(delay_seconds):
                    return None
                attempt += 1
                delay_seconds = min(
                    delay_seconds * 2,
                    GET_LOGS_RETRY_MAX_DELAY_SECONDS,
                )

    async def throttle(self) -> bool:
        if self._request_interval_seconds is None:
            return False
        loop = asyncio.get_running_loop()
        now = loop.time()
        if self._last_request_ts is not None:
            elapsed = now - self._last_request_ts
            sleep_for = self._request_interval_seconds - elapsed
            if sleep_for > 0:
                logger.debug("Throttling event log reader requests for %.3fs", sleep_for)
                if await self._sleep(sleep_for):
                    return True
                now = loop.time()
        self._last_request_ts = now
        return False

    def _is_stopped(self) -> bool:
        return self._stop_event is not None and self._stop_event.is_set()

    async def _sleep(self, delay_seconds: float) -> bool:
        if self._stop_event is None:
            await asyncio.sleep(delay_seconds)
            return False
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay_seconds)
        except TimeoutError:
            return False
        return True


def is_retryable_get_logs_error(exc: web3.exceptions.Web3Exception) -> bool:
    if not isinstance(exc, web3.exceptions.Web3RPCError):
        return False

    code: int | None = None
    message = str(exc).lower()

    rpc_error = exc.rpc_response.get("error") if isinstance(exc.rpc_response, dict) else None
    if isinstance(rpc_error, dict):
        maybe_code = rpc_error.get("code")
        if isinstance(maybe_code, int):
            code = maybe_code
        rpc_message = rpc_error.get("message")
        if isinstance(rpc_message, str):
            message = f"{message} {rpc_message.lower()}"

    if code in {429, -32005}:
        return True

    return any(
        marker in message
        for marker in (
            "429",
            "rate limit",
            "too many requests",
            "throughput",
            "compute units per second",
        )
    )
