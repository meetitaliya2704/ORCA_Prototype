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


class SSTSnapshotStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    STALE_REFRESHING = "stale_refreshing"


class SSTSnapshotMetadata(BaseModel):
    status: SSTSnapshotStatus
    snapshot_id: str | None = None
    tile_id: str
    provider_valid_time: datetime
    refreshed_at: datetime
    fresh_until: datetime
    stale_until: datetime
    refresh_job_id: str | None = None
    refresh_blocked_until: datetime | None = None


class SSTSnapshotResponse(SSTResponse):
    snapshot: SSTSnapshotMetadata


class RefreshTileReference(BaseModel):
    id: str


class RefreshAcceptedResponse(BaseModel):
    status: Literal["refreshing"] = "refreshing"
    code: Literal["MARINE_DATA_REFRESH_IN_PROGRESS"] = (
        "MARINE_DATA_REFRESH_IN_PROGRESS"
    )
    source: Literal["sst", "chlorophyll"] = "sst"
    job_id: str
    tile: RefreshTileReference
    retry_after_seconds: int = Field(default=5, ge=1)


class RefreshJobResponse(BaseModel):
    job_id: str
    source: Literal["sst", "chlorophyll"] = "sst"
    tile_id: str
    state: Literal["queued", "running", "succeeded", "partial", "failed", "cancelled"]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempt_count: int = Field(ge=0)
    snapshot_valid_time: datetime | None = None
    error_code: str | None = None
    message: str | None = None
    retryable: bool | None = None
    next_retry_at: datetime | None = None
    retry_after_seconds: int | None = Field(default=5, ge=1)
    snapshot_available: bool


class ChlorophyllCacheStatus(StrEnum):
    FRESH = "fresh"
    REFRESHED = "refreshed"
    STALE = "stale"


class ChlorophyllSamplingQuality(StrEnum):
    EXACT_GRID_CELL = "exact_grid_cell"
    NEAREST_GRID_CELL = "nearest_grid_cell"
    NEAREST_VALID_WATER_CELL = "nearest_valid_water_cell"


class ChlorophyllDataProvenance(StrEnum):
    MULTI_SENSOR_MERGED_SATELLITE_PIXEL = (
        "multi_sensor_merged_satellite_pixel"
    )
    SPACE_TIME_INTERPOLATED_GAP_FILL = "space_time_interpolated_gap_fill"


