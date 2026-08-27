import asyncio
from datetime import UTC, datetime

import httpx

from app.schemas.marine import SourceResult, SourceStatus


class DemoMarineSource:
    """Deterministic adapter used until an official adapter replaces it."""

    def __init__(self, name: str, variable: str, value: float, unit: str):
        self.name = name
        self.variable = variable
        self.value = value
        self.unit = unit

    async def fetch(
        self,
        client: httpx.AsyncClient,
        latitude: float,
        longitude: float,
    ) -> SourceResult:
        del client
        await asyncio.sleep(0.01)

        return SourceResult(
            source=self.name,
            status=SourceStatus.FRESH,
            data={
                "variable": self.variable,
                "value": self.value,
                "unit": self.unit,
                "latitude": latitude,
                "longitude": longitude,
                "quality": "demo",
            },
            fetched_at=datetime.now(UTC),
        )

