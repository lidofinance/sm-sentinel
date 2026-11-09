import asyncio
import sqlite3
from dataclasses import replace

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.util.exc import CommandError
from sqlalchemy import text

from sentinel.app.database_models import Base
from sentinel.app.storage import RuntimeIdentityMismatch
from sentinel.module_types import ModuleType
from sentinel.app.alertmanager_storage import AlertmanagerOutbox


async def test_shared_database_namespaces_outbox_and_preserves_other_tables(database_factory):
    database = await database_factory()
    async with database.transaction() as session:
        await session.execute(text("CREATE TABLE requests (value TEXT)"))
        await session.execute(text("INSERT INTO requests VALUES ('another subsystem')"))
        await AlertmanagerOutbox(session).enqueue_new("evm", "one", [("42", 100, "hello")], now=100)
    async with database.session() as session:
        assert (await session.execute(text("SELECT value FROM requests"))).one() == (
            "another subsystem",
        )
        assert await AlertmanagerOutbox(session).pending_count() == 1
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0001"


@pytest.mark.parametrize("rollback", [True, False])
async def test_outbox_and_other_state_share_one_transaction(database_factory, rollback):
    database = await database_factory()
    async with database.transaction() as session:
        await session.execute(text("CREATE TABLE example_checkpoint (block INTEGER)"))

    class AbortTransaction(Exception):
        pass

    try:
        async with database.transaction() as session:
            await session.execute(text("INSERT INTO example_checkpoint VALUES (123)"))
            await AlertmanagerOutbox(session).enqueue_new(
                "evm", "one", [("42", 100, "hello")], now=100
            )
            if rollback:
                raise AbortTransaction
    except AbortTransaction:
        pass
    await database.close()
    await database.open()
    expected = 0 if rollback else 1
    async with database.session() as session:
        assert await session.scalar(text("SELECT COUNT(*) FROM example_checkpoint")) == expected
        outbox = AlertmanagerOutbox(session)
        assert await outbox.pending_count() == expected
        assert await outbox.has_receipt("evm", "one", now=100) is not rollback


async def test_nested_failure_rolls_back_only_inner_work(database_factory):
    database = await database_factory()
    async with database.transaction() as session:
        await session.execute(text("CREATE TABLE example_state (value INTEGER)"))
        await session.execute(text("INSERT INTO example_state VALUES (1)"))
        with pytest.raises(ValueError):
            async with session.begin_nested():
                await session.execute(text("INSERT INTO example_state VALUES (2)"))
                raise ValueError("abort inner")
        await session.execute(text("INSERT INTO example_state VALUES (3)"))
    async with database.session() as session:
        assert (
            await session.execute(text("SELECT value FROM example_state ORDER BY value"))
        ).all() == [(1,), (3,)]


@pytest.mark.parametrize(
    "changes", [{"chain_id": 2}, {"module_address": "0x5678"}, {"module_type": ModuleType.CURATED}]
)
async def test_database_rejects_another_runtime_without_rebinding(database_factory, changes):
    original = await database_factory()
    async with original.transaction() as session:
        await AlertmanagerOutbox(session).enqueue_new(
            "evm", "retained", [("42", 100, "hello")], now=0
        )
    path, identity = original.path, original.identity
    await original.close()
    with pytest.raises(RuntimeIdentityMismatch):
        await database_factory(path, replace(identity, **changes))
    reopened = await database_factory(path, identity)
    async with reopened.session() as session:
        assert await session.scalar(text("SELECT chain_id FROM runtime_identity")) == "1"
        outbox = AlertmanagerOutbox(session)
        delivery = await outbox.next_pending(source_ids=frozenset({"evm"}))
        assert delivery is not None
        assert (delivery.chat_id, delivery.message) == (100, "hello")
        assert await outbox.has_receipt("evm", "retained", now=0)


async def test_unknown_database_revision_is_rejected(database_factory):
    database = await database_factory()
    async with database.transaction() as session:
        await session.execute(
            text("UPDATE alembic_version SET version_num = 'unknown_future_revision'")
        )
    await database.close()
    with pytest.raises(CommandError, match="Can't locate revision"):
        await database.open()
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "unknown_future_revision",
        )


async def test_migration_matches_orm_schema_and_sqlite_settings(database_factory):
    database = await database_factory()
    async with database.engine.connect() as connection:
        differences = await connection.run_sync(
            lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
        )
        assert differences == []
        assert await connection.scalar(text("PRAGMA journal_mode")) == "wal"
        assert await connection.scalar(text("PRAGMA synchronous")) == 2
        assert await connection.scalar(text("PRAGMA foreign_keys")) == 1


async def test_cancellation_rolls_back_receipt_and_deliveries(database_factory):
    database = await database_factory()
    inserted = asyncio.Event()

    async def write():
        async with database.transaction() as session:
            await AlertmanagerOutbox(session).enqueue_new(
                "evm", "cancelled", [("42", 100, "hello")], now=100
            )
            inserted.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(write())
    await asyncio.wait_for(inserted.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with database.session() as session:
        outbox = AlertmanagerOutbox(session)
        assert await outbox.pending_count() == 0
        assert not await outbox.has_receipt("evm", "cancelled", now=100)


async def test_failed_initial_migration_preserves_unversioned_data(database_factory, tmp_path):
    from sqlalchemy.exc import OperationalError

    path = tmp_path / "prototype.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE runtime_identity (marker TEXT)")
        connection.execute("INSERT INTO runtime_identity VALUES ('preserve me')")
    with pytest.raises(OperationalError, match="no such column"):
        await database_factory(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT marker FROM runtime_identity").fetchone() == (
            "preserve me",
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='alembic_version'"
            ).fetchall()
            == []
        )


async def test_wrong_identity_is_rejected_before_any_migration(database_factory, monkeypatch):
    from unittest.mock import Mock
    from sentinel.app import database as database_module

    original = await database_factory()
    await original.close()
    upgrade = Mock(side_effect=AssertionError("migration must not run"))
    monkeypatch.setattr(database_module, "upgrade_schema", upgrade)
    with pytest.raises(RuntimeIdentityMismatch):
        await database_factory(original.path, replace(original.identity, chain_id=2))
    upgrade.assert_not_called()


async def test_existing_database_with_missing_identity_is_not_claimed(database_factory):
    database = await database_factory()
    async with database.transaction() as session:
        await session.execute(text("DELETE FROM runtime_identity"))
    await database.close()
    with pytest.raises(RuntimeIdentityMismatch):
        await database.open()
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT * FROM runtime_identity").fetchall() == []


async def test_cli_cannot_initialize_database_but_can_upgrade_bound_database(
    tmp_path, database_factory
):
    from alembic import command
    from alembic.config import Config
    from sentinel.app.database import MIGRATIONS_PATH

    path = tmp_path / "cli.sqlite3"
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{path}")
    with pytest.raises(CommandError, match="Initialize a new database by starting Sentinel"):
        await asyncio.to_thread(command.upgrade, config, "head")
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
        )
    database = await database_factory(path)
    async with database.transaction() as session:
        await AlertmanagerOutbox(session).enqueue_new(
            "evm", "retained", [("42", 100, "hello")], now=0
        )
    await database.close()
    await asyncio.to_thread(command.upgrade, config, "head")
    await database.open()
    async with database.session() as session:
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
        assert await AlertmanagerOutbox(session).pending_count() == 1
        assert (await session.execute(text("SELECT * FROM chat_migrations"))).all() == []
    await database.close()
    await asyncio.to_thread(command.downgrade, config, "base")
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("alembic_version",)]
        assert connection.execute("SELECT * FROM alembic_version").fetchall() == []
