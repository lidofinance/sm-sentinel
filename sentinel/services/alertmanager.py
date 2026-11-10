"""A durable, per-chat outbox for external operator notifications."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from telegram.error import ChatMigrated, TelegramError

from sentinel.alertmanager import OperatorAlert
from sentinel.app.chat_migration import ChatMigrationConflict, ChatMigrationService
from sentinel.app.database import SentinelDatabase
from sentinel.app import alertmanager_storage
from sentinel.app.alertmanager_storage import AlertmanagerOutbox, PendingAlertDelivery
from sentinel.metrics.alertmanager import AlertmanagerMetrics
from sentinel.modules.base import BaseModuleAdapter

logger = logging.getLogger(__name__)
METRICS_REFRESH_SECONDS = 5
WORKER_RETRY_INITIAL_SECONDS = 1.0
WORKER_RETRY_MAX_SECONDS = 60.0


class AlertmanagerBatchTooLarge(ValueError):
    """The batch cannot fit even in an empty delivery queue."""


class AlertmanagerScopeUnavailable(RuntimeError):
    """The runtime cannot yet determine which module may receive alerts."""


class AlertmanagerScopeMismatch(ValueError):
    """An alert targets a different chain or staking module."""


@dataclass(frozen=True, slots=True)
class AlertmanagerSubmission:
    """Outcome of an authenticated batch. Zero queued messages means no subscribed chats."""

    accepted: bool
    queued_messages: int = 0


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
        self._metrics_refresh_at: float | None = None

    async def refresh_queue_metrics(self) -> None:
        async with self._metrics_lock:
            # Changes committed after this point schedule another refresh.
            self._metrics_refresh_at = None
            try:
                async with self._database.session() as session:
                    rows = await AlertmanagerOutbox(session).queue_state()
            except SQLAlchemyError:
                self._schedule_metrics_refresh()
                logger.warning("Unable to refresh Alertmanager queue metrics", exc_info=True)
                return
            state = {source: (count, oldest) for source, count, oldest in rows}
            self._metric_sources.update(state)
            for source_id in self._metric_sources:
                count, oldest = state.get(source_id, (0, None))
                self._metrics.update_queue(source_id, count, oldest)

    def _schedule_metrics_refresh(self) -> None:
        """Coalesce queue gauge reads instead of scanning the outbox after every change."""
        if self._metrics_refresh_at is None:
            self._metrics_refresh_at = time.monotonic() + METRICS_REFRESH_SECONDS

    async def submit(
        self, source_id: str, digest: str, alerts: tuple[OperatorAlert, ...]
    ) -> AlertmanagerSubmission:
        """Accept a batch from a source already identified by the HTTP authenticator."""
        async with self._chat_migrations.state_lock:
            return await self._submit(source_id, digest, alerts)

    async def _submit(
        self, source_id: str, digest: str, alerts: tuple[OperatorAlert, ...]
    ) -> AlertmanagerSubmission:
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
                return AlertmanagerSubmission(accepted=False)
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
        self._schedule_metrics_refresh()
        self._wake.set()
        return AlertmanagerSubmission(accepted=True, queued_messages=len(deliveries))

    async def run(self) -> None:
        retry_delay = WORKER_RETRY_INITIAL_SECONDS
        while True:
            try:
                await self._run_once()
            except Exception:
                # External alerts are optional; their failures must not stop chain monitoring.
                logger.exception(
                    "Alertmanager delivery worker failed; retrying",
                    extra={"retry_in_seconds": retry_delay},
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, WORKER_RETRY_MAX_SECONDS)
            else:
                retry_delay = WORKER_RETRY_INITIAL_SECONDS

    async def _run_once(self) -> None:
        self._wake.clear()
        if self._metrics_refresh_at is not None and time.monotonic() >= self._metrics_refresh_at:
            await self.refresh_queue_metrics()
        if await self.deliver_one():
            return
        timeout = (
            None
            if self._metrics_refresh_at is None
            else max(0.0, self._metrics_refresh_at - time.monotonic())
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
                logger.info(
                    "Alertmanager notification dropped: chat %s no longer follows "
                    "node operator %s; source: %s",
                    delivery.chat_id,
                    delivery.node_operator_id,
                    delivery.source_id,
                    extra=_delivery_log_context(delivery),
                )
                self._metrics.deliveries.labels(
                    source_id=delivery.source_id, outcome="unsubscribed"
                ).inc()
                self._schedule_metrics_refresh()
                return True
        try:
            await self._send_message(delivery.chat_id, delivery.message)
        except ChatMigrated as exc:
            try:
                await self._chat_migrations.migrate(delivery.chat_id, exc.new_chat_id)
            except ChatMigrationConflict:
                # A retry would hit the same conflict and block every delivery queued behind it.
                logger.error(
                    "Alertmanager delivery chat migration conflicts with the journal",
                    extra={"source_id": delivery.source_id, "chat_id": delivery.chat_id},
                )
                async with self._database.transaction() as session:
                    await AlertmanagerOutbox(session).complete(delivery)
                outcome = "failed"
            else:
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
            logger.info(
                "Alertmanager notification sent to chat %s for node operator %s; source: %s",
                delivery.chat_id,
                delivery.node_operator_id,
                delivery.source_id,
                extra=_delivery_log_context(delivery),
            )
            outcome = "sent"
        self._metrics.deliveries.labels(source_id=delivery.source_id, outcome=outcome).inc()
        self._schedule_metrics_refresh()
        return True


def _delivery_log_context(delivery: PendingAlertDelivery) -> dict[str, object]:
    return {
        "source_id": delivery.source_id,
        "node_operator_id": delivery.node_operator_id,
        "chat_id": delivery.chat_id,
    }
