from typing import Protocol

import httpx

from app.schemas.marine import SourceResult


class MarineSource(Protocol):
    name: str

    async def fetch(
        self,
        client: httpx.AsyncClient,
        latitude: float,
        longitude: float,
    ) -> SourceResult:
        """Fetch one normalized marine-source result."""
        ...

