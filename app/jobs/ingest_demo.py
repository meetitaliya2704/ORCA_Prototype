import asyncio
import json

import httpx

from app.clients.demo import DemoMarineSource
from app.services.cache import MemoryJsonCache
from app.services.marine import MarineConditionsService


async def ingest_demo() -> None:
    sources = [
        DemoMarineSource("sst", "SST", 29.4, "degC"),
        DemoMarineSource("waves", "WAVE_HEIGHT", 1.6, "m"),
        DemoMarineSource("wind", "WIND_SPEED", 18.0, "km/h"),
    ]

    transport = httpx.AsyncHTTPTransport(retries=1)
    async with httpx.AsyncClient(
        timeout=20.0,
        transport=transport,
    ) as client:
        service = MarineConditionsService(
            client=client,
            cache=MemoryJsonCache(),
            sources=sources,
            cache_ttl=300,
        )
        result = await service.get_conditions(20.5, 72.9)

    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    asyncio.run(ingest_demo())
