from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import SecretStr

from app.agents.errors import AssistantExecutionError
from app.domain.speech_safety import evaluate_voice_transcript_safety
from app.schemas.speech import VoiceTranscriptionResponse


_DEFAULT_MARITIME_PROMPT = (
    "ORCA marine intelligence queries: Potential Fishing Zones, PFZ, INCOIS advisory, "
    "coordinates, latitude, longitude, degrees, sea surface temperature, SST, "
    "wave height, wind speed, ocean currents, tides, chlorophyll, knots, metres, km, "
    "nautical miles, coastal landing centres, Veraval, Porbandar, Mumbai, Mangalore, "
    "Cochin, Chennai, Visakhapatnam, Paradip."
)


class GroqSpeechTranscriptionService:
    """Audio transcription service using Groq's Whisper API with maritime safety gates."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str = "whisper-large-v3-turbo",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_seconds: float = 15.0,
        max_file_bytes: int = 15 * 1024 * 1024,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_file_bytes = max_file_bytes
        self._http_client = http_client

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: str | None = None,
        custom_prompt: str | None = None,
    ) -> VoiceTranscriptionResponse:
        """Transcribe in-memory audio bytes to text and evaluate safety gates."""
        if not audio_bytes or len(audio_bytes.strip()) == 0:
            raise AssistantExecutionError(
                "SPEECH_EMPTY_AUDIO",
                "Uploaded audio recording is empty",
                retryable=False,
                http_status=400,
            )

        if len(audio_bytes) > self.max_file_bytes:
            raise AssistantExecutionError(
                "SPEECH_FILE_TOO_LARGE",
                f"Audio recording exceeds maximum allowed size of {self.max_file_bytes // (1024 * 1024)}MB",
                retryable=False,
                http_status=413,
            )

        headers = {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
        }
        files = {
            "file": (filename, audio_bytes, content_type or "audio/webm"),
        }
        data: dict[str, Any] = {
            "model": self.model,
            "response_format": "verbose_json",
            "temperature": "0",
            "prompt": (custom_prompt or _DEFAULT_MARITIME_PROMPT),
        }
        if language and language.strip():
            data["language"] = language.strip()

        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=self.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/audio/transcriptions",
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=self.timeout_seconds,
                    )
        except httpx.TimeoutException as exc:
            raise AssistantExecutionError(
                "SPEECH_TIMEOUT",
                "Audio transcription request timed out",
                retryable=True,
                http_status=504,
            ) from exc
        except httpx.NetworkError as exc:
            raise AssistantExecutionError(
                "SPEECH_UNAVAILABLE",
                "Network failure communicating with transcription service",
                retryable=True,
                http_status=503,
            ) from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise AssistantExecutionError(
                "SPEECH_UNAVAILABLE",
                f"Unexpected failure contacting speech service: {exc}",
                retryable=True,
                http_status=503,
            ) from exc

        if response.status_code == 429:
            raise AssistantExecutionError(
                "SPEECH_RATE_LIMITED",
                "Speech transcription rate limit reached. Please try again in a moment.",
                retryable=True,
                http_status=429,
            )
        if response.status_code in {401, 403}:
            raise AssistantExecutionError(
                "SPEECH_AUTHENTICATION_FAILED",
                "Speech service authentication failed",
                retryable=False,
                http_status=500,
            )
        if 400 <= response.status_code < 500:
            error_detail = "Audio could not be processed by transcription service"
            try:
                err_data = response.json()
                if "error" in err_data and "message" in err_data["error"]:
                    error_detail = err_data["error"]["message"]
            except Exception:
                pass
            raise AssistantExecutionError(
                "SPEECH_INVALID_AUDIO",
                error_detail,
                retryable=False,
                http_status=400,
            )
        if response.status_code >= 500:
            raise AssistantExecutionError(
                "SPEECH_UNAVAILABLE",
                "Speech transcription provider is temporarily unavailable",
                retryable=True,
                http_status=503,
            )

        try:
            result_json = response.json()
        except Exception as exc:
            raise AssistantExecutionError(
                "SPEECH_PARSE_FAILED",
                "Invalid response received from speech transcription service",
                retryable=True,
                http_status=502,
            ) from exc

        transcribed_text = (result_json.get("text") or "").strip()
        detected_language = result_json.get("language")
        duration = result_json.get("duration")

        # Deterministic safety gate evaluation
        safety = evaluate_voice_transcript_safety(transcribed_text)

        return VoiceTranscriptionResponse(
            text=transcribed_text,
            language=str(detected_language) if detected_language else None,
            duration_seconds=float(duration) if duration is not None else None,
            requires_confirmation=safety.requires_confirmation,
            confirmation_prompt=safety.confirmation_prompt,
            detected_coordinates=safety.detected_coordinates,
            detected_limits=safety.detected_limits,
            safety_warning=safety.safety_warning,
        )

