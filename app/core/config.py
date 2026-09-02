from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ORCA Base API"
    app_env: str = "development"
    api_prefix: str = "/v1"

    redis_enabled: bool = False
    redis_url: str | None = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300

    http_connect_timeout: float = 5.0
    http_read_timeout: float = 20.0
    http_retry_attempts: int = 3

    incois_base_url: str = "https://incois.gov.in/MarineFisheries"
    pfz_fetch_concurrency: int = Field(default=4, ge=1, le=20)
    pfz_cache_ttl_seconds: int = Field(default=1800, ge=1, le=86400)
    pfz_stale_ttl_seconds: int = Field(default=86400, ge=1, le=604800)

    copernicus_sst_enabled: bool = False
    copernicus_sst_dataset_id: str = Field(
        default="METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2",
        min_length=1,
    )
    copernicus_sst_variable: str = Field(default="analysed_sst", min_length=1)
    copernicus_sst_search_radius_km: float = Field(default=50.0, gt=0, le=500)
    copernicus_sst_lookback_days: int = Field(default=3, ge=1, le=30)
    copernicus_sst_cache_ttl_seconds: int = Field(
        default=21600,
        ge=1,
        le=604800,
    )
    copernicus_sst_stale_ttl_seconds: int = Field(
        default=86400,
        ge=1,
        le=2592000,
    )

    copernicus_waves_enabled: bool = False
    copernicus_waves_dataset_id: str = Field(
        default="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
        min_length=1,
    )
    copernicus_waves_height_variable: str = Field(default="VHM0", min_length=1)
    copernicus_waves_period_variable: str = Field(default="VTM02", min_length=1)
    copernicus_waves_direction_variable: str = Field(default="VMDR", min_length=1)
    copernicus_waves_search_radius_km: float = Field(default=50.0, gt=0, le=500)
    copernicus_waves_time_tolerance_hours: int = Field(default=3, ge=1, le=24)
    copernicus_waves_cache_ttl_seconds: int = Field(
        default=3600,
        ge=1,
        le=604800,
    )
    copernicus_waves_stale_ttl_seconds: int = Field(
        default=21600,
        ge=1,
        le=2592000,
    )
    copernicus_waves_cycle_cache_ttl_seconds: int = Field(
        default=3600,
        ge=1,
        le=86400,
    )

    copernicus_wind_enabled: bool = False
    copernicus_wind_dataset_id: str = Field(
        default="cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H",
        min_length=1,
    )
    copernicus_wind_eastward_variable: str = Field(
        default="eastward_wind",
        min_length=1,
    )
    copernicus_wind_northward_variable: str = Field(
        default="northward_wind",
        min_length=1,
    )
    copernicus_wind_search_radius_km: float = Field(default=50.0, gt=0, le=500)
    copernicus_wind_max_age_hours: float = Field(default=30.0, gt=0, le=168)
    copernicus_wind_cache_ttl_seconds: int = Field(
        default=3600,
        ge=1,
        le=604800,
    )
    copernicus_wind_stale_ttl_seconds: int = Field(
        default=21600,
        ge=1,
        le=2592000,
    )

    chlorophyll_enabled: bool = False
    chlorophyll_dataset_id: str = Field(
        default="cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
        min_length=1,
    )
    chlorophyll_dataset_version: str = Field(default="202311", min_length=1)
    chlorophyll_variable: str = Field(default="CHL", min_length=1)
    chlorophyll_uncertainty_variable: str = Field(
        default="CHL_uncertainty",
        min_length=1,
    )
    chlorophyll_flags_variable: str = Field(default="flags", min_length=1)
    chlorophyll_max_radius_km: float = Field(default=10.0, gt=0, le=100)
    chlorophyll_cache_ttl_seconds: int = Field(
        default=21600,
        ge=1,
        le=604800,
    )
    chlorophyll_max_stale_seconds: int = Field(
        default=86400,
        ge=1,
        le=2592000,
    )
    chlorophyll_freshness_hours: float = Field(default=72.0, gt=0, le=720)
    chlorophyll_high_uncertainty_percent: float = Field(
        default=50.0,
        ge=0,
        le=100,
    )

    copernicus_currents_enabled: bool = False
    copernicus_currents_dataset_id: str = Field(
        default="cmems_mod_glo_phy_anfc_merged-uv_PT1H-i", min_length=1
    )
    copernicus_currents_dataset_version: str = Field(default="202211", min_length=1)
    copernicus_currents_static_dataset_id: str = Field(
        default="cmems_mod_glo_phy_anfc_0.083deg_static", min_length=1
    )
    copernicus_currents_static_dataset_version: str = Field(
        default="202211", min_length=1
    )
    copernicus_currents_max_radius_km: float = Field(default=15.0, gt=0, le=100)
    copernicus_currents_calm_threshold_mps: float = Field(default=0.001, ge=0, le=1)
    copernicus_currents_time_tolerance_hours: float = Field(default=1.0, gt=0, le=6)
    copernicus_currents_component_tolerance_mps: float = Field(
        default=0.002, gt=0, le=0.1
    )
    copernicus_currents_cache_ttl_seconds: int = Field(default=1800, ge=1, le=86400)
    copernicus_currents_stale_ttl_seconds: int = Field(default=21600, ge=1, le=604800)
    copernicus_currents_max_horizon_hours: int = Field(default=240, ge=1, le=240)

    copernicus_tides_enabled: bool = False
    copernicus_tides_dataset_id: str = Field(
        default="cmems_mod_glo_phy_anfc_merged-sl_PT1H-i", min_length=1
    )
    copernicus_tides_dataset_version: str = Field(default="202411", min_length=1)
    copernicus_tides_static_dataset_id: str = Field(
        default="cmems_mod_glo_phy_anfc_0.083deg_static", min_length=1
    )
    copernicus_tides_static_dataset_version: str = Field(default="202211", min_length=1)
    copernicus_tides_static_dataset_part: str = Field(default="bathy", min_length=1)
    copernicus_tides_max_radius_km: float = Field(default=10.0, gt=0, le=100)
    copernicus_tides_static_alignment_tolerance_km: float = Field(default=1.0, gt=0, le=10)
    copernicus_tides_time_tolerance_hours: float = Field(default=1.0, gt=0, le=6)
    copernicus_tides_decomposition_tolerance_m: float = Field(default=0.005, gt=0, le=1)
    copernicus_tides_cache_ttl_seconds: int = Field(default=1800, ge=1, le=86400)
    copernicus_tides_stale_ttl_seconds: int = Field(default=21600, ge=1, le=604800)
    copernicus_tides_static_cache_ttl_seconds: int = Field(default=604800, ge=3600, le=2592000)
    copernicus_tides_metadata_cache_ttl_seconds: int = Field(default=3600, ge=1, le=86400)
    copernicus_tides_metadata_unavailable_ttl_seconds: int = Field(default=600, ge=1, le=86400)
    copernicus_tides_availability_ttl_seconds: int = Field(default=600, ge=1, le=86400)
    copernicus_tides_event_cache_ttl_seconds: int = Field(default=1800, ge=1, le=86400)
    copernicus_tides_minimum_consecutive_samples: int = Field(default=3, ge=3, le=12)
    copernicus_tides_max_horizon_hours: int = Field(default=240, ge=1, le=240)

    ecmwf_wind_enabled: bool = False
    ecmwf_wind_model: str = "ifs"
    ecmwf_wind_resolution: str = "0p25"
    ecmwf_wind_u_parameter: str = "10u"
    ecmwf_wind_v_parameter: str = "10v"
    ecmwf_wind_primary_source: str = "ecmwf"
    ecmwf_wind_fallback_source: str = "aws"
    ecmwf_wind_max_retries: int = Field(default=2, ge=0, le=5)
    ecmwf_wind_retry_initial_seconds: float = Field(default=1.0, gt=0, le=10)
    ecmwf_wind_retry_max_seconds: float = Field(default=8.0, gt=0, le=30)
    ecmwf_wind_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    ecmwf_wind_read_timeout_seconds: float = Field(default=50.0, gt=0, le=300)
    ecmwf_wind_calm_threshold_mps: float = Field(default=0.001, ge=0, le=1)
    ecmwf_wind_max_horizon_hours: int = Field(default=360, ge=144, le=360)
    ecmwf_wind_cycle_cache_ttl_seconds: int = Field(default=900, ge=1, le=86400)
    ecmwf_wind_cycle_stale_ttl_seconds: int = Field(
        default=3600, ge=1, le=172800
    )
    ecmwf_wind_field_cache_ttl_seconds: int = Field(
        default=3600, ge=1, le=86400
    )
    ecmwf_wind_field_cache_max_entries: int = Field(default=3, ge=1, le=12)
    ecmwf_wind_field_cache_max_bytes: int = Field(
        default=67108864, ge=1048576, le=536870912
    )
    ecmwf_wind_point_cache_ttl_seconds: int = Field(
        default=3600, ge=1, le=86400
    )
    ecmwf_wind_point_stale_ttl_seconds: int = Field(
        default=21600, ge=1, le=604800
    )
    ecmwf_wind_max_stale_cycle_age_hours: float = Field(
        default=24.0, gt=0, le=72
    )
    ecmwf_wind_max_download_bytes: int = Field(
        default=10485760, ge=1048576, le=104857600
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def redis_configuration_is_complete(self) -> "Settings":
        if self.redis_enabled and not (self.redis_url or "").strip():
            raise ValueError(
                "REDIS_URL is required when REDIS_ENABLED=true"
            )
        return self

    @model_validator(mode="after")
    def pfz_cache_windows_are_ordered(self) -> "Settings":
        if self.pfz_stale_ttl_seconds < self.pfz_cache_ttl_seconds:
            raise ValueError(
                "PFZ_STALE_TTL_SECONDS must be greater than or equal to "
                "PFZ_CACHE_TTL_SECONDS"
            )
        return self

    @model_validator(mode="after")
    def sst_cache_windows_are_ordered(self) -> "Settings":
        if (
            self.copernicus_sst_stale_ttl_seconds
            < self.copernicus_sst_cache_ttl_seconds
        ):
            raise ValueError(
                "COPERNICUS_SST_STALE_TTL_SECONDS must be greater than or "
                "equal to COPERNICUS_SST_CACHE_TTL_SECONDS"
            )
        return self

    @model_validator(mode="after")
    def wave_cache_windows_are_ordered(self) -> "Settings":
        if (
            self.copernicus_waves_stale_ttl_seconds
            < self.copernicus_waves_cache_ttl_seconds
        ):
            raise ValueError(
                "COPERNICUS_WAVES_STALE_TTL_SECONDS must be greater than or "
                "equal to COPERNICUS_WAVES_CACHE_TTL_SECONDS"
            )
        return self

    @model_validator(mode="after")
    def wind_cache_windows_are_ordered(self) -> "Settings":
        if (
            self.copernicus_wind_stale_ttl_seconds
            < self.copernicus_wind_cache_ttl_seconds
        ):
            raise ValueError(
                "COPERNICUS_WIND_STALE_TTL_SECONDS must be greater than or "
                "equal to COPERNICUS_WIND_CACHE_TTL_SECONDS"
            )
        return self

    @model_validator(mode="after")
    def chlorophyll_cache_windows_are_ordered(self) -> "Settings":
        if (
            self.chlorophyll_max_stale_seconds
            < self.chlorophyll_cache_ttl_seconds
        ):
            raise ValueError(
                "CHLOROPHYLL_MAX_STALE_SECONDS must be greater than or equal "
                "to CHLOROPHYLL_CACHE_TTL_SECONDS"
            )
        return self

    @model_validator(mode="after")
    def current_cache_windows_are_ordered(self) -> "Settings":
        if (
            self.copernicus_currents_stale_ttl_seconds
            < self.copernicus_currents_cache_ttl_seconds
        ):
            raise ValueError(
                "COPERNICUS_CURRENTS_STALE_TTL_SECONDS must be greater than or "
                "equal to COPERNICUS_CURRENTS_CACHE_TTL_SECONDS"
            )
        return self

    @model_validator(mode="after")
    def tide_cache_windows_are_ordered(self) -> "Settings":
        if self.copernicus_tides_stale_ttl_seconds < self.copernicus_tides_cache_ttl_seconds:
            raise ValueError(
                "COPERNICUS_TIDES_STALE_TTL_SECONDS must be greater than or equal to COPERNICUS_TIDES_CACHE_TTL_SECONDS"
            )
        return self

    @model_validator(mode="after")
    def ecmwf_configuration_is_valid(self) -> "Settings":
        allowed_sources = {"ecmwf", "aws", "azure", "google"}
        fallback = self.ecmwf_wind_fallback_source.strip().lower()
        primary = self.ecmwf_wind_primary_source.strip().lower()
        if primary not in allowed_sources:
            raise ValueError("ECMWF_WIND_PRIMARY_SOURCE is unsupported")
        if fallback and fallback not in allowed_sources:
            raise ValueError("ECMWF_WIND_FALLBACK_SOURCE is unsupported")
        if fallback and fallback == primary:
            raise ValueError("ECMWF primary and fallback sources must differ")
        if (
            self.ecmwf_wind_model != "ifs"
            or self.ecmwf_wind_resolution != "0p25"
            or self.ecmwf_wind_u_parameter != "10u"
            or self.ecmwf_wind_v_parameter != "10v"
        ):
            raise ValueError("Unsupported ECMWF IFS wind configuration")
        if (
            self.ecmwf_wind_retry_max_seconds
            < self.ecmwf_wind_retry_initial_seconds
        ):
            raise ValueError("ECMWF retry maximum must not be less than initial")
        if (
            self.ecmwf_wind_cycle_stale_ttl_seconds
            < self.ecmwf_wind_cycle_cache_ttl_seconds
        ):
            raise ValueError("ECMWF cycle stale TTL must cover the fresh TTL")
        if (
            self.ecmwf_wind_point_stale_ttl_seconds
            < self.ecmwf_wind_point_cache_ttl_seconds
        ):
            raise ValueError("ECMWF point stale TTL must cover the fresh TTL")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
