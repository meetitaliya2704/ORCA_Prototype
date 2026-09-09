from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.db.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import normalize_async_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url="postgresql://",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_MIGRATION_CONFIGURATION_MISSING")
    engine = create_async_engine(
        normalize_async_database_url(settings.database_url),
        poolclass=NullPool,
        pool_pre_ping=True,
        echo=False,
        hide_parameters=True,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    except Exception:  # noqa: BLE001 - suppress credential-bearing driver errors
        raise RuntimeError("DATABASE_MIGRATION_CONNECTION_FAILED") from None
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
