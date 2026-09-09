from __future__ import annotations

from app.agents.capabilities import get_capability
from app.agents.state import ORCAAgentState


def coordinator_node(state: ORCAAgentState) -> dict[str, object]:
    """Initialize one bounded run without deciding capability availability."""
    return {
        "step_count": state.get("step_count", 0) + 1,
        "service_call_count": state.get("service_call_count", 0),
    }


def capability_guard_node(state: ORCAAgentState) -> dict[str, object]:
    """The application registry, never model output, owns availability."""
    routed = state["routing_outcome"].routing
    return {
        "step_count": state["step_count"] + 1,
        "capability_status": get_capability(routed.intent).availability,
    }
