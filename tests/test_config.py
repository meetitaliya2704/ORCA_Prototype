import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import cache as cache_module
from app.services.cache import RedisConfigurationError, RedisJsonCache


def test_cors_origins_are_explicit_normalized_and_deduplicated():
    settings = Settings(
        _env_file=None,
        cors_allowed_origins=[
            "http://localhost:3000/",
            "http://localhost:3000",
            "https://orca.example.org",
        ],
    )
    assert settings.cors_allowed_origins == [
        "http://localhost:3000",
        "https://orca.example.org",
    ]


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "file:///tmp/orca",
        "https://orca.example.org/path",
        "https://user:secret@orca.example.org",
    ],
)
def test_unsafe_cors_origins_are_rejected(origin):
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        Settings(_env_file=None, cors_allowed_origins=[origin])


def test_database_configuration_is_optional_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_enabled is False
    assert settings.database_url is None
    assert settings.database_pool_size == 3
    assert settings.database_max_overflow == 2
    assert settings.assistant_enabled is False
    assert settings.assistant_gemini_routing_enabled is False
    assert settings.assistant_model == "gemini-3.7-flash"
    assert settings.google_api_key is None
    assert not hasattr(settings, "pfz_sector_codes")
    assert settings.redis_enabled is False
    assert settings.pfz_fetch_concurrency == 4
    assert settings.pfz_cache_ttl_seconds == 1800
    assert settings.pfz_stale_ttl_seconds == 86400
    assert settings.performance_diagnostics_enabled is False
    assert settings.performance_server_timing_enabled is False
    assert settings.performance_log_slow_request_ms == 1000
    assert settings.performance_profile_max_provider_concurrency == 2
    assert settings.marine_snapshots_enabled is False
    assert settings.marine_snapshot_tile_size_degrees == 2
    assert settings.marine_snapshot_heavy_concurrency == 2
    assert settings.marine_snapshot_wait_timeout_seconds == 90
    assert settings.marine_snapshot_startup_warm_enabled is False
    assert settings.marine_snapshot_max_stale_seconds == 172800
    assert settings.marine_snapshot_job_retention_seconds == 3600
    assert settings.sst_snapshot_refresh_check_seconds == 21600
    assert settings.sst_snapshot_fresh_seconds == 86400
    assert settings.sst_snapshot_time_lookback_days == 3
    assert settings.sst_snapshot_retryable_base_delay_seconds == 30
    assert settings.sst_snapshot_retryable_max_delay_seconds == 900
    assert settings.sst_snapshot_non_retryable_cooldown_seconds == 900
    assert settings.chlorophyll_snapshots_enabled is False
    assert settings.chlorophyll_snapshot_startup_warm_enabled is False
    assert settings.chlorophyll_snapshot_refresh_check_seconds == 21600
    assert settings.chlorophyll_snapshot_fresh_seconds == 86400
    assert settings.chlorophyll_snapshot_max_stale_seconds == 172800
    assert settings.chlorophyll_snapshot_schema_version == "chlorophyll-snapshot-v1"
    assert settings.marine_snapshot_prewarm_points_json == []
    assert settings.copernicus_sst_enabled is False
    assert settings.copernicus_sst_dataset_id == "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2"
    assert settings.copernicus_sst_variable == "analysed_sst"
    assert settings.copernicus_sst_search_radius_km == 50
    assert settings.copernicus_sst_lookback_days == 3
    assert settings.copernicus_waves_enabled is False
    assert (
        settings.copernicus_waves_dataset_id == "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
    )
    assert settings.copernicus_waves_height_variable == "VHM0"
    assert settings.copernicus_waves_period_variable == "VTM02"
    assert settings.copernicus_waves_direction_variable == "VMDR"
    assert settings.copernicus_waves_search_radius_km == 50
    assert settings.copernicus_waves_time_tolerance_hours == 3
    assert settings.copernicus_wind_enabled is False
    assert (
        settings.copernicus_wind_dataset_id
        == "cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H"
    )
    assert settings.copernicus_wind_eastward_variable == "eastward_wind"
    assert settings.copernicus_wind_northward_variable == "northward_wind"
    assert settings.copernicus_wind_search_radius_km == 50
    assert settings.copernicus_wind_max_age_hours == 30
    assert settings.chlorophyll_enabled is False
    assert (
        settings.chlorophyll_dataset_id
        == "cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D"
    )
    assert settings.chlorophyll_dataset_version == "202311"
    assert settings.chlorophyll_variable == "CHL"
    assert settings.chlorophyll_uncertainty_variable == "CHL_uncertainty"
    assert settings.chlorophyll_flags_variable == "flags"
    assert settings.chlorophyll_max_radius_km == 10
    assert settings.chlorophyll_freshness_hours == 72
    assert settings.chlorophyll_high_uncertainty_percent == 50
    assert settings.copernicus_currents_enabled is False
    assert (
        settings.copernicus_currents_dataset_id
        == "cmems_mod_glo_phy_anfc_merged-uv_PT1H-i"
    )
    assert settings.copernicus_currents_dataset_version == "202211"
    assert settings.copernicus_currents_max_radius_km == 15
    assert settings.copernicus_currents_calm_threshold_mps == 0.001
    assert settings.copernicus_currents_component_tolerance_mps == 0.002
    assert settings.copernicus_tides_enabled is False
    assert (
        settings.copernicus_tides_dataset_id
        == "cmems_mod_glo_phy_anfc_merged-sl_PT1H-i"
    )
    assert settings.copernicus_tides_dataset_version == "202411"
    assert settings.copernicus_tides_max_radius_km == 10
    assert settings.copernicus_tides_static_alignment_tolerance_km == 1
    assert settings.copernicus_tides_decomposition_tolerance_m == 0.005
    assert settings.copernicus_tides_static_cache_ttl_seconds == 604800
    assert settings.copernicus_tides_availability_ttl_seconds == 600
    assert settings.ecmwf_wind_enabled is False
    assert settings.ecmwf_wind_model == "ifs"
    assert settings.ecmwf_wind_resolution == "0p25"
    assert settings.ecmwf_wind_u_parameter == "10u"
    assert settings.ecmwf_wind_v_parameter == "10v"
    assert settings.ecmwf_wind_primary_source == "ecmwf"
    assert settings.ecmwf_wind_fallback_source == "aws"
    assert settings.ecmwf_wind_connect_timeout_seconds == 10
    assert settings.ecmwf_wind_read_timeout_seconds == 50
    assert settings.ecmwf_wind_calm_threshold_mps == 0.001
    assert settings.ecmwf_wind_max_horizon_hours == 360


