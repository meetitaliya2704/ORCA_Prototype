import asyncio
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from app.agents.intents import (
    GeminiFunctionIntentRouter,
    GeminiRouterError,
    GeminiRouterOutputError,
    _map_gemini_error,
    validated_required_information,
)
from app.schemas.assistant import (
    AssistantRequest,
    IntentRoutingResult,
    RequiredInformation,
)


class FakeBoundModel:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.messages = []

    async def ainvoke(self, messages):
        self.messages.append(messages)
        if self.error:
            raise self.error
        return self.response


class FakeChatModel:
    def __init__(self, bound):
        self.bound = bound
        self.tools = None
        self.tool_choice = None

    def bind_tools(self, tools, *, tool_choice):
        self.tools = tools
        self.tool_choice = tool_choice
        return self.bound


async def test_gemini_router_forces_exactly_one_typed_function():
    message = SimpleNamespace(
        tool_calls=[
            {
                "name": "route_request",
                "args": {
                    "intent": "nearest_pfz",
                    "confidence": 0.9,
                    "required_information": [],
                },
            }
        ],
        usage_metadata={"input_tokens": 21, "output_tokens": 7},
    )
    bound = FakeBoundModel(response=message)
    chat = FakeChatModel(bound)
    router = GeminiFunctionIntentRouter(
        api_key=SecretStr("not-a-real-key"), chat_model=chat
    )
    outcome = await router.route(
        AssistantRequest(message="Nearest PFZ", latitude=20.5, longitude=72.9)
    )
    assert chat.tool_choice == "route_request"
    assert len(chat.tools) == 1
    assert chat.tools[0]["name"] == "route_request"
    assert "$defs" not in chat.tools[0]["parameters"]
    assert "additionalProperties" not in chat.tools[0]["parameters"]
    assert outcome.routing.intent == "nearest_pfz"
    assert outcome.input_tokens == 21
    assert outcome.output_tokens == 7
    assert len(bound.messages) == 1


@pytest.mark.parametrize(
    "tool_calls",
    [
        [],
        [{"name": "unknown_tool", "args": {}}],
        [
            {
                "name": "route_request",
                "args": {
                    "intent": "nearest_pfz",
                    "confidence": 1,
                    "required_information": [],
                },
            },
            {
                "name": "route_request",
                "args": {
                    "intent": "nearest_pfz",
                    "confidence": 1,
                    "required_information": [],
                },
            },
        ],
        [
            {
                "name": "route_request",
                "args": {
                    "intent": "invented",
                    "confidence": 1,
                    "required_information": [],
                },
            }
        ],
    ],
)
async def test_invalid_or_unknown_tool_output_is_rejected(tool_calls):
    chat = FakeChatModel(
        FakeBoundModel(
            response=SimpleNamespace(tool_calls=tool_calls, usage_metadata={})
        )
    )
    router = GeminiFunctionIntentRouter(
        api_key=SecretStr("not-a-real-key"), chat_model=chat
    )
    with pytest.raises(GeminiRouterOutputError):
        await router.route(AssistantRequest(message="test"))


@pytest.mark.parametrize(
    "values",
    [
        {"confidence": 0.5, "required_information": []},
        {"intent": "nearest_pfz", "confidence": -0.1, "required_information": []},
        {"intent": "nearest_pfz", "confidence": 1.1, "required_information": []},
        {
            "intent": "nearest_pfz",
            "confidence": 0.5,
            "required_information": "location",
        },
        {
            "intent": "nearest_pfz",
            "confidence": 0.5,
            "required_information": [],
            "extra": True,
        },
    ],
)
def test_routing_schema_rejects_invalid_arguments(values):
    with pytest.raises(ValidationError):
        IntentRoutingResult.model_validate(values)


@pytest.mark.parametrize(
    ("status_code", "expected", "retryable"),
    [
        (429, "ASSISTANT_ROUTER_RATE_LIMITED", True),
        (503, "ASSISTANT_ROUTER_UNAVAILABLE", True),
        (401, "ASSISTANT_ROUTER_AUTHENTICATION_FAILED", False),
        (403, "ASSISTANT_ROUTER_AUTHENTICATION_FAILED", False),
        (400, "ASSISTANT_ROUTER_INVALID_REQUEST", False),
    ],
)
def test_gemini_errors_are_safely_classified(status_code, expected, retryable):
    error = type("ProviderError", (Exception,), {"status_code": status_code})()
    mapped = _map_gemini_error(error)
    assert mapped.code == expected
    assert mapped.retryable is retryable
    assert "ProviderError" not in str(mapped)


def test_clarification_fields_are_canonical_and_genuinely_missing():
    request = AssistantRequest(
        message="clarify",
        latitude=20.5,
        longitude=72.9,
    )
    result = validated_required_information(
        request,
        "clarification_required",
        (
            RequiredInformation.LOCATION,
            RequiredInformation.REQUESTED_TIME,
            RequiredInformation.OPERATIONAL_LIMITS,
        ),
    )
    assert result == (
        RequiredInformation.REQUESTED_TIME,
        RequiredInformation.OPERATIONAL_LIMITS,
    )


async def test_router_timeout_is_bounded_and_cancellation_propagates():
    class SlowBound:
        async def ainvoke(self, messages):
            del messages
            await asyncio.sleep(1)

    router = GeminiFunctionIntentRouter(
        api_key=SecretStr("not-a-real-key"),
        chat_model=FakeChatModel(SlowBound()),
        timeout_seconds=0.001,
    )
    with pytest.raises(GeminiRouterError) as captured:
        await router.route(AssistantRequest(message="test"))
    assert captured.value.code == "ASSISTANT_ROUTER_TIMEOUT"


async def test_gemini_router_caches_identical_queries_with_zero_tokens():
    message = SimpleNamespace(
        tool_calls=[
            {
                "name": "route_request",
                "args": {
                    "intent": "marine_conditions",
                    "confidence": 0.95,
                    "required_information": [],
                },
            }
        ],
        usage_metadata={"input_tokens": 150, "output_tokens": 30},
    )
    bound = FakeBoundModel(response=message)
    chat = FakeChatModel(bound)
    router = GeminiFunctionIntentRouter(
        api_key=SecretStr("not-a-real-key"), chat_model=chat
    )

    req = AssistantRequest(message="Check marine conditions", latitude=18.9, longitude=72.8)
    # Turn 1: Calls model
    res1 = await router.route(req)
    assert len(bound.messages) == 1
    assert res1.input_tokens == 150
    assert res1.output_tokens == 30
    assert res1.routing.intent == "marine_conditions"

    # Turn 2: Exact same query should hit in-memory cache (0 tokens, no model call)
    res2 = await router.route(req)
    assert len(bound.messages) == 1
    assert res2.input_tokens == 0
    assert res2.output_tokens == 0
    assert res2.routing.intent == "marine_conditions"


def test_gemini_errors_detects_resource_exhausted_string():
    error = RuntimeError("google.api_core.exceptions.ResourceExhausted: 429 Resource has been exhausted (e.g. check quota)")
    mapped = _map_gemini_error(error)
    assert mapped.code == "ASSISTANT_ROUTER_RATE_LIMITED"
    assert mapped.retryable is True

