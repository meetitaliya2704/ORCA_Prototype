from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.agents.capabilities import AssistantIntent, CapabilityAvailability


class AssistantConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="en", min_length=2, max_length=16)
    recent_messages: tuple[AssistantConversationMessage, ...] = Field(
        default=(), max_length=20
    )


class IntentRoutingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: AssistantIntent
    confidence: float = Field(ge=0, le=1)
    required_information: tuple[str, ...] = Field(default=(), max_length=8)
    brief_explanation: str = Field(min_length=1, max_length=500)


class AssistantResponseStatus(StrEnum):
    ROUTED = "routed"
    CLARIFICATION_REQUIRED = "clarification_required"
    CAPABILITY_NOT_AVAILABLE = "capability_not_available"


class AssistantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: AssistantIntent
    capability_status: CapabilityAvailability
    status: AssistantResponseStatus
    message: str
    required_information: tuple[str, ...] = ()
