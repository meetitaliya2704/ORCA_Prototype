import json
import httpx
import pytest
from pydantic import SecretStr

from app.agents.capabilities import AssistantIntent
from app.agents.explainer import LLMResponseExplainer
from app.schemas.assistant import (
    AssistantConversationMessage,
    AssistantResponseStatus,
)


@pytest.mark.asyncio
async def test_explainer_openrouter_success():
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        data = json.loads(request.content.decode())
        assert data["model"] == "nex-agi/nex-n2.5-mini:free"
        assert len(data["messages"]) >= 2
        # Check that system prompt contains language instruction
        assert "English" in data["messages"][0]["content"]
        assert "User's Question: Can I go fishing today?" in data["messages"][-1]["content"]

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                "Based on current marine forecasts for your area, conditions are favorable "
                                "for fishing with wave heights around 1.1m and light winds. Here are the details:"
                            ),
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        explainer = LLMResponseExplainer(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        ans = await explainer.explain(
            message="Can I go fishing today?",
            language="en",
            intent=AssistantIntent.MARINE_CONDITIONS,
            deterministic_answer="Significant wave height: 1.1 m. Wind speed: 8.5 kt.",
            status=AssistantResponseStatus.COMPLETED,
        )

    assert ans is not None
    assert "favorable for fishing" in ans
    assert len(captured_requests) == 1


@pytest.mark.asyncio
async def test_explainer_openrouter_hindi_response():
    def handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode())
        assert "Hindi" in data["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "आज समुद्र में स्थितियां सामान्य और सुरक्षित हैं। लहरों की ऊंचाई लगभग 1.1 मीटर है।",
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        explainer = LLMResponseExplainer(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        ans = await explainer.explain(
            message="क्या आज समुद्र में जाना सुरक्षित है?",
            language="hi",
            intent=AssistantIntent.OPERATIONAL_CONDITIONS,
            deterministic_answer="Operational outcome: Safe To Venture. Wave height: 1.1 m.",
            status=AssistantResponseStatus.COMPLETED,
        )

    assert ans is not None
    assert "लहरों की ऊंचाई" in ans


@pytest.mark.asyncio
async def test_explainer_openrouter_conversational_greeting():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "નમસ્તે! હું ORCA છું — તમારો દરિયાઈ સહાયક. હું તમને માછીમારી ક્ષેત્ર (PFZ) અને દરિયાઈ હવામાનમાં મદદ કરી શકું છું.",
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        explainer = LLMResponseExplainer(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        ans = await explainer.explain(
            message="કેમ છો? તમે કોણ છો?",
            language="gu",
            intent=AssistantIntent.UNSUPPORTED,
            deterministic_answer="ORCA can assist with Potential Fishing Zones...",
            status=AssistantResponseStatus.COMPLETED,
        )

    assert ans is not None
    assert "ORCA" in ans


@pytest.mark.asyncio
async def test_explainer_includes_recent_conversation_messages():
    captured_messages = []

    def handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode())
        captured_messages.extend(data["messages"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Understood, here is the updated info."}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        explainer = LLMResponseExplainer(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        recent = (
            AssistantConversationMessage(role="user", content="Where is Veraval?"),
            AssistantConversationMessage(role="assistant", content="Veraval is on the Gujarat coast."),
        )
        await explainer.explain(
            message="What are the waves like there?",
            language="en",
            intent=AssistantIntent.MARINE_CONDITIONS,
            deterministic_answer="Wave height: 1.5 m.",
            status=AssistantResponseStatus.COMPLETED,
            recent_messages=recent,
        )

    # Check that previous turns were passed
    roles = [m["role"] for m in captured_messages]
    assert "system" in roles
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_explainer_http_error_gracefully_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        explainer = LLMResponseExplainer(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        ans = await explainer.explain(
            message="Hello",
            language="en",
            intent=AssistantIntent.UNSUPPORTED,
            deterministic_answer="Fallback text",
            status=AssistantResponseStatus.COMPLETED,
        )

    assert ans is None


@pytest.mark.asyncio
async def test_explainer_rate_limit_gracefully_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(429, text="Too Many Requests")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        explainer = LLMResponseExplainer(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        ans = await explainer.explain(
            message="Hello",
            language="en",
            intent=AssistantIntent.UNSUPPORTED,
            deterministic_answer="Fallback text",
            status=AssistantResponseStatus.COMPLETED,
        )

    assert ans is None


@pytest.mark.asyncio
async def test_graph_with_explainer_produces_natural_response():
    from app.agents.graph import AssistantServices, ORCAAssistantGraph
    from app.agents.intents import DeterministicIntentRouter
    from app.schemas.assistant import AssistantRequest
    from app.services.assistant_store import InMemoryAssistantPersistence

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Hello! I am ORCA, your dedicated marine intelligence assistant. How can I help you today?",
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        explainer = LLMResponseExplainer(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        graph = ORCAAssistantGraph(
            router=DeterministicIntentRouter(),
            persistence=InMemoryAssistantPersistence(),
            services=AssistantServices(
                pfz_nearest=None,
                evidence=None,
                assessment=None,
            ),
            model="nex-agi/nex-n2.5-mini:free",
            explainer=explainer,
        )

        response = await graph.query(
            AssistantRequest(message="Hello, who are you?")
        )

    assert "I am ORCA, your dedicated marine intelligence assistant" in response.answer

