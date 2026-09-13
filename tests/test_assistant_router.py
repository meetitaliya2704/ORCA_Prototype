import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.agents.intents import (
    DeterministicIntentRouter,
    FallbackIntentRouter,
    GeminiFunctionIntentRouter,
    GeminiRouterError,
    GeminiRouterOutputError,
    GroqFunctionIntentRouter,
    GroqRouterError,
    GroqRouterOutputError,
    OpenRouterError,
    OpenRouterFunctionIntentRouter,
    OpenRouterOutputError,
    _map_gemini_error,
    _map_openrouter_error,
    validated_required_information,
)
from app.schemas.assistant import (
    AssistantRequest,
    IntentRoutingResult,
    RequiredInformation,
    RoutingMode,
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


async def test_openrouter_router_forces_tool_and_parses_tool_call():
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        data = json.loads(request.content.decode())
        assert data["model"] == "nex-agi/nex-n2.5-mini:free"
        assert data["temperature"] == 0.0
        assert data["max_tokens"] == 250
        assert data["tool_choice"] == {
            "type": "function",
            "function": {"name": "route_request"},
        }
        assert len(data["tools"]) == 1
        assert data["tools"][0]["function"]["name"] == "route_request"

        return httpx.Response(
            200,
            json={
                "id": "gen-123",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_abc",
                                    "type": "function",
                                    "function": {
                                        "name": "route_request",
                                        "arguments": json.dumps(
                                            {
                                                "intent": "nearest_pfz",
                                                "confidence": 0.95,
                                                "required_information": [],
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 80, "completion_tokens": 20},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        router = OpenRouterFunctionIntentRouter(
            api_key=SecretStr("test-openrouter-key"),
            http_client=client,
        )
        req = AssistantRequest(message="Nearest PFZ", latitude=20.5, longitude=72.9)
        outcome = await router.route(req)

    assert len(captured_requests) == 1
    assert captured_requests[0].headers["Authorization"] == "Bearer test-openrouter-key"
    assert captured_requests[0].headers["HTTP-Referer"] == "https://orca-marine.org"
    assert outcome.routing.intent == "nearest_pfz"
    assert outcome.routing.confidence == 0.95
    assert outcome.mode == RoutingMode.OPENROUTER
    assert outcome.model == "nex-agi/nex-n2.5-mini:free"
    assert outcome.input_tokens == 80
    assert outcome.output_tokens == 20


async def test_openrouter_router_parses_content_json_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        # Model returning markdown json block in message.content instead of tool_calls
        content = "```json\n{\"intent\": \"marine_conditions\", \"confidence\": 0.9, \"required_information\": []}\n```"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": content,
                        }
                    }
                ],
                "usage": {"prompt_tokens": 90, "completion_tokens": 25},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        router = OpenRouterFunctionIntentRouter(
            api_key=SecretStr("test-openrouter-key"),
            http_client=client,
        )
        req = AssistantRequest(message="Check marine conditions", latitude=19.0, longitude=72.8)
        outcome = await router.route(req)

    assert outcome.routing.intent == "marine_conditions"
    assert outcome.routing.confidence == 0.9
    assert outcome.mode == RoutingMode.OPENROUTER


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (429, "ASSISTANT_ROUTER_RATE_LIMITED", True),
        (401, "ASSISTANT_ROUTER_AUTHENTICATION_FAILED", False),
        (403, "ASSISTANT_ROUTER_AUTHENTICATION_FAILED", False),
        (400, "ASSISTANT_ROUTER_INVALID_REQUEST", False),
    ],
)
async def test_openrouter_router_error_classification(status_code, expected_code, retryable):
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status_code, text="Error message")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        router = OpenRouterFunctionIntentRouter(
            api_key=SecretStr("test-openrouter-key"),
            http_client=client,
        )
        with pytest.raises(OpenRouterError) as captured:
            await router.route(AssistantRequest(message="hello"))

    assert captured.value.code == expected_code
    assert captured.value.retryable is retryable


async def test_openrouter_router_automatic_retry_success():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "route_request",
                                        "arguments": json.dumps(
                                            {"intent": "nearest_pfz", "confidence": 0.85, "required_information": []}
                                        ),
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        router = OpenRouterFunctionIntentRouter(
            api_key=SecretStr("test-key"),
            http_client=client,
            max_retries=1,
        )
        outcome = await router.route(AssistantRequest(message="Nearest PFZ", latitude=20.0, longitude=72.0))

    assert calls == 2
    assert outcome.routing.intent == "nearest_pfz"