def test_enabled_assistant_can_run_without_database() -> None:
    settings = Settings(_env_file=None, assistant_enabled=True, database_enabled=False)
    assert settings.assistant_enabled is True
    assert settings.database_enabled is False


def test_gemini_router_requires_backend_key() -> None:
    with pytest.raises(ValidationError, match="GOOGLE_API_KEY"):
        Settings(
            _env_file=None,
            database_enabled=True,
            database_url="postgresql://host/database",
            assistant_enabled=True,
            assistant_gemini_routing_enabled=True,
        )


def test_enabled_redis_requires_a_url() -> None:
    with pytest.raises(ValidationError, match="REDIS_URL is required"):
        Settings(
            _env_file=None,
            redis_enabled=True,
            redis_url="",
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"performance_log_slow_request_ms": -1},
        {"performance_profile_max_provider_concurrency": 0},
        {"performance_profile_max_provider_concurrency": 9},
    ],
)
def test_performance_diagnostics_configuration_is_bounded(overrides) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"marine_snapshot_tile_size_degrees": 0},
        {"marine_snapshot_heavy_concurrency": 0},
        {"marine_snapshot_wait_timeout_seconds": 0},
        {"marine_snapshot_scheduler_check_seconds": 0},
        {"sst_snapshot_time_lookback_days": 0},
        {"sst_snapshot_retryable_base_delay_seconds": 0},
        {"sst_snapshot_non_retryable_cooldown_seconds": 0},
    ],
)
def test_snapshot_configuration_is_bounded(overrides) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_snapshot_stale_window_must_cover_fresh_window() -> None:
    with pytest.raises(ValidationError, match="MARINE_SNAPSHOT_MAX_STALE_SECONDS"):
        Settings(
            _env_file=None,
            sst_snapshot_fresh_seconds=100,
            marine_snapshot_max_stale_seconds=99,
        )

    with pytest.raises(
        ValidationError, match="SST_SNAPSHOT_RETRYABLE_MAX_DELAY_SECONDS"
    ):
        Settings(
            _env_file=None,
            sst_snapshot_retryable_base_delay_seconds=31,
            sst_snapshot_retryable_max_delay_seconds=30,
        )


def test_snapshot_prewarm_points_are_strictly_validated() -> None:
    settings = Settings(
        _env_file=None,
        marine_snapshot_prewarm_points_json=[{"latitude": 18.025, "longitude": 70.525}],
    )
    assert settings.marine_snapshot_prewarm_points_json[0].latitude == 18.025
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            marine_snapshot_prewarm_points_json=[{"latitude": 91, "longitude": 0}],
        )


def test_tide_cache_ttls_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="COPERNICUS_TIDES_STALE_TTL_SECONDS"):
        Settings(
            _env_file=None,
            copernicus_tides_cache_ttl_seconds=60,
            copernicus_tides_stale_ttl_seconds=30,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"copernicus_tides_max_radius_km": 0},
        {"copernicus_tides_static_alignment_tolerance_km": 0},
        {"copernicus_tides_time_tolerance_hours": 0},
        {"copernicus_tides_decomposition_tolerance_m": 0},
        {"copernicus_tides_minimum_consecutive_samples": 2},
        {"copernicus_tides_availability_ttl_seconds": 0},
    ],
)
def test_tide_configuration_is_bounded(overrides) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


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


def test_sst_cache_ttls_must_be_ordered() -> None:
    with pytest.raises(
        ValidationError,
        match="COPERNICUS_SST_STALE_TTL_SECONDS must be greater",
    ):
        Settings(
            _env_file=None,
            copernicus_sst_cache_ttl_seconds=60,
            copernicus_sst_stale_ttl_seconds=30,
        )


