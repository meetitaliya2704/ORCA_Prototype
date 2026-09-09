from types import MappingProxyType

import pytest
from pydantic import ValidationError

from app.agents.capabilities import (
    CAPABILITY_REGISTRY,
    AssistantIntent,
    CapabilityAvailability,
    get_capability,
)
from app.agents.coordinator import capability_guard_node, coordinator_node
from app.agents.intents import (
    DeterministicIntentRouter,
    IntentRouterNotConfigured,
    StubIntentRouter,
)
from app.schemas.assistant import AssistantRequest, IntentRoutingResult


def route(intent: AssistantIntent) -> IntentRoutingResult:
    return IntentRoutingResult(
        intent=intent,
        confidence=0.9,
        required_information=(),
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
            capability_status="available",
        )


def test_coordinator_never_promotes_planned_capability() -> None:
    state = {
        "request": AssistantRequest(message="Find a lower-risk route"),
        "routing_outcome": type(
            "Outcome", (), {"routing": route(AssistantIntent.LOWER_RISK_ROUTE)}
        )(),
        "step_count": 1,
    }
    output = capability_guard_node(state)
    assert output["capability_status"] == CapabilityAvailability.PLANNED


def test_coordinator_only_initializes_bounded_counters() -> None:
    output = coordinator_node({"step_count": 0, "service_call_count": 0})
    assert output == {"step_count": 1, "service_call_count": 0}


async def test_stub_router_never_calls_a_model() -> None:
    with pytest.raises(IntentRouterNotConfigured):
        await StubIntentRouter().route(AssistantRequest(message="Nearest PFZ"))


@pytest.mark.parametrize(
    ("message", "language", "intent"),
    [
        ("Where is the nearest PFZ?", "en", "nearest_pfz"),
        ("आज मेरे पास सबसे नज़दीकी पीएफ़ज़ेड कहाँ है?", "hi", "nearest_pfz"),
        ("મારી નજીક સમુદ્રની સ્થિતિ કેવી છે?", "gu", "marine_conditions"),
    ],
)
async def test_deterministic_router_supports_obvious_multilingual_requests(
    message, language, intent
) -> None:
    outcome = await DeterministicIntentRouter().route(
        AssistantRequest(message=message, preferred_language=language)
    )
    assert outcome.routing.intent == intent
    assert "location" in outcome.routing.required_information
