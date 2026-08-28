import asyncio
from datetime import UTC, datetime

import pytest

from app.clients.copernicus_waves import (
    WaveProviderCell,
    WaveSourceUnavailableError,
    parse_latest_cycle_reference,
)
from app.services.cache import MemoryJsonCache
from app.services.waves import (
    CopernicusWaveService,
    NoValidWaveDataError,
    NoWaveTimeAvailableError,
)


CYCLE = datetime(2026, 8, 28, tzinfo=UTC)
FORECAST = datetime(2026, 8, 29, tzinfo=UTC)


def cell(
    *,
    latitude: float = 18.025,
    longitude: float = 70.525,
    valid_time: datetime = CYCLE,
    height: float | None = 2.5299999434500933,
    period: float | None = 5.859999869018793,
    direction_from: float | None = 246.21999851986766,
) -> WaveProviderCell:
    return WaveProviderCell(
        latitude=latitude,
        longitude=longitude,
        valid_time=valid_time,
        significant_wave_height_m=height,
        mean_wave_period_s=period,
        mean_wave_direction_from_deg=direction_from,
    )


class FakeProvider:
    def __init__(self, cells=None, error: Exception | None = None) -> None:
        self.cells = cells if cells is not None else [cell()]
        self.error = error
        self.calls: list[dict] = []

    async def fetch_cells(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.cells


class FakeCycleResolver:
    def __init__(
        self,
        reference: datetime | None = CYCLE,
        error: Exception | None = None,
    ) -> None:
        self.reference = reference
        self.error = error
        self.calls: list[dict] = []

    async def resolve_cycle(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.reference


def make_service(
    provider: FakeProvider,
    *,
    resolver: FakeCycleResolver | None = None,
    cache: MemoryJsonCache | None = None,
    radius: float = 50,
) -> CopernicusWaveService:
    return CopernicusWaveService(
        provider=provider,
        cycle_resolver=resolver or FakeCycleResolver(),
        cache=cache or MemoryJsonCache(),
        dataset_id="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
        dataset_version="202411",
        height_variable="VHM0",
        period_variable="VTM02",
        direction_variable="VMDR",
        search_radius_km=radius,
        time_tolerance_hours=3,
        fresh_ttl_seconds=3600,
        stale_ttl_seconds=21600,
        cycle_ttl_seconds=3600,
        now=lambda: datetime(2026, 8, 28, 17, 36, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_verified_analysis_values_are_decoded_once_and_direction_is_from() -> None:
    result = await make_service(FakeProvider()).get_waves(
        latitude=18.025,
        longitude=70.525,
        at=CYCLE,
    )

    assert result.significant_wave_height.value == pytest.approx(2.53)
    assert result.mean_wave_period.value == pytest.approx(5.86)
    assert result.mean_wave_direction_from.value == pytest.approx(246.22)
    assert result.mean_wave_direction_from.unit == "degree"
    assert result.time_classification == "analysis"
    assert result.forecast_lead_hours == 0
    assert "mean_wave_direction_from" in result.model_dump()


@pytest.mark.asyncio
async def test_verified_twenty_four_hour_forecast_values() -> None:
    provider = FakeProvider(
        [
            cell(
                valid_time=FORECAST,
                height=2.7899999376386404,
                period=6.069999864324927,
                direction_from=247.84999848343432,
            )
        ]
    )

    result = await make_service(provider).get_waves(
        latitude=18.025,
        longitude=70.525,
        at=FORECAST,
    )

    assert result.significant_wave_height.value == pytest.approx(2.79)
    assert result.mean_wave_period.value == pytest.approx(6.07)
    assert result.mean_wave_direction_from.value == pytest.approx(247.85)
    assert result.time_classification == "forecast"
    assert result.forecast_lead_hours == 24


@pytest.mark.asyncio
async def test_incomplete_and_invalid_cells_are_filtered() -> None:
    provider = FakeProvider(
        [
            cell(latitude=18.025, height=None),
            cell(latitude=18.03, period=float("nan")),
            cell(latitude=18.04, direction_from=float("inf")),
            cell(latitude=18.05, height=-32767.0),
            cell(latitude=18.06, height=2.0, period=5.0, direction_from=240.0),
        ]
    )

    result = await make_service(provider).get_waves(
        latitude=18.025,
        longitude=70.525,
        at=CYCLE,
    )

    assert result.sampled_location.latitude == 18.06
    assert result.significant_wave_height.value == 2.0


@pytest.mark.asyncio
async def test_coastal_request_uses_nearest_complete_ocean_cell() -> None:
    provider = FakeProvider(
        [
            cell(latitude=20.5, longitude=72.916666, height=None),
            cell(latitude=20.5, longitude=72.75, height=1.25),
        ]
    )

    result = await make_service(provider).get_waves(
        latitude=20.5,
        longitude=72.9,
        at=CYCLE,
    )

    assert result.sampled_location.longitude == 72.75
    assert result.quality == "nearest_valid_ocean_cell"
    assert any("Nearest complete wave model cell" in item for item in result.warnings)


@pytest.mark.asyncio
async def test_maximum_radius_is_enforced() -> None:
    service = make_service(
        FakeProvider([cell(latitude=19.0, longitude=70.525)]),
        radius=10,
    )

    with pytest.raises(NoValidWaveDataError):
        await service.get_waves(latitude=18.025, longitude=70.525, at=CYCLE)


@pytest.mark.asyncio
async def test_spatial_tie_break_uses_latitude_then_longitude(monkeypatch) -> None:
    provider = FakeProvider(
        [
            cell(latitude=18.1, longitude=70.6),
            cell(latitude=18.0, longitude=70.4),
        ]
    )
    monkeypatch.setattr(
        "app.services.waves.haversine_distance_km",
        lambda *args: 10.0,
    )

    result = await make_service(provider).get_waves(
        latitude=18.025,
        longitude=70.525,
        at=CYCLE,
    )

    assert result.sampled_location.latitude == 18.0


@pytest.mark.asyncio
async def test_analysis_selects_latest_timestamp_not_later_than_request() -> None:
    query = datetime(2026, 8, 27, 23, 30, tzinfo=UTC)
    provider = FakeProvider(
        [
            cell(valid_time=datetime(2026, 8, 27, 21, tzinfo=UTC), height=2.1),
            cell(valid_time=CYCLE, height=2.2),
        ]
    )

    result = await make_service(provider).get_waves(
        latitude=18.025,
        longitude=70.525,
        at=query,
    )

    assert result.valid_time == datetime(2026, 8, 27, 21, tzinfo=UTC)
    assert result.time_classification == "analysis"


@pytest.mark.asyncio
async def test_forecast_selects_first_timestamp_at_or_after_request() -> None:
    query = datetime(2026, 8, 28, 1, tzinfo=UTC)
    provider = FakeProvider(
        [
            cell(valid_time=CYCLE, height=2.1),
            cell(valid_time=datetime(2026, 8, 28, 3, tzinfo=UTC), height=2.2),
        ]
    )

    result = await make_service(provider).get_waves(
        latitude=18.025,
        longitude=70.525,
        at=query,
    )

    assert result.valid_time == datetime(2026, 8, 28, 3, tzinfo=UTC)
    assert result.time_classification == "forecast"
    assert result.forecast_lead_hours == 3


@pytest.mark.asyncio
async def test_time_tolerance_and_ten_day_horizon_are_enforced() -> None:
    service = make_service(
        FakeProvider(
            [cell(valid_time=datetime(2026, 8, 28, 5, tzinfo=UTC))]
        )
    )
    with pytest.raises(NoWaveTimeAvailableError):
        await service.get_waves(
            latitude=18.025,
            longitude=70.525,
            at=datetime(2026, 8, 28, 1, tzinfo=UTC),
        )

    provider = FakeProvider()
    with pytest.raises(NoWaveTimeAvailableError):
        await make_service(provider).get_waves(
            latitude=18.025,
            longitude=70.525,
            at=datetime(2026, 9, 8, tzinfo=UTC),
        )
    assert provider.calls == []


def test_cycle_metadata_parser_uses_latest_official_reference() -> None:
    result = parse_latest_cycle_reference(
        [
            "mfwamglocep_2026082800_R20260827_00H.nc",
            "mfwamglocep_2026082900_R20260828_00H.nc",
            "unrelated.txt",
        ]
    )

    assert result == CYCLE


@pytest.mark.asyncio
async def test_missing_cycle_metadata_returns_unknown_without_fabrication() -> None:
    resolver = FakeCycleResolver(reference=None)
    result = await make_service(
        FakeProvider(),
        resolver=resolver,
    ).get_waves(
        latitude=18.025,
        longitude=70.525,
        at=CYCLE,
    )

    assert result.forecast_reference_time is None
    assert result.forecast_lead_hours is None
    assert result.time_classification == "unknown"
    assert any("cycle metadata" in item for item in result.warnings)


@pytest.mark.asyncio
async def test_fresh_cache_and_cycle_cache_prevent_provider_calls() -> None:
    provider = FakeProvider()
    resolver = FakeCycleResolver()
    service = make_service(provider, resolver=resolver)

    refreshed = await service.get_waves(
        latitude=18.025,
        longitude=70.525,
        at=CYCLE,
    )
    fresh = await service.get_waves(
        latitude=18.025,
        longitude=70.525,
        at=CYCLE,
    )

    assert refreshed.cache_status == "refreshed"
    assert fresh.cache_status == "fresh"
    assert len(provider.calls) == 1
    assert len(resolver.calls) == 1


@pytest.mark.asyncio
async def test_provider_failure_returns_only_matching_stale_value() -> None:
    cache = MemoryJsonCache()
    provider = FakeProvider()
    service = make_service(provider, cache=cache)
    original = await service.get_waves(
        latitude=18.025,
        longitude=70.525,
        at=CYCLE,
    )
    fresh_key = next(
        key
        for key in cache._values
        if key.startswith("waves:") and key.endswith(":fresh")
    )
    cache._values.pop(fresh_key)
    provider.error = WaveSourceUnavailableError("private provider detail")

    stale = await service.get_waves(
        latitude=18.025,
        longitude=70.525,
        at=CYCLE,
    )

    assert stale.cache_status == "stale"
    assert stale.valid_time == original.valid_time
    assert stale.retrieved_at == original.retrieved_at


@pytest.mark.asyncio
async def test_temporal_cache_isolation_uses_three_hour_buckets() -> None:
    provider = FakeProvider(
        [
            cell(valid_time=CYCLE),
            cell(valid_time=datetime(2026, 8, 28, 3, tzinfo=UTC)),
        ]
    )
    service = make_service(provider)

    await service.get_waves(latitude=18.025, longitude=70.525, at=CYCLE)
    await service.get_waves(
        latitude=18.025,
        longitude=70.525,
        at=datetime(2026, 8, 28, 3, tzinfo=UTC),
    )

    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_identical_concurrent_misses_make_one_provider_call() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingProvider(FakeProvider):
        async def fetch_cells(self, **kwargs):
            self.calls.append(kwargs)
            started.set()
            await release.wait()
            return self.cells

    provider = BlockingProvider()
    service = make_service(provider)
    tasks = [
        asyncio.create_task(
            service.get_waves(
                latitude=18.025,
                longitude=70.525,
                at=CYCLE,
            )
        )
        for _ in range(4)
    ]
    await started.wait()
    release.set()
    results = await asyncio.gather(*tasks)

    assert len(provider.calls) == 1
    assert sum(item.cache_status == "refreshed" for item in results) == 1
    assert sum(item.cache_status == "fresh" for item in results) == 3
