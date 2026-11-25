"""Alertmanager repositories use the caller's session and transaction."""

from dataclasses import dataclass

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.app.chat_migration import ChatScopedRepository
from sentinel.app.database_models import (
    AlertmanagerDeliveryRow,
    AlertmanagerDisabledSourceRow,
    AlertmanagerRequestRow,
)

REQUEST_DEDUP_SECONDS = 60
MAX_PENDING_DELIVERIES = 10_000
MAX_PENDING_PER_SOURCE = 1000


class AlertmanagerOutboxFull(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PendingAlertDelivery:
    id: int
    source_id: str
    node_operator_id: str
    chat_id: int
    message: str


class AlertmanagerPreferences:
    """Opt-outs keyed by Telegram user ID and authenticated source ID."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def disabled_sources(self, user_id: int) -> set[str]:
        sources = await self._session.scalars(
            select(AlertmanagerDisabledSourceRow.source_id).where(
                AlertmanagerDisabledSourceRow.user_id == user_id
            )
        )
        return set(sources)

    async def disabled_recipients(self, source_id: str) -> set[int]:
        users = await self._session.scalars(
            select(AlertmanagerDisabledSourceRow.user_id).where(
                AlertmanagerDisabledSourceRow.source_id == source_id
            )
        )
        return set(users)

    async def is_disabled(self, user_id: int, source_id: str) -> bool:
        return (
            await self._session.get(AlertmanagerDisabledSourceRow, (user_id, source_id)) is not None
        )

    async def set_enabled(self, user_id: int, source_id: str, *, enabled: bool) -> None:
        if enabled:
            await self._session.execute(
                delete(AlertmanagerDisabledSourceRow).where(
                    AlertmanagerDisabledSourceRow.user_id == user_id,
                    AlertmanagerDisabledSourceRow.source_id == source_id,
                )
            )
        else:
            await self._session.execute(
                sqlite_insert(AlertmanagerDisabledSourceRow)
                .values(user_id=user_id, source_id=source_id)
                .on_conflict_do_nothing()
            )


class AlertmanagerOutbox(ChatScopedRepository):
    async def pending_count(self) -> int:
        return await self._session.scalar(select(func.count(AlertmanagerDeliveryRow.id))) or 0

    async def pending_for_source(self, source_id: str) -> int:
        return (
            await self._session.scalar(
                select(func.count(AlertmanagerDeliveryRow.id)).where(
                    AlertmanagerDeliveryRow.source_id == source_id
                )
            )
            or 0
        )

    async def has_receipt(self, source_id: str, digest: str, *, now: float) -> bool:
        pending = (
            select(AlertmanagerDeliveryRow.id)
            .where(
                AlertmanagerDeliveryRow.source_id == AlertmanagerRequestRow.source_id,
                AlertmanagerDeliveryRow.request_digest == AlertmanagerRequestRow.digest,
            )
            .exists()
        )
        return (
            await self._session.scalar(
                select(AlertmanagerRequestRow.source_id).where(
                    AlertmanagerRequestRow.source_id == source_id,
                    AlertmanagerRequestRow.digest == digest,
                    (AlertmanagerRequestRow.expires_at > now) | pending,
                )
            )
            is not None
        )

    async def queue_state(self) -> list[tuple[str, int, float]]:
        rows = await self._session.execute(
            select(
                AlertmanagerDeliveryRow.source_id,
                func.count(AlertmanagerDeliveryRow.id),
                func.min(AlertmanagerDeliveryRow.enqueued_at),
            ).group_by(AlertmanagerDeliveryRow.source_id)
        )
        return [(source, count, oldest) for source, count, oldest in rows]

    async def enqueue_new(
        self, source_id: str, digest: str, deliveries: list[tuple[str, int, str]], *, now: float
    ) -> None:
        """Enqueue after has_receipt returned False in the same write transaction.

        The caller retains the SQLite writer reservation from deduplication through this insert.
        """
        pending = (
            select(AlertmanagerDeliveryRow.id)
            .where(
                AlertmanagerDeliveryRow.source_id == AlertmanagerRequestRow.source_id,
                AlertmanagerDeliveryRow.request_digest == AlertmanagerRequestRow.digest,
            )
            .exists()
        )
        await self._session.execute(
            delete(AlertmanagerRequestRow).where(
                AlertmanagerRequestRow.expires_at <= now,
                ~pending,
            )
        )
        if await self.pending_count() + len(deliveries) > MAX_PENDING_DELIVERIES:
            raise AlertmanagerOutboxFull("Alertmanager delivery queue is full")
        if await self.pending_for_source(source_id) + len(deliveries) > MAX_PENDING_PER_SOURCE:
            raise AlertmanagerOutboxFull("Source delivery queue is full")
        await self._session.execute(
            insert(AlertmanagerRequestRow).values(
                source_id=source_id,
                digest=digest,
                expires_at=now + REQUEST_DEDUP_SECONDS,
            )
        )
        if deliveries:
            await self._session.execute(
                insert(AlertmanagerDeliveryRow),
                [
                    dict(
                        source_id=source_id,
                        request_digest=digest,
                        node_operator_id=operator_id,
                        chat_id=chat_id,
                        message=message,
                        enqueued_at=now,
                    )
                    for operator_id, chat_id, message in deliveries
                ],
            )

    async def next_pending(self, *, source_ids: frozenset[str]) -> PendingAlertDelivery | None:
        if not source_ids:
            return None
        row = await self._session.scalar(
            select(AlertmanagerDeliveryRow)
            .where(
                AlertmanagerDeliveryRow.source_id.in_(source_ids),
            )
            .order_by(AlertmanagerDeliveryRow.id)
            .limit(1)
        )
        if row is None:
            return None
        return PendingAlertDelivery(
            row.id, row.source_id, row.node_operator_id, row.chat_id, row.message
        )

    async def migrate_chat_id(self, old_chat_id: int, new_chat_id: int) -> None:
        # Preserve IDs (FIFO) and receipts.
        await self._session.execute(
            update(AlertmanagerDeliveryRow)
            .where(AlertmanagerDeliveryRow.chat_id == old_chat_id)
            .values(chat_id=new_chat_id)
        )

    async def complete(self, delivery: PendingAlertDelivery) -> None:
        await self._session.execute(
            delete(AlertmanagerDeliveryRow).where(
                AlertmanagerDeliveryRow.id == delivery.id,
                AlertmanagerDeliveryRow.chat_id == delivery.chat_id,
            )
        )
