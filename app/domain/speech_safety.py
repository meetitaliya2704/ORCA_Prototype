from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.graph import _extract_coordinates_from_text


_LIMIT_PATTERNS = [
    # Wave heights: e.g. wave height 2.5m, wave 2.5 metres, 2.5m waves
    (
        "max_wave_height_m",
        re.compile(
            r"(?:wave(?:s)?\s*(?:height)?\s*(?:of|up\s*to|below|under)?\s*|height\s*)(\d+(?:\.\d+)?)\s*(?:m\b|meter|metre)",
            re.IGNORECASE,
        ),
    ),
    (
        "max_wave_height_m",
        re.compile(
            r"(\d+(?:\.\d+)?)\s*(?:m\b|meter|metre)s?\s*(?:wave|swell)",
            re.IGNORECASE,
        ),
    ),
    # Wind speeds: e.g. wind speed 15 knots, 15 kt wind, 10 m/s
    (
        "max_wind_speed_kts",
        re.compile(
            r"(?:wind\s*(?:speed)?\s*(?:of|up\s*to|below|under)?\s*)(\d+(?:\.\d+)?)\s*(?:kt|knot|kts|knots)",
            re.IGNORECASE,
        ),
    ),
    (
        "max_wind_speed_mps",
        re.compile(
            r"(?:wind\s*(?:speed)?\s*(?:of|up\s*to|below|under)?\s*)(\d+(?:\.\d+)?)\s*(?:m/s|mps)",
            re.IGNORECASE,
        ),
    ),
]

_SENSITIVE_KEYWORD_REGEX = re.compile(
    r"\b(latitude|longitude|lat|lon|degrees?|pfz|potential\s+fishing\s+zone|wave|wind|knot|knots|metre|meter|kilometre|kilometer|nautical\s+mile)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class VoiceSafetyEvaluation:
    requires_confirmation: bool
    confirmation_prompt: str
    detected_coordinates: tuple[float, float] | None
    detected_limits: dict[str, float] | None
    safety_warning: str | None


def evaluate_voice_transcript_safety(text: str) -> VoiceSafetyEvaluation:
    """Evaluate a voice transcript for navigation safety.

    Mandatory safety rule:
    Never immediately execute a voice transcript containing coordinates or vessel limits.
    Users must confirm or correct the transcript first to prevent critical misrecognitions
    (e.g., 72.9 becoming 79, metres becoming kilometres, wave height 2.5 becoming 25).
    """
    clean_text = text.strip()
    if not clean_text:
        return VoiceSafetyEvaluation(
            requires_confirmation=False,
            confirmation_prompt="",
            detected_coordinates=None,
            detected_limits=None,
            safety_warning=None,
        )

    # 1. Detect coordinates
    coords = _extract_coordinates_from_text(clean_text)

    # 2. Detect vessel operational limits
    detected_limits: dict[str, float] = {}
    for key, pattern in _LIMIT_PATTERNS:
        match = pattern.search(clean_text)
        if match:
            try:
                val = float(match.group(1))
                detected_limits[key] = val
            except (ValueError, IndexError):
                pass

    has_sensitive_keywords = bool(_SENSITIVE_KEYWORD_REGEX.search(clean_text))
    has_critical_data = coords is not None or bool(detected_limits) or has_sensitive_keywords

    safety_warning: str | None = None
    if coords is not None or detected_limits:
        safety_warning = (
            "⚠️ Please double-check coordinates and operational limits before proceeding. "
            "Microphone transcription can occasionally mishear numbers (e.g. 72.9 as 79 or 2.5 as 25)."
        )

    confirmation_prompt = f'We understood: "{clean_text}". Continue?'

    # In the voice workflow, confirmation is always required so the user reviews the transcript
    return VoiceSafetyEvaluation(
        requires_confirmation=True,
        confirmation_prompt=confirmation_prompt,
        detected_coordinates=coords,
        detected_limits=detected_limits or None,
        safety_warning=safety_warning,
    )

