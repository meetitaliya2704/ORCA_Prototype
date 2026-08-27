import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.clients.incois_pfz import (
    IncoisPFZClient,
    PFZBatchPageBundle,
    PFZBatchSectorResult,
    PFZPageBundle,
    PFZSourceUnavailableError,
)
from app.parsers.pfz_html import PFZParseError
from app.schemas.pfz import (
    DiscoveredPFZSector,
    PFZCacheStatus,
    PFZSnapshot,
)
from app.services.cache import MemoryJsonCache
from app.services.pfz import (
    PFZ_FRESH_CACHE_KEY,
    PFZ_LAST_SUCCESS_CACHE_KEY,
    PFZSnapshotService,
)


FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def one_sector_batch() -> PFZBatchPageBundle:
    sector = DiscoveredPFZSector(
        sector_code="SEC001",
        display_label="Discovery label only",
    )
    return PFZBatchPageBundle(
        discovered_sectors=(sector,),
        sector_results=(
            PFZBatchSectorResult(
                discovered_sector=sector,
                pages=PFZPageBundle(
                    sector_code="SEC001",
                    home_html=load_fixture("incois_home.html"),
                    sector_html=load_fixture("incois_sec001.html"),
                    source_url="https://incois.test/TextData?secid=SEC001",
                ),
            ),
        ),
    )


class FakeBatchClient:
    home_url = (
        "https://incois.test/TextDataHome?mfid=1&request_locale=en"
    )
    fetch_concurrency = 4

    def __init__(
        self,
        batch: PFZBatchPageBundle | None = None,
        error: Exception | None = None,
    ) -> None:
        self.batch = batch or one_sector_batch()
        self.error = error
        self.batch_calls = 0
        self.retry_calls: list[str] = []

    async def fetch_batch_once(self) -> PFZBatchPageBundle:
        self.batch_calls += 1
        if self.error is not None:
            raise self.error
        return self.batch

    async def fetch_sector_once_fresh(self, sector_code: str) -> PFZPageBundle:
        self.retry_calls.append(sector_code)
        if self.error is not None:
            raise self.error
        raise AssertionError("A valid initial page must not be retried")


class RecordingMemoryCache(MemoryJsonCache):
    def __init__(self) -> None:
        super().__init__()
        self.writes: list[tuple[str, int]] = []

    async def set(self, key: str, value: dict, ttl: int) -> None:
        self.writes.append((key, ttl))
        await super().set(key, value, ttl)


