from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.router import api_router
from app.clients.demo import DemoMarineSource
from app.clients.incois_pfz import IncoisPFZClient
from app.core.config import get_settings
from app.services.cache import MemoryJsonCache, RedisJsonCache
from app.services.marine import MarineConditionsService
from app.services.pfz import (
    PFZNearestService,
    PFZPreviewService,
    PFZSnapshotService,
)


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    timeout = httpx.Timeout(
        connect=settings.http_connect_timeout,
        read=settings.http_read_timeout,
        write=10.0,
        pool=5.0,
    )
    transport = httpx.AsyncHTTPTransport(retries=1)
    client = httpx.AsyncClient(timeout=timeout, transport=transport)

    if settings.redis_enabled:
        assert settings.redis_url is not None
        cache = RedisJsonCache(settings.redis_url)
    else:
        cache = MemoryJsonCache()

    sources = [
        DemoMarineSource("sst", "SST", 29.4, "degC"),
        DemoMarineSource("waves", "WAVE_HEIGHT", 1.6, "m"),
        DemoMarineSource("wind", "WIND_SPEED", 18.0, "km/h"),
    ]

    app.state.marine_service = MarineConditionsService(
        client=client,
        cache=cache,
        sources=sources,
        cache_ttl=settings.cache_ttl_seconds,
    )
    pfz_client = IncoisPFZClient(
        base_url=settings.incois_base_url,
        connect_timeout=settings.http_connect_timeout,
        read_timeout=settings.http_read_timeout,
        fetch_concurrency=settings.pfz_fetch_concurrency,
    )
    app.state.pfz_service = PFZPreviewService(pfz_client)
    pfz_snapshot_service = PFZSnapshotService(
        client=pfz_client,
        cache=cache,
        fresh_ttl_seconds=settings.pfz_cache_ttl_seconds,
        stale_ttl_seconds=settings.pfz_stale_ttl_seconds,
    )
    app.state.pfz_snapshot_service = pfz_snapshot_service
    app.state.pfz_nearest_service = PFZNearestService(
        snapshot_service=pfz_snapshot_service
    )

    yield

    await cache.close()
    await client.aclose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(api_router, prefix=settings.api_prefix)
