import asyncio
import json

from app.clients.incois_pfz import (
    IncoisPFZClient,
    PFZSourceUnavailableError,
)
from app.core.config import get_settings
from app.parsers.pfz_html import PFZParseError
from app.services.pfz import PFZPreviewService


async def ingest_configured_sectors() -> dict[str, object]:
    settings = get_settings()
    service = PFZPreviewService(
        IncoisPFZClient(
            base_url=settings.incois_base_url,
            connect_timeout=settings.http_connect_timeout,
            read_timeout=settings.http_read_timeout,
            session_attempts=settings.pfz_session_attempts,
        )
    )

    advisories: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []

    for sector_code in settings.configured_pfz_sectors:
        try:
            advisory = await service.preview_sector(sector_code)
            advisories.append(advisory.model_dump(mode="json"))
        except (PFZSourceUnavailableError, PFZParseError, ValueError) as exc:
            failures.append({"sector_code": sector_code, "error": str(exc)})

    return {
        "status": "completed" if not failures else "completed_with_failures",
        "advisories": advisories,
        "failures": failures,
    }


if __name__ == "__main__":
    result = asyncio.run(ingest_configured_sectors())
    print(json.dumps(result, indent=2))

