import asyncio
from datetime import UTC, datetime

import pytest

from app.clients.copernicus_sst import (
    SSTAuthenticationError,
    SSTProviderCell,
    SSTSourceNotConfiguredError,
    SSTSourceUnavailableError,
    load_copernicus_sst_cells,
)
from app.services.cache import MemoryJsonCache
from app.services.sst import CopernicusSSTService, NoValidSSTError


ANALYSIS_TIME = datetime(2026, 8, 27, tzinfo=UTC)
QUERY_TIME = datetime(2026, 8, 27, 12, tzinfo=UTC)


def cell(
    latitude: float = 18.025,
    longitude: float = 70.525,
    value: float | None = 301.46999326348305,
    *,
    analysis_time: datetime = ANALYSIS_TIME,
    mask: int | None = 1,
) -> SSTProviderCell:
    return SSTProviderCell(
        latitude=latitude,
        longitude=longitude,
        analysis_time=analysis_time,
        value_kelvin=value,
        mask=mask,
    )


class FakeProvider:
    def __init__(self, cells=None, error: Exception | None = None) -> None:
        self.cells = cells if cells is not None else [cell()]
        self.error = error
        self.calls: list[dict] = []

    async def fetch_cells(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        if self.error is not None:
            raise self.error
        return self.cells


def make_service(
    provider: FakeProvider,
    *,
    cache: MemoryJsonCache | None = None,
    radius: float = 50,
) -> CopernicusSSTService:
    return CopernicusSSTService(
        provider=provider,
        cache=cache or MemoryJsonCache(),
        dataset_id="METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2",
        variable="analysed_sst",
        search_radius_km=radius,
        lookback_days=3,
        fresh_ttl_seconds=21600,
        stale_ttl_seconds=86400,
        now=lambda: datetime(2026, 8, 28, 13, 49, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_verified_kelvin_is_converted_exactly_once() -> None:
    service = make_service(FakeProvider())

    result = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )

    assert result.source_value == pytest.approx(301.469993)
    assert result.value == pytest.approx(28.32)
    assert result.unit == "°C"
    assert result.source_unit == "K"
    assert result.quality == "exact_grid_cell"


@pytest.mark.asyncio
async def test_float32_grid_coordinate_noise_is_exact_grid_cell() -> None:
    provider = FakeProvider(
        [cell(18.024999618530273, 70.5250015258789)]
    )
    service = make_service(provider)

    result = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )

    assert result.quality == "exact_grid_cell"
    assert result.sample_distance_km == 0.0
    assert result.warnings == []


@pytest.mark.asyncio
async def test_non_finite_and_null_values_are_filtered() -> None:
    provider = FakeProvider(
        [
            cell(18.025, 70.525, None),
            cell(18.03, 70.53, float("nan")),
            cell(18.04, 70.54, float("inf")),
            cell(18.05, 70.55, float("-inf")),
            cell(18.06, 70.56, 300.0),
        ]
    )
    service = make_service(provider)

    result = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )

    assert result.sampled_location.latitude == 18.06
    assert result.source_value == 300.0


@pytest.mark.asyncio
async def test_decoded_fill_value_is_filtered() -> None:
    provider = FakeProvider(
        [
            cell(18.025, 70.525, -32768.0),
            cell(18.03, 70.53, 300.0),
        ]
    )
    service = make_service(provider)

    result = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )

    assert result.sampled_location.latitude == 18.03
    assert result.source_value == 300.0


@pytest.mark.asyncio
async def test_nearest_valid_cell_uses_full_distance() -> None:
    provider = FakeProvider(
        [
            cell(18.2, 70.525, 299),
            cell(18.03, 70.525, 300),
        ]
    )
    service = make_service(provider)

    result = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )

    assert result.sampled_location.latitude == 18.03


@pytest.mark.asyncio
async def test_maximum_radius_is_enforced() -> None:
    service = make_service(FakeProvider([cell(19, 70.525, 300)]), radius=10)

    with pytest.raises(NoValidSSTError):
        await service.get_sst(
            latitude=18.025,
            longitude=70.525,
            at=QUERY_TIME,
        )


@pytest.mark.asyncio
async def test_equal_distance_uses_latitude_then_longitude_tie_break(
    monkeypatch,
) -> None:
    provider = FakeProvider(
        [
            cell(18.025, 70.625, 301),
            cell(18.025, 70.425, 300),
        ]
    )
    service = make_service(provider)
    monkeypatch.setattr(
        "app.services.sst.haversine_distance_km",
        lambda *args: 10.0,
    )

    result = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )

    assert result.sampled_location.longitude == 70.425


@pytest.mark.asyncio
async def test_land_cell_uses_nearest_ocean_quality_and_warning() -> None:
    provider = FakeProvider(
        [
            cell(20.5, 72.9, None, mask=2),
            cell(20.475, 72.825, 301, mask=1),
        ]
    )
    service = make_service(provider)

    result = await service.get_sst(
        latitude=20.5,
        longitude=72.9,
        at=QUERY_TIME,
    )

    assert result.quality == "nearest_valid_ocean_cell"
    assert result.sampled_location.longitude == 72.825
    assert result.warnings == [
        "Requested grid cell was land; nearest valid ocean cell was used"
    ]


@pytest.mark.asyncio
async def test_no_valid_cell_returns_typed_error() -> None:
    service = make_service(FakeProvider([cell(value=None, mask=2)]))

    with pytest.raises(NoValidSSTError):
        await service.get_sst(
            latitude=18.025,
            longitude=70.525,
            at=QUERY_TIME,
        )


