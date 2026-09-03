import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.snapshots.jobs import RefreshJobManager
from app.snapshots.models import RefreshJobStatus
from app.snapshots.store import InMemorySnapshotStore
from tests.test_snapshot_store import snapshot


@pytest.mark.asyncio
async def test_identical_refreshes_are_single_flight():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    store = InMemorySnapshotStore(now=lambda: now)
    jobs = RefreshJobManager(store=store, now=lambda: now)
    gate = asyncio.Event()
    calls = 0

    async def factory(job_id):
        nonlocal calls
        calls += 1
        await gate.wait()
        return snapshot(now)

    first, second = await asyncio.gather(*[
        jobs.request(deduplication_key="key", source="sst", tile_id="tile", factory=factory)
        for _ in range(2)
    ])
    assert first.job_id == second.job_id
    gate.set()
    result = await jobs.wait(first.job_id, 1)
    assert result.state == RefreshJobStatus.SUCCEEDED
    assert calls == 1


@pytest.mark.asyncio
async def test_timeout_does_not_cancel_shared_refresh():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    jobs = RefreshJobManager(store=InMemorySnapshotStore(now=lambda: now), now=lambda: now)
    gate = asyncio.Event()
    async def factory(job_id):
        await gate.wait()
        return snapshot(now)
    job = await jobs.request(deduplication_key="key", source="sst", tile_id="tile", factory=factory)
    assert (await jobs.wait(job.job_id, 0.001)).state == RefreshJobStatus.RUNNING
    gate.set()
    assert (await jobs.wait(job.job_id, 1)).state == RefreshJobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_failure_is_sanitized_and_does_not_publish():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    store = InMemorySnapshotStore(now=lambda: now)
    jobs = RefreshJobManager(store=store, now=lambda: now)
    async def factory(job_id):
        raise RuntimeError("secret C:/Users/name/credentials token=abc")
    job = await jobs.request(deduplication_key="key", source="sst", tile_id="tile", factory=factory)
    result = await jobs.wait(job.job_id, 1)
    assert result.state == RefreshJobStatus.FAILED
    assert "secret" not in (result.message or "")
    assert (await store.get_latest("key")).snapshot is None


@pytest.mark.asyncio
async def test_cancellation_never_publishes_partial_snapshot():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    store = InMemorySnapshotStore(now=lambda: now)
    jobs = RefreshJobManager(store=store, now=lambda: now)
    gate = asyncio.Event()
    async def factory(job_id):
        await gate.wait()
        return snapshot(now)
    job = await jobs.request(deduplication_key="key", source="sst", tile_id="tile", factory=factory)
    await jobs.close()
    assert (await jobs.get(job.job_id)).state == RefreshJobStatus.CANCELLED
    assert (await store.get_latest("key")).snapshot is None


@pytest.mark.asyncio
async def test_heavy_refresh_concurrency_is_bounded():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    jobs = RefreshJobManager(
        store=InMemorySnapshotStore(now=lambda: now), heavy_concurrency=2, now=lambda: now
    )
    active = maximum = 0
    gate = asyncio.Event()
    async def factory(job_id):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await gate.wait()
        active -= 1
        return snapshot(now)
    requested = [
        await jobs.request(deduplication_key=f"key-{index}", source="sst", tile_id=f"tile-{index}", factory=factory)
        for index in range(4)
    ]
    await asyncio.sleep(0)
    assert maximum == 2
    gate.set()
    await asyncio.gather(*(jobs.wait(item.job_id, 1) for item in requested))
