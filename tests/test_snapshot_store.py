from datetime import UTC, datetime, timedelta

import pytest

from app.snapshots.models import (
    RegionalSnapshot, SnapshotCoverage, SnapshotIdentity, SnapshotMetadata,
    SnapshotState, SSTRegionalCell, SSTRegionalPayload,
)
from app.snapshots.store import InMemorySnapshotStore


def snapshot(now: datetime, *, fresh=60, stale=120, value=28.0):
    identity = SnapshotIdentity(
        source="sst", product_id="p", dataset_id="d", dataset_version="v",
        variable="analysed_sst", tile_id="tile", provider_valid_time=now,
        configuration_identity="config",
    )
    coverage = SnapshotCoverage(
        minimum_latitude=0, maximum_latitude=2,
        minimum_longitude=0, maximum_longitude=2,
    )
    return RegionalSnapshot(
        metadata=SnapshotMetadata(
            identity=identity, logical_coverage=coverage,
            provider_request_coverage=coverage, retrieved_at=now, stored_at=now,
            fresh_until=now + timedelta(seconds=fresh),
            stale_until=now + timedelta(seconds=stale),
            last_successful_refresh_id="job",
        ),
        payload=SSTRegionalPayload(
            latitudes=(1.0,), longitudes=(1.0,),
            cells=(SSTRegionalCell(latitude=1, longitude=1, value_celsius=value, source_value_kelvin=value + 273.15),),
            provider_valid_time=now, product_id="p", dataset_id="d",
            dataset_version="v", variable="analysed_sst",
        ),
    )


@pytest.mark.asyncio
async def test_atomic_fresh_stale_and_expired_lookup():
    clock = [datetime(2026, 9, 1, tzinfo=UTC)]
    store = InMemorySnapshotStore(now=lambda: clock[0])
    await store.publish("sst:snapshot:a", snapshot(clock[0]))
    assert (await store.get_latest("sst:snapshot:a")).state == SnapshotState.FRESH
    clock[0] += timedelta(seconds=61)
    assert (await store.get_latest("sst:snapshot:a")).state == SnapshotState.STALE
    clock[0] += timedelta(seconds=60)
    assert (await store.get_latest("sst:snapshot:a")).snapshot is None


@pytest.mark.asyncio
async def test_failed_refresh_preserves_success_and_return_is_defensive():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    store = InMemorySnapshotStore(now=lambda: now)
    original = snapshot(now)
    await store.publish("key", original)
    await store.mark_refreshing("key")
    await store.record_failed_refresh("key", "SST_SOURCE_UNAVAILABLE")
    found = await store.get_latest("key")
    assert found.snapshot == original
    assert found.snapshot is not original


@pytest.mark.asyncio
async def test_configuration_namespaces_are_isolated():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    store = InMemorySnapshotStore(now=lambda: now)
    await store.publish("sst:snapshot:config-a", snapshot(now))
    assert (await store.get_latest("sst:snapshot:config-b")).snapshot is None
    assert (await store.get_latest("sst:point:config-a")).snapshot is None


@pytest.mark.asyncio
async def test_latest_successful_lookup_is_scoped_and_uses_provider_time():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    store = InMemorySnapshotStore(now=lambda: now)
    await store.publish("day-one", snapshot(now - timedelta(hours=2)))
    await store.publish("day-two", snapshot(now))
    found = await store.get_latest_successful(
        source="sst", tile_id="tile", configuration_identity="config"
    )
    assert found.snapshot.payload.provider_valid_time == now
    missing = await store.get_latest_successful(
        source="sst", tile_id="tile", configuration_identity="different"
    )
    assert missing.snapshot is None
