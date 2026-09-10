from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.agents.capabilities import AssistantIntent, CapabilityAvailability
from app.schemas.assessment import (
    AssessmentOutcome,
    EvidenceConfidence,
    OperationalLimits,
)
from app.schemas.pfz import PFZGeoJSONFeature
from app.schemas.pfz_journey import JourneyFeatureCollection, PFZResolutionStatus


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("requested_time must include a timezone offset")
    return value.astimezone(UTC)


AssistantTime = Annotated[datetime, AfterValidator(_aware_utc)]
AssistantSourceName = Literal[
    "pfz", "sst", "chlorophyll", "waves", "wind", "currents", "sea_level"
]
AssistantSourceState = Literal["available", "degraded", "pending", "unavailable"]


class AssistantLanguage(StrEnum):
    ENGLISH = "en"
    HINDI = "hi"
    GUJARATI = "gu"
    MARATHI = "mr"
    TAMIL = "ta"
    TELUGU = "te"
    MALAYALAM = "ml"
    BENGALI = "bn"


class AssistantMode(StrEnum):
    LIVE = "live"
    DEMONSTRATION = "demonstration"


class RequiredInformation(StrEnum):
    LOCATION = "location"
    REQUESTED_TIME = "requested_time"
    OPERATIONAL_LIMITS = "operational_limits"


class AssistantConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4000)
    preferred_language: AssistantLanguage = AssistantLanguage.ENGLISH
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    requested_time: AssistantTime | None = None
    operational_limits: OperationalLimits = Field(default_factory=OperationalLimits)
    mode: AssistantMode = AssistantMode.LIVE
    recent_messages: tuple[AssistantConversationMessage, ...] = Field(
        default=(), max_length=20
    )

    @model_validator(mode="after")
    def coordinate_pair_is_complete(self) -> AssistantRequest:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self


class IntentRoutingResult(BaseModel):
    """Validated arguments accepted from the sole routing function."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: AssistantIntent
    confidence: float = Field(ge=0, le=1)
    required_information: tuple[RequiredInformation, ...] = Field(
        default=(), max_length=3
    )


class RoutingMode(StrEnum):
    GEMINI = "gemini_function_call"
    DETERMINISTIC = "deterministic_fallback"
    DEMONSTRATION = "demonstration_fixture"


class AssistantResponseStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    CLARIFICATION_REQUIRED = "clarification_required"
    CAPABILITY_NOT_AVAILABLE = "capability_not_available"
    FAILED = "failed"


class AssistantEvidenceStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    NOT_COLLECTED = "not_collected"


class AssistantEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AssistantEvidenceStatus = AssistantEvidenceStatus.NOT_COLLECTED
    available_sources: int = Field(default=0, ge=0, le=7)
    degraded_sources: int = Field(default=0, ge=0, le=7)
    pending_sources: int = Field(default=0, ge=0, le=7)
    unavailable_sources: int = Field(default=0, ge=0, le=7)
    assessment_outcome: AssessmentOutcome | None = None
    evidence_confidence: EvidenceConfidence | None = None
    pfz_status: PFZResolutionStatus | None = None


class AssistantSourceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: AssistantSourceName
    state: AssistantSourceState
    provider: str | None = Field(default=None, max_length=200)
    product_id: str | None = Field(default=None, max_length=300)
    dataset_id: str | None = Field(default=None, max_length=300)
    valid_time: datetime | None = None
    freshness: str | None = Field(default=None, max_length=64)


class AssistantWarning(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False
    retry_after_seconds: int | None = Field(default=None, ge=1, le=3600)


class AssistantDemonstrationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: Literal["Demonstration Snapshot"] = "Demonstration Snapshot"
    original_retrieval_time: datetime
    created_at: datetime


class AssistantDemoFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original_retrieval_time: datetime
    created_at: datetime
    intent: AssistantIntent
    answer: str = Field(min_length=1, max_length=4000)
    evidence_summary: AssistantEvidenceSummary
    sources: tuple[AssistantSourceSummary, ...]
    warnings: tuple[AssistantWarning, ...]
    geojson: JourneyFeatureCollection | None = None


class AssistantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    run_id: UUID
    detected_intent: AssistantIntent
    capability_status: CapabilityAvailability
    completion_status: AssistantResponseStatus
    answer: str = Field(min_length=1, max_length=4000)
    required_information: tuple[RequiredInformation, ...] = ()
    evidence_summary: AssistantEvidenceSummary = Field(
        default_factory=AssistantEvidenceSummary
    )
    sources: tuple[AssistantSourceSummary, ...] = ()
    warnings: tuple[AssistantWarning, ...] = ()
    geojson: JourneyFeatureCollection | PFZGeoJSONFeature | None = None
    routing_mode: RoutingMode
    model: str | None = Field(default=None, max_length=100)
    demonstration: AssistantDemonstrationMetadata | None = None
    geofences_evaluated: Literal[False] = False
    generated_at: datetime

    @model_validator(mode="after")
    def demonstration_metadata_matches_mode(self) -> AssistantResponse:
        is_demo = self.routing_mode == RoutingMode.DEMONSTRATION
        if is_demo != (self.demonstration is not None):
            raise ValueError("demonstration metadata must match demonstration routing")
        return self
