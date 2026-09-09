from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from app.agents.capabilities import AssistantIntent, CapabilityAvailability
from app.agents.intents import RouterOutcome
from app.schemas.assistant import (
    AssistantEvidenceSummary,
    AssistantRequest,
    AssistantResponse,
    AssistantResponseStatus,
    AssistantSourceSummary,
    AssistantWarning,
)
from app.services.assistant_store import AssistantTurnReferences


class ORCAAgentState(TypedDict):
    request: AssistantRequest
    references: AssistantTurnReferences
    started_at_ns: int
    step_count: int
    service_call_count: int
    previous_sources: dict[str, Any]
    previous_intent: AssistantIntent | None
    routing_outcome: NotRequired[RouterOutcome]
    capability_status: NotRequired[CapabilityAvailability]
    completion_status: NotRequired[AssistantResponseStatus]
    deterministic_result: NotRequired[Any]
    evidence_summary: NotRequired[AssistantEvidenceSummary]
    sources: NotRequired[tuple[AssistantSourceSummary, ...]]
    warnings: NotRequired[tuple[AssistantWarning, ...]]
    answer: NotRequired[str]
    response: NotRequired[AssistantResponse]
    error_code: NotRequired[str]
