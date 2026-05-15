import asyncio
import logging
import os

import signal
from asyncio import BaseEventLoop
from typing import Any, cast

import web3.exceptions
from web3 import AsyncWeb3, WebSocketProvider
from eth_utils import event_abi_to_log_topic, get_all_event_abis
from web3.utils.subscriptions import (
    LogsSubscription,
    LogsSubscriptionContext,
)
from web3._utils.events import get_event_data
from web3.types import EventData, FilterParams
from websockets import ConnectionClosed

from sentinel.app.contracts import ContractABIs
from sentinel.app.health import HealthState
from sentinel.config import Config, get_config
from sentinel.models import (
    Event,
    Block,
)
from sentinel.modules.base import EventSource, ModuleAdapter

logger = logging.getLogger(__name__)
logging.getLogger("web3.providers.persistent.subscription_manager").setLevel(logging.WARNING)

BACKFILL_GET_LOGS_RETRY_INITIAL_DELAY_SECONDS = 2.0
BACKFILL_GET_LOGS_RETRY_MAX_DELAY_SECONDS = 60.0


def topics_to_follow(event_names: set[str], *abis) -> dict:
    topics = {}
    for event in [event for abi in abis for event in get_all_event_abis(abi)]:
        if event["name"] not in event_names:
            continue

        topic = event_abi_to_log_topic(event)
        existing = topics.get(topic)
        if existing is not None:
            if _event_decoder_shape(existing) != _event_decoder_shape(event):
                raise RuntimeError(
                    f"Event topic collision for {event['name']} with incompatible ABI inputs"
                )
            continue

        topics[topic] = event
    return topics


def _event_decoder_shape(event_abi: Any) -> tuple[str, tuple[tuple[str, bool], ...]]:
    return (
        event_abi["name"],
        tuple((item["type"], bool(item.get("indexed"))) for item in event_abi.get("inputs", [])),
    )


