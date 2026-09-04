from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.schemas.marine import (
    ChlorophyllResponse,
    ChlorophyllSnapshotResponse,
    CurrentResponse,
    ECMWFWindForecastResponse,
    SSTResponse,
    SSTSnapshotResponse,
    SeaLevelResponse,
    WaveResponse,
    WindResponse,
)
from app.schemas.pfz import NearestPFZResponse


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("at must include a timezone offset")
    return value.astimezone(UTC)


EvidenceTime = Annotated[datetime, AfterValidator(_aware_utc)]


class EvidenceRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    at: EvidenceTime | None = None
    include_pfz: bool = True
    include_sst: bool = True
    include_chlorophyll: bool = True
    include_waves: bool = True
    include_wind: bool = True
    include_currents: bool = True
    include_sea_level: bool = True

    @model_validator(mode="after")
    def at_least_one_source_is_requested(self) -> "EvidenceRequest":
        if not any(
            (
                self.include_pfz,
                self.include_sst,
                self.include_chlorophyll,
                self.include_waves,
                self.include_wind,
                self.include_currents,
                self.include_sea_level,
            )
        ):
            raise ValueError("at least one evidence source must be requested")
        return self


class EvidenceRequestMetadata(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    at: datetime


class EvidenceState(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    PENDING = "pending"
    UNAVAILABLE = "unavailable"
    NOT_REQUESTED = "not_requested"


class EvidenceBundleStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


T = TypeVar("T", bound=BaseModel)


class EvidenceItem(BaseModel, Generic[T]):
    state: EvidenceState
    data: T | None = None

    @model_validator(mode="after")
    def usable_state_requires_data(self) -> "EvidenceItem[T]":
        usable = self.state in {EvidenceState.AVAILABLE, EvidenceState.DEGRADED}
        if usable != (self.data is not None):
            raise ValueError("available/degraded evidence must contain typed data")
        return self


class EvidenceSources(BaseModel):
    pfz: EvidenceItem[NearestPFZResponse]
    sst: EvidenceItem[SSTSnapshotResponse | SSTResponse]
    chlorophyll: EvidenceItem[ChlorophyllSnapshotResponse | ChlorophyllResponse]
    waves: EvidenceItem[WaveResponse]
    wind: EvidenceItem[WindResponse | ECMWFWindForecastResponse]
    currents: EvidenceItem[CurrentResponse]
    sea_level: EvidenceItem[SeaLevelResponse]


class EvidenceFailure(BaseModel):
    source: Literal[
        "pfz", "sst", "chlorophyll", "waves", "wind", "currents", "sea_level"
    ]
    state: Literal["pending", "unavailable"]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool
    retry_after_seconds: int | None = Field(default=None, ge=1)
    refresh_job_id: str | None = None


class EvidenceSummary(BaseModel):
    requested_sources: int = Field(ge=1, le=7)
    available_sources: int = Field(ge=0, le=7)
    unavailable_sources: int = Field(ge=0, le=7)
    degraded_sources: int = Field(ge=0, le=7)
    pending_sources: int = Field(ge=0, le=7)


class MarineEvidenceResponse(BaseModel):
    request: EvidenceRequestMetadata
    generated_at: datetime
    status: EvidenceBundleStatus
    summary: EvidenceSummary
    evidence: EvidenceSources
    failures: list[EvidenceFailure] = Field(default_factory=list)
    notices: list[str] = Field(
        default_factory=lambda: [
            "Decision-support information; not certified navigation advice."
        ]
    )

    @model_validator(mode="after")
    def timestamps_are_aware(self) -> "MarineEvidenceResponse":
        if self.request.at.tzinfo is None or self.request.at.utcoffset() is None:
            raise ValueError("request time must be timezone-aware")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return self
