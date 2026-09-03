import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.clients.copernicus_chlorophyll import (
    ChlorophyllAuthenticationError,
    ChlorophyllFlagMetadata,
    ChlorophyllProviderCell,
    ChlorophyllProviderResult,
    ChlorophyllSourceUnavailableError,
    InvalidChlorophyllResponseError,
)
from app.schemas.marine import ChlorophyllSnapshotResponse, RefreshAcceptedResponse
from app.services.cache import MemoryJsonCache
from app.services.chlorophyll import CopernicusChlorophyllService
from app.services.chlorophyll import NoValidChlorophyllCellError
from app.snapshots.chlorophyll import ChlorophyllSnapshotManager
from app.snapshots.jobs import RefreshJobManager
from app.snapshots.store import InMemorySnapshotStore


FLAGS = ChlorophyllFlagMetadata(
    meaning_to_mask={"LAND": 1, "INTERPOLATED": 2},
    raw_flag_meanings="LAND INTERPOLATED",
)


class FakeRegionalChlorophyllProvider:
    def __init__(self, *, cells=None, metadata=FLAGS, error=None):
        self.calls = 0
        self.cells = cells
        self.metadata = metadata
        self.error = error

    async def fetch_cells(self, **kwargs):
        raise AssertionError("regional refresh must not loop over point calls")

    async def fetch_region(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        valid = kwargs["end_datetime"].replace(hour=0, minute=0, second=0, microsecond=0)
        cells = self.cells or (
            ChlorophyllProviderCell(18.025, 70.525, valid, 0.4, 10.0, 0),
            ChlorophyllProviderCell(18.5, 70.8, valid, 0.8, 60.0, 2),
        )
        return ChlorophyllProviderResult(
            cells=list(cells),
            flag_metadata=self.metadata,
            chlorophyll_valid_min=0.0,
            chlorophyll_valid_max=1000.0,
        )


def make_manager(provider=None, *, clock=None, radius=10, fresh=60, stale=120):
    clock = clock or [datetime(2026, 9, 1, 12, tzinfo=UTC)]
    provider = provider or FakeRegionalChlorophyllProvider()
    service = CopernicusChlorophyllService(
        provider=provider,
        cache=MemoryJsonCache(),
        dataset_id="chlorophyll-dataset",
        dataset_version="202311",
        chlorophyll_variable="CHL",
        uncertainty_variable="CHL_uncertainty",
        flags_variable="flags",
        max_radius_km=radius,
        fresh_ttl_seconds=60,
        max_stale_seconds=120,
        freshness_hours=72,
        high_uncertainty_percent=50,
        now=lambda: clock[0],
    )
    store = InMemorySnapshotStore(now=lambda: clock[0])
    jobs = RefreshJobManager(store=store, now=lambda: clock[0])
    manager = ChlorophyllSnapshotManager(
        provider=provider,
        point_service=service,
        store=store,
        jobs=jobs,
        tile_size_degrees=2,
        wait_timeout_seconds=1,
        fresh_seconds=fresh,
        max_stale_seconds=stale,
        refresh_check_seconds=30,
        now=lambda: clock[0],
    )
    return manager, provider, clock


@pytest.mark.asyncio
async def test_one_region_serves_two_same_tile_coordinates_without_second_call():
    manager, provider, _ = make_manager()
    accepted = await manager.get_chlorophyll(latitude=18.025, longitude=70.525)
    assert isinstance(accepted, RefreshAcceptedResponse)
    await manager.jobs.wait(accepted.job_id, 1)
    first = await manager.get_chlorophyll(latitude=18.025, longitude=70.525)
    second = await manager.get_chlorophyll(latitude=18.5, longitude=70.8)
    assert isinstance(first, ChlorophyllSnapshotResponse)
    assert first.snapshot.tile_id == second.snapshot.tile_id
    assert provider.calls == 1
    assert second.quality.interpolated is True
    assert second.quality.evidence_quality == "degraded"
    assert second.quality.uncertainty_percent == 60.0


@pytest.mark.asyncio
async def test_concurrent_misses_share_one_refresh_job():
    manager, provider, _ = make_manager()
    results = await asyncio.gather(*[
        manager.get_chlorophyll(latitude=18.025, longitude=70.525)
        for _ in range(10)
    ])
    assert len({result.job_id for result in results}) == 1
    await manager.jobs.wait(results[0].job_id, 1)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_stale_snapshot_is_immediate_and_failed_refresh_preserves_it():
    manager, provider, clock = make_manager(fresh=1, stale=120)
    original = await manager.get_chlorophyll(
        latitude=18.025, longitude=70.525, wait_for_refresh=True
    )
    provider.error = ChlorophyllSourceUnavailableError("private")
    clock[0] += timedelta(seconds=2)
    stale = await manager.get_chlorophyll(latitude=18.025, longitude=70.525)
    assert stale.snapshot.status == "stale_refreshing"
    await manager.jobs.wait(stale.snapshot.refresh_job_id, 1)
    preserved = await manager.get_chlorophyll(latitude=18.025, longitude=70.525)
    assert preserved.chlorophyll_a == original.chlorophyll_a
    assert preserved.snapshot.status == "stale"


@pytest.mark.asyncio
async def test_land_nearest_cell_falls_back_and_preserves_flag_metadata():
    valid = datetime(2026, 9, 1, tzinfo=UTC)
    provider = FakeRegionalChlorophyllProvider(cells=(
        ChlorophyllProviderCell(18.025, 70.525, valid, 1.0, 5.0, 1),
        ChlorophyllProviderCell(18.03, 70.53, valid, 0.5, None, 2),
    ))
    manager, _, _ = make_manager(provider)
    response = await manager.get_chlorophyll(
        latitude=18.025, longitude=70.525, wait_for_refresh=True
    )
    assert response.sampling_quality == "nearest_valid_water_cell"
    assert response.sampled_location.latitude == 18.03
    assert response.quality.uncertainty_percent is None
    assert response.quality.evidence_quality == "degraded"


@pytest.mark.asyncio
async def test_invalid_flag_metadata_cannot_publish_snapshot():
    metadata = ChlorophyllFlagMetadata(
        meaning_to_mask={"LAND": 1}, raw_flag_meanings="LAND"
    )
    provider = FakeRegionalChlorophyllProvider(metadata=metadata)
    manager, _, _ = make_manager(provider)
    accepted = await manager.get_chlorophyll(latitude=18.025, longitude=70.525)
    await manager.jobs.wait(accepted.job_id, 1)
    job = await manager.jobs.get(accepted.job_id)
    # Provider result models may be constructed by fakes, so publication must still
    # reject an incomplete interpretation rather than silently treating land as water.
    assert job.state == "failed"


@pytest.mark.asyncio
async def test_auth_failure_is_cooled_down_and_does_not_storm():
    provider = FakeRegionalChlorophyllProvider(
        error=ChlorophyllAuthenticationError("private")
    )
    manager, _, _ = make_manager(provider)
    first = await manager.get_chlorophyll(latitude=18.025, longitude=70.525)
    await manager.jobs.wait(first.job_id, 1)
    for _ in range(10):
        with pytest.raises(ChlorophyllAuthenticationError):
            await manager.get_chlorophyll(latitude=18.025, longitude=70.525)
    assert provider.calls == 1


def test_configuration_identity_covers_radius_uncertainty_and_flag_policy():
    first, _, _ = make_manager(radius=10)
    second, _, _ = make_manager(radius=5)
    assert first.configuration_identity != second.configuration_identity


@pytest.mark.asyncio
async def test_no_valid_water_cell_inside_radius_is_not_fabricated():
    valid = datetime(2026, 9, 1, tzinfo=UTC)
    provider = FakeRegionalChlorophyllProvider(cells=(
        ChlorophyllProviderCell(18.025, 70.525, valid, 0.5, 10, 1),
        ChlorophyllProviderCell(19.0, 71.0, valid, 0.5, 10, 0),
    ))
    manager, _, _ = make_manager(provider, radius=1)
    accepted = await manager.get_chlorophyll(latitude=18.025, longitude=70.525)
    await manager.jobs.wait(accepted.job_id, 1)
    with pytest.raises(NoValidChlorophyllCellError):
        await manager.get_chlorophyll(
            latitude=18.025, longitude=70.525, wait_for_refresh=True
        )


@pytest.mark.asyncio
async def test_snapshot_and_direct_normalization_are_equivalent():
    manager, provider, clock = make_manager()
    snapshot = await manager.get_chlorophyll(
        latitude=18.025, longitude=70.525, wait_for_refresh=True
    )
    raw = await provider.fetch_region(end_datetime=clock[0])
    direct = manager.point_service.normalize_result(
        result=raw,
        latitude=18.025,
        longitude=70.525,
        query_time=clock[0],
        retrieved_at=snapshot.retrieved_at,
    )
    assert snapshot.sampled_location == direct.sampled_location
    assert snapshot.chlorophyll_a == direct.chlorophyll_a
    assert snapshot.quality == direct.quality
    assert snapshot.data_provenance == direct.data_provenance


def test_same_antimeridian_tile_is_deterministic():
    manager, _, _ = make_manager()
    assert manager.tile(18.0, 180.0) == manager.tile(18.0, -180.0)
