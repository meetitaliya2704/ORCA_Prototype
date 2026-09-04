from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.schemas.assessment import (
    MarineAssessmentResponse,
    OperationalLimits,
)
from app.schemas.evidence import MarineEvidenceResponse
from app.schemas.pfz import NearestPFZResponse


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("at must include a timezone offset")
    return value.astimezone(UTC)


JourneyTime = Annotated[datetime, AfterValidator(_aware_utc)]


class JourneyLocation(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class PFZJourneyRequest(BaseModel):
    origin: JourneyLocation
    at: JourneyTime | None = None
    operational_limits: OperationalLimits
    near_limit_percentage: float | None = Field(
        default=None, gt=0, le=100, allow_inf_nan=False
    )
    include_origin_evidence: bool = True
    include_destination_evidence: bool = True
    include_geojson: bool = True

    @model_validator(mode="after")
    def at_least_one_limit_is_required(self) -> "PFZJourneyRequest":
        if self.operational_limits.supplied_count() == 0:
            raise ValueError("at least one operational limit must be supplied")
        return self


class PFZJourneyRequestMetadata(BaseModel):
    origin: JourneyLocation
    at: datetime
    operational_limits: OperationalLimits
    near_limit_percentage: float | None
    include_origin_evidence: bool
    include_destination_evidence: bool
    include_geojson: bool


class JourneyStatus(StrEnum):
    PFZ_AVAILABLE_WITHIN_CONFIGURED_LIMITS = (
        "PFZ_AVAILABLE_WITHIN_CONFIGURED_LIMITS"
    )
    PFZ_AVAILABLE_CAUTION = "PFZ_AVAILABLE_CAUTION"
    PFZ_AVAILABLE_LIMIT_EXCEEDED = "PFZ_AVAILABLE_LIMIT_EXCEEDED"
    PFZ_AVAILABLE_INSUFFICIENT_EVIDENCE = (
        "PFZ_AVAILABLE_INSUFFICIENT_EVIDENCE"
    )
    NO_VALID_PFZ = "NO_VALID_PFZ"
    PFZ_REFRESH_PENDING = "PFZ_REFRESH_PENDING"
    PFZ_SOURCE_UNAVAILABLE = "PFZ_SOURCE_UNAVAILABLE"
    POLICY_NOT_CONFIGURED = "POLICY_NOT_CONFIGURED"


class PFZResolutionStatus(StrEnum):
    PFZ_FOUND = "PFZ_FOUND"
    NO_VALID_PFZ = "NO_VALID_PFZ"
    PFZ_REFRESH_PENDING = "PFZ_REFRESH_PENDING"
    PFZ_SOURCE_UNAVAILABLE = "PFZ_SOURCE_UNAVAILABLE"


class PFZResolutionFailure(BaseModel):
    code: Literal[
        "NO_VALID_PFZ",
        "PFZ_DATA_PENDING",
        "PFZ_DATA_UNAVAILABLE",
    ]
    message: str = Field(min_length=1)
    retryable: bool
    retry_after_seconds: int | None = Field(default=None, ge=1)
    refresh_job_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class PFZResolution(BaseModel):
    status: PFZResolutionStatus
    failure: PFZResolutionFailure | None = None

    @model_validator(mode="after")
    def failure_matches_status(self) -> "PFZResolution":
        if (self.status == PFZResolutionStatus.PFZ_FOUND) == (self.failure is not None):
            raise ValueError("PFZ failure must be absent only when a PFZ was found")
        return self


class JourneyLocationState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class JourneyLocationFailure(BaseModel):
    code: Literal["EVIDENCE_COLLECTION_FAILED"] = "EVIDENCE_COLLECTION_FAILED"
    message: Literal["Marine evidence could not be collected"] = (
        "Marine evidence could not be collected"
    )


class JourneyLocationResult(BaseModel):
    location: JourneyLocation
    state: JourneyLocationState
    evidence: MarineEvidenceResponse | None = None
    assessment: MarineAssessmentResponse | None = None
    failure: JourneyLocationFailure | None = None

    @model_validator(mode="after")
    def payload_matches_state(self) -> "JourneyLocationResult":
        if self.state == JourneyLocationState.AVAILABLE:
            if self.assessment is None or self.failure is not None:
                raise ValueError("available location requires an assessment")
        elif self.assessment is not None or self.failure is None:
            raise ValueError("unavailable location requires a safe failure")
        return self


class JourneyDistance(BaseModel):
    kilometres: float = Field(ge=0)
    bearing_degrees: float = Field(ge=0, lt=360)
    direction: Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class JourneyReasonCode(StrEnum):
    VALID_PFZ_FOUND = "VALID_PFZ_FOUND"
    NO_VALID_PFZ = "NO_VALID_PFZ"
    PFZ_DATA_PENDING = "PFZ_DATA_PENDING"
    PFZ_DATA_UNAVAILABLE = "PFZ_DATA_UNAVAILABLE"
    ORIGIN_LIMIT_EXCEEDED = "ORIGIN_LIMIT_EXCEEDED"
    DESTINATION_LIMIT_EXCEEDED = "DESTINATION_LIMIT_EXCEEDED"
    ORIGIN_EVIDENCE_INSUFFICIENT = "ORIGIN_EVIDENCE_INSUFFICIENT"
    DESTINATION_EVIDENCE_INSUFFICIENT = "DESTINATION_EVIDENCE_INSUFFICIENT"
    ORIGIN_CAUTION = "ORIGIN_CAUTION"
    DESTINATION_CAUTION = "DESTINATION_CAUTION"
    WITHIN_CONFIGURED_LIMITS_AT_CHECKED_LOCATIONS = (
        "WITHIN_CONFIGURED_LIMITS_AT_CHECKED_LOCATIONS"
    )
    ROUTE_NOT_EVALUATED = "ROUTE_NOT_EVALUATED"
    GEOFENCES_NOT_EVALUATED = "GEOFENCES_NOT_EVALUATED"
    OFFICIAL_WARNINGS_NOT_INTEGRATED = "OFFICIAL_WARNINGS_NOT_INTEGRATED"
    PFZ_DOES_NOT_GUARANTEE_FISH_PRESENCE = (
        "PFZ_DOES_NOT_GUARANTEE_FISH_PRESENCE"
    )


class JourneyReason(BaseModel):
    code: JourneyReasonCode
    message: str = Field(min_length=1)


class JourneyLimitations(BaseModel):
    route_evaluated: Literal[False] = False
    geofences_evaluated: Literal[False] = False
    official_warning_coverage: Literal["not_integrated"] = "not_integrated"


class JourneyPointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class JourneyLineGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: tuple[tuple[float, float], tuple[float, float]]


class OriginFeatureProperties(BaseModel):
    feature_type: Literal["origin"] = "origin"


class DestinationFeatureProperties(BaseModel):
    feature_type: Literal["pfz_destination"] = "pfz_destination"
    sector_code: str
    region_name: str
    landing_centre: str


class ReferenceLineFeatureProperties(BaseModel):
    feature_type: Literal["reference_line"] = "reference_line"
    label: Literal["reference_line_not_evaluated_route"] = (
        "reference_line_not_evaluated_route"
    )
    navigable_route: Literal[False] = False
    route_evaluated: Literal[False] = False
    geofences_evaluated: Literal[False] = False


class OriginFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: JourneyPointGeometry
    properties: OriginFeatureProperties = Field(default_factory=OriginFeatureProperties)


class DestinationFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: JourneyPointGeometry
    properties: DestinationFeatureProperties


class ReferenceLineFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: JourneyLineGeometry
    properties: ReferenceLineFeatureProperties = Field(
        default_factory=ReferenceLineFeatureProperties
    )


class JourneyFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: tuple[OriginFeature, DestinationFeature, ReferenceLineFeature]


class PFZJourneyResponse(BaseModel):
    request: PFZJourneyRequestMetadata
    generated_at: datetime
    journey_status: JourneyStatus
    pfz_resolution: PFZResolution
    pfz: NearestPFZResponse | None
    origin: JourneyLocationResult
    destination: JourneyLocationResult | None
    distance: JourneyDistance | None
    reasons: list[JourneyReason]
    reason_codes: list[JourneyReasonCode]
    notices: list[str]
    limitations: JourneyLimitations = Field(default_factory=JourneyLimitations)
    geojson: JourneyFeatureCollection | None = None

    @model_validator(mode="after")
    def response_is_consistent(self) -> "PFZJourneyResponse":
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        found = self.pfz_resolution.status == PFZResolutionStatus.PFZ_FOUND
        if found != (self.pfz is not None and self.destination is not None):
            raise ValueError("PFZ and destination must exist exactly when PFZ is found")
        if found != (self.distance is not None):
            raise ValueError("distance must exist exactly when PFZ is found")
        if self.geojson is not None and not found:
            raise ValueError("GeoJSON requires a resolved PFZ")
        if self.reason_codes != [reason.code for reason in self.reasons]:
            raise ValueError("reason_codes must preserve reason ordering")
        return self
