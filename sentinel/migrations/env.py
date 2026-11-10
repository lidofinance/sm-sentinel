"""Alembic supports runtime connection sharing and the async CLI."""

import asyncio

from alembic import context
from alembic.util import CommandError
from sqlalchemy import Connection, inspect, select
from sqlalchemy.ext.asyncio import create_async_engine

from sentinel.app.database import configure_sqlite
from sentinel.app.database_models import Base, RuntimeIdentityRow

config = context.config


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def require_bound_database(connection: Connection) -> None:
    if (
        not inspect(connection).has_table("runtime_identity")
        or connection.scalar(select(RuntimeIdentityRow.id).where(RuntimeIdentityRow.id == 1))
        is None
    ):
        raise CommandError(
            "Alembic CLI requires a database with runtime identity. "
            "Initialize a new database by starting Sentinel with the intended chain/module; "
            "use the CLI only for subsequent schema upgrades."
        )


async def run_async_migrations() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("sqlalchemy.url is required for the migration CLI")
    engine = create_async_engine(url)
    configure_sqlite(engine)
    try:
        async with engine.connect() as connection:
            await connection.execution_options(sqlite_write=True)
            async with connection.begin():
                await connection.run_sync(require_bound_database)
                await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=Base.metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()
elif "connection" in config.attributes:
    run_migrations(config.attributes["connection"])
else:
    asyncio.run(run_async_migrations())
