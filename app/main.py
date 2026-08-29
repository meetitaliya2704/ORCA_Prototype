from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.router import api_router
from app.clients.demo import DemoMarineSource
from app.clients.copernicus_sst import CopernicusMarineSSTProvider
from app.clients.copernicus_waves import (
    COPERNICUS_WAVE_DATASET_VERSION,
    CopernicusMarineWaveCycleResolver,
    CopernicusMarineWaveProvider,
)
from app.clients.copernicus_wind import (
    COPERNICUS_WIND_DATASET_VERSION,
    CopernicusMarineWindProvider,
)
from app.clients.incois_pfz import IncoisPFZClient
from app.core.config import get_settings
from app.services.cache import MemoryJsonCache, RedisJsonCache
from app.services.marine import MarineConditionsService
from app.services.pfz import (
    PFZNearestService,
    PFZPreviewService,
    PFZSnapshotService,
)
from app.services.sst import CopernicusSSTMarineSource, CopernicusSSTService
from app.services.waves import CopernicusWaveMarineSource, CopernicusWaveService
from app.services.wind import CopernicusWindMarineSource, CopernicusWindService


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

    if settings.copernicus_sst_enabled:
        sst_service = CopernicusSSTService(
            provider=CopernicusMarineSSTProvider(),
            cache=cache,
            dataset_id=settings.copernicus_sst_dataset_id,
            variable=settings.copernicus_sst_variable,
            search_radius_km=settings.copernicus_sst_search_radius_km,
            lookback_days=settings.copernicus_sst_lookback_days,
            fresh_ttl_seconds=settings.copernicus_sst_cache_ttl_seconds,
            stale_ttl_seconds=settings.copernicus_sst_stale_ttl_seconds,
        )
        sst_source = CopernicusSSTMarineSource(sst_service)
        app.state.sst_service = sst_service
    else:
        sst_source = DemoMarineSource("sst", "SST", 29.4, "degC")
        app.state.sst_service = None

    if settings.copernicus_waves_enabled:
        wave_service = CopernicusWaveService(
            provider=CopernicusMarineWaveProvider(),
            cycle_resolver=CopernicusMarineWaveCycleResolver(),
            cache=cache,
            dataset_id=settings.copernicus_waves_dataset_id,
            dataset_version=COPERNICUS_WAVE_DATASET_VERSION,
            height_variable=settings.copernicus_waves_height_variable,
            period_variable=settings.copernicus_waves_period_variable,
            direction_variable=settings.copernicus_waves_direction_variable,
            search_radius_km=settings.copernicus_waves_search_radius_km,
            time_tolerance_hours=(
                settings.copernicus_waves_time_tolerance_hours
            ),
            fresh_ttl_seconds=settings.copernicus_waves_cache_ttl_seconds,
            stale_ttl_seconds=settings.copernicus_waves_stale_ttl_seconds,
            cycle_ttl_seconds=(
                settings.copernicus_waves_cycle_cache_ttl_seconds
            ),
        )
        wave_source = CopernicusWaveMarineSource(wave_service)
        app.state.wave_service = wave_service
    else:
        wave_source = DemoMarineSource("waves", "WAVE_HEIGHT", 1.6, "m")
        app.state.wave_service = None

    if settings.copernicus_wind_enabled:
        wind_service = CopernicusWindService(
            provider=CopernicusMarineWindProvider(),
            cache=cache,
            dataset_id=settings.copernicus_wind_dataset_id,
            dataset_version=COPERNICUS_WIND_DATASET_VERSION,
            eastward_variable=settings.copernicus_wind_eastward_variable,
            northward_variable=settings.copernicus_wind_northward_variable,
            search_radius_km=settings.copernicus_wind_search_radius_km,
            max_age_hours=settings.copernicus_wind_max_age_hours,
            fresh_ttl_seconds=settings.copernicus_wind_cache_ttl_seconds,
            stale_ttl_seconds=settings.copernicus_wind_stale_ttl_seconds,
        )
        wind_source = CopernicusWindMarineSource(wind_service)
        app.state.wind_service = wind_service
    else:
        wind_source = DemoMarineSource("wind", "WIND_SPEED", 18.0, "km/h")
        app.state.wind_service = None

    sources = [
        sst_source,
        wave_source,
        wind_source,
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
