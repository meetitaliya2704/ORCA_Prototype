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


class WaveCacheStatus(StrEnum):
    FRESH = "fresh"
    REFRESHED = "refreshed"
    STALE = "stale"


class WaveQuality(StrEnum):
    EXACT_GRID_CELL = "exact_grid_cell"
    NEAREST_VALID_OCEAN_CELL = "nearest_valid_ocean_cell"


class WaveTimeClassification(StrEnum):
    ANALYSIS = "analysis"
    FORECAST = "forecast"
    UNKNOWN = "unknown"


class WaveValue(BaseModel):
    value: float
    unit: Literal["m", "s", "degree"]


class WaveSourceMetadata(BaseModel):
    name: Literal["Copernicus Marine"] = "Copernicus Marine"
    product_id: Literal["GLOBAL_ANALYSISFORECAST_WAV_001_027"] = (
        "GLOBAL_ANALYSISFORECAST_WAV_001_027"
    )
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    model: Literal["Météo-France MFWAM"] = "Météo-France MFWAM"
    data_type: Literal["numerical_model_analysis_forecast"] = (
        "numerical_model_analysis_forecast"
    )


class WaveResponse(BaseModel):
    requested_location: SSTLocation
    sampled_location: SSTLocation
    sample_distance_km: float = Field(ge=0)
    requested_time: datetime
    valid_time: datetime
    forecast_reference_time: datetime | None = None
    forecast_lead_hours: float | None = None
    time_classification: WaveTimeClassification
    significant_wave_height: WaveValue
    mean_wave_period: WaveValue
    mean_wave_direction_from: WaveValue
    retrieved_at: datetime
    source: WaveSourceMetadata
    quality: WaveQuality
    cache_status: WaveCacheStatus
    warnings: list[str] = Field(default_factory=list)
    notice: Literal[
        "Model-based decision-support data; verify official marine advisories."
    ] = "Model-based decision-support data; verify official marine advisories."

    @model_validator(mode="after")
    def wave_timestamps_are_timezone_aware(self) -> "WaveResponse":
        values = [
            self.requested_time,
            self.valid_time,
            self.retrieved_at,
        ]
        if self.forecast_reference_time is not None:
            values.append(self.forecast_reference_time)
        if any(value.tzinfo is None or value.utcoffset() is None for value in values):
            raise ValueError("wave timestamps must be timezone-aware")
        if (
            self.time_classification == WaveTimeClassification.UNKNOWN
            and (
                self.forecast_reference_time is not None
                or self.forecast_lead_hours is not None
            )
        ):
            raise ValueError("unknown wave time classification cannot include forecast metadata")
        return self


class WindCacheStatus(StrEnum):
    FRESH = "fresh"
    REFRESHED = "refreshed"
    STALE = "stale"


class WindQuality(StrEnum):
    EXACT_GRID_CELL = "exact_grid_cell"
    NEAREST_VALID_GRID_CELL = "nearest_valid_grid_cell"


class WindValue(BaseModel):
    value: float
    unit: Literal["m/s"] = "m/s"


class WindDirectionFrom(BaseModel):
    value: float | None
    unit: Literal["degree"] = "degree"
    compass: Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"] | None


class WindSourceMetadata(BaseModel):
    name: Literal["Copernicus Marine"] = "Copernicus Marine"
    product_id: Literal["WIND_GLO_PHY_L4_NRT_012_004"] = (
        "WIND_GLO_PHY_L4_NRT_012_004"
    )
    dataset_id: str = Field(min_length=1)
    dataset_version: Literal["202207"] = "202207"
    data_type: Literal["near_real_time_blended_analysis"] = (
        "near_real_time_blended_analysis"
    )
    forecast_available: Literal[False] = False


class WindResponse(BaseModel):
    requested_location: SSTLocation
    sampled_location: SSTLocation
    sample_distance_km: float = Field(ge=0)
    requested_time: datetime
    valid_time: datetime
    data_age_hours: float = Field(ge=0)
    eastward_wind: WindValue
    northward_wind: WindValue
    wind_speed: WindValue
    wind_direction_from: WindDirectionFrom
    retrieved_at: datetime
    source: WindSourceMetadata
    quality: WindQuality
    cache_status: WindCacheStatus
    warnings: list[str] = Field(default_factory=list)
    notice: Literal["Recent blended analysis, not a future wind forecast."] = (
        "Recent blended analysis, not a future wind forecast."
    )

    @model_validator(mode="after")
    def wind_response_is_consistent(self) -> "WindResponse":
        values = (self.requested_time, self.valid_time, self.retrieved_at)
        if any(value.tzinfo is None or value.utcoffset() is None for value in values):
            raise ValueError("wind timestamps must be timezone-aware")
        if (self.wind_direction_from.value is None) != (
            self.wind_direction_from.compass is None
        ):
            raise ValueError("wind direction value and compass must both be null")
        return self
