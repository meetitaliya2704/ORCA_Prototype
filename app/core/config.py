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


@lru_cache
def get_settings() -> Settings:
    return Settings()
