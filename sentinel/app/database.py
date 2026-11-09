"""Runtime-owned async database and explicit transaction boundaries."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, event, inspect, select, insert
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sentinel.app.database_models import RuntimeIdentityRow
from sentinel.app.storage import RuntimeIdentity, RuntimeIdentityMismatch

MIGRATIONS_PATH = Path(__file__).resolve().parents[1] / "migrations"


def configure_sqlite(engine: AsyncEngine) -> None:
    """Explicit BEGIN works across Python 3.11+ and includes DDL/savepoints."""

    @event.listens_for(engine.sync_engine, "connect")
    def connect(dbapi_connection, _record):
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def begin(connection: Connection) -> None:
        # Acquire the writer reservation BEFORE any quota/dedup reads.
        mode = (
            "BEGIN IMMEDIATE" if connection.get_execution_options().get("sqlite_write") else "BEGIN"
        )
        connection.exec_driver_sql(mode)


def upgrade_schema(connection: Connection) -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


class SentinelDatabase:
    def __init__(self, path: Path, identity: RuntimeIdentity) -> None:
        self.path = path
        self.identity = identity
        self._engine: AsyncEngine | None = None

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("Sentinel database is not open")
        return self._engine

    async def open(self) -> None:
        if self._engine is not None:
            return
        self._engine = create_async_engine(
            URL.create("sqlite+aiosqlite", database=str(self.path)),
            connect_args={"timeout": 5},
        )
        configure_sqlite(self.engine)
        try:
            async with self.engine.connect() as connection:
                await connection.execution_options(sqlite_write=True)
                async with connection.begin():
                    # Check ownership before migrations can touch an existing database.
                    bound = await connection.run_sync(self._check_identity)
                    await connection.run_sync(upgrade_schema)
                    if not bound:
                        await connection.execute(
                            insert(RuntimeIdentityRow).values(
                                id=1,
                                chain_id=str(self.identity.chain_id),
                                module_address=self.identity.module_address,
                                module_type=self.identity.module_type.value,
                            )
                        )
        except BaseException:
            await self.close()
            raise

    def _check_identity(self, connection: Connection) -> bool:
        schema = inspect(connection)
        if not schema.has_table("runtime_identity"):
            if schema.has_table("alembic_version"):
                raise RuntimeIdentityMismatch("Sentinel database has no runtime identity")
            return False
        row = connection.execute(
            select(
                RuntimeIdentityRow.chain_id,
                RuntimeIdentityRow.module_address,
                RuntimeIdentityRow.module_type,
            ).where(RuntimeIdentityRow.id == 1)
        ).one_or_none()
        expected = (
            str(self.identity.chain_id),
            self.identity.module_address,
            self.identity.module_type.value,
        )
        if row is None or tuple(row) != expected:
            raise RuntimeIdentityMismatch("Sentinel database belongs to another runtime")
        return True

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """One session per operation/task; close read transactions before external I/O."""
        async with async_sessionmaker(self.engine, expire_on_commit=False)() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """Pass this session to every participating repository for one atomic write.

        Use session.begin_nested() explicitly for a recoverable inner savepoint.
        Never perform Telegram/RPC calls while holding the transaction.
        """
        async with self.session() as session, session.begin():
            options: dict[str, object] = {"sqlite_write": True}
            await session.connection(execution_options=options)
            yield session

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