class Subscription:
    def __init__(
        self,
        w3: AsyncWeb3,
        *,
        health: HealthState,
        module_adapter: ModuleAdapter,
        backfill_w3: AsyncWeb3 | None = None,
    ):
        super().__init__()
        self._shutdown_event = asyncio.Event()
        self._subscriptions_started = asyncio.Event()
        self._w3 = w3
        self._backfill_w3 = backfill_w3 or w3
        self.cfg: Config = get_config()
        self.reconfigure_module_adapter(module_adapter)
        self._health = health
        rps_limit = self.cfg.process_blocks_requests_per_second
        self._process_blocks_request_interval = (1 / rps_limit) if rps_limit else None
        self._last_process_blocks_request_ts: float | None = None

    def reconfigure_module_adapter(self, module_adapter: ModuleAdapter) -> None:
        self.module_adapter = module_adapter
        self.update_event_bindings(
            module_adapter.contract_abis,
            notifiable_events=module_adapter.notifiable_events(),
            side_effect_events=module_adapter.side_effect_events(),
            event_sources=module_adapter.event_sources(),
            topic_abis=module_adapter.topic_abis(),
        )

    def update_event_bindings(
        self,
        contract_abis: ContractABIs,
        *,
        notifiable_events: set[str],
        side_effect_events: set[str],
        event_sources: tuple[EventSource, ...],
        topic_abis: tuple[list[dict], ...],
    ) -> None:
        self.contract_abis = contract_abis
        self.notifiable_events = notifiable_events
        self.event_sources = event_sources
        self.abi_by_topics = topics_to_follow(
            self.notifiable_events | side_effect_events, *topic_abis
        )

    def start_catchup(self, until_block: int) -> None:
        """Hook for subclasses to prepare for catch-up/backfill mode.

        The base implementation is a no-op.
        """

        _ = until_block

    def finish_catchup(self) -> None:
        """Hook for subclasses to finish catch-up/backfill mode.

        The base implementation is a no-op.
        """

    async def wait_until_subscribed(self, *, timeout: float = 10.0) -> None:
        """Wait until subscriptions are established (or raise on timeout)."""

        await asyncio.wait_for(self._subscriptions_started.wait(), timeout=timeout)

    async def get_block_number(self) -> int:
        """Return the latest block number from the persistent provider.

        Uses the main (subscription) provider rather than the backfill provider
        to avoid contention when backfill is running concurrently.
        """

        async for w3 in self.w3:
            return await w3.eth.get_block_number()
        raise RuntimeError("Web3 provider generator ended before returning a block number")

    @property
    async def w3(self):
        if not await self._w3.provider.is_connected():
            await self._w3.provider.connect()
            logger.info("Web3 provider connected")
        yield self._w3

    @property
    async def backfill_w3(self):
        if not await self._backfill_w3.provider.is_connected():
            await self._backfill_w3.provider.connect()
            logger.info("Web3 backfill provider connected")
        yield self._backfill_w3

    def setup_signal_handlers(self, loop):
        loop.add_signal_handler(signal.SIGINT, self._signal_handler, loop)
        loop.add_signal_handler(signal.SIGTERM, self._signal_handler, loop)

    def _signal_handler(self, loop: BaseEventLoop):
        async def _safe_unsubscribe_all():
            try:
                await self._w3.subscription_manager.unsubscribe_all()
            except ConnectionClosed:
                pass

        logger.info("Signal received, shutting down...")
        loop.create_task(_safe_unsubscribe_all())
        self._shutdown_event.set()
        self._health.mark_subscription_inactive()

    @staticmethod
    def reconnect(func):
        async def wrapper(self, *args, **kwargs):
            while True:
                try:
                    return await func(self, *args, **kwargs)
                except ConnectionClosed:
                    self._health.mark_subscription_inactive()
                    if self._shutdown_event.is_set():
                        break
                    logger.info("Web3 provider disconnected, reconnecting...")

        return wrapper

    async def shutdown(self):
        await self._shutdown_event.wait()

    def request_shutdown(self) -> None:
        """Trigger shutdown (e.g., from a supervising task)."""

        self._shutdown_event.set()

    def _decode_event(self, w3: AsyncWeb3, event_abi: dict, log: dict[str, Any]) -> Event:
        event_data: EventData = get_event_data(w3.codec, event_abi, log)
        return Event(
            event=event_data["event"],
            args=event_data["args"],
            block=event_data["blockNumber"],
            tx=event_data["transactionHash"],
            address=event_data["address"],
        )

    def _topic_filter_for_events(self, event_names: set[str]) -> list[Any]:
        topics = [
            topic
            for topic, event_abi in self.abi_by_topics.items()
            if event_abi["name"] in event_names
        ]
        if not topics:
            raise RuntimeError(f"No ABI topics configured for events: {sorted(event_names)}")
        if len(topics) == 1:
            return topics
        return [topics]

    @reconnect
    async def subscribe(self):
        if self._shutdown_event.is_set():
            return
        async for w3 in self.w3:
            await w3.subscription_manager.subscribe(self._build_log_subscriptions())
            logger.info("Subscriptions started")
            self._subscriptions_started.set()
            self._health.mark_subscription_active()

            await w3.subscription_manager.handle_subscriptions()

            if self._shutdown_event.is_set():
                break

    async def process_blocks_from(self, start_block: int, end_block: int | None = None):
        w3 = await anext(self.backfill_w3)
        end_block = end_block or await w3.eth.get_block_number()
        if start_block >= end_block:
            logger.info("No blocks to process")
            logger.info("Backfill complete at block %s", end_block)
            return
        logger.info("Processing blocks from %s to %s", start_block, end_block)
        batch_size = self.cfg.block_batch_size
        for batch_start in range(start_block, end_block + 1, batch_size):
            batch_end = min(batch_start + batch_size - 1, end_block)
            logger.info(
                "Fetching logs for blocks %s-%s across %s sources",
                batch_start,
                batch_end,
                len(self.event_sources),
            )

            for source in self.event_sources:
                logger.debug(
                    "Fetching logs for %s %s blocks %s-%s",
                    source.name,
                    source.address,
                    batch_start,
                    batch_end,
                )
                filter_params = FilterParams(
                    fromBlock=batch_start,
                    toBlock=batch_end,
                    address=source.address,
                )
                if source.event_names is not None:
                    filter_params["topics"] = self._topic_filter_for_events(set(source.event_names))
                try:
                    logs = await self._get_logs_with_retry(
                        w3=w3,
                        filter_params=filter_params,
                        contract=source.address,
                        batch_start=batch_start,
                        batch_end=batch_end,
                    )
                    if logs is None:
                        break
                except web3.exceptions.Web3Exception as e:
                    logger.error("Error fetching logs: %s", e)
                    self._shutdown_event.set()
                    break
                for log in logs:
                    event_topic = log["topics"][0]
                    event_abi = self.abi_by_topics.get(event_topic)
                    if not event_abi:
                        continue
                    event = self._decode_event(w3, event_abi, log)
                    if source.predicate is not None and not source.predicate(event):
                        continue
                    await self.process_event_log(event)
                    await asyncio.sleep(0)
            if self._shutdown_event.is_set():
                break
            await self.process_new_block(Block(number=batch_end))
            self._health.mark_progress()
            logger.debug("Processed blocks up to %s", batch_end)
        if self._shutdown_event.is_set():
            logger.warning("Backfill interrupted before reaching block %s", end_block)
            return
        logger.info("Backfill complete at block %s", end_block)

    @staticmethod
    def _is_retryable_get_logs_error(exc: web3.exceptions.Web3Exception) -> bool:
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

    async def _get_logs_with_retry(
        self,
        *,
        w3: AsyncWeb3,
        filter_params: FilterParams,
        contract: str,
        batch_start: int,
        batch_end: int,
    ) -> list[Any] | None:
        attempt = 1
        delay_seconds = BACKFILL_GET_LOGS_RETRY_INITIAL_DELAY_SECONDS

        while True:
            if self._shutdown_event.is_set():
                return None

            await self._throttle_process_blocks_request()
            try:
                return await w3.eth.get_logs(filter_params)
            except web3.exceptions.Web3Exception as exc:
                if not self._is_retryable_get_logs_error(exc):
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
                await asyncio.sleep(delay_seconds)
                attempt += 1
                delay_seconds = min(
                    delay_seconds * 2,
                    BACKFILL_GET_LOGS_RETRY_MAX_DELAY_SECONDS,
                )

    async def _throttle_process_blocks_request(self):
        if self._process_blocks_request_interval is None:
            return
        loop = asyncio.get_running_loop()
        now = loop.time()
        if self._last_process_blocks_request_ts is not None:
            elapsed = now - self._last_process_blocks_request_ts
            sleep_for = self._process_blocks_request_interval - elapsed
            if sleep_for > 0:
                logger.debug("Throttling process_blocks_from requests for %.3fs", sleep_for)
                await asyncio.sleep(sleep_for)
                now = loop.time()
        self._last_process_blocks_request_ts = now

    async def _handle_event_log_subscription(self, context: LogsSubscriptionContext):
        # web3 stubs type `context.result` too broadly; treat as a log receipt-like mapping.
        result = cast(dict[str, Any], context.result)
        event_topic = result["topics"][0]
        event_abi = self.abi_by_topics.get(event_topic)
        if not event_abi:
            return
        event = self._decode_event(self._w3, event_abi, result)
        if hasattr(context, "predicate") and not context.predicate(event):
            return
        self._health.mark_progress()
        await self.process_event_log_from_subscription(event)

    def _build_log_subscriptions(self) -> list[LogsSubscription]:
        subscriptions = []
        for source in self.event_sources:
            handler_context = {}
            if source.predicate is not None:
                handler_context["predicate"] = source.predicate

            kwargs: dict[str, Any] = {
                "address": source.address,
                "handler": self._handle_event_log_subscription,
            }
            if source.event_names is not None:
                kwargs["topics"] = self._topic_filter_for_events(set(source.event_names))
            if handler_context:
                kwargs["handler_context"] = handler_context

            subscriptions.append(LogsSubscription(**kwargs))
        return subscriptions

    async def process_event_log(self, event: Event):
        raise NotImplementedError

    async def process_new_block(self, block: Block):
        raise NotImplementedError

    async def process_event_log_from_subscription(self, event: Event):
        """Handle a log event received via the live subscription."""

        await self.process_event_log(event)


class TerminalSubscription(Subscription):
    async def process_event_log(self, event: Event):
        logger.warning("Event %s emitted with data: %s", event.event, event.args)

    async def process_new_block(self, block):
        logger.warning("Current block number: %s", block.number)


if __name__ == "__main__":
    from sentinel.app.module_adapter import build_module_adapter_from_config
    from sentinel.chain import ConnectOnDemand

    cfg = get_config()
    provider = AsyncWeb3(WebSocketProvider(os.getenv("WEB3_SOCKET_PROVIDER")))
    module_adapter = build_module_adapter_from_config(cfg, provider, ConnectOnDemand(provider))

    asyncio.run(
        TerminalSubscription(
            provider,
            health=HealthState(),
            module_adapter=module_adapter,
        ).subscribe()
    )
