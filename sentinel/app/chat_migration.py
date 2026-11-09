"""Coordinate chat migration across PTB subscriptions and durable deliveries."""

import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from sentinel.app.alertmanager_storage import AlertmanagerOutbox
from sentinel.app.database import SentinelDatabase
from sentinel.app.database_models import ChatMigrationRow
from sentinel.app.storage import BotStorage, ChatStorage

if TYPE_CHECKING:
    from sentinel.app.application import SentinelApplication

logger = logging.getLogger(__name__)


class ChatMigrationService:
    def __init__(self, application: "SentinelApplication", database: SentinelDatabase) -> None:
        self._application = application
        self._database = database
        # Queue selection/fan-out must see subscriptions and persisted chat IDs together.
        # Never hold this lock during a Telegram request.
        self.state_lock = asyncio.Lock()

    async def migrate(self, old_chat_id: int, new_chat_id: int) -> None:
        if old_chat_id == new_chat_id:
            return
        async with self.state_lock:
            # Finish applying a committed migration even if its Telegram handler is cancelled.
            task = asyncio.create_task(self._migrate(old_chat_id, new_chat_id))
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise
        logger.info("Migrated chat id %s -> %s", old_chat_id, new_chat_id)

    async def _migrate(self, old_chat_id: int, new_chat_id: int) -> None:
        async with self._database.transaction() as session:
            previous = await session.scalar(
                select(ChatMigrationRow).where(ChatMigrationRow.old_chat_id == old_chat_id)
            )
            if previous is None:
                session.add(ChatMigrationRow(old_chat_id=old_chat_id, new_chat_id=new_chat_id))
            elif previous.new_chat_id != new_chat_id:
                raise ValueError("Chat migration conflicts with the recorded destination")
            await AlertmanagerOutbox(session).migrate_chat_id(old_chat_id, new_chat_id)
        self._migrate_subscriptions(old_chat_id, new_chat_id)

    async def recover(self) -> None:
        """Replay durable migrations against loaded pickle state before processing updates.

        Keep the journal: deleting entries would make an older pickle snapshot unsafe to restore.
        Replaying against already-migrated state does not restore removed subscriptions.
        """
        async with self.state_lock:
            async with self._database.session() as session:
                migrations = (
                    await session.execute(
                        select(ChatMigrationRow.old_chat_id, ChatMigrationRow.new_chat_id).order_by(
                            ChatMigrationRow.id
                        )
                    )
                ).all()
            for old_chat_id, new_chat_id in migrations:
                self._migrate_subscriptions(old_chat_id, new_chat_id)

    def _migrate_subscriptions(self, old_chat_id: int, new_chat_id: int) -> None:
        application = self._application
        old_chat_data = application.chat_data.get(old_chat_id)
        new_chat_data = application.chat_data.get(new_chat_id)
        if old_chat_data is not None:
            if new_chat_data is None:
                application.migrate_chat_data(old_chat_id=old_chat_id, new_chat_id=new_chat_id)
            else:
                subscriptions = ChatStorage(new_chat_data).node_operators
                for operator_id in ChatStorage(old_chat_data).node_operators.ids():
                    subscriptions.follow(operator_id)
                application.drop_chat_data(old_chat_id)
                application.mark_data_for_update_persistence(chat_ids=new_chat_id)
        storage = BotStorage(application.bot_data)
        storage.migrate_chat_id(old_chat_id, new_chat_id)
        new_chat_data = application.chat_data.get(new_chat_id)
        if new_chat_data is not None:
            for operator_id in ChatStorage(new_chat_data).node_operators.ids():
                storage.node_operator_chats.subscribe(operator_id, new_chat_id)
