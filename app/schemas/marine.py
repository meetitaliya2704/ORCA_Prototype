from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator


class SourceStatus(StrEnum):
    FRESH = "fresh"
    CACHED = "cached"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    STALE = "stale"


class SourceResult(BaseModel):
    source: str
    status: SourceStatus
    data: dict[str, Any] | None = None
    error: str | None = None
    fetched_at: datetime | None = None
    cached: bool = False


class MarineConditionsResponse(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    generated_at: datetime
    sources: dict[str, SourceResult]
    warning: str = (
        "Prototype decision support only; verify official marine advisories."
    )


def _timezone_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("at must include a timezone offset")
    return value.astimezone(UTC)


SSTQueryTime = Annotated[datetime, AfterValidator(_timezone_aware_utc)]


class SSTLocation(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SSTSourceMetadata(BaseModel):
    name: Literal["Copernicus Marine"] = "Copernicus Marine"
    product_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    variable: str = Field(min_length=1)


class SSTCacheStatus(StrEnum):
    FRESH = "fresh"
    REFRESHED = "refreshed"
    STALE = "stale"


class SSTQuality(StrEnum):
    EXACT_GRID_CELL = "exact_grid_cell"
    NEAREST_VALID_OCEAN_CELL = "nearest_valid_ocean_cell"


class SSTResponse(BaseModel):
    variable: Literal["SST"] = "SST"
    requested_location: SSTLocation
    sampled_location: SSTLocation
    sample_distance_km: float = Field(ge=0)
    value: float
    unit: Literal["°C"] = "°C"
    source_value: float
    source_unit: Literal["K"] = "K"
    analysis_time: datetime
    retrieved_at: datetime
    source: SSTSourceMetadata
    quality: SSTQuality
    cache_status: SSTCacheStatus
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def timestamps_are_timezone_aware(self) -> "SSTResponse":
        for field_name, value in (
            ("analysis_time", self.analysis_time),
            ("retrieved_at", self.retrieved_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        return self
