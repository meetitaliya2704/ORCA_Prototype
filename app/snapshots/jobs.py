from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.clients.copernicus_sst import (
    InvalidSSTResponseError,
    SSTAuthenticationError,
    SSTDependencyMissingError,
    SSTSourceNotConfiguredError,
    SSTSourceUnavailableError,
)
from app.core.performance import measured_lock, performance_span
from app.services.sst import NoValidSSTError, sst_error_code
from app.snapshots.models import (
    RefreshFailureClassification,
    RefreshFailureGate,
    RefreshJob,
    RefreshJobStatus,
    RegionalSnapshot,
)
from app.snapshots.store import InMemorySnapshotStore


RefreshFactory = Callable[[str], Awaitable[RegionalSnapshot]]
FailureClassifier = Callable[[Exception], RefreshFailureClassification]
ErrorCodeResolver = Callable[[Exception], str]


def classify_refresh_failure(exc: Exception) -> RefreshFailureClassification:
    if isinstance(exc, NoValidSSTError):
        return RefreshFailureClassification.REQUEST_RESULT
    if isinstance(
        exc,
        (
            SSTAuthenticationError,
            SSTDependencyMissingError,
            SSTSourceNotConfiguredError,
            InvalidSSTResponseError,
            ValueError,
        ),
    ):
        return RefreshFailureClassification.NON_RETRYABLE
    if isinstance(exc, (SSTSourceUnavailableError, TimeoutError, ConnectionError)):
        return RefreshFailureClassification.RETRYABLE
    return RefreshFailureClassification.NON_RETRYABLE


class RefreshBlockedError(RuntimeError):
    def __init__(self, gate: RefreshFailureGate):
        super().__init__("Snapshot refresh is blocked by a prior failure")
        self.gate = gate


