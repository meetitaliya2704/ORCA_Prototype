from __future__ import annotations

from app.agents.capabilities import (
    CapabilityAvailability,
    get_capability,
)
from app.agents.state import ORCAAgentState
from app.schemas.assistant import (
    AssistantResponse,
    AssistantResponseStatus,
)


def coordinator_node(state: ORCAAgentState) -> dict[str, object]:
    """Resolve a validated route against the immutable capability registry."""
    routing = state.get("routing")
    if routing is None:
        return {
            "step_count": state["step_count"] + 1,
            "error_code": "INTENT_ROUTING_REQUIRED",
        }

    capability = get_capability(routing.intent)
    if capability.availability == CapabilityAvailability.AVAILABLE:
        status = AssistantResponseStatus.ROUTED
        message = "The request was routed to an available deterministic capability."
    elif capability.availability in {
        CapabilityAvailability.PLANNED,
        CapabilityAvailability.PLANNED_OR_PARTIAL,
    }:
        status = AssistantResponseStatus.CAPABILITY_NOT_AVAILABLE
        message = (
            "This capability is planned or partial and is not available for "
            "production assistant execution."
        )
    else:
        status = AssistantResponseStatus.CLARIFICATION_REQUIRED
        message = "Additional clarification is required before routing."

    return {
        "step_count": state["step_count"] + 1,
        "response": AssistantResponse(
            intent=routing.intent,
            capability_status=capability.availability,
            status=status,
            message=message,
            required_information=routing.required_information,
        ),
    }
