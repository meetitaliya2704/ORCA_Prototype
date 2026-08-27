from functools import lru_cache

from pydantic import model_validator
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
    pfz_sector_codes: str = "SEC001,SEC002"
    pfz_session_attempts: int = 2

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

    @property
    def configured_pfz_sectors(self) -> tuple[str, ...]:
        return tuple(
            sector.strip().upper()
            for sector in self.pfz_sector_codes.split(",")
            if sector.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