class RefreshJobManager:
    def __init__(
        self,
        *,
        store: InMemorySnapshotStore,
        heavy_concurrency: int = 2,
        history_retention_seconds: int = 3600,
        retryable_base_delay_seconds: int = 30,
        retryable_max_delay_seconds: int = 900,
        non_retryable_cooldown_seconds: int = 900,
        now=None,
    ) -> None:
        self.store = store
        self._now = now or (lambda: datetime.now(UTC))
        self._semaphore = asyncio.Semaphore(heavy_concurrency)
        self._retention = timedelta(seconds=history_retention_seconds)
        self._retryable_base_delay = retryable_base_delay_seconds
        self._retryable_max_delay = retryable_max_delay_seconds
        self._non_retryable_cooldown = non_retryable_cooldown_seconds
        self._lock = asyncio.Lock()
        self._jobs: dict[str, RefreshJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._active_by_key: dict[str, str] = {}
        self._failure_gates: dict[str, RefreshFailureGate] = {}

    async def request(
        self, *, deduplication_key: str, source: str, tile_id: str,
        factory: RefreshFactory, failure_gate_key: str | None = None,
        configuration_identity: str = "default", retry_failed: bool = False,
        failure_classifier: FailureClassifier = classify_refresh_failure,
        error_code_resolver: ErrorCodeResolver = sst_error_code,
        failure_message: str = "SST snapshot refresh failed",
    ) -> RefreshJob:
        failure_gate_key = failure_gate_key or deduplication_key
        async with measured_lock(self._lock):
            self._expire_locked()
            existing_id = self._active_by_key.get(deduplication_key)
            if existing_id is not None:
                return self._jobs[existing_id].model_copy(deep=True)
            gate = self._failure_gates.get(failure_gate_key)
            now = self._now().astimezone(UTC)
            if gate is not None and now < gate.blocked_until and not retry_failed:
                raise RefreshBlockedError(gate.model_copy(deep=True))
            job = RefreshJob(
                job_id=uuid4().hex,
                deduplication_key=deduplication_key,
                source=source,
                tile_id=tile_id,
                state=RefreshJobStatus.QUEUED,
                created_at=self._now().astimezone(UTC),
            )
            self._jobs[job.job_id] = job
            self._active_by_key[deduplication_key] = job.job_id
            await self.store.mark_refreshing(deduplication_key)
            self._tasks[job.job_id] = asyncio.create_task(
                self._run(
                    job.job_id,
                    failure_gate_key,
                    configuration_identity,
                    factory,
                    failure_classifier,
                    error_code_resolver,
                    failure_message,
                ),
                name=f"orca-refresh-{job.job_id}"
            )
            return job.model_copy(deep=True)

    async def _run(
        self, job_id: str, failure_gate_key: str,
        configuration_identity: str, factory: RefreshFactory,
        failure_classifier: FailureClassifier,
        error_code_resolver: ErrorCodeResolver,
        failure_message: str,
    ) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = job.model_copy(update={
            "state": RefreshJobStatus.RUNNING,
            "started_at": self._now().astimezone(UTC),
            "attempt_count": job.attempt_count + 1,
        })
        try:
            with performance_span("semaphore.wait"):
                await self._semaphore.acquire()
            try:
                snapshot = await factory(job_id)
            finally:
                self._semaphore.release()
            await self.store.publish(job.deduplication_key, snapshot)
            self._failure_gates.pop(failure_gate_key, None)
            self._jobs[job_id] = self._jobs[job_id].model_copy(update={
                "state": RefreshJobStatus.SUCCEEDED,
                "completed_at": self._now().astimezone(UTC),
                "snapshot_valid_time": snapshot.payload.provider_valid_time,
            })
        except asyncio.CancelledError:
            await self.store.clear_refreshing(job.deduplication_key)
            self._jobs[job_id] = self._jobs[job_id].model_copy(update={
                "state": RefreshJobStatus.CANCELLED,
                "completed_at": self._now().astimezone(UTC),
                "error_code": "REFRESH_CANCELLED",
                "message": "Snapshot refresh was cancelled",
            })
            raise
        except Exception as exc:
            code = error_code_resolver(exc)
            classification = failure_classifier(exc)
            previous = self._failure_gates.get(failure_gate_key)
            attempts = (previous.attempt_count if previous is not None else 0) + 1
            now = self._now().astimezone(UTC)
            if classification == RefreshFailureClassification.RETRYABLE:
                delay = min(
                    self._retryable_base_delay * (2 ** (attempts - 1)),
                    self._retryable_max_delay,
                )
                provider_delay = getattr(exc, "retry_after_seconds", None)
                if isinstance(provider_delay, int) and provider_delay > 0:
                    delay = max(delay, min(provider_delay, self._retryable_max_delay))
                next_retry_at = now + timedelta(seconds=delay)
                retryable = True
                retry_after_seconds = delay
            else:
                delay = self._non_retryable_cooldown
                next_retry_at = None
                retryable = False
                retry_after_seconds = None
            gate = RefreshFailureGate(
                gate_key=failure_gate_key,
                last_job_id=job_id,
                error_code=code,
                classification=classification,
                attempt_count=attempts,
                failed_at=now,
                blocked_until=now + timedelta(seconds=delay),
                configuration_identity=configuration_identity,
            )
            self._failure_gates[failure_gate_key] = gate
            await self.store.record_failed_refresh(job.deduplication_key, code)
            self._jobs[job_id] = self._jobs[job_id].model_copy(update={
                "state": RefreshJobStatus.FAILED,
                "completed_at": self._now().astimezone(UTC),
                "error_code": code,
                "message": failure_message,
                "retryable": retryable,
                "next_retry_at": next_retry_at,
                "retry_after_seconds": retry_after_seconds,
            })
        finally:
            async with self._lock:
                self._active_by_key.pop(job.deduplication_key, None)
                self._tasks.pop(job_id, None)

    async def wait(self, job_id: str, timeout_seconds: float) -> RefreshJob:
        async with self._lock:
            task = self._tasks.get(job_id)
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout_seconds)
            except TimeoutError:
                pass
        return await self.get(job_id)

    async def get(self, job_id: str) -> RefreshJob:
        async with self._lock:
            self._expire_locked()
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job.model_copy(deep=True)

    async def failure_gate(self, key: str) -> RefreshFailureGate | None:
        async with self._lock:
            gate = self._failure_gates.get(key)
            if gate is None or self._now().astimezone(UTC) >= gate.blocked_until:
                return None
            return gate.model_copy(deep=True)

    async def clear_failure_gate(self, key: str) -> None:
        async with self._lock:
            self._failure_gates.pop(key, None)

    def _expire_locked(self) -> None:
        cutoff = self._now().astimezone(UTC) - self._retention
        expired = [
            job_id for job_id, job in self._jobs.items()
            if job.completed_at is not None and job.completed_at < cutoff
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)

    async def close(self) -> None:
        async with self._lock:
            tasks = tuple(self._tasks.items())
        for _, task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        for job_id, _ in tasks:
            job = self._jobs[job_id]
            if job.state in {RefreshJobStatus.QUEUED, RefreshJobStatus.RUNNING}:
                self._jobs[job_id] = job.model_copy(update={
                    "state": RefreshJobStatus.CANCELLED,
                    "completed_at": self._now().astimezone(UTC),
                    "error_code": "REFRESH_CANCELLED",
                    "message": "Snapshot refresh was cancelled",
                })
                await self.store.clear_refreshing(job.deduplication_key)
        async with self._lock:
            self._tasks.clear()
            self._active_by_key.clear()
