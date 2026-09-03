import asyncio

import pytest

from app.snapshots.scheduler import SnapshotScheduler


class FakeManager:
    def __init__(self):
        self.calls = []

    class Tile:
        def __init__(self, safe_id): self.safe_id = safe_id

    def tile(self, latitude, longitude):
        return self.Tile(f"{int(latitude // 2)}:{int(longitude // 2)}")

    async def schedule_if_due(self, latitude, longitude):
        self.calls.append((latitude, longitude))
        return f"job-{len(self.calls)}"


@pytest.mark.asyncio
async def test_scheduler_deduplicates_prewarm_tiles():
    manager = FakeManager()
    scheduler = SnapshotScheduler(
        manager=manager,
        points=((18.025, 70.525), (18.1, 70.6), (20.5, 72.9)),
        check_seconds=60,
    )
    jobs = await scheduler.check()
    assert len(jobs) == 2
    assert len(manager.calls) == 2


@pytest.mark.asyncio
async def test_scheduler_start_is_non_blocking_and_shutdown_is_clean():
    manager = FakeManager()
    gate = asyncio.Event()
    async def sleep(_): await gate.wait()
    scheduler = SnapshotScheduler(
        manager=manager, points=((18.025, 70.525),), check_seconds=60, sleep=sleep
    )
    scheduler.start(warm_immediately=True)
    await asyncio.sleep(0)
    assert manager.calls == [(18.025, 70.525)]
    await scheduler.close()
    assert scheduler._task is None


def test_disabled_scheduler_with_no_points_starts_no_task():
    scheduler = SnapshotScheduler(
        manager=FakeManager(), points=(), check_seconds=60
    )
    scheduler.start(warm_immediately=True)
    assert scheduler._task is None
