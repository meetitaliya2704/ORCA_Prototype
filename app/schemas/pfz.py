from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


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

