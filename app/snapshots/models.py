from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SnapshotState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    REFRESHING = "refreshing"
    STALE_REFRESHING = "stale_refreshing"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class RefreshJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RefreshFailureClassification(StrEnum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    REQUEST_RESULT = "request_result"


class SnapshotCoverage(BaseModel):
    model_config = ConfigDict(frozen=True)
    minimum_latitude: float
    maximum_latitude: float
    minimum_longitude: float
    maximum_longitude: float
    antimeridian_wrap: bool = False


class TileKey(BaseModel):
    model_config = ConfigDict(frozen=True)
    latitude_index: int
    longitude_index: int
    tile_size_degrees: float
    minimum_latitude: float
    maximum_latitude: float
    minimum_longitude: float
    maximum_longitude: float
    antimeridian_wrap: bool = False
    tiling_schema_version: str = "sst-tiles-v1"

    @property
    def safe_id(self) -> str:
        size = format(self.tile_size_degrees, ".6g")
        return (
            f"{self.tiling_schema_version}:{size}:"
            f"{self.latitude_index}:{self.longitude_index}"
        )


class SnapshotIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: str
    product_id: str
    dataset_id: str
    dataset_version: str
    variable: str
    variables: tuple[str, ...] = ()
    tile_id: str
    provider_valid_time: datetime
    configuration_identity: str
    schema_version: str = "sst-snapshot-v1"


class SnapshotMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    identity: SnapshotIdentity
    logical_coverage: SnapshotCoverage
    provider_request_coverage: SnapshotCoverage
    retrieved_at: datetime
    stored_at: datetime
    fresh_until: datetime
    stale_until: datetime
    last_successful_refresh_id: str
    provider_warnings: tuple[str, ...] = ()


class SSTRegionalCell(BaseModel):
    model_config = ConfigDict(frozen=True)
    latitude: float
    longitude: float
    value_celsius: float | None
    source_value_kelvin: float | None


class SSTRegionalPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    latitudes: tuple[float, ...]
    longitudes: tuple[float, ...]
    cells: tuple[SSTRegionalCell, ...]
    provider_valid_time: datetime
    product_id: str
    dataset_id: str
    dataset_version: str
    variable: str


class ChlorophyllRegionalCell(BaseModel):
    model_config = ConfigDict(frozen=True)
    latitude: float
    longitude: float
    chlorophyll_mg_m3: float | None
    uncertainty_percent: float | None
    flag_value: int | None


class ChlorophyllRegionalPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    latitudes: tuple[float, ...]
    longitudes: tuple[float, ...]
    cells: tuple[ChlorophyllRegionalCell, ...]
    provider_valid_time: datetime
    product_id: str
    dataset_id: str
    dataset_version: str
    chlorophyll_variable: str
    uncertainty_variable: str
    flags_variable: str
    meaning_to_mask: dict[str, int]
    raw_flag_meanings: str | tuple[str, ...]
    chlorophyll_valid_min: float
    chlorophyll_valid_max: float
    spatial_resolution_km: float


class RegionalSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    metadata: SnapshotMetadata
    payload: SSTRegionalPayload | ChlorophyllRegionalPayload


class SnapshotLookup(BaseModel):
    model_config = ConfigDict(frozen=True)
    state: SnapshotState
    snapshot: RegionalSnapshot | None = None


class RefreshJob(BaseModel):
    model_config = ConfigDict(frozen=True)
    job_id: str
    deduplication_key: str = Field(exclude=True)
    source: str
    tile_id: str
    state: RefreshJobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempt_count: int = 0
    snapshot_valid_time: datetime | None = None
    error_code: str | None = None
    message: str | None = None
    retryable: bool | None = None
    next_retry_at: datetime | None = None
    retry_after_seconds: int | None = None


class RefreshFailureGate(BaseModel):
    model_config = ConfigDict(frozen=True)
    gate_key: str = Field(exclude=True)
    last_job_id: str
    error_code: str
    classification: RefreshFailureClassification
    attempt_count: int = Field(ge=1)
    failed_at: datetime
    blocked_until: datetime
    configuration_identity: str = Field(exclude=True)
