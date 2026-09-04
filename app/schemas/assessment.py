from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.schemas.evidence import EvidenceFailure, EvidenceItem
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


AssessmentTime = Annotated[datetime, AfterValidator(_aware_utc)]


class OperationalLimits(BaseModel):
    maximum_significant_wave_height_m: float | None = Field(
        default=None, gt=0, allow_inf_nan=False
    )
    maximum_wind_speed_m_s: float | None = Field(
        default=None, gt=0, allow_inf_nan=False
    )
    maximum_surface_current_speed_m_s: float | None = Field(
        default=None, gt=0, allow_inf_nan=False
    )

    def supplied_count(self) -> int:
        return sum(
            value is not None
            for value in (
                self.maximum_significant_wave_height_m,
                self.maximum_wind_speed_m_s,
                self.maximum_surface_current_speed_m_s,
            )
        )


class AssessmentRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    at: AssessmentTime | None = None
    operational_limits: OperationalLimits
    near_limit_percentage: float | None = Field(
        default=None, gt=0, le=100, allow_inf_nan=False
    )
    include_pfz_context: bool = True

    @model_validator(mode="after")
    def at_least_one_limit_is_required(self) -> "AssessmentRequest":
        if self.operational_limits.supplied_count() == 0:
            raise ValueError("at least one operational limit must be supplied")
        return self


class AssessmentRequestMetadata(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    at: datetime
    operational_limits: OperationalLimits
    near_limit_percentage: float | None = None
    include_pfz_context: bool


class AssessmentOutcome(StrEnum):
    WITHIN_CONFIGURED_LIMITS = "WITHIN_CONFIGURED_LIMITS"
    CAUTION = "CAUTION"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    POLICY_NOT_CONFIGURED = "POLICY_NOT_CONFIGURED"


class EvidenceConfidence(StrEnum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


class RuleOutcome(StrEnum):
    WITHIN_LIMIT = "within_limit"
    NEAR_LIMIT = "near_limit"
    EXCEEDED = "exceeded"
    UNKNOWN = "unknown"


class RuleEvidenceQuality(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    INSUFFICIENT = "insufficient"


class NearLimitPolicy(BaseModel):
    enabled: bool
    percentage: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def percentage_matches_enabled_state(self) -> "NearLimitPolicy":
        if self.enabled != (self.percentage is not None):
            raise ValueError("enabled near-limit policy requires a percentage")
        return self


class AssessmentPolicy(BaseModel):
    policy_id: Literal["request_supplied_limits"] = "request_supplied_limits"
    policy_version: Literal["1"] = "1"
    limit_source: Literal["request"] = "request"
    near_limit: NearLimitPolicy
    evaluated_at: datetime


class OperationalRuleResult(BaseModel):
    rule_id: Literal["wave_height_limit", "wind_speed_limit", "surface_current_limit"]
    parameter: Literal[
        "significant_wave_height", "wind_speed", "total_surface_current_speed"
    ]
    observed_value: float | None
    unit: Literal["m", "m/s"]
    configured_limit: float = Field(gt=0, allow_inf_nan=False)
    comparison: Literal["greater_than"] = "greater_than"
    outcome: RuleOutcome
    evidence_source: Literal["copernicus_marine", "ecmwf"] | None
    evidence_valid_time: datetime | None
    evidence_quality: RuleEvidenceQuality


class AssessmentReason(BaseModel):
    code: Literal[
        "WAVE_LIMIT_EXCEEDED",
        "WIND_LIMIT_EXCEEDED",
        "CURRENT_LIMIT_EXCEEDED",
        "WAVE_NEAR_LIMIT",
        "WIND_NEAR_LIMIT",
        "CURRENT_NEAR_LIMIT",
        "WAVE_EVIDENCE_MISSING",
        "WIND_EVIDENCE_MISSING",
        "CURRENT_EVIDENCE_MISSING",
        "EVIDENCE_DEGRADED",
        "OFFICIAL_WARNINGS_NOT_INTEGRATED",
    ]
    message: str = Field(min_length=1)
    rule_id: str | None = None
    evidence_item: str | None = None

    @model_validator(mode="after")
    def reason_references_evidence(self) -> "AssessmentReason":
        if self.rule_id is None and self.evidence_item is None:
            raise ValueError("reason must reference a rule or evidence item")
        return self


class CriticalEvidence(BaseModel):
    waves: EvidenceItem[WaveResponse]
    wind: EvidenceItem[WindResponse | ECMWFWindForecastResponse]
    currents: EvidenceItem[CurrentResponse]


class AssessmentContext(BaseModel):
    pfz: EvidenceItem[NearestPFZResponse]
    sst: EvidenceItem[SSTSnapshotResponse | SSTResponse]
    chlorophyll: EvidenceItem[ChlorophyllSnapshotResponse | ChlorophyllResponse]
    sea_level: EvidenceItem[SeaLevelResponse]


class MarineAssessmentResponse(BaseModel):
    request: AssessmentRequestMetadata
    generated_at: datetime
    outcome: AssessmentOutcome
    evidence_confidence: EvidenceConfidence
    policy: AssessmentPolicy
    rules: list[OperationalRuleResult]
    reasons: list[AssessmentReason]
    missing_critical_evidence: list[
        Literal["waves", "wind", "currents"]
    ] = Field(default_factory=list)
    critical_evidence: CriticalEvidence
    context: AssessmentContext
    source_failures: list[EvidenceFailure] = Field(default_factory=list)
    official_warning_coverage: Literal["not_integrated"] = "not_integrated"
    notices: list[str]

    @model_validator(mode="after")
    def timestamps_are_aware(self) -> "MarineAssessmentResponse":
        for value in (
            self.request.at,
            self.generated_at,
            self.policy.evaluated_at,
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("assessment timestamps must be timezone-aware")
        return self
