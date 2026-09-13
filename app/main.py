import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.clients.copernicus_chlorophyll import CopernicusMarineChlorophyllProvider
from app.clients.copernicus_currents import (
    CopernicusCurrentMetadataResolver,
    CopernicusMarineCurrentProvider,
)
from app.clients.copernicus_sst import CopernicusMarineSSTProvider
from app.clients.copernicus_tides import (
    CopernicusMarineTideProvider,
    CopernicusTideMetadataResolver,
)
from app.clients.copernicus_waves import (
    COPERNICUS_WAVE_DATASET_VERSION,
    CopernicusMarineWaveCycleResolver,
    CopernicusMarineWaveProvider,
)
from app.clients.copernicus_wind import (
    COPERNICUS_WIND_DATASET_VERSION,
    CopernicusMarineWindProvider,
)
from app.clients.demo import DemoMarineSource
from app.clients.ecmwf_wind import ECMWFOpenDataWindProvider
from app.clients.incois_pfz import IncoisPFZClient
from app.core.config import get_settings
from app.core.performance import (
    InstrumentedAsyncProxy,
    InstrumentedJsonCache,
    PerformanceMiddleware,
    PerformanceRecorder,
)
from app.services.assessment import MarineAssessmentService
from app.services.cache import MemoryJsonCache, RedisJsonCache
from app.services.chlorophyll import (
    CopernicusChlorophyllMarineSource,
    CopernicusChlorophyllService,
)
from app.services.currents import (
    CopernicusCurrentMarineSource,
    CopernicusCurrentService,
)
from app.services.evidence import MarineEvidenceService
from app.services.marine import MarineConditionsService
from app.services.pfz import (
    PFZNearestService,
    PFZPreviewService,
    PFZSnapshotService,
)
from app.services.pfz_journey import PFZJourneyService
from app.services.sst import CopernicusSSTMarineSource, CopernicusSSTService
from app.services.tides import CopernicusTideMarineSource, CopernicusTideService
from app.services.waves import CopernicusWaveMarineSource, CopernicusWaveService
from app.services.wind import CopernicusWindMarineSource, CopernicusWindService
from app.services.wind_forecast import (
    BoundedWindFieldCache,
    ECMWFWindForecastService,
    ECMWFWindMarineSource,
    TimeSelectingWindMarineSource,
)
from app.snapshots.chlorophyll import ChlorophyllSnapshotManager
from app.snapshots.jobs import RefreshJobManager
from app.snapshots.manager import SSTSnapshotManager
from app.snapshots.scheduler import SnapshotScheduler
from app.snapshots.store import InMemorySnapshotStore

settings = get_settings()


def _measured(
    target,
    phases: dict[str, str],
    enabled: bool,
    semaphore: asyncio.Semaphore | None = None,
):
    return InstrumentedAsyncProxy(target, phases, semaphore) if enabled else target


