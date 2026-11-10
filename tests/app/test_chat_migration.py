import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from prometheus_client import CollectorRegistry
from sqlalchemy import select
from telegram import Update
from telegram.error import ChatMigrated, Forbidden, NetworkError
from telegram.ext import ApplicationBuilder

from sentinel.app.application import SentinelApplication
from sentinel.app.context import BotContext
from sentinel.app.alertmanager_storage import AlertmanagerOutbox
from sentinel.app.database_models import AlertmanagerDeliveryRow, ChatMigrationRow
from sentinel.app.storage import BotStorage, ChatStorage, create_persistence
from sentinel.handlers.tracking import chat_migration
from sentinel.metrics.alertmanager import AlertmanagerMetrics
from sentinel.services.alertmanager import AlertmanagerDeliveryService


@pytest.fixture
async def migrated_chat(database_factory, chat_migrations_factory, module_adapter_factory):
    database = await database_factory()
    application = (
        ApplicationBuilder()
        .application_class(SentinelApplication)
        .token("123:TEST")
        .persistence(create_persistence(database.path.parent))
        .build()
    )
    application.chat_data[-100]["node_operators"] = {"42"}
    storage = BotStorage(application.bot_data)
    storage.groups.add(-100)
    storage.node_operator_chats.subscribe("42", -100)
    migrations = chat_migrations_factory(database, application)
    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        database=database,
        chat_migrations=migrations,
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda operator: storage.resolve_target_chats({operator}),
        send_message=sender,
    )
    async with database.transaction() as session:
        outbox = AlertmanagerOutbox(session)
        await outbox.enqueue_new(
            "evm", "batch", [("42", -100, "first"), ("42", -100, "second")], now=0
        )
    return SimpleNamespace(
        database=database,
        application=application,
        migrations=migrations,
        storage=storage,
        sender=sender,
        service=service,
    )


async def pending(database):
    async with database.session() as session:
        return (
            await session.execute(
                select(
                    AlertmanagerDeliveryRow.chat_id,
                    AlertmanagerDeliveryRow.message,
                ).order_by(AlertmanagerDeliveryRow.id)
            )
        ).all()


@pytest.mark.parametrize("trigger", ["update", "error"])
async def test_migration_preserves_whole_queue_and_subscription_routing(migrated_chat, trigger):
    state = migrated_chat
    if trigger == "update":
        context = cast(
            BotContext, SimpleNamespace(runtime=SimpleNamespace(chat_migrations=state.migrations))
        )
        update = cast(
            Update,
            SimpleNamespace(
                message=SimpleNamespace(
                    chat_id=-100,
                    migrate_to_chat_id=-200,
                    migrate_from_chat_id=None,
                )
            ),
        )
        await chat_migration(update, context)
        await chat_migration(update, context)
    else:
        state.sender.side_effect = ChatMigrated(-200)
        assert await state.service.deliver_one() is True
        state.sender.side_effect = None
        state.sender.reset_mock()
    assert await pending(state.database) == [(-200, "first"), (-200, "second")]
    assert state.storage.resolve_target_chats({"42"}) == {-200}
    assert state.application.chat_data[-200]["node_operators"] == {"42"}
    assert await state.service.deliver_one() is True
    assert await state.service.deliver_one() is True
    assert await state.service.deliver_one() is False
    assert [call.args for call in state.sender.await_args_list] == [
        (-200, "first"),
        (-200, "second"),
    ]


@pytest.mark.parametrize(
    "error", [None, Forbidden("old chat gone"), NetworkError("connection lost")]
)
async def test_inflight_delivery_cannot_delete_migrated_queue(migrated_chat, error):
    state = migrated_chat
    started, release = asyncio.Event(), asyncio.Event()

    async def send(chat, message):
        started.set()
        await release.wait()
        if error is not None:
            raise error

    state.sender.side_effect = send
    delivery = asyncio.create_task(state.service.deliver_one())
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        await asyncio.wait_for(state.migrations.migrate(-100, -200), timeout=2)
        release.set()
        await delivery
        assert await pending(state.database) == [(-200, "first"), (-200, "second")]
        state.sender.side_effect = None
        state.sender.reset_mock()
        assert await state.service.deliver_one() is True
        assert await state.service.deliver_one() is True
        assert [call.args for call in state.sender.await_args_list] == [
            (-200, "first"),
            (-200, "second"),
        ]
    finally:
        delivery.cancel()
        await asyncio.gather(delivery, return_exceptions=True)