class ChlorophyllEvidenceQuality(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"


class ChlorophyllValue(BaseModel):
    value: float = Field(ge=0)
    unit: Literal["mg/m³"] = "mg/m³"


class ChlorophyllQualityMetadata(BaseModel):
    flag_value: int = Field(ge=0)
    land: Literal[False] = False
    interpolated: bool
    uncertainty_percent: float | None = Field(default=None, ge=0)
    evidence_quality: ChlorophyllEvidenceQuality


class ChlorophyllResponse(BaseModel):
    provider: Literal["Copernicus Marine"] = "Copernicus Marine"
    product_id: Literal["OCEANCOLOUR_GLO_BGC_L4_NRT_009_102"] = (
        "OCEANCOLOUR_GLO_BGC_L4_NRT_009_102"
    )
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    source_classification: Literal["satellite_derived_multi_sensor"] = (
        "satellite_derived_multi_sensor"
    )
    processing_level: Literal["L4"] = "L4"
    gap_filled_product: Literal[True] = True
    requested_location: SSTLocation
    sampled_location: SSTLocation
    sample_distance_km: float = Field(ge=0)
    chlorophyll_a: ChlorophyllValue
    analysis_time: datetime
    retrieved_at: datetime
    spatial_resolution_km: float = Field(gt=0)
    sampling_quality: ChlorophyllSamplingQuality
    data_provenance: ChlorophyllDataProvenance
    quality: ChlorophyllQualityMetadata
    cache_status: ChlorophyllCacheStatus
    warnings: list[str] = Field(default_factory=list)
    attribution: Literal[
        "Generated using CMEMS Products, production centre ACRI-ST"
    ] = "Generated using CMEMS Products, production centre ACRI-ST"
    notice: Literal[
        "Satellite-derived chlorophyll-a is an environmental indicator and "
        "does not independently confirm fish presence."
    ] = (
        "Satellite-derived chlorophyll-a is an environmental indicator and "
        "does not independently confirm fish presence."
    )

    @model_validator(mode="after")
    def chlorophyll_timestamps_are_timezone_aware(self) -> "ChlorophyllResponse":
        values = (self.analysis_time, self.retrieved_at)
        if any(value.tzinfo is None or value.utcoffset() is None for value in values):
            raise ValueError("chlorophyll timestamps must be timezone-aware")
        return self


class ChlorophyllSnapshotResponse(ChlorophyllResponse):
    snapshot: SSTSnapshotMetadata


class CurrentCacheStatus(StrEnum):
    FRESH = "fresh"
    REFRESHED = "refreshed"
    STALE = "stale"


class CurrentSamplingQuality(StrEnum):
    EXACT_GRID_CELL = "exact_grid_cell"
    NEAREST_GRID_CELL = "nearest_grid_cell"
    NEAREST_VALID_WATER_CELL = "nearest_valid_water_cell"


class CurrentEvidenceQuality(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"


class CurrentTimeClassification(StrEnum):
    ANALYSIS = "analysis"
    FORECAST = "forecast"
    UNKNOWN = "unknown"


class CurrentSourceClassification(BaseModel):
    category: Literal["numerical_ocean_model"] = "numerical_ocean_model"
    temporal_mode: Literal["analysis_or_forecast"] = "analysis_or_forecast"
    quantity: Literal["total_surface_current"] = "total_surface_current"
    observation: Literal[False] = False


class CurrentVector(BaseModel):
    eastward_mps: float | None
    northward_mps: float | None


class CurrentTotalVector(CurrentVector):
    eastward_mps: float
    northward_mps: float
    speed_mps: float = Field(ge=0)
    direction_toward_deg: float | None = Field(default=None, ge=0, lt=360)
    direction_toward_compass: Literal[
        "N", "NE", "E", "SE", "S", "SW", "W", "NW", "CALM"
    ]


class CurrentComponents(BaseModel):
    general_circulation: CurrentVector
    tide: CurrentVector
    stokes_drift: CurrentVector


class CurrentResidual(BaseModel):
    eastward: float | None
    northward: float | None


class CurrentResponse(BaseModel):
    provider: Literal["Copernicus Marine Service"] = "Copernicus Marine Service"
    product_id: Literal["GLOBAL_ANALYSISFORECAST_PHY_001_024"] = (
        "GLOBAL_ANALYSISFORECAST_PHY_001_024"
    )
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    source_classification: CurrentSourceClassification = Field(
        default_factory=CurrentSourceClassification
    )
    requested_location: SSTLocation
    sampled_location: SSTLocation
    distance_km: float = Field(ge=0)
    sampled_depth_m: float = Field(gt=0)
    depth_selection: Literal["fixed_surface_level"] = "fixed_surface_level"
    total_current: CurrentTotalVector
    components: CurrentComponents
    decomposition_complete: bool
    component_residual_mps: CurrentResidual
    time_classification: CurrentTimeClassification
    valid_time: datetime
    forecast_reference_time: datetime | None = None
    forecast_lead_hours: float | None = Field(default=None, ge=0)
    analysis_or_retrieval_time: datetime
    sampling_quality: CurrentSamplingQuality
    evidence_quality: CurrentEvidenceQuality
    cache_status: CurrentCacheStatus
    warnings: list[str] = Field(default_factory=list)
    attribution: Literal["Copernicus Marine Service"] = "Copernicus Marine Service"
    notice: Literal[
        "Numerical model estimate for decision support; not certified navigation instructions."
    ] = "Numerical model estimate for decision support; not certified navigation instructions."

    @model_validator(mode="after")
    def current_response_is_consistent(self) -> "CurrentResponse":
        timestamps = [self.valid_time, self.analysis_or_retrieval_time]
        if self.forecast_reference_time is not None:
            timestamps.append(self.forecast_reference_time)
        if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
            raise ValueError("current timestamps must be timezone-aware")
        if self.time_classification == CurrentTimeClassification.UNKNOWN and (
            self.forecast_reference_time is not None
            or self.forecast_lead_hours is not None
        ):
            raise ValueError("unknown current classification cannot include forecast metadata")
        return self


class TideCacheStatus(StrEnum):
    FRESH = "fresh"
    REFRESHED = "refreshed"
    STALE = "stale"


class TideSamplingQuality(StrEnum):
    EXACT_GRID_CELL = "exact_grid_cell"
    NEAREST_GRID_CELL = "nearest_grid_cell"
    NEAREST_VALID_WATER_CELL = "nearest_valid_water_cell"


class TideEvidenceQuality(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"


class TideTimeClassification(StrEnum):
    ANALYSIS = "analysis"
    FORECAST = "forecast"
    UNKNOWN = "unknown"


class SeaLevelSourceClassification(BaseModel):
    category: Literal["numerical_ocean_model"] = "numerical_ocean_model"
    quantity: Literal["sea_level_and_astronomical_tide"] = (
        "sea_level_and_astronomical_tide"
    )
    observation: Literal[False] = False
    harbour_specific: Literal[False] = False
    chart_datum: Literal[False] = False


class SeaLevelComponents(BaseModel):
    non_tidal_dynamic_sea_level_m: float
    inverse_barometer_m: float
    global_mean_steric_variation_m: float
    global_mean_mass_variation_m: float
    tide_loading_m: float


class SeaLevelResponse(BaseModel):
    provider: Literal["Copernicus Marine Service"] = "Copernicus Marine Service"
    product_id: Literal["GLOBAL_ANALYSISFORECAST_PHY_001_024"] = (
        "GLOBAL_ANALYSISFORECAST_PHY_001_024"
    )
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    source_classification: SeaLevelSourceClassification = Field(
        default_factory=SeaLevelSourceClassification
    )
    requested_location: SSTLocation
    sampled_location: SSTLocation
    distance_km: float = Field(ge=0)
    bathymetry_m: float | None = Field(default=None, ge=0)
    provider_surface_level_coordinate_m: float = Field(ge=0)
    depth_selection: Literal["fixed_surface_level"] = "fixed_surface_level"
    valid_time: datetime
    time_classification: TideTimeClassification
    forecast_reference_time: datetime | None = None
    forecast_lead_hours: float | None = Field(default=None, ge=0)
    astronomical_tide_elevation_m: float
    total_modelled_sea_level_m: float
    components: SeaLevelComponents
    reconstructed_total_sea_level_m: float
    decomposition_residual_m: float
    sampling_quality: TideSamplingQuality
    model_evidence_quality: TideEvidenceQuality
    spatial_representativeness: TideEvidenceQuality
    decomposition_evidence_quality: TideEvidenceQuality
    cache_status: TideCacheStatus
    retrieved_at: datetime
    warnings: list[str] = Field(default_factory=list)
    attribution: Literal["E.U. Copernicus Marine Service Information"] = (
        "E.U. Copernicus Marine Service Information"
    )
    notice: Literal[
        "Numerical model estimate; not a harbour tide table, chart-datum height or certified navigation instruction."
    ] = "Numerical model estimate; not a harbour tide table, chart-datum height or certified navigation instruction."

    @model_validator(mode="after")
    def sea_level_time_metadata_is_consistent(self) -> "SeaLevelResponse":
        if self.valid_time.tzinfo is None or self.retrieved_at.tzinfo is None:
            raise ValueError("sea-level timestamps must be timezone-aware")
        if self.time_classification == TideTimeClassification.UNKNOWN:
            if self.forecast_reference_time is not None or self.forecast_lead_hours is not None:
                raise ValueError("unknown time classification cannot include forecast metadata")
        return self


class SeaLevelEvent(BaseModel):
    event_type: Literal["high", "low"]
    provider_sample_time: datetime
    provider_sample_height_m: float
    estimated_time: datetime | None = None
    estimated_height_m: float | None = None
    time_is_interpolated: bool
    interpolation_method: Literal["three_point_quadratic"] | None = None
    provider_cadence_minutes: Literal[60] = 60
    timing_uncertainty_minutes_at_least: Literal[60] = 60


class SeaLevelRequestedWindow(BaseModel):
    start: datetime
    end: datetime
    duration_hours: int = Field(ge=24, le=72)


class SeaLevelProviderWindow(BaseModel):
    start: datetime
    end: datetime
    cadence_minutes: Literal[60] = 60
    sample_count: int = Field(ge=3)
    has_left_padding: Literal[True] = True
    has_right_padding: Literal[True] = True


class SeaLevelEventsResponse(BaseModel):
    provider: Literal["Copernicus Marine Service"] = "Copernicus Marine Service"
    product_id: Literal["GLOBAL_ANALYSISFORECAST_PHY_001_024"] = (
        "GLOBAL_ANALYSISFORECAST_PHY_001_024"
    )
    dataset_id: str
    dataset_version: str
    source_classification: SeaLevelSourceClassification = Field(
        default_factory=SeaLevelSourceClassification
    )
    requested_location: SSTLocation
    sampled_location: SSTLocation
    distance_km: float = Field(ge=0)
    bathymetry_m: float | None = Field(default=None, ge=0)
    provider_surface_level_coordinate_m: float = Field(ge=0)
    requested_window: SeaLevelRequestedWindow
    provider_window: SeaLevelProviderWindow
    astronomical_tide_events: list[SeaLevelEvent]
    total_sea_level_extrema: list[SeaLevelEvent]
    sampling_quality: TideSamplingQuality
    spatial_representativeness: TideEvidenceQuality
    cache_status: TideCacheStatus
    retrieved_at: datetime
    warnings: list[str] = Field(default_factory=list)
    attribution: Literal["E.U. Copernicus Marine Service Information"] = (
        "E.U. Copernicus Marine Service Information"
    )
    notice: Literal[
        "Estimated extrema from hourly numerical model values; not a harbour tide table, chart-datum height or certified navigation instruction."
    ] = "Estimated extrema from hourly numerical model values; not a harbour tide table, chart-datum height or certified navigation instruction."


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
