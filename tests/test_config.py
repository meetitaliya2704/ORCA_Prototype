import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import cache as cache_module
from app.services.cache import RedisConfigurationError, RedisJsonCache


def test_database_configuration_is_not_required() -> None:
    settings = Settings(_env_file=None)

    assert not hasattr(settings, "database_url")
    assert not hasattr(settings, "pfz_sector_codes")
    assert settings.redis_enabled is False
    assert settings.pfz_fetch_concurrency == 4
    assert settings.pfz_cache_ttl_seconds == 1800
    assert settings.pfz_stale_ttl_seconds == 86400


def test_enabled_redis_requires_a_url() -> None:
    with pytest.raises(ValidationError, match="REDIS_URL is required"):
        Settings(
            _env_file=None,
            redis_enabled=True,
            redis_url="",
        )


def test_enabled_redis_requires_the_optional_package(monkeypatch) -> None:
    def missing_redis(name: str):
        assert name == "redis.asyncio"
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(cache_module, "import_module", missing_redis)

    with pytest.raises(RedisConfigurationError, match="optional 'redis' package"):
        RedisJsonCache("redis://localhost:6379/0")


def test_pfz_cache_ttls_must_be_ordered() -> None:
    with pytest.raises(
        ValidationError,
        match="PFZ_STALE_TTL_SECONDS must be greater",
    ):
        Settings(
            _env_file=None,
            pfz_cache_ttl_seconds=60,
            pfz_stale_ttl_seconds=30,
        )


@pytest.mark.parametrize("concurrency", [0, 21])
def test_pfz_fetch_concurrency_is_bounded(concurrency: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, pfz_fetch_concurrency=concurrency)