def make_service(
    client,
    cache: MemoryJsonCache | None = None,
) -> PFZSnapshotService:
    return PFZSnapshotService(
        client=client,
        cache=cache or MemoryJsonCache(),
        fresh_ttl_seconds=1800,
        stale_ttl_seconds=86400,
        now=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_complete_refresh_retries_failed_sector_with_fresh_session() -> None:
    home_calls = 0
    sector_calls: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal home_calls
        if request.url.path.endswith("TextDataHome"):
            home_calls += 1
            return httpx.Response(
                200,
                text=load_fixture("incois_home_sectors.html"),
                headers={"set-cookie": f"JSESSIONID=session-{home_calls}; Path=/"},
            )

        sector_code = request.url.params["secid"]
        sector_calls[sector_code] = sector_calls.get(sector_code, 0) + 1
        expected_session = 2 if sector_code == "SEC003" and sector_calls[sector_code] == 2 else 1
        assert request.headers.get("cookie") == f"JSESSIONID=session-{expected_session}"

        if sector_code == "SEC003" and sector_calls[sector_code] == 1:
            return httpx.Response(200, text=load_fixture("invalid_session.html"))
        if sector_code == "SEC003":
            return httpx.Response(
                200,
                text=load_fixture("incois_sectorname_variant.html"),
            )
        return httpx.Response(200, text=load_fixture("incois_sec001.html"))

    transport = httpx.MockTransport(handler)
    client = IncoisPFZClient(
        base_url="https://incois.test",
        fetch_concurrency=2,
        client_factory=lambda: httpx.AsyncClient(
            transport=transport,
            base_url="https://incois.test",
            follow_redirects=True,
        ),
    )

    snapshot = await make_service(client).get_snapshot()

    assert home_calls == 2
    assert sector_calls == {"SEC001": 1, "SEC003": 2, "SEC004": 1}
    assert snapshot.completeness == "complete"
    assert snapshot.cache_status == "refreshed"
    assert snapshot.discovered_sector_count == 3
    assert snapshot.successful_sector_count == 3
    assert snapshot.failed_sector_count == 0
    assert snapshot.total_location_count == 3
    assert [
        result.discovered_sector.sector_code
        for result in snapshot.successful_sectors
    ] == ["SEC001", "SEC003", "SEC004"]
    assert snapshot.successful_sectors[1].advisory.region_name == "Odisha"
    assert snapshot.successful_sectors[1].discovered_sector.display_label != "Odisha"


@pytest.mark.asyncio
async def test_partial_snapshot_preserves_typed_failed_sector() -> None:
    valid_sector = DiscoveredPFZSector(
        sector_code="SEC001",
        display_label="First",
    )
    failed_sector = DiscoveredPFZSector(
        sector_code="SEC003",
        display_label="Second",
    )
    batch = PFZBatchPageBundle(
        discovered_sectors=(valid_sector, failed_sector),
        sector_results=(
            one_sector_batch().sector_results[0],
            PFZBatchSectorResult(
                discovered_sector=failed_sector,
                error=PFZParseError("missing markers"),
            ),
        ),
    )
    client = FakeBatchClient(batch=batch, error=PFZParseError("still invalid"))
    client.error = None

    async def failed_retry(sector_code: str) -> PFZPageBundle:
        client.retry_calls.append(sector_code)
        raise PFZParseError("still invalid")

    client.fetch_sector_once_fresh = failed_retry

    snapshot = await make_service(client).get_snapshot()

    assert snapshot.completeness == "partial"
    assert snapshot.successful_sector_count == 1
    assert snapshot.failed_sector_count == 1
    assert snapshot.failed_sectors[0].discovered_sector.sector_code == "SEC003"
    assert snapshot.failed_sectors[0].code == "INVALID_PFZ_RESPONSE"
    assert client.retry_calls == ["SEC003"]


@pytest.mark.asyncio
async def test_fresh_cache_hit_makes_no_source_request() -> None:
    cache = MemoryJsonCache()
    priming_client = FakeBatchClient()
    priming_service = make_service(priming_client, cache)
    refreshed = await priming_service.get_snapshot()

    zero_request_client = FakeBatchClient(
        error=AssertionError("source must not be called")
    )
    cached = await make_service(zero_request_client, cache).get_snapshot()

    assert refreshed.cache_status == "refreshed"
    assert cached.cache_status == "fresh"
    assert zero_request_client.batch_calls == 0


@pytest.mark.asyncio
async def test_cache_miss_writes_fresh_and_last_success_entries() -> None:
    cache = RecordingMemoryCache()
    client = FakeBatchClient()

    snapshot = await make_service(client, cache).get_snapshot()

    assert snapshot.cache_status == "refreshed"
    assert client.batch_calls == 1
    assert await cache.get(PFZ_FRESH_CACHE_KEY) is not None
    assert await cache.get(PFZ_LAST_SUCCESS_CACHE_KEY) is not None
    assert cache.writes == [
        (PFZ_FRESH_CACHE_KEY, 1800),
        (PFZ_LAST_SUCCESS_CACHE_KEY, 86400),
    ]


@pytest.mark.asyncio
async def test_stale_fallback_preserves_timestamps_and_adds_warning() -> None:
    cache = MemoryJsonCache()
    original = await make_service(FakeBatchClient(), cache).get_snapshot()
    cache._values.pop(PFZ_FRESH_CACHE_KEY)
    unavailable = FakeBatchClient(
        error=PFZSourceUnavailableError("private transport detail")
    )

    stale = await make_service(unavailable, cache).get_snapshot()

    assert stale.cache_status == "stale"
    assert stale.retrieved_at == original.retrieved_at
    assert stale.generated_at == original.generated_at
    assert stale.successful_sectors[0].advisory.fetched_at == (
        original.successful_sectors[0].advisory.fetched_at
    )
    assert stale.warnings[-1] == (
        "PFZ refresh failed; returning the last successful cached snapshot"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        PFZSourceUnavailableError("offline"),
        PFZParseError("invalid home page"),
    ],
)
async def test_refresh_failure_without_stale_cache_raises_typed_error(
    error: Exception,
) -> None:
    service = make_service(FakeBatchClient(error=error))

    with pytest.raises(type(error)):
        await service.get_snapshot()


@pytest.mark.asyncio
async def test_simultaneous_cache_misses_launch_one_refresh() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class SlowClient(FakeBatchClient):
        async def fetch_batch_once(self) -> PFZBatchPageBundle:
            self.batch_calls += 1
            started.set()
            await release.wait()
            return self.batch

    client = SlowClient()
    service = make_service(client)
    tasks = [asyncio.create_task(service.get_snapshot()) for _ in range(5)]
    await started.wait()
    release.set()

    snapshots = await asyncio.gather(*tasks)

    assert client.batch_calls == 1
    assert sum(item.cache_status == "refreshed" for item in snapshots) == 1
    assert sum(item.cache_status == "fresh" for item in snapshots) == 4
