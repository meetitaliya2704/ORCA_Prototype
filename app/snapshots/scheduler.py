from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from typing import Protocol


class SchedulableSnapshotManager(Protocol):
    def tile(self, latitude: float, longitude: float): ...
    async def schedule_if_due(self, latitude: float, longitude: float) -> str | None: ...


class SnapshotScheduler:
    """Small lifespan-owned scheduler for configured SST prewarm tiles."""

    def __init__(
        self,
        *,
        manager: SchedulableSnapshotManager,
        points: Iterable[tuple[float, float]],
        check_seconds: float,
        sleep: Callable[[float], object] = asyncio.sleep,
    ) -> None:
        self.manager = manager
        unique: dict[str, tuple[float, float]] = {}
        for latitude, longitude in points:
            unique.setdefault(manager.tile(latitude, longitude).safe_id, (latitude, longitude))
        self.points = tuple(unique.values())
        self.check_seconds = check_seconds
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None

    def start(self, *, warm_immediately: bool) -> None:
        if self._task is None and self.points:
            self._task = asyncio.create_task(
                self._run(warm_immediately), name="orca-marine-snapshot-scheduler"
            )

    async def _run(self, warm_immediately: bool) -> None:
        try:
            if warm_immediately:
                await self.check()
            while True:
                await self._sleep(self.check_seconds)  # type: ignore[misc]
                await self.check()
        except asyncio.CancelledError:
            raise

    async def check(self) -> tuple[str, ...]:
        jobs: list[str] = []
        for latitude, longitude in self.points:
            job_id = await self.manager.schedule_if_due(latitude, longitude)
            if job_id is not None:
                jobs.append(job_id)
        return tuple(jobs)

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