async def test_openrouter_router_retry_exhausted_raises_unavailable():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="Service Unavailable")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        router = OpenRouterFunctionIntentRouter(
            api_key=SecretStr("test-key"),
            http_client=client,
            max_retries=1,
        )
        with pytest.raises(OpenRouterError) as captured:
            await router.route(AssistantRequest(message="Nearest PFZ"))

    assert calls == 2
    assert captured.value.code == "ASSISTANT_ROUTER_UNAVAILABLE"


async def test_openrouter_router_invalid_output_raises_output_error():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "I am not able to parse this."
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        router = OpenRouterFunctionIntentRouter(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        with pytest.raises(OpenRouterOutputError):
            await router.route(AssistantRequest(message="Nearest PFZ"))


async def test_openrouter_fallback_order_to_deterministic_router():
    """Nex-N2.5-Mini -> failure / invalid output / 429 -> ORCA deterministic router."""
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(429, text="Rate limit exceeded")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        primary = OpenRouterFunctionIntentRouter(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        fallback = DeterministicIntentRouter()
        chained_router = FallbackIntentRouter(primary=primary, fallback=fallback)

        outcome = await chained_router.route(
            AssistantRequest(message="where is the nearest pfz", latitude=20.0, longitude=72.0)
        )

    assert outcome.mode == RoutingMode.DETERMINISTIC
    assert outcome.routing.intent == "nearest_pfz"
    assert outcome.warning is not None
    assert outcome.warning.code == "ASSISTANT_ROUTER_RATE_LIMITED"
    assert "OpenRouter" in outcome.warning.message


async def test_openrouter_router_caches_identical_queries():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "route_request",
                                        "arguments": json.dumps(
                                            {"intent": "marine_conditions", "confidence": 0.95, "required_information": []}
                                        ),
                                    }
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 15},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        router = OpenRouterFunctionIntentRouter(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        req = AssistantRequest(message="Check marine conditions", latitude=19.0, longitude=72.8)

        # Call 1: calls mock endpoint
        res1 = await router.route(req)
        assert calls == 1
        assert res1.input_tokens == 120
        assert res1.output_tokens == 15

        # Call 2: identical query should hit cache (0 tokens, no mock call)
        res2 = await router.route(req)
        assert calls == 1
        assert res2.input_tokens == 0
        assert res2.output_tokens == 0
        assert res2.routing.intent == "marine_conditions"


async def test_groq_router_success():
    def handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode())
        assert data["model"] == "qwen/qwen3.8-27b"
        assert data["tool_choice"] == {"type": "function", "function": {"name": "route_request"}}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "route_request",
                                        "arguments": json.dumps(
                                            {"intent": "nearest_pfz", "confidence": 0.98, "required_information": []}
                                        ),
                                    }
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 150, "completion_tokens": 20},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        router = GroqFunctionIntentRouter(
            api_key=SecretStr("groq-test-key"),
            http_client=client,
        )
        outcome = await router.route(AssistantRequest(message="Nearest PFZ", latitude=19.0, longitude=72.8))

    assert outcome.mode == RoutingMode.GROQ
    assert outcome.routing.intent == "nearest_pfz"
    assert outcome.input_tokens == 150
    assert outcome.output_tokens == 20


async def test_groq_fallback_order_to_deterministic_router():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(429, text="Rate limit reached")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        primary = GroqFunctionIntentRouter(
            api_key=SecretStr("groq-test-key"),
            http_client=client,
        )
        fallback = DeterministicIntentRouter()
        chained_router = FallbackIntentRouter(primary=primary, fallback=fallback)

        outcome = await chained_router.route(
            AssistantRequest(message="where is the nearest pfz", latitude=20.0, longitude=72.0)
        )

    assert outcome.mode == RoutingMode.DETERMINISTIC
    assert outcome.routing.intent == "nearest_pfz"
    assert outcome.warning is not None
    assert outcome.warning.code == "ASSISTANT_ROUTER_RATE_LIMITED"
    assert "Groq" in outcome.warning.message



