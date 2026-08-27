import asyncio
import json

from app.clients.incois_pfz import IncoisPFZClient
from app.core.config import get_settings
from app.services.cache import MemoryJsonCache, RedisJsonCache
from app.services.pfz import PFZSnapshotService


async def ingest_pfz_snapshot() -> dict[str, object]:
    settings = get_settings()
    if settings.redis_enabled:
        assert settings.redis_url is not None
        cache = RedisJsonCache(settings.redis_url)
    else:
        cache = MemoryJsonCache()

    service = PFZSnapshotService(
        client=IncoisPFZClient(
            base_url=settings.incois_base_url,
            connect_timeout=settings.http_connect_timeout,
            read_timeout=settings.http_read_timeout,
            fetch_concurrency=settings.pfz_fetch_concurrency,
        ),
        cache=cache,
        fresh_ttl_seconds=settings.pfz_cache_ttl_seconds,
        stale_ttl_seconds=settings.pfz_stale_ttl_seconds,
    )

    try:
        snapshot = await service.get_snapshot()
        return snapshot.model_dump(mode="json")
    finally:
        await cache.close()


if __name__ == "__main__":
    result = asyncio.run(ingest_pfz_snapshot())
    print(json.dumps(result, indent=2))
