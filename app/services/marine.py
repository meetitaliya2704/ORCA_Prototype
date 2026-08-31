import asyncio
from datetime import UTC, datetime

import httpx

from app.clients.base import MarineSource
from app.schemas.marine import (
    MarineConditionsResponse,
    SourceResult,
    SourceStatus,
)
from app.services.cache import JsonCache


class MarineConditionsService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        cache: JsonCache,
        sources: list[MarineSource],
        cache_ttl: int,
    ) -> None:
        self.client = client
        self.cache = cache
        self.sources = sources
        self.cache_ttl = cache_ttl

    async def get_conditions(
        self,
        latitude: float,
        longitude: float,
        at: datetime | None = None,
    ) -> MarineConditionsResponse:
        time_bucket = at.astimezone(UTC).isoformat() if at else "current"
        cache_key = (
            f"conditions:{latitude:.6f}:{longitude:.6f}:{time_bucket}"
        )
        cached = await self.cache.get(cache_key)

        if cached is not None:
            response = MarineConditionsResponse.model_validate(cached)
            for result in response.sources.values():
                result.cached = True
                result.status = SourceStatus.CACHED
            return response

        tasks = [
            source.fetch(self.client, latitude, longitude, at)
            for source in self.sources
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, SourceResult] = {}
        for source, result in zip(self.sources, raw_results, strict=True):
            if isinstance(result, Exception):
                results[source.name] = SourceResult(
                    source=source.name,
                    status=SourceStatus.UNAVAILABLE,
                    error=str(result),
                )
            else:
                results[source.name] = result

        response = MarineConditionsResponse(
            latitude=latitude,
            longitude=longitude,
            generated_at=datetime.now(UTC),
            sources=results,
        )
        await self.cache.set(
            cache_key,
            response.model_dump(mode="json"),
            self.cache_ttl,
        )
        return response

