from datetime import UTC, datetime, timedelta
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


class ECMWFWindCacheStatus(StrEnum):
    FRESH = "fresh"
    REFRESHED = "refreshed"
    STALE = "stale"


class ECMWFWindFreshness(StrEnum):
    CURRENT_CYCLE = "current_cycle"
    STALE_CYCLE = "stale_cycle"


class ECMWFWindQuality(StrEnum):
    EXACT_GRID_CELL = "exact_grid_cell"
    NEAREST_VALID_GRID_CELL = "nearest_valid_grid_cell"


class ECMWFWindSourceMetadata(BaseModel):
    provider: Literal["ECMWF"] = "ECMWF"
    model: Literal["IFS"] = "IFS"
    resolution_degrees: Literal[0.25] = 0.25
    classification: Literal["forecast"] = "forecast"
    source_mirror: Literal["ecmwf", "aws", "azure", "google"]
    source_url: Literal["https://www.ecmwf.int/"] = "https://www.ecmwf.int/"
    licence: Literal["CC BY 4.0"] = "CC BY 4.0"
    licence_url: Literal["https://creativecommons.org/licenses/by/4.0/"] = (
        "https://creativecommons.org/licenses/by/4.0/"
    )
    copyright_statement: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    disclaimer: str = Field(min_length=1)
    modification_notice: str = Field(min_length=1)


class ECMWFWindForecastResponse(BaseModel):
    provider: Literal["ECMWF"] = "ECMWF"
    selected_mirror: Literal["ecmwf", "aws", "azure", "google"]
    model: Literal["IFS"] = "IFS"
    resolution_degrees: Literal[0.25] = 0.25
    source_classification: Literal["numerical_forecast"] = "numerical_forecast"
    requested_latitude: float = Field(ge=-90, le=90)
    requested_longitude: float = Field(ge=-180, le=180)
    sampled_latitude: float = Field(ge=-90, le=90)
    sampled_longitude: float = Field(ge=-180, lt=180)
    classification: Literal["forecast"] = "forecast"
    requested_location: SSTLocation
    sampled_location: SSTLocation
    distance_km: float = Field(ge=0)
    eastward_wind_mps: float
    northward_wind_mps: float
    speed_mps: float = Field(ge=0)
    wind_speed_mps: float = Field(ge=0)
    direction_from_degrees: float | None = Field(default=None, ge=0, lt=360)
    wind_direction_from_deg: float | None = Field(default=None, ge=0, lt=360)
    compass_direction_from: (
        Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"] | None
    ) = None
    forecast_reference_time: datetime
    forecast_step: int = Field(ge=0, le=360)
    forecast_lead_hours: int = Field(ge=0, le=360)
    valid_time: datetime
    requested_at: datetime
    requested_time: datetime
    retrieved_at: datetime
    source: ECMWFWindSourceMetadata
    quality: ECMWFWindQuality
    freshness: ECMWFWindFreshness
    cache_status: ECMWFWindCacheStatus
    warnings: list[str] = Field(default_factory=list)
    derived_fields: list[str] = Field(
        default_factory=lambda: [
            "wind_speed_mps",
            "wind_direction_from_deg",
            "compass_direction_from",
            "sampled_location",
            "distance_km",
        ]
    )
    notice: Literal[
        "Numerical atmospheric-model forecast; uncertainty increases with lead time. "
        "Not an observation or navigation advice."
    ] = (
        "Numerical atmospheric-model forecast; uncertainty increases with lead time. "
        "Not an observation or navigation advice."
    )

    @model_validator(mode="before")
    @classmethod
    def populate_explicit_contract_fields(cls, value: Any) -> Any:
        """Accept pre-contract cached records while serializing explicit fields."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        requested = data.get("requested_location") or {}
        sampled = data.get("sampled_location") or {}
        source = data.get("source") or {}
        if isinstance(requested, BaseModel):
            requested = requested.model_dump()
        if isinstance(sampled, BaseModel):
            sampled = sampled.model_dump()
        if isinstance(source, BaseModel):
            source = source.model_dump()
        data.setdefault("selected_mirror", source.get("source_mirror"))
        data.setdefault("requested_latitude", requested.get("latitude"))
        data.setdefault("requested_longitude", requested.get("longitude"))
        data.setdefault("sampled_latitude", sampled.get("latitude"))
        data.setdefault("sampled_longitude", sampled.get("longitude"))
        data.setdefault("speed_mps", data.get("wind_speed_mps"))
        data.setdefault(
            "direction_from_degrees", data.get("wind_direction_from_deg")
        )
        data.setdefault("forecast_step", data.get("forecast_lead_hours"))
        data.setdefault("requested_at", data.get("requested_time"))
        return data

    @model_validator(mode="after")
    def forecast_metadata_is_consistent(self) -> "ECMWFWindForecastResponse":
        timestamps = (
            self.forecast_reference_time,
            self.valid_time,
            self.requested_time,
            self.retrieved_at,
        )
        if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
            raise ValueError("ECMWF forecast timestamps must be timezone-aware")
        expected = self.forecast_reference_time + timedelta(
            hours=self.forecast_lead_hours
        )
        if expected != self.valid_time:
            raise ValueError("forecast reference plus lead must equal valid time")
        if self.forecast_step != self.forecast_lead_hours:
            raise ValueError("forecast step and lead hours must match")
        if self.requested_at != self.requested_time:
            raise ValueError("requested forecast timestamps must match")
        if (
            self.requested_latitude != self.requested_location.latitude
            or self.requested_longitude != self.requested_location.longitude
            or self.sampled_latitude != self.sampled_location.latitude
            or self.sampled_longitude != self.sampled_location.longitude
        ):
            raise ValueError("flat and structured forecast coordinates must match")
        if self.speed_mps != self.wind_speed_mps:
            raise ValueError("forecast speed fields must match")
        if self.direction_from_degrees != self.wind_direction_from_deg:
            raise ValueError("forecast direction fields must match")
        if self.selected_mirror != self.source.source_mirror:
            raise ValueError("selected mirror must match source metadata")
        if (self.wind_direction_from_deg is None) != (
            self.compass_direction_from is None
        ):
            raise ValueError("forecast wind direction and compass must both be null")
        return self