async def test_recovery_replays_migration_against_last_saved_pickle(
    migrated_chat, chat_migrations_factory, module_adapter_factory
):
    state = migrated_chat
    state.application.mark_data_for_update_persistence(chat_ids=-100)
    await state.application.update_persistence()
    await state.application.persistence.flush()
    await state.migrations.migrate(-100, -200)
    # Simulate abrupt restart: no update_persistence/flush after the migration.
    await state.database.close()
    await state.database.open()
    persisted = create_persistence(state.database.path.parent)
    restarted = (
        ApplicationBuilder().application_class(SentinelApplication).token("123:TEST").build()
    )
    restarted.bot_data.update(await persisted.get_bot_data())
    for chat, data in (await persisted.get_chat_data()).items():
        restarted.chat_data[chat].update(data)
    storage = BotStorage(restarted.bot_data)
    assert storage.resolve_target_chats({"42"}) == {-100}
    recovery = chat_migrations_factory(state.database, restarted)
    await recovery.recover()
    await recovery.recover()
    assert storage.resolve_target_chats({"42"}) == {-200}
    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        database=state.database,
        chat_migrations=recovery,
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda op: storage.resolve_target_chats({op}),
        send_message=sender,
    )
    assert await service.deliver_one()
    assert await service.deliver_one()
    assert [call.args for call in sender.await_args_list] == [(-200, "first"), (-200, "second")]
    assert await pending(state.database) == []
    # Replaying a permanent journal must not resurrect a later unsubscribe.
    ChatStorage(restarted.chat_data[-200]).node_operators.unfollow("42")
    storage.node_operator_chats.unsubscribe("42", -200)
    await recovery.recover()
    assert storage.resolve_target_chats({"42"}) == set()


async def test_failed_queue_migration_rolls_back_journal_and_subscriptions(
    migrated_chat, monkeypatch
):
    state = migrated_chat
    monkeypatch.setattr(
        AlertmanagerOutbox, "migrate_chat_id", AsyncMock(side_effect=RuntimeError("write failed"))
    )
    with pytest.raises(RuntimeError, match="write failed"):
        await state.migrations.migrate(-100, -200)
    async with state.database.session() as session:
        assert (await session.scalars(select(ChatMigrationRow))).all() == []
    assert state.storage.resolve_target_chats({"42"}) == {-100}
    assert await pending(state.database) == [(-100, "first"), (-100, "second")]


async def test_cancelled_migration_finishes_before_releasing_state_lock(migrated_chat, monkeypatch):
    state = migrated_chat
    entered, release = asyncio.Event(), asyncio.Event()
    original = AlertmanagerOutbox.migrate_chat_id

    async def delayed(outbox, old, new):
        await original(outbox, old, new)
        entered.set()
        await release.wait()

    monkeypatch.setattr(AlertmanagerOutbox, "migrate_chat_id", delayed)
    task = asyncio.create_task(state.migrations.migrate(-100, -200))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert state.storage.resolve_target_chats({"42"}) == {-200}
        assert await pending(state.database) == [(-200, "first"), (-200, "second")]
        assert not state.migrations.state_lock.locked()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_conflicting_chat_migration_drops_delivery_without_blocking_queue(migrated_chat):
    state = migrated_chat
    async with state.database.transaction() as session:
        session.add(ChatMigrationRow(old_chat_id=-100, new_chat_id=-200))
    state.sender.side_effect = [ChatMigrated(-300), None]

    assert await state.service.deliver_one() is True
    assert await pending(state.database) == [(-100, "second")]
    assert await state.service.deliver_one() is True
    assert await pending(state.database) == []
    assert [call.args for call in state.sender.await_args_list] == [
        (-100, "first"),
        (-100, "second"),
    ]
