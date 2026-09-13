from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.agents.errors import AssistantExecutionError
from app.api.routes.speech import router
from app.schemas.speech import VoiceTranscriptionResponse


class FakeSpeechService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def transcribe(self, *, audio_bytes, filename="audio.webm", content_type="audio/webm", language=None):
        self.calls.append({
            "audio_bytes": audio_bytes,
            "filename": filename,
            "content_type": content_type,
            "language": language,
        })
        if self.error:
            raise self.error
        return self.result


def app_with_speech(service=...):
    application = FastAPI()
    application.include_router(router, prefix="/v1")
    if service is not ...:
        application.state.speech_service = service
    return application


@pytest.mark.asyncio
async def test_transcribe_endpoint_returns_success():
    expected = VoiceTranscriptionResponse(
        text="Find the nearest PFZ from latitude 20.5, longitude 72.9",
        language="English",
        duration_seconds=3.2,
        requires_confirmation=True,
        confirmation_prompt='We understood: "Find the nearest PFZ from latitude 20.5, longitude 72.9". Continue?',
        detected_coordinates=(20.5, 72.9),
        safety_warning="Please verify coordinates before continuing",
    )
    service = FakeSpeechService(result=expected)
    app = app_with_speech(service)

    files = {"file": ("query.webm", b"dummy-audio-bytes", "audio/webm")}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/v1/assistant/transcribe", files=files)

    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == expected.text
    assert data["requires_confirmation"] is True
    assert data["detected_coordinates"] == [20.5, 72.9]
    assert len(service.calls) == 1


@pytest.mark.asyncio
async def test_transcribe_endpoint_returns_503_when_service_not_configured():
    app = app_with_speech(None)
    files = {"file": ("query.webm", b"dummy-audio-bytes", "audio/webm")}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/v1/assistant/transcribe", files=files)

    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "SPEECH_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_transcribe_endpoint_maps_execution_errors():
    service = FakeSpeechService(
        error=AssistantExecutionError("SPEECH_RATE_LIMITED", "Too many requests", http_status=429)
    )
    app = app_with_speech(service)
    files = {"file": ("query.webm", b"dummy-audio-bytes", "audio/webm")}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/v1/assistant/transcribe", files=files)

    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "SPEECH_RATE_LIMITED"

