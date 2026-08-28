from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator


class PFZLocation(BaseModel):
    landing_centre: str = Field(min_length=1)
    direction: str | None = None
    bearing_deg: float | None = Field(default=None, ge=0, le=360)
    distance_min_km: float | None = Field(default=None, ge=0)
    distance_max_km: float | None = Field(default=None, ge=0)
    depth_min_m: float | None = Field(default=None, ge=0)
    depth_max_m: float | None = Field(default=None, ge=0)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def ranges_are_ordered(self) -> "PFZLocation":
        pairs = (
            (self.distance_min_km, self.distance_max_km, "distance"),
            (self.depth_min_m, self.depth_max_m, "depth"),
        )
        for minimum, maximum, label in pairs:
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{label} minimum cannot exceed maximum")
        return self


class PFZAdvisory(BaseModel):
    sector_code: str = Field(pattern=r"^SEC\d{3}$")
    region_name: str = Field(min_length=1)
    forecast_date: date
    valid_until: date
    satellite_message: str | None = None
    locations: list[PFZLocation] = Field(min_length=1)
    parse_warnings: list[str] = Field(default_factory=list)
    source: str = "INCOIS"
    source_url: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validity_is_consistent(self) -> "PFZAdvisory":
        if self.valid_until < self.forecast_date:
            raise ValueError("valid_until cannot be before forecast_date")
        return self


class PFZCacheStatus(StrEnum):
    FRESH = "fresh"
    REFRESHED = "refreshed"
    STALE = "stale"


class PFZSnapshotCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class PFZSectorErrorCode(StrEnum):
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    INVALID_PFZ_RESPONSE = "INVALID_PFZ_RESPONSE"


class DiscoveredPFZSector(BaseModel):
    sector_code: str = Field(pattern=r"^SEC\d+$")
    display_label: str


class SuccessfulPFZSector(BaseModel):
    discovered_sector: DiscoveredPFZSector
    advisory: PFZAdvisory


class FailedPFZSector(BaseModel):
    discovered_sector: DiscoveredPFZSector
    code: PFZSectorErrorCode
    message: str = Field(min_length=1)


class PFZSnapshot(BaseModel):
    generated_at: datetime
    retrieved_at: datetime
    discovered_sector_count: int = Field(ge=1)
    successful_sector_count: int = Field(ge=1)
    failed_sector_count: int = Field(ge=0)
    discovered_sectors: list[DiscoveredPFZSector] = Field(min_length=1)
    successful_sectors: list[SuccessfulPFZSector] = Field(min_length=1)
    failed_sectors: list[FailedPFZSector] = Field(default_factory=list)
    total_location_count: int = Field(ge=1)
    completeness: PFZSnapshotCompleteness
    cache_status: PFZCacheStatus
    warnings: list[str] = Field(default_factory=list)
    source_name: str = "INCOIS"
    source_url: str

    @model_validator(mode="after")
    def counts_and_completeness_are_consistent(self) -> "PFZSnapshot":
        if self.discovered_sector_count != len(self.discovered_sectors):
            raise ValueError("discovered sector count is inconsistent")
        if self.successful_sector_count != len(self.successful_sectors):
            raise ValueError("successful sector count is inconsistent")
        if self.failed_sector_count != len(self.failed_sectors):
            raise ValueError("failed sector count is inconsistent")
        if self.discovered_sector_count != (
            self.successful_sector_count + self.failed_sector_count
        ):
            raise ValueError("sector result counts are inconsistent")

        location_count = sum(
            len(result.advisory.locations) for result in self.successful_sectors
        )
        if self.total_location_count != location_count:
            raise ValueError("PFZ location count is inconsistent")

        expected = (
            PFZSnapshotCompleteness.COMPLETE
            if self.failed_sector_count == 0
            else PFZSnapshotCompleteness.PARTIAL
        )
        if self.completeness != expected:
            raise ValueError("snapshot completeness is inconsistent")
        return self


def _timezone_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("at must include a timezone offset")
    return value.astimezone(UTC)


TimezoneAwareUTCDateTime = Annotated[datetime, AfterValidator(_timezone_aware_utc)]


class NearestPFZQuery(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    at: TimezoneAwareUTCDateTime | None = None


class NearestPFZQueryResult(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    at: datetime


class PFZValueRange(BaseModel):
    minimum: float | None = Field(default=None, ge=0)
    maximum: float | None = Field(default=None, ge=0)


class NearestPFZLocation(BaseModel):
    sector_code: str = Field(pattern=r"^SEC\d+$")
    region_name: str = Field(min_length=1)
    landing_centre: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    distance_km: float = Field(ge=0)
    bearing_deg: float = Field(ge=0, lt=360)
    direction: Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    distance_from_coast_km: PFZValueRange
    depth_m: PFZValueRange


class PFZSourceMetadata(BaseModel):
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    retrieved_at: datetime


class PFZGeoJSONGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class PFZGeoJSONProperties(BaseModel):
    sector_code: str
    region_name: str
    landing_centre: str
    distance_km: float
    bearing_deg: float
    direction: Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class PFZGeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: PFZGeoJSONGeometry
    properties: PFZGeoJSONProperties


class NearestPFZResponse(BaseModel):
    query: NearestPFZQueryResult
    nearest_pfz: NearestPFZLocation
    valid_from: datetime
    valid_until: datetime
    forecast_date: date
    source: PFZSourceMetadata
    cache_status: PFZCacheStatus
    completeness: PFZSnapshotCompleteness
    failed_sectors: list[FailedPFZSector] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    geojson: PFZGeoJSONFeature
    notice: str = (
        "Decision-support information; verify current official advisories."
    )

    @model_validator(mode="after")
    def validity_window_is_timezone_aware(self) -> "NearestPFZResponse":
        for field_name, value in (
            ("valid_from", self.valid_from),
            ("valid_until", self.valid_until),
            ("query.at", self.query.at),
            ("source.retrieved_at", self.source.retrieved_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.valid_until < self.valid_from:
            raise ValueError("valid_until cannot be before valid_from")
        return self

