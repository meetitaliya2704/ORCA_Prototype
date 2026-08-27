from app.services.cache import MemoryJsonCache


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


async def test_memory_cache_honors_ttl_without_sleeping() -> None:
    clock = FakeClock()
    cache = MemoryJsonCache(clock=clock)
    value = {"source": "INCOIS"}

    await cache.set("pfz", value, ttl=30)

    assert await cache.get("pfz") == value
    clock.value = 129.999
    assert await cache.get("pfz") == value

    clock.value = 130.0
    assert await cache.get("pfz") is None
    assert "pfz" not in cache._values
