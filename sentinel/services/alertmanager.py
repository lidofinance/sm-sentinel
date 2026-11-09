"""A durable, per-chat outbox for external operator notifications."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from sqlalchemy.exc import SQLAlchemyError

from telegram.error import ChatMigrated, TelegramError

from sentinel.alertmanager import OperatorAlert
from sentinel.app.chat_migration import ChatMigrationService
from sentinel.app.database import SentinelDatabase
from sentinel.app import alertmanager_storage
from sentinel.app.alertmanager_storage import AlertmanagerOutbox
from sentinel.metrics.alertmanager import AlertmanagerMetrics
from sentinel.modules.base import BaseModuleAdapter

logger = logging.getLogger(__name__)
METRICS_RETRY_SECONDS = 5


class AlertmanagerBatchTooLarge(ValueError):
    """The batch cannot fit even in an empty delivery queue."""


class AlertmanagerScopeUnavailable(RuntimeError):
    """The runtime cannot yet determine which module may receive alerts."""


class AlertmanagerScopeMismatch(ValueError):
    """An alert targets a different chain or staking module."""


class AlertmanagerDeliveryService:
    def __init__(
        self,
        *,
        database: SentinelDatabase,
        chat_migrations: ChatMigrationService,
        chain_id: int,
        module_adapter: BaseModuleAdapter,
        metrics: AlertmanagerMetrics,
        source_ids: frozenset[str],
        resolve_chats: Callable[[str], set[int]],
        send_message: Callable[[int, str], Awaitable[None]],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._database = database
        self._chat_migrations = chat_migrations
        self._chain_id = chain_id
        self._module_adapter = module_adapter
        self._metrics = metrics
        self._metric_sources = set(source_ids)
        self._source_ids = source_ids
        self._resolve_chats = resolve_chats
        self._send_message = send_message
        self._clock = clock
        self._wake = asyncio.Event()
        self._metrics_lock = asyncio.Lock()
        self._metrics_retry_at: float | None = None

    async def refresh_queue_metrics(self) -> None:
        async with self._metrics_lock:
            try:
                async with self._database.session() as session:
                    rows = await AlertmanagerOutbox(session).queue_state()
            except SQLAlchemyError:
                self._metrics_retry_at = time.monotonic() + METRICS_RETRY_SECONDS
                logger.warning("Unable to refresh Alertmanager queue metrics", exc_info=True)
                return
            state = {source: (count, oldest) for source, count, oldest in rows}
            self._metric_sources.update(state)
            for source_id in self._metric_sources:
                count, oldest = state.get(source_id, (0, None))
                self._metrics.update_queue(source_id, count, oldest)
            self._metrics_retry_at = None

    async def submit(self, source_id: str, digest: str, alerts: tuple[OperatorAlert, ...]) -> bool:
        """Accept a batch from a source already identified by the HTTP authenticator."""
        async with self._chat_migrations.state_lock:
            return await self._submit(source_id, digest, alerts)

    async def _submit(self, source_id: str, digest: str, alerts: tuple[OperatorAlert, ...]) -> bool:
        staking_module_id = self._module_adapter.staking_module_id
        if staking_module_id is None:
            raise AlertmanagerScopeUnavailable("Staking module ID is unavailable")
        # Validate the entire batch before deduplicating or resolving recipients.
        for index, alert in enumerate(alerts):
            if alert.chain_id != self._chain_id:
                raise AlertmanagerScopeMismatch(
                    f"alerts[{index}].labels.chain_id does not match this instance"
                )
            if alert.staking_module_id != staking_module_id:
                raise AlertmanagerScopeMismatch(
                    f"alerts[{index}].labels.staking_module_id does not match this instance"
                )
        now = self._clock()
        async with self._database.transaction() as session:
            outbox = AlertmanagerOutbox(session)
            # A retry acknowledges the original recipients, even if subscriptions have since changed.
            if await outbox.has_receipt(source_id, digest, now=now):
                return False
            deliveries: list[tuple[str, int, str]] = []
            for alert in alerts:
                messages = alert.messages(source_id=source_id)
                for chat_id in sorted(self._resolve_chats(alert.node_operator_id)):
                    deliveries.extend(
                        (alert.node_operator_id, chat_id, message) for message in messages
                    )
                    if len(deliveries) > min(
                        alertmanager_storage.MAX_PENDING_DELIVERIES,
                        alertmanager_storage.MAX_PENDING_PER_SOURCE,
                    ):
                        raise AlertmanagerBatchTooLarge(
                            "Batch exceeds the delivery limit after subscriber fan-out and text "
                            "splitting; reduce the alert group size or annotation length"
                        )
            await outbox.enqueue_new(source_id, digest, deliveries, now=now)
        await self.refresh_queue_metrics()
        self._wake.set()
        return True

    async def run(self) -> None:
        while True:
            self._wake.clear()
            if self._metrics_retry_at is not None and time.monotonic() >= self._metrics_retry_at:
                await self.refresh_queue_metrics()
            if not await self.deliver_one():
                timeout = (
                    None
                    if self._metrics_retry_at is None
                    else max(0.0, self._metrics_retry_at - time.monotonic())
                )
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=timeout)
                except TimeoutError:
                    pass

    async def deliver_one(self) -> bool:
        async with self._chat_migrations.state_lock:
            async with self._database.session() as session:
                delivery = await AlertmanagerOutbox(session).next_pending(
                    source_ids=self._source_ids
                )
            if delivery is None:
                return False
            # Respect unsubscribe and removed chats even for notifications queued before a restart.
            if delivery.chat_id not in self._resolve_chats(delivery.node_operator_id):
                async with self._database.transaction() as session:
                    await AlertmanagerOutbox(session).complete(delivery)
                self._metrics.deliveries.labels(
                    source_id=delivery.source_id, outcome="unsubscribed"
                ).inc()
                await self.refresh_queue_metrics()
                return True
        try:
            await self._send_message(delivery.chat_id, delivery.message)
        except ChatMigrated as exc:
            await self._chat_migrations.migrate(delivery.chat_id, exc.new_chat_id)
            outcome = "migrated"
        except TelegramError as exc:
            # PTB owns retries; a final error must not start another retry cycle here.
            logger.warning(
                "Alertmanager notification delivery failed",
                extra={
                    "source_id": delivery.source_id,
                    "chat_id": delivery.chat_id,
                    "error_type": type(exc).__name__,
                },
            )
            async with self._database.transaction() as session:
                await AlertmanagerOutbox(session).complete(delivery)
            outcome = "failed"
        else:
            async with self._database.transaction() as session:
                await AlertmanagerOutbox(session).complete(delivery)
            outcome = "sent"
        self._metrics.deliveries.labels(source_id=delivery.source_id, outcome=outcome).inc()
        await self.refresh_queue_metrics()
        return True