@pytest.mark.asyncio
async def test_latest_analysis_not_later_than_query_is_selected() -> None:
    provider = FakeProvider(
        [
            cell(value=299, analysis_time=datetime(2026, 8, 26, tzinfo=UTC)),
            cell(value=300, analysis_time=datetime(2026, 8, 27, tzinfo=UTC)),
            cell(value=310, analysis_time=datetime(2026, 8, 28, tzinfo=UTC)),
        ]
    )
    service = make_service(provider)

    result = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )

    assert result.analysis_time == ANALYSIS_TIME
    assert result.source_value == 300


@pytest.mark.asyncio
async def test_only_future_analysis_returns_no_valid_sst() -> None:
    provider = FakeProvider(
        [cell(analysis_time=datetime(2026, 8, 28, tzinfo=UTC))]
    )
    service = make_service(provider)

    with pytest.raises(NoValidSSTError):
        await service.get_sst(
            latitude=18.025,
            longitude=70.525,
            at=QUERY_TIME,
        )


@pytest.mark.asyncio
async def test_fresh_cache_prevents_provider_call() -> None:
    provider = FakeProvider()
    service = make_service(provider)

    refreshed = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )
    fresh = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )

    assert refreshed.cache_status == "refreshed"
    assert fresh.cache_status == "fresh"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_provider_failure_returns_matching_stale_value() -> None:
    cache = MemoryJsonCache()
    provider = FakeProvider()
    service = make_service(provider, cache=cache)
    original = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )
    fresh_key = next(key for key in cache._values if key.endswith(":fresh"))
    cache._values.pop(fresh_key)
    provider.error = SSTSourceUnavailableError("private provider detail")

    stale = await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=QUERY_TIME,
    )

    assert stale.cache_status == "stale"
    assert stale.retrieved_at == original.retrieved_at
    assert any("matching stale data" in item for item in stale.warnings)


@pytest.mark.asyncio
async def test_provider_failure_without_stale_value_is_propagated() -> None:
    service = make_service(
        FakeProvider(error=SSTSourceUnavailableError("private provider detail"))
    )

    with pytest.raises(SSTSourceUnavailableError):
        await service.get_sst(
            latitude=18.025,
            longitude=70.525,
            at=QUERY_TIME,
        )


@pytest.mark.asyncio
async def test_unrelated_location_does_not_reuse_cache() -> None:
    provider = FakeProvider(
        [
            cell(18.025, 70.525, 301),
            cell(-18.025, -70.525, 302),
        ]
    )
    service = make_service(provider)

    await service.get_sst(latitude=18.025, longitude=70.525, at=QUERY_TIME)
    await service.get_sst(latitude=-18.025, longitude=-70.525, at=QUERY_TIME)

    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_unrelated_analysis_date_does_not_reuse_cache() -> None:
    provider = FakeProvider(
        [
            cell(value=300, analysis_time=datetime(2026, 8, 27, tzinfo=UTC)),
            cell(value=301, analysis_time=datetime(2026, 8, 28, tzinfo=UTC)),
        ]
    )
    service = make_service(provider)

    await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=datetime(2026, 8, 27, 12, tzinfo=UTC),
    )
    await service.get_sst(
        latitude=18.025,
        longitude=70.525,
        at=datetime(2026, 8, 28, 12, tzinfo=UTC),
    )

    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_omitted_time_uses_injected_timezone_aware_utc_now() -> None:
    provider = FakeProvider(
        [cell(value=301, analysis_time=datetime(2026, 8, 28, tzinfo=UTC))]
    )
    service = make_service(provider)

    result = await service.get_sst(latitude=18.025, longitude=70.525)

    assert result.analysis_time == datetime(2026, 8, 28, tzinfo=UTC)
    assert provider.calls[0]["end_datetime"] == datetime(
        2026, 8, 28, 13, 49, tzinfo=UTC
    )


@pytest.mark.asyncio
async def test_simultaneous_identical_misses_make_one_provider_call() -> None:
    provider = FakeProvider()
    service = make_service(provider)

    results = await asyncio.gather(
        *(
            service.get_sst(
                latitude=18.025,
                longitude=70.525,
                at=QUERY_TIME,
            )
            for _ in range(5)
        )
    )

    assert len(provider.calls) == 1
    assert sum(item.cache_status == "refreshed" for item in results) == 1
    assert sum(item.cache_status == "fresh" for item in results) == 4


def test_missing_optional_package_is_typed(monkeypatch) -> None:
    def missing_package(name: str):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(
        "app.clients.copernicus_sst.import_module",
        missing_package,
    )

    with pytest.raises(SSTSourceNotConfiguredError):
        load_copernicus_sst_cells(
            dataset_id="dataset",
            variable="analysed_sst",
            minimum_latitude=0,
            maximum_latitude=1,
            minimum_longitude=0,
            maximum_longitude=1,
            start_datetime=ANALYSIS_TIME,
            end_datetime=QUERY_TIME,
        )


def test_missing_or_invalid_credentials_are_typed(monkeypatch) -> None:
    class FakeCopernicus:
        @staticmethod
        def open_dataset(**kwargs):
            del kwargs
            raise RuntimeError("authentication credentials unavailable")

    def fake_import(name: str):
        if name == "copernicusmarine":
            return FakeCopernicus()
        return object()

    monkeypatch.setattr("app.clients.copernicus_sst.import_module", fake_import)

    with pytest.raises(SSTAuthenticationError):
        load_copernicus_sst_cells(
            dataset_id="dataset",
            variable="analysed_sst",
            minimum_latitude=0,
            maximum_latitude=1,
            minimum_longitude=0,
            maximum_longitude=1,
            start_datetime=ANALYSIS_TIME,
            end_datetime=QUERY_TIME,
        )
