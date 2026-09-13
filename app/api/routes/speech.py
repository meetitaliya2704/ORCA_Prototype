from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status

from app.agents.errors import AssistantExecutionError
from app.schemas.speech import VoiceTranscriptionResponse

router = APIRouter(tags=["speech"])


@router.post(
    "/assistant/transcribe",
    response_model=VoiceTranscriptionResponse,
    summary="Transcribe voice audio to text with maritime safety evaluation",
    responses={
        400: {"description": "Invalid or unprocessable audio data"},
        413: {"description": "Audio file exceeds maximum size limit"},
        429: {"description": "Transcription rate limit reached"},
        503: {"description": "Speech transcription service is not configured or unavailable"},
    },
)
async def transcribe_assistant_voice(
    request: Request,
    file: UploadFile = File(..., description="Audio recording file (webm, wav, mp4, ogg, etc.)"),
    language: str | None = Query(default=None, description="Optional ISO language hint (e.g. en, hi, gu)"),
) -> VoiceTranscriptionResponse:
    """Transcribe audio query using Whisper and evaluate navigation safety gates.

    Does not store raw audio on disk. Returns transcript and safety confirmation prompt.
    """
    speech_service = getattr(request.app.state, "speech_service", None)
    if speech_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SPEECH_NOT_CONFIGURED",
                "message": "Voice transcription service is not configured or enabled",
            },
        )

    try:
        audio_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SPEECH_READ_FAILED", "message": f"Failed reading uploaded audio: {exc}"},
        ) from exc

    try:
        return await speech_service.transcribe(
            audio_bytes=audio_bytes,
            filename=file.filename or "audio.webm",
            content_type=file.content_type or "audio/webm",
            language=language,
        )
    except AssistantExecutionError as exc:
        raise HTTPException(
            status_code=exc.http_status or 500,
            detail={"code": exc.code, "message": str(exc)},
        ) from None

