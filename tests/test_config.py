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
    assert settings.copernicus_sst_enabled is False
    assert (
        settings.copernicus_sst_dataset_id
        == "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2"
    )
    assert settings.copernicus_sst_variable == "analysed_sst"
    assert settings.copernicus_sst_search_radius_km == 50
    assert settings.copernicus_sst_lookback_days == 3
    assert settings.copernicus_waves_enabled is False
    assert (
        settings.copernicus_waves_dataset_id
        == "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
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