@pytest.mark.parametrize("radius", [0, 501])
def test_sst_search_radius_is_bounded(radius: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, copernicus_sst_search_radius_km=radius)


def test_wave_cache_ttls_must_be_ordered() -> None:
    with pytest.raises(
        ValidationError,
        match="COPERNICUS_WAVES_STALE_TTL_SECONDS must be greater",
    ):
        Settings(
            _env_file=None,
            copernicus_waves_cache_ttl_seconds=60,
            copernicus_waves_stale_ttl_seconds=30,
        )


@pytest.mark.parametrize("radius", [0, 501])
def test_wave_search_radius_is_bounded(radius: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, copernicus_waves_search_radius_km=radius)


@pytest.mark.parametrize("tolerance", [0, 25])
def test_wave_time_tolerance_is_bounded(tolerance: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            copernicus_waves_time_tolerance_hours=tolerance,
        )


def test_wind_cache_ttls_must_be_ordered() -> None:
    with pytest.raises(
        ValidationError,
        match="COPERNICUS_WIND_STALE_TTL_SECONDS must be greater",
    ):
        Settings(
            _env_file=None,
            copernicus_wind_cache_ttl_seconds=60,
            copernicus_wind_stale_ttl_seconds=30,
        )


@pytest.mark.parametrize("radius", [0, 501])
def test_wind_search_radius_is_bounded(radius: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, copernicus_wind_search_radius_km=radius)


@pytest.mark.parametrize("max_age", [0, 169])
def test_wind_max_age_is_bounded(max_age: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, copernicus_wind_max_age_hours=max_age)


def test_chlorophyll_cache_ttls_must_be_ordered() -> None:
    with pytest.raises(
        ValidationError,
        match="CHLOROPHYLL_MAX_STALE_SECONDS must be greater",
    ):
        Settings(
            _env_file=None,
            chlorophyll_cache_ttl_seconds=60,
            chlorophyll_max_stale_seconds=30,
        )


@pytest.mark.parametrize("radius", [0, 101])
def test_chlorophyll_radius_is_bounded(radius: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chlorophyll_max_radius_km=radius)


@pytest.mark.parametrize("threshold", [-0.01, 100.01])
def test_chlorophyll_uncertainty_threshold_is_bounded(threshold: float) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            chlorophyll_high_uncertainty_percent=threshold,
        )


def test_current_cache_ttls_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="COPERNICUS_CURRENTS_STALE_TTL_SECONDS"):
        Settings(
            _env_file=None,
            copernicus_currents_cache_ttl_seconds=60,
            copernicus_currents_stale_ttl_seconds=30,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"copernicus_currents_max_radius_km": 0},
        {"copernicus_currents_time_tolerance_hours": 0},
        {"copernicus_currents_calm_threshold_mps": -0.1},
        {"copernicus_currents_component_tolerance_mps": 0},
    ],
)
def test_current_configuration_bounds(overrides) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


@pytest.mark.parametrize("source", ["invalid", "ECMWF-SIGNED-URL"])
def test_ecmwf_sources_are_validated(source: str) -> None:
    with pytest.raises(ValidationError, match="PRIMARY_SOURCE"):
        Settings(_env_file=None, ecmwf_wind_primary_source=source)


def test_ecmwf_fallback_may_be_empty_but_must_differ() -> None:
    assert (
        Settings(
            _env_file=None, ecmwf_wind_fallback_source=""
        ).ecmwf_wind_fallback_source
        == ""
    )
    with pytest.raises(ValidationError, match="must differ"):
        Settings(
            _env_file=None,
            ecmwf_wind_primary_source="aws",
            ecmwf_wind_fallback_source="aws",
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"ecmwf_wind_model": "aifs"},
        {"ecmwf_wind_resolution": "0p4"},
        {"ecmwf_wind_u_parameter": "u"},
        {"ecmwf_wind_v_parameter": "v"},
    ],
)
def test_unsupported_ecmwf_product_configuration_is_rejected(overrides) -> None:
    with pytest.raises(ValidationError, match="Unsupported ECMWF"):
        Settings(_env_file=None, **overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"ecmwf_wind_connect_timeout_seconds": 0},
        {"ecmwf_wind_read_timeout_seconds": 0},
        {"ecmwf_wind_calm_threshold_mps": -0.1},
        {"ecmwf_wind_max_horizon_hours": 361},
    ],
)
def test_ecmwf_operational_bounds_are_validated(overrides) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_ecmwf_cache_windows_and_retry_bounds_are_validated() -> None:
    with pytest.raises(ValidationError, match="cycle stale TTL"):
        Settings(
            _env_file=None,
            ecmwf_wind_cycle_cache_ttl_seconds=60,
            ecmwf_wind_cycle_stale_ttl_seconds=30,
        )
    with pytest.raises(ValidationError, match="retry maximum"):
        Settings(
            _env_file=None,
            ecmwf_wind_retry_initial_seconds=5,
            ecmwf_wind_retry_max_seconds=1,
        )
