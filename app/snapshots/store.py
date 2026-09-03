from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.performance import performance_span
from app.snapshots.models import RegionalSnapshot, SnapshotLookup, SnapshotState


class InMemorySnapshotStore:
    """Atomic, process-local store for fully materialized immutable snapshots."""

    def __init__(self, *, now=None) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._lock = asyncio.Lock()
        self._latest: dict[str, RegionalSnapshot] = {}
        self._refreshing: set[str] = set()
        self._failures: dict[str, tuple[str, datetime]] = {}

    async def get_latest(self, key: str) -> SnapshotLookup:
        with performance_span("snapshot.lookup"):
            async with self._lock:
                snapshot = self._latest.get(key)
                refreshing = key in self._refreshing
                if snapshot is None:
                    return SnapshotLookup(
                        state=SnapshotState.REFRESHING if refreshing else SnapshotState.FAILED
                    )
                now = self._now().astimezone(UTC)
                if now <= snapshot.metadata.fresh_until:
                    state = SnapshotState.FRESH
                elif now <= snapshot.metadata.stale_until:
                    state = (
                        SnapshotState.STALE_REFRESHING if refreshing else SnapshotState.STALE
                    )
                else:
                    return SnapshotLookup(
                        state=SnapshotState.REFRESHING if refreshing else SnapshotState.FAILED
                    )
                return SnapshotLookup(state=state, snapshot=snapshot.model_copy(deep=True))

    async def get_exact(self, identity_key: str) -> RegionalSnapshot | None:
        async with self._lock:
            snapshot = self._latest.get(identity_key)
            return snapshot.model_copy(deep=True) if snapshot is not None else None

    async def get_latest_successful(
        self, *, source: str, tile_id: str, configuration_identity: str
    ) -> SnapshotLookup:
        with performance_span("snapshot.lookup"):
            async with self._lock:
                candidates = [
                    value for value in self._latest.values()
                    if value.metadata.identity.source == source
                    and value.metadata.identity.tile_id == tile_id
                    and value.metadata.identity.configuration_identity == configuration_identity
                ]
                if not candidates:
                    return SnapshotLookup(state=SnapshotState.FAILED)
                snapshot = max(
                    candidates, key=lambda value: value.payload.provider_valid_time
                )
                now = self._now().astimezone(UTC)
                if now <= snapshot.metadata.fresh_until:
                    state = SnapshotState.FRESH
                elif now <= snapshot.metadata.stale_until:
                    state = SnapshotState.STALE
                else:
                    return SnapshotLookup(state=SnapshotState.FAILED)
                return SnapshotLookup(state=state, snapshot=snapshot.model_copy(deep=True))

    async def publish(self, key: str, snapshot: RegionalSnapshot) -> None:
        # Deep validation/copy completes before taking the lock; publication is one assignment.
        owned = RegionalSnapshot.model_validate(snapshot.model_dump(mode="python"))
        async with self._lock:
            self._latest[key] = owned
            self._refreshing.discard(key)
            self._failures.pop(key, None)

    async def mark_refreshing(self, key: str) -> None:
        async with self._lock:
            self._refreshing.add(key)

    async def record_failed_refresh(self, key: str, code: str) -> None:
        async with self._lock:
            self._refreshing.discard(key)
            self._failures[key] = (code, self._now().astimezone(UTC))

    async def clear_refreshing(self, key: str) -> None:
        async with self._lock:
            self._refreshing.discard(key)

    async def list_metadata(self):
        async with self._lock:
            return tuple(item.metadata.model_copy(deep=True) for item in self._latest.values())

    async def remove_expired_unusable(self) -> int:
        now = self._now().astimezone(UTC)
        async with self._lock:
            expired = [
                key for key, value in self._latest.items()
                if value.metadata.stale_until < now and key not in self._refreshing
            ]
            for key in expired:
                self._latest.pop(key, None)
            return len(expired)
