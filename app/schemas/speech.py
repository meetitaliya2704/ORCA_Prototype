from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceTranscriptionResponse(BaseModel):
    """Normalized response for voice query speech-to-text transcription."""

    text: str = Field(..., description="Transcribed query text in user's spoken language")
    language: str | None = Field(default=None, description="Detected source language name or ISO code")
    duration_seconds: float | None = Field(default=None, ge=0.0, description="Duration of processed audio in seconds")
    requires_confirmation: bool = Field(
        default=False,
        description="Whether this voice transcript contains coordinates, vessel limits, or safety-critical data requiring user verification before execution",
    )
    confirmation_prompt: str | None = Field(
        default=None,
        description="User-facing confirmation message formatted for safety review",
    )
    detected_coordinates: tuple[float, float] | None = Field(
        default=None,
        description="Coordinates (latitude, longitude) extracted from speech if detected",
    )
    detected_limits: dict[str, float] | None = Field(
        default=None,
        description="Extracted operational limits such as wave height or wind speed",
    )
    safety_warning: str | None = Field(
        default=None,
        description="Warning prompt instructing user to verify potentially misrecognized numbers",
    )

