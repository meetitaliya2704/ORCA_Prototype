from __future__ import annotations

from typing import NotRequired, TypedDict

from app.schemas.assistant import (
    AssistantRequest,
    AssistantResponse,
    IntentRoutingResult,
)


class ORCAAgentState(TypedDict):
    """Shared state contract for a future LangGraph StateGraph."""

    request: AssistantRequest
    step_count: int
    routing: NotRequired[IntentRoutingResult]
    response: NotRequired[AssistantResponse]
    error_code: NotRequired[str]
