from types import MappingProxyType

import pytest
from pydantic import ValidationError

from app.agents.capabilities import (
    CAPABILITY_REGISTRY,
    AssistantIntent,
    CapabilityAvailability,
    get_capability,
)
from app.agents.coordinator import coordinator_node
from app.agents.intents import IntentRouterNotConfigured, StubIntentRouter
from app.schemas.assistant import AssistantRequest, IntentRoutingResult


def route(intent: AssistantIntent) -> IntentRoutingResult:
    return IntentRoutingResult(
        intent=intent,
        confidence=0.9,
        required_information=(),
        brief_explanation="Typed fixture route.",
    )


def test_capability_registry_is_immutable_and_application_owned() -> None:
    assert isinstance(CAPABILITY_REGISTRY, MappingProxyType)
    assert (
        get_capability(AssistantIntent.NEAREST_PFZ).availability
        == CapabilityAvailability.AVAILABLE
    )
    assert (
        get_capability(AssistantIntent.OFFICIAL_ALERTS).availability
        == CapabilityAvailability.PLANNED_OR_PARTIAL
    )
    assert (
        get_capability(AssistantIntent.LOWER_RISK_ROUTE).availability
        == CapabilityAvailability.PLANNED
    )
    with pytest.raises(TypeError):
        CAPABILITY_REGISTRY[AssistantIntent.LOWER_RISK_ROUTE] = get_capability(
            AssistantIntent.NEAREST_PFZ
        )


def test_route_result_cannot_claim_capability_availability() -> None:
    with pytest.raises(ValidationError):
        IntentRoutingResult(
            intent="lower_risk_route",
            confidence=1,
            required_information=[],
            brief_explanation="Model claim.",
            capability_status="available",
        )


def test_coordinator_never_promotes_planned_capability() -> None:
    output = coordinator_node(
        {
            "request": AssistantRequest(message="Find a lower-risk route"),
            "routing": route(AssistantIntent.LOWER_RISK_ROUTE),
            "step_count": 0,
        }
    )
    response = output["response"]
    assert response.capability_status == CapabilityAvailability.PLANNED
    assert response.status == "capability_not_available"


async def test_stub_router_never_calls_a_model() -> None:
    with pytest.raises(IntentRouterNotConfigured):
        await StubIntentRouter().route(AssistantRequest(message="Nearest PFZ"))
