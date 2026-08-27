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
from app.services.pfz import PFZPreviewService


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

    cache = (
        RedisJsonCache(settings.redis_url)
        if settings.redis_enabled
        else MemoryJsonCache()
    )

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
    app.state.pfz_service = PFZPreviewService(
        IncoisPFZClient(
            base_url=settings.incois_base_url,
            connect_timeout=settings.http_connect_timeout,
            read_timeout=settings.http_read_timeout,
            session_attempts=settings.pfz_session_attempts,
        )
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
