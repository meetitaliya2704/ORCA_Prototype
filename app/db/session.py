from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.db.errors import DatabaseOperationError, sanitize_database_error


def _secret_value(value: SecretStr | str) -> str:
    return value.get_secret_value() if isinstance(value, SecretStr) else value


def normalize_async_database_url(value: SecretStr | str) -> str:
    url = _secret_value(value).strip()
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("DATABASE_URL must use PostgreSQL with asyncpg")
    return url


class DatabaseSessionManager:
    def __init__(self, settings: Settings) -> None:
        if settings.database_url is None:
            raise ValueError("Database configuration is unavailable")
        self.engine: AsyncEngine = create_async_engine(
            normalize_async_database_url(settings.database_url),
            echo=False,
            hide_parameters=True,
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            pool_recycle=settings.database_pool_recycle_seconds,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as exc:
            await session.rollback()
            raise DatabaseOperationError(sanitize_database_error(exc)) from None
        except BaseException:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def close(self) -> None:
        await self.engine.dispose()


def build_database_manager(
    settings: Settings | None = None,
) -> DatabaseSessionManager | None:
    configured = settings or get_settings()
    if not configured.database_enabled:
        return None
    return DatabaseSessionManager(configured)


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    manager: DatabaseSessionManager | None = getattr(
        request.app.state, "database_manager", None
    )
    if manager is None:
        raise DatabaseOperationError(
            sanitize_database_error(RuntimeError("database disabled"))
        )
    async with manager.session() as session:
        yield session
