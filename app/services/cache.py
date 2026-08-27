import json
import time
from collections.abc import Callable
from importlib import import_module
from typing import Any, Protocol


class RedisConfigurationError(RuntimeError):
    """Raised when the optional Redis cache cannot be configured."""


class JsonCache(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None: ...

    async def close(self) -> None: ...


class MemoryJsonCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._values: dict[str, tuple[dict[str, Any], float]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        cached = self._values.get(key)
        if cached is None:
            return None

        value, expires_at = cached
        if self._clock() >= expires_at:
            self._values.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        self._values[key] = (value, self._clock() + ttl)

    async def close(self) -> None:
        self._values.clear()


class RedisJsonCache:
    def __init__(self, url: str) -> None:
        if not url.strip():
            raise RedisConfigurationError(
                "REDIS_URL is required when Redis caching is enabled"
            )

        try:
            redis_asyncio = import_module("redis.asyncio")
        except ImportError as exc:
            raise RedisConfigurationError(
                "Redis caching is enabled, but the optional 'redis' package "
                "is not installed; install ORCA with the 'redis' extra"
            ) from exc

        self._client = redis_asyncio.from_url(url, decode_responses=True)

    async def get(self, key: str) -> dict[str, Any] | None:
        value = await self._client.get(key)
        return json.loads(value) if value is not None else None

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        await self._client.set(key, json.dumps(value), ex=ttl)

    async def close(self) -> None:
        await self._client.aclose()

