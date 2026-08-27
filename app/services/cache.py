import json
from typing import Any, Protocol

import redis.asyncio as redis


class JsonCache(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None: ...

    async def close(self) -> None: ...


class MemoryJsonCache:
    def __init__(self) -> None:
        self._values: dict[str, dict[str, Any]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        return self._values.get(key)

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        del ttl
        self._values[key] = value

    async def close(self) -> None:
        self._values.clear()


class RedisJsonCache:
    def __init__(self, url: str) -> None:
        self._client = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> dict[str, Any] | None:
        value = await self._client.get(key)
        return json.loads(value) if value is not None else None

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        await self._client.set(key, json.dumps(value), ex=ttl)

    async def close(self) -> None:
        await self._client.aclose()

