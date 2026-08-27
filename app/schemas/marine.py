from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SourceStatus(StrEnum):
    FRESH = "fresh"
    CACHED = "cached"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class SourceResult(BaseModel):
    source: str
    status: SourceStatus
    data: dict[str, Any] | None = None
    error: str | None = None
    fetched_at: datetime | None = None
    cached: bool = False


class MarineConditionsResponse(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    generated_at: datetime
    sources: dict[str, SourceResult]
    warning: str = (
        "Prototype decision support only; verify official marine advisories."
    )