def _build_sst_provider(measure):
    """One lazy provider construction path shared by direct and snapshot SST."""
    return measure(
        CopernicusMarineSSTProvider(),
        {"fetch_cells": "provider.load", "fetch_region": "provider.load"},
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database_manager = None
    if settings.database_enabled:
        try:
            from app.db.session import DatabaseSessionManager

            database_manager = DatabaseSessionManager(settings)
        except (ImportError, ValueError):
            raise RuntimeError("DATABASE_STARTUP_CONFIGURATION_FAILED") from None
    app.state.database_manager = database_manager

    diagnostics_enabled = bool(
        getattr(
            app.state,
            "performance_diagnostics_enabled",
            settings.performance_diagnostics_enabled,
        )
    )
    instrumentation_enabled = diagnostics_enabled or bool(
        getattr(
            app.state,
            "performance_server_timing_enabled",
            settings.performance_server_timing_enabled,
        )
    )
    profile_semaphore = (
        asyncio.Semaphore(settings.performance_profile_max_provider_concurrency)
        if getattr(app.state, "performance_isolated_cache", False)
        else None
    )
    measure = lambda target, phases: _measured(
        target, phases, instrumentation_enabled, profile_semaphore
    )
    timeout = httpx.Timeout(
        connect=settings.http_connect_timeout,
        read=settings.http_read_timeout,
        write=10.0,
        pool=5.0,
    )
    transport = httpx.AsyncHTTPTransport(retries=1)
    client = httpx.AsyncClient(timeout=timeout, transport=transport)

    if getattr(app.state, "performance_isolated_cache", False):
        base_cache = MemoryJsonCache()
    elif settings.redis_enabled:
        assert settings.redis_url is not None
        base_cache = RedisJsonCache(settings.redis_url)
    else:
        base_cache = MemoryJsonCache()
    cache = InstrumentedJsonCache(base_cache) if instrumentation_enabled else base_cache

    if settings.copernicus_sst_enabled:
        sst_provider = _build_sst_provider(measure)
        sst_service = CopernicusSSTService(
            provider=sst_provider,
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

    snapshot_schedulers = []
    refresh_jobs = None
    app.state.sst_snapshot_manager = None
    app.state.chlorophyll_snapshot_manager = None

    if settings.copernicus_waves_enabled:
        wave_service = CopernicusWaveService(
            provider=measure(
                CopernicusMarineWaveProvider(),
                {"fetch_cells": "provider.load"},
            ),
            cycle_resolver=measure(
                CopernicusMarineWaveCycleResolver(),
                {"resolve_cycle": "provider.metadata"},
            ),
            cache=cache,
            dataset_id=settings.copernicus_waves_dataset_id,
            dataset_version=COPERNICUS_WAVE_DATASET_VERSION,
            height_variable=settings.copernicus_waves_height_variable,
            period_variable=settings.copernicus_waves_period_variable,
            direction_variable=settings.copernicus_waves_direction_variable,
            search_radius_km=settings.copernicus_waves_search_radius_km,
            time_tolerance_hours=(settings.copernicus_waves_time_tolerance_hours),
            fresh_ttl_seconds=settings.copernicus_waves_cache_ttl_seconds,
            stale_ttl_seconds=settings.copernicus_waves_stale_ttl_seconds,
            cycle_ttl_seconds=(settings.copernicus_waves_cycle_cache_ttl_seconds),
        )
        wave_source = CopernicusWaveMarineSource(wave_service)
        app.state.wave_service = wave_service
    else:
        wave_source = DemoMarineSource("waves", "WAVE_HEIGHT", 1.6, "m")
        app.state.wave_service = None

    if settings.copernicus_wind_enabled:
        wind_service = CopernicusWindService(
            provider=measure(
                CopernicusMarineWindProvider(),
                {"fetch_cells": "provider.load"},
            ),
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

    if settings.chlorophyll_enabled:
        chlorophyll_provider = measure(
            CopernicusMarineChlorophyllProvider(),
            {"fetch_cells": "provider.load", "fetch_region": "provider.load"},
        )
        chlorophyll_service = CopernicusChlorophyllService(
            provider=chlorophyll_provider,
            cache=cache,
            dataset_id=settings.chlorophyll_dataset_id,
            dataset_version=settings.chlorophyll_dataset_version,
            chlorophyll_variable=settings.chlorophyll_variable,
            uncertainty_variable=settings.chlorophyll_uncertainty_variable,
            flags_variable=settings.chlorophyll_flags_variable,
            max_radius_km=settings.chlorophyll_max_radius_km,
            fresh_ttl_seconds=settings.chlorophyll_cache_ttl_seconds,
            max_stale_seconds=settings.chlorophyll_max_stale_seconds,
            freshness_hours=settings.chlorophyll_freshness_hours,
            high_uncertainty_percent=(settings.chlorophyll_high_uncertainty_percent),
        )
        chlorophyll_source = CopernicusChlorophyllMarineSource(chlorophyll_service)
        app.state.chlorophyll_service = chlorophyll_service
    else:
        chlorophyll_source = DemoMarineSource(
            "chlorophyll",
            "CHLOROPHYLL_A",
            0.4,
            "mg/m³",
        )
        app.state.chlorophyll_service = None

    snapshot_store = None
    snapshots_requested = settings.marine_snapshots_enabled and (
        app.state.sst_service is not None
        or (
            settings.chlorophyll_snapshots_enabled
            and app.state.chlorophyll_service is not None
        )
    )
    if snapshots_requested:
        snapshot_store = InMemorySnapshotStore()
        refresh_jobs = RefreshJobManager(
            store=snapshot_store,
            heavy_concurrency=settings.marine_snapshot_heavy_concurrency,
            history_retention_seconds=settings.marine_snapshot_job_retention_seconds,
            retryable_base_delay_seconds=settings.sst_snapshot_retryable_base_delay_seconds,
            retryable_max_delay_seconds=settings.sst_snapshot_retryable_max_delay_seconds,
            non_retryable_cooldown_seconds=settings.sst_snapshot_non_retryable_cooldown_seconds,
        )
    if refresh_jobs is not None and app.state.sst_service is not None:
        sst_snapshot_manager = SSTSnapshotManager(
            provider=sst_provider,
            point_service=sst_service,
            store=snapshot_store,
            jobs=refresh_jobs,
            tile_size_degrees=settings.marine_snapshot_tile_size_degrees,
            wait_timeout_seconds=settings.marine_snapshot_wait_timeout_seconds,
            fresh_seconds=settings.sst_snapshot_fresh_seconds,
            max_stale_seconds=settings.marine_snapshot_max_stale_seconds,
            refresh_check_seconds=settings.sst_snapshot_refresh_check_seconds,
            lookback_days=settings.sst_snapshot_time_lookback_days,
        )
        app.state.sst_snapshot_manager = sst_snapshot_manager
        scheduler = SnapshotScheduler(
            manager=sst_snapshot_manager,
            points=(
                (point.latitude, point.longitude)
                for point in settings.marine_snapshot_prewarm_points_json
            ),
            check_seconds=settings.marine_snapshot_scheduler_check_seconds,
        )
        scheduler.start(warm_immediately=settings.marine_snapshot_startup_warm_enabled)
        snapshot_schedulers.append(scheduler)
    if (
        refresh_jobs is not None
        and settings.chlorophyll_snapshots_enabled
        and app.state.chlorophyll_service is not None
    ):
        chlorophyll_snapshot_manager = ChlorophyllSnapshotManager(
            provider=chlorophyll_provider,
            point_service=chlorophyll_service,
            store=snapshot_store,
            jobs=refresh_jobs,
            tile_size_degrees=settings.marine_snapshot_tile_size_degrees,
            wait_timeout_seconds=settings.marine_snapshot_wait_timeout_seconds,
            fresh_seconds=settings.chlorophyll_snapshot_fresh_seconds,
            max_stale_seconds=settings.chlorophyll_snapshot_max_stale_seconds,
            refresh_check_seconds=settings.chlorophyll_snapshot_refresh_check_seconds,
            schema_version=settings.chlorophyll_snapshot_schema_version,
        )
        app.state.chlorophyll_snapshot_manager = chlorophyll_snapshot_manager
        scheduler = SnapshotScheduler(
            manager=chlorophyll_snapshot_manager,
            points=(
                (point.latitude, point.longitude)
                for point in settings.marine_snapshot_prewarm_points_json
            ),
            check_seconds=settings.marine_snapshot_scheduler_check_seconds,
        )
        scheduler.start(
            warm_immediately=settings.chlorophyll_snapshot_startup_warm_enabled
        )
        snapshot_schedulers.append(scheduler)
    app.state.snapshot_scheduler = (
        snapshot_schedulers[0] if snapshot_schedulers else None
    )
    app.state.snapshot_schedulers = tuple(snapshot_schedulers)
    app.state.snapshot_job_manager = refresh_jobs

    if settings.copernicus_currents_enabled:
        current_service = CopernicusCurrentService(
            provider=measure(
                CopernicusMarineCurrentProvider(),
                {
                    "available_times": "provider.availability",
                    "fetch_cells": "provider.load",
                },
            ),
            metadata_resolver=measure(
                CopernicusCurrentMetadataResolver(),
                {"resolve": "provider.metadata"},
            ),
            cache=cache,
            dataset_id=settings.copernicus_currents_dataset_id,
            dataset_version=settings.copernicus_currents_dataset_version,
            static_dataset_id=settings.copernicus_currents_static_dataset_id,
            static_dataset_version=settings.copernicus_currents_static_dataset_version,
            max_radius_km=settings.copernicus_currents_max_radius_km,
            calm_threshold_mps=settings.copernicus_currents_calm_threshold_mps,
            time_tolerance_hours=settings.copernicus_currents_time_tolerance_hours,
            component_tolerance_mps=settings.copernicus_currents_component_tolerance_mps,
            fresh_ttl_seconds=settings.copernicus_currents_cache_ttl_seconds,
            stale_ttl_seconds=settings.copernicus_currents_stale_ttl_seconds,
            max_horizon_hours=settings.copernicus_currents_max_horizon_hours,
        )
        current_source = CopernicusCurrentMarineSource(current_service)
        app.state.current_service = current_service
    else:
        current_source = DemoMarineSource(
            "currents", "TOTAL_SURFACE_CURRENT_SPEED", 0.2, "m/s"
        )
        app.state.current_service = None

    if settings.copernicus_tides_enabled:
        tide_service = CopernicusTideService(
            provider=measure(
                CopernicusMarineTideProvider(),
                {
                    "available_times": "provider.availability",
                    "fetch_dynamic": "provider.load",
                    "fetch_static": "provider.static_mask",
                },
            ),
            metadata_resolver=measure(
                CopernicusTideMetadataResolver(),
                {"resolve": "provider.metadata"},
            ),
            cache=cache,
            dataset_id=settings.copernicus_tides_dataset_id,
            dataset_version=settings.copernicus_tides_dataset_version,
            static_dataset_id=settings.copernicus_tides_static_dataset_id,
            static_dataset_version=settings.copernicus_tides_static_dataset_version,
            static_dataset_part=settings.copernicus_tides_static_dataset_part,
            max_radius_km=settings.copernicus_tides_max_radius_km,
            static_alignment_tolerance_km=settings.copernicus_tides_static_alignment_tolerance_km,
            time_tolerance_hours=settings.copernicus_tides_time_tolerance_hours,
            max_horizon_hours=settings.copernicus_tides_max_horizon_hours,
            decomposition_tolerance_m=settings.copernicus_tides_decomposition_tolerance_m,
            fresh_ttl_seconds=settings.copernicus_tides_cache_ttl_seconds,
            stale_ttl_seconds=settings.copernicus_tides_stale_ttl_seconds,
            static_ttl_seconds=settings.copernicus_tides_static_cache_ttl_seconds,
            metadata_ttl_seconds=settings.copernicus_tides_metadata_cache_ttl_seconds,
            metadata_unavailable_ttl_seconds=settings.copernicus_tides_metadata_unavailable_ttl_seconds,
            availability_ttl_seconds=settings.copernicus_tides_availability_ttl_seconds,
            event_ttl_seconds=settings.copernicus_tides_event_cache_ttl_seconds,
            minimum_consecutive_samples=settings.copernicus_tides_minimum_consecutive_samples,
        )
        tide_source = CopernicusTideMarineSource(tide_service)
        app.state.tide_service = tide_service
    else:
        tide_source = DemoMarineSource(
            "sea_level", "TOTAL_MODELLED_SEA_LEVEL", 0.0, "m"
        )
        app.state.tide_service = None

    if settings.ecmwf_wind_enabled:
        ecmwf_provider = ECMWFOpenDataWindProvider(
            model=settings.ecmwf_wind_model,
            resolution=settings.ecmwf_wind_resolution,
            u_parameter=settings.ecmwf_wind_u_parameter,
            v_parameter=settings.ecmwf_wind_v_parameter,
            maximum_retries=settings.ecmwf_wind_max_retries,
            retry_initial_seconds=settings.ecmwf_wind_retry_initial_seconds,
            retry_max_seconds=settings.ecmwf_wind_retry_max_seconds,
            total_timeout_seconds=(
                settings.ecmwf_wind_connect_timeout_seconds
                + settings.ecmwf_wind_read_timeout_seconds
            ),
            max_download_bytes=settings.ecmwf_wind_max_download_bytes,
        )
        ecmwf_wind_service = ECMWFWindForecastService(
            provider=measure(
                ecmwf_provider,
                {
                    "discover_cycles": "provider.availability",
                    "retrieve_field": "provider.load",
                },
            ),
            point_cache=cache,
            field_cache=BoundedWindFieldCache(
                ttl_seconds=settings.ecmwf_wind_field_cache_ttl_seconds,
                max_entries=settings.ecmwf_wind_field_cache_max_entries,
                max_bytes=settings.ecmwf_wind_field_cache_max_bytes,
            ),
            primary_source=settings.ecmwf_wind_primary_source,
            fallback_source=(settings.ecmwf_wind_fallback_source.strip() or None),
            cycle_cache_ttl_seconds=settings.ecmwf_wind_cycle_cache_ttl_seconds,
            cycle_stale_ttl_seconds=settings.ecmwf_wind_cycle_stale_ttl_seconds,
            point_cache_ttl_seconds=settings.ecmwf_wind_point_cache_ttl_seconds,
            point_stale_ttl_seconds=settings.ecmwf_wind_point_stale_ttl_seconds,
            max_stale_cycle_age_hours=(settings.ecmwf_wind_max_stale_cycle_age_hours),
            calm_threshold_mps=settings.ecmwf_wind_calm_threshold_mps,
            max_horizon_hours=settings.ecmwf_wind_max_horizon_hours,
        )
        wind_source = TimeSelectingWindMarineSource(
            wind_source,
            ECMWFWindMarineSource(ecmwf_wind_service),
        )
        app.state.ecmwf_wind_service = ecmwf_wind_service
    else:
        app.state.ecmwf_wind_service = None

    sources = [
        sst_source,
        wave_source,
        wind_source,
        chlorophyll_source,
        current_source,
        tide_source,
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
        snapshot_service=pfz_snapshot_service,
        enable_coastal_fallback=True,
    )
    try:
        from app.services.indian_coastline_pfz import get_indian_coastline_snapshot

        initial_pfz = get_indian_coastline_snapshot()
        pfz_dump = initial_pfz.model_dump(mode="json")
        await cache.set("pfz:snapshot:fresh", pfz_dump, settings.pfz_cache_ttl_seconds)
        await cache.set("pfz:snapshot:last_success", pfz_dump, settings.pfz_stale_ttl_seconds)
    except Exception:
        pass
    from app.services.demo_fallbacks import (
        DemoChlorophyllService,
        DemoCurrentService,
        DemoECMWFWindService,
        DemoSSTService,
        DemoTideService,
        DemoWaveService,
        DemoWindService,
    )

    coastal_fallback_sources = {
        "sst": DemoSSTService(),
        "chlorophyll": DemoChlorophyllService(),
        "waves": DemoWaveService(),
        "wind": DemoWindService(),
        "currents": DemoCurrentService(),
        "sea_level": DemoTideService(),
    }

    app.state.evidence_service = (
        MarineEvidenceService(
            pfz_service=app.state.pfz_nearest_service,
            sst_service=app.state.sst_service,
            sst_snapshot_manager=app.state.sst_snapshot_manager,
            chlorophyll_service=app.state.chlorophyll_service,
            chlorophyll_snapshot_manager=app.state.chlorophyll_snapshot_manager,
            wave_service=app.state.wave_service,
            recent_wind_service=app.state.wind_service,
            forecast_wind_service=app.state.ecmwf_wind_service,
            current_service=app.state.current_service,
            sea_level_service=app.state.tide_service,
            fallback_services=coastal_fallback_sources,
            source_timeout_seconds=2.5,
            max_concurrent_sources=settings.evidence_max_concurrent_sources,
        )
        if settings.evidence_aggregation_enabled
        else None
    )
    app.state.assessment_service = (
        MarineAssessmentService(evidence_service=app.state.evidence_service)
        if app.state.evidence_service is not None
        else None
    )
    app.state.pfz_journey_service = (
        PFZJourneyService(
            pfz_service=app.state.pfz_nearest_service,
            evidence_service=app.state.evidence_service,
            assessment_service=app.state.assessment_service,
        )
        if app.state.evidence_service is not None
        and app.state.assessment_service is not None
        else None
    )
    app.state.assistant_service = None
    if settings.assistant_enabled:
        try:
            from app.agents.explainer import LLMResponseExplainer
            from app.agents.graph import AssistantServices, ORCAAssistantGraph
            from app.agents.intents import (
                DeterministicIntentRouter,
                FallbackIntentRouter,
                GeminiFunctionIntentRouter,
                GroqFunctionIntentRouter,
                OpenRouterFunctionIntentRouter,
            )
            from app.services.assistant_store import (
                InMemoryAssistantPersistence,
                SQLAlchemyAssistantPersistence,
            )

            fallback_router = DeterministicIntentRouter()
            provider = settings.orca_assistant_provider.strip().lower()
            explainer: LLMResponseExplainer | None = None

            if (
                provider == "groq"
                and settings.groq_api_key is not None
                and settings.groq_api_key.get_secret_value().strip()
            ):
                router = FallbackIntentRouter(
                    GroqFunctionIntentRouter(
                        api_key=settings.groq_api_key,
                        model=settings.orca_assistant_model,
                        base_url=settings.groq_base_url,
                        timeout_seconds=min(
                            settings.assistant_model_timeout_seconds, 10.0
                        ),
                    ),
                    fallback_router,
                )
                configured_model = settings.orca_assistant_model
                explainer = LLMResponseExplainer(
                    provider="groq",
                    api_key=settings.groq_api_key,
                    model=settings.orca_assistant_model,
                    base_url=settings.groq_base_url,
                    timeout_seconds=min(
                        settings.assistant_model_timeout_seconds, 12.0
                    ),
                )
            elif (
                provider == "openrouter"
                and settings.openrouter_api_key is not None
                and settings.openrouter_api_key.get_secret_value().strip()
            ):
                router = FallbackIntentRouter(
                    OpenRouterFunctionIntentRouter(
                        api_key=settings.openrouter_api_key,
                        model=settings.orca_assistant_model,
                        base_url=settings.openrouter_base_url,
                        timeout_seconds=min(
                            settings.assistant_model_timeout_seconds, 10.0
                        ),
                    ),
                    fallback_router,
                )
                configured_model = settings.orca_assistant_model
                explainer = LLMResponseExplainer(
                    provider="openrouter",
                    api_key=settings.openrouter_api_key,
                    model=settings.orca_assistant_model,
                    base_url=settings.openrouter_base_url,
                    timeout_seconds=min(
                        settings.assistant_model_timeout_seconds, 12.0
                    ),
                )
            elif (
                (provider == "gemini" or settings.assistant_gemini_routing_enabled)
                and settings.google_api_key is not None
                and settings.google_api_key.get_secret_value().strip()
            ):
                router = FallbackIntentRouter(
                    GeminiFunctionIntentRouter(
                        api_key=settings.google_api_key,
                        model=settings.assistant_model,
                        timeout_seconds=settings.assistant_model_timeout_seconds,
                    ),
                    fallback_router,
                )
                configured_model = settings.assistant_model
                explainer = LLMResponseExplainer(
                    provider="gemini",
                    api_key=settings.google_api_key,
                    model=settings.assistant_model,
                    timeout_seconds=settings.assistant_model_timeout_seconds,
                )
            else:
                router = fallback_router
                configured_model = None
            persistence = (
                SQLAlchemyAssistantPersistence(database_manager.session_factory)
                if database_manager is not None and settings.database_enabled
                else InMemoryAssistantPersistence()
            )
            app.state.assistant_service = ORCAAssistantGraph(
                router=router,
                persistence=persistence,
                services=AssistantServices(
                    pfz_nearest=app.state.pfz_nearest_service,
                    evidence=app.state.evidence_service,
                    assessment=app.state.assessment_service,
                    pfz_journey=app.state.pfz_journey_service,
                ),
                model=configured_model,
                graph_timeout_seconds=settings.assistant_graph_timeout_seconds,
                max_scientific_service_calls=(
                    settings.assistant_max_scientific_service_calls
                ),
                explainer=explainer,
            )
        except ImportError:
            raise RuntimeError("ASSISTANT_DEPENDENCY_MISSING") from None

    try:
        yield
    finally:
        for snapshot_scheduler in snapshot_schedulers:
            await snapshot_scheduler.close()
        if refresh_jobs is not None:
            await refresh_jobs.close()
        await cache.close()
        await client.aclose()
        if database_manager is not None:
            await database_manager.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.state.performance_diagnostics_enabled = settings.performance_diagnostics_enabled
app.state.performance_server_timing_enabled = settings.performance_server_timing_enabled
app.state.performance_log_slow_request_ms = settings.performance_log_slow_request_ms
app.state.performance_recorder = PerformanceRecorder()
app.state.performance_isolated_cache = False
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
)
app.add_middleware(PerformanceMiddleware)
app.include_router(api_router, prefix=settings.api_prefix)
