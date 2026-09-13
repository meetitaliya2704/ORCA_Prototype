from __future__ import annotations

import json
import httpx
import pytest
from pydantic import SecretStr

from app.agents.errors import AssistantExecutionError
from app.domain.speech_safety import evaluate_voice_transcript_safety
from app.services.speech import GroqSpeechTranscriptionService


@pytest.mark.asyncio
async def test_speech_service_transcribes_audio_successfully():
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "task": "transcribe",
                "language": "English",
                "duration": 4.5,
                "text": "What are the wave conditions near Mumbai?",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GroqSpeechTranscriptionService(
            api_key=SecretStr("groq-test-key"),
            model="whisper-large-v3-turbo",
            http_client=client,
        )
        result = await service.transcribe(
            audio_bytes=b"fake-audio-bytes-for-testing",
            filename="query.webm",
            content_type="audio/webm",
        )

    assert result.text == "What are the wave conditions near Mumbai?"
    assert result.language == "English"
    assert result.duration_seconds == 4.5
    assert result.requires_confirmation is True
    assert 'We understood: "What are the wave conditions near Mumbai?". Continue?' in result.confirmation_prompt
    assert len(captured_requests) == 1


@pytest.mark.asyncio
async def test_speech_safety_detects_coordinates_and_prompts_confirmation():
    transcript = "Find the nearest PFZ from latitude 20.5, longitude 72.9"
    safety = evaluate_voice_transcript_safety(transcript)

    assert safety.requires_confirmation is True
    assert safety.detected_coordinates == (20.5, 72.9)
    assert safety.confirmation_prompt == 'We understood: "Find the nearest PFZ from latitude 20.5, longitude 72.9". Continue?'
    assert safety.safety_warning is not None
    assert "72.9 as 79" in safety.safety_warning


@pytest.mark.asyncio
async def test_speech_safety_detects_vessel_limits():
    transcript = "Can I venture out with wave height 2.5 metres and wind speed 15 knots?"
    safety = evaluate_voice_transcript_safety(transcript)

    assert safety.requires_confirmation is True
    assert safety.detected_limits is not None
    assert safety.detected_limits.get("max_wave_height_m") == 2.5
    assert safety.detected_limits.get("max_wind_speed_kts") == 15.0
    assert safety.safety_warning is not None


@pytest.mark.asyncio
async def test_speech_service_rejects_empty_audio():
    service = GroqSpeechTranscriptionService(api_key=SecretStr("test-key"))
    with pytest.raises(AssistantExecutionError) as exc_info:
        await service.transcribe(audio_bytes=b"")
    assert exc_info.value.code == "SPEECH_EMPTY_AUDIO"
    assert exc_info.value.http_status == 400


@pytest.mark.asyncio
async def test_speech_service_rejects_oversized_audio():
    service = GroqSpeechTranscriptionService(
        api_key=SecretStr("test-key"),
        max_file_bytes=100,
    )
    with pytest.raises(AssistantExecutionError) as exc_info:
        await service.transcribe(audio_bytes=b"x" * 200)
    assert exc_info.value.code == "SPEECH_FILE_TOO_LARGE"
    assert exc_info.value.http_status == 413


@pytest.mark.asyncio
async def test_speech_service_maps_rate_limiting_429():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GroqSpeechTranscriptionService(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        with pytest.raises(AssistantExecutionError) as exc_info:
            await service.transcribe(audio_bytes=b"fake-audio")
        assert exc_info.value.code == "SPEECH_RATE_LIMITED"
        assert exc_info.value.http_status == 429


@pytest.mark.asyncio
async def test_speech_service_maps_server_error_500():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GroqSpeechTranscriptionService(
            api_key=SecretStr("test-key"),
            http_client=client,
        )
        with pytest.raises(AssistantExecutionError) as exc_info:
            await service.transcribe(audio_bytes=b"fake-audio")
        assert exc_info.value.code == "SPEECH_UNAVAILABLE"
        assert exc_info.value.http_status == 503

