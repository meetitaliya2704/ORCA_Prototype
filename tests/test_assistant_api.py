from datetime import UTC, datetime
from uuid import uuid4

import httpx
from fastapi import FastAPI

from app.agents.errors import AssistantExecutionError
from app.api.routes.assistant import router
from app.schemas.assistant import AssistantResponse

NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)


def response() -> AssistantResponse:
    return AssistantResponse(
        conversation_id=uuid4(),
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        run_id=uuid4(),
        detected_intent="marine_conditions",
        capability_status="available",
        completion_status="completed",
        answer="Marine evidence collection is complete.",
        routing_mode="deterministic_fallback",
        generated_at=NOW,
    )


class FakeAssistant:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def query(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.result


def app_with(service=...):
    application = FastAPI()
    application.include_router(router, prefix="/v1")
    if service is not ...:
        application.state.assistant_service = service
    return application


async def post(application, payload):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        return await client.post("/v1/assistant/query", json=payload)


async def test_typed_assistant_endpoint_returns_ids_and_result():
    service = FakeAssistant(response())
    result = await post(
        app_with(service),
        {
            "message": "What are the marine conditions?",
            "preferred_language": "en",
            "latitude": 20.5,
            "longitude": 72.9,
            "requested_time": "2026-09-09T12:00:00Z",
        },
    )
    assert result.status_code == 200
    assert result.json()["detected_intent"] == "marine_conditions"
    assert result.json()["completion_status"] == "completed"
    assert len(service.calls) == 1


async def test_request_validation_rejects_partial_location_naive_time_and_language():
    application = app_with(FakeAssistant(response()))
    partial = await post(application, {"message": "conditions", "latitude": 20.5})
    naive = await post(
        application,
        {"message": "conditions", "requested_time": "2026-09-09T12:00:00"},
    )
    language = await post(
        application, {"message": "conditions", "preferred_language": "fr"}
    )
    assert partial.status_code == naive.status_code == language.status_code == 422


async def test_disabled_and_failed_assistant_errors_are_sanitized():
    disabled = await post(app_with(), {"message": "conditions"})
    assert disabled.status_code == 503
    assert disabled.json()["detail"]["code"] == "ASSISTANT_NOT_CONFIGURED"

    failed = await post(
        app_with(
            FakeAssistant(
                error=AssistantExecutionError(
                    "ASSISTANT_GRAPH_TIMEOUT",
                    "The assistant request timed out",
                    retryable=True,
                )
            )
        ),
        {"message": "conditions"},
    )
    assert failed.status_code == 503
    body = failed.text
    assert "ASSISTANT_GRAPH_TIMEOUT" in body
    assert "postgresql" not in body
    assert "api_key" not in body

    missing_conversation = await post(
        app_with(
            FakeAssistant(
                error=AssistantExecutionError(
                    "PERSISTENCE_RECORD_NOT_FOUND",
                    "The requested assistant conversation was not found",
                    http_status=404,
                )
            )
        ),
        {"message": "continue", "conversation_id": str(uuid4())},
    )
    assert missing_conversation.status_code == 404
    assert missing_conversation.json()["detail"]["code"] == (
        "PERSISTENCE_RECORD_NOT_FOUND"
    )


def test_openapi_contains_typed_assistant_contract():
    schema = app_with(FakeAssistant(response())).openapi()
    operation = schema["paths"]["/v1/assistant/query"]["post"]
    assert operation["tags"] == ["assistant"]
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    response_ref = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert request_ref.endswith("/AssistantRequest")
    assert response_ref.endswith("/AssistantResponse")
    request_schema = schema["components"]["schemas"]["AssistantRequest"]
    assert request_schema["properties"]["latitude"]["anyOf"][0]["type"] == "number"
