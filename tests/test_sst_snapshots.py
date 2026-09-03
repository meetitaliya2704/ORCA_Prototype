import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.clients.copernicus_sst import SSTProviderCell, SSTRegionalField, SSTSourceUnavailableError
from app.schemas.marine import RefreshAcceptedResponse, SSTSnapshotResponse
from app.services.cache import MemoryJsonCache
from app.services.sst import CopernicusSSTService
from app.services.sst import NoValidSSTError
from app.snapshots.jobs import RefreshJobManager
from app.snapshots.manager import SSTSnapshotManager
from app.snapshots.store import InMemorySnapshotStore


class FakeRegionalProvider:
    def __init__(self, cells=None, error=None):
        self.calls = 0
        self.error = error
        self.cells = cells

    async def fetch_cells(self, **kwargs):
        raise AssertionError("snapshot refresh must not loop over point retrieval")

    async def fetch_region(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        valid = kwargs["end_datetime"].replace(hour=0, minute=0, second=0, microsecond=0)
        cells = self.cells or (
            SSTProviderCell(18.025, 70.525, valid, 301.46999326348305),
            SSTProviderCell(18.1, 70.6, valid, 300.15),
        )
        return SSTRegionalField(
            latitudes=tuple(sorted({item.latitude for item in cells})),
            longitudes=tuple(sorted({item.longitude for item in cells})),
            cells=tuple(cells), analysis_time=valid,
        )


def make_manager(provider=None, *, clock=None, radius=50, fresh=60, stale=120):
    clock = clock or [datetime(2026, 9, 1, 12, tzinfo=UTC)]
    provider = provider or FakeRegionalProvider()
    service = CopernicusSSTService(
        provider=provider, cache=MemoryJsonCache(), dataset_id="dataset",
        variable="analysed_sst", search_radius_km=radius, lookback_days=3,
        fresh_ttl_seconds=60, stale_ttl_seconds=120, now=lambda: clock[0],
    )
    store = InMemorySnapshotStore(now=lambda: clock[0])
    jobs = RefreshJobManager(store=store, now=lambda: clock[0])
    return SSTSnapshotManager(
        provider=provider, point_service=service, store=store, jobs=jobs,
        tile_size_degrees=2, wait_timeout_seconds=1, fresh_seconds=fresh,
        max_stale_seconds=stale, refresh_check_seconds=30, lookback_days=3,
        now=lambda: clock[0],
    ), provider, clock


@pytest.mark.asyncio
async def test_missing_then_one_region_serves_two_same_tile_coordinates():
    manager, provider, _ = make_manager()
    missing = await manager.get_sst(latitude=18.025, longitude=70.525)
    assert isinstance(missing, RefreshAcceptedResponse)
    await manager.jobs.wait(missing.job_id, 1)
    first = await manager.get_sst(latitude=18.025, longitude=70.525)
    second = await manager.get_sst(latitude=18.1, longitude=70.6)
    assert isinstance(first, SSTSnapshotResponse)
    assert isinstance(second, SSTSnapshotResponse)
    assert first.value == pytest.approx(28.32, abs=.001)
    assert provider.calls == 1
    assert first.snapshot.tile_id == second.snapshot.tile_id


@pytest.mark.asyncio
async def test_concurrent_missing_requests_share_job_and_provider_call():
    manager, provider, _ = make_manager()
    results = await asyncio.gather(*[
        manager.get_sst(latitude=18.025, longitude=70.525) for _ in range(10)
    ])
    assert len({item.job_id for item in results}) == 1
    await manager.jobs.wait(results[0].job_id, 1)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_wait_mode_returns_refreshed_then_fresh():
    manager, provider, _ = make_manager()
    first = await manager.get_sst(
        latitude=18.025, longitude=70.525, wait_for_refresh=True
    )
    second = await manager.get_sst(latitude=18.025, longitude=70.525)
    assert first.cache_status == "refreshed"
    assert second.cache_status == "fresh"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_stale_snapshot_is_returned_while_exactly_one_refresh_runs():
    manager, provider, clock = make_manager(fresh=10, stale=120)
    first = await manager.get_sst(latitude=18.025, longitude=70.525, wait_for_refresh=True)
    original_retrieved = first.retrieved_at
    clock[0] += timedelta(seconds=11)
    stale = await manager.get_sst(latitude=18.025, longitude=70.525)
    duplicate = await manager.get_sst(latitude=18.025, longitude=70.525)
    assert stale.snapshot.status == "stale_refreshing"
    assert stale.retrieved_at == original_retrieved
    assert stale.snapshot.refresh_job_id == duplicate.snapshot.refresh_job_id
    await manager.jobs.wait(stale.snapshot.refresh_job_id, 1)
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_failed_refresh_never_overwrites_last_success():
    manager, provider, clock = make_manager(fresh=1, stale=120)
    original = await manager.get_sst(latitude=18.025, longitude=70.525, wait_for_refresh=True)
    provider.error = SSTSourceUnavailableError("private details")
    clock[0] += timedelta(seconds=2)
    stale = await manager.get_sst(latitude=18.025, longitude=70.525)
    await manager.jobs.wait(stale.snapshot.refresh_job_id, 1)
    preserved = await manager.get_sst(latitude=18.025, longitude=70.525)
    assert preserved.source_value == original.source_value


@pytest.mark.asyncio
async def test_another_tile_creates_another_regional_call():
    manager, provider, _ = make_manager()
    for latitude in (18.025, 20.5):
        result = await manager.get_sst(latitude=latitude, longitude=70.525)
        await manager.jobs.wait(result.job_id, 1)
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_regional_sampling_filters_invalid_values_and_uses_coastal_fallback():
    valid = datetime(2026, 9, 1, tzinfo=UTC)
    provider = FakeRegionalProvider(cells=(
        SSTProviderCell(18.025, 70.525, valid, float("nan")),
        SSTProviderCell(18.03, 70.53, valid, 301.15),
    ))
    manager, _, _ = make_manager(provider)
    result = await manager.get_sst(
        latitude=18.025, longitude=70.525, wait_for_refresh=True
    )
    assert result.sampled_location.latitude == 18.03
    assert result.quality == "nearest_valid_ocean_cell"


@pytest.mark.asyncio
async def test_no_valid_regional_cell_inside_radius_is_typed():
    valid = datetime(2026, 9, 1, tzinfo=UTC)
    provider = FakeRegionalProvider(cells=(
        SSTProviderCell(19.0, 71.0, valid, 301.15),
    ))
    manager, _, _ = make_manager(provider, radius=1)
    accepted = await manager.get_sst(latitude=18.025, longitude=70.525)
    await manager.jobs.wait(accepted.job_id, 1)
    with pytest.raises(NoValidSSTError):
        await manager.get_sst(
            latitude=18.025, longitude=70.525, wait_for_refresh=True
        )


def test_configuration_identity_changes_with_scientific_policy():
    first, _, _ = make_manager(radius=50)
    second, _, _ = make_manager(radius=25)
    assert first.configuration_identity != second.configuration_identity


@pytest.mark.asyncio
async def test_regional_and_direct_normalization_are_equivalent():
    manager, provider, clock = make_manager()
    snapshot_result = await manager.get_sst(
        latitude=18.025, longitude=70.525, wait_for_refresh=True
    )
    valid = clock[0].replace(hour=0)
    direct = manager.point_service.normalize_cells(
        cells=list((await provider.fetch_region(
            dataset_id="dataset", variable="analysed_sst",
            minimum_latitude=18, maximum_latitude=20,
            minimum_longitude=70, maximum_longitude=72,
            start_datetime=valid - timedelta(days=3), end_datetime=valid,
        )).cells),
        latitude=18.025, longitude=70.525,
        start_datetime=valid - timedelta(days=3), query_time=valid,
        retrieved_at=snapshot_result.retrieved_at,
    )
    assert snapshot_result.sampled_location == direct.sampled_location
    assert snapshot_result.value == direct.value
    assert snapshot_result.source_value == direct.source_value
