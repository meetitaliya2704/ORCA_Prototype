import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.db.session import DatabaseSessionManager, normalize_async_database_url


def test_enabled_database_requires_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(_env_file=None, database_enabled=True)


@pytest.mark.parametrize(
    ("source", "expected_prefix"),
    [
        ("postgres://host/database", "postgresql+asyncpg://"),
        ("postgresql://host/database", "postgresql+asyncpg://"),
        ("postgresql+asyncpg://host/database", "postgresql+asyncpg://"),
    ],
)
def test_database_url_is_normalized_for_asyncpg(
    source: str, expected_prefix: str
) -> None:
    assert normalize_async_database_url(SecretStr(source)).startswith(expected_prefix)


def test_non_postgresql_database_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        normalize_async_database_url("sqlite:///local.db")


def test_database_secret_is_redacted() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:private@host/database",
    )
    assert "private" not in repr(settings.database_url)


async def test_engine_uses_safe_logging_and_pre_ping() -> None:
    settings = Settings(
        _env_file=None,
        database_enabled=True,
        database_url="postgresql+asyncpg://user:private@host/database",
    )
    manager = DatabaseSessionManager(settings)
    try:
        assert manager.engine.echo is False
        assert manager.engine.sync_engine.hide_parameters is True
        assert manager.engine.pool._pre_ping is True
    finally:
        await manager.close()
