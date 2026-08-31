import asyncio
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clients.copernicus_chlorophyll import (
    ChlorophyllAuthenticationError,
    ChlorophyllDependencyMissingError,
    ChlorophyllFlagMetadata,
    ChlorophyllProviderCell,
    ChlorophyllProviderResult,
    ChlorophyllSourceNotConfiguredError,
    ChlorophyllSourceUnavailableError,
    InvalidChlorophyllResponseError,
    load_copernicus_chlorophyll_cells,
    parse_chlorophyll_flag_metadata,
)
from app.main import app
from app.schemas.marine import ChlorophyllResponse
from app.services.cache import MemoryJsonCache
from app.services.chlorophyll import (
    ChlorophyllDataUnavailableError,
    CopernicusChlorophyllService,
    InvalidChlorophyllTimeError,
    NoValidChlorophyllCellError,
)
from app.services.geospatial import haversine_distance_km


NOW = datetime(2026, 8, 31, 20, 50, 56, tzinfo=UTC)
ANALYSIS = datetime(2026, 8, 30, tzinfo=UTC)
FLAGS = parse_chlorophyll_flag_metadata([1, 2], "LAND INTERPOLATED")


def cell(
    *,
    latitude: float = 18.0208320618,
    longitude: float = 70.5208435059,
    analysis_time: datetime = ANALYSIS,
    chlorophyll: float | None = 0.3887457848,
    uncertainty: float | None = 20.0,
    flag: int | None = 0,
) -> ChlorophyllProviderCell:
    return ChlorophyllProviderCell(
        latitude=latitude,
        longitude=longitude,
        analysis_time=analysis_time,
        chlorophyll_mg_m3=chlorophyll,
        uncertainty_percent=uncertainty,
        flag_value=flag,
    )


def result(
    cells: list[ChlorophyllProviderCell] | None = None,
    metadata: ChlorophyllFlagMetadata = FLAGS,
) -> ChlorophyllProviderResult:
    return ChlorophyllProviderResult(cells=cells or [cell()], flag_metadata=metadata)


class FakeProvider:
    def __init__(self, provider_result=None, error: Exception | None = None) -> None:
        self.result = provider_result or result()
        self.error = error
        self.calls: list[dict] = []

    async def fetch_cells(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class BlockingFakeProvider(FakeProvider):
    def __init__(self, provider_result=None) -> None:
        super().__init__(provider_result)
        self.release = asyncio.Event()

    async def fetch_cells(self, **kwargs):
        self.calls.append(kwargs)
        await self.release.wait()
        return self.result


def make_service(
    provider: FakeProvider | None = None,
    cache: MemoryJsonCache | None = None,
    **overrides,
) -> CopernicusChlorophyllService:
    options = {
        "provider": provider or FakeProvider(),
        "cache": cache or MemoryJsonCache(),
        "dataset_id": "cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
        "dataset_version": "202311",
        "chlorophyll_variable": "CHL",
        "uncertainty_variable": "CHL_uncertainty",
        "flags_variable": "flags",
        "max_radius_km": 10.0,
        "fresh_ttl_seconds": 21600,
        "max_stale_seconds": 86400,
        "freshness_hours": 72.0,
        "high_uncertainty_percent": 50.0,
        "now": lambda: NOW,
    }
    options.update(overrides)
    return CopernicusChlorophyllService(**options)


def read_metadata_fixture() -> dict:
    path = Path(__file__).parent / "fixtures" / "copernicus_chlorophyll_metadata.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_sanitized_flag_metadata_fixture_parses_exact_live_representation() -> None:
    fixture = read_metadata_fixture()
    metadata = parse_chlorophyll_flag_metadata(
        fixture["flag_masks"], fixture["flag_meanings_raw"]
    )
    assert fixture["flag_meanings"] == ["LAND", "INTERPOLATED"]
    assert metadata.land_mask == 1
    assert metadata.interpolated_mask == 2
    assert metadata.raw_flag_meanings == "LAND INTERPOLATED"


def test_flag_metadata_uses_meanings_not_array_positions() -> None:
    metadata = parse_chlorophyll_flag_metadata([2, 1], ["INTERPOLATED", "LAND"])
    assert metadata.land_mask == 1
    assert metadata.interpolated_mask == 2


@pytest.mark.parametrize(
    ("masks", "meanings"),
    [
        ([2], ["INTERPOLATED"]),
        ([1], ["LAND"]),
        ([1, 2], ["LAND"]),
        ([1, 2], ["LAND", "LAND"]),
        ([1, 1], ["LAND", "INTERPOLATED"]),
        ([3, 4], ["LAND", "INTERPOLATED"]),
        ([1, "bad"], ["LAND", "INTERPOLATED"]),
    ],
)
def test_malformed_or_incomplete_flag_metadata_is_rejected(masks, meanings) -> None:
    with pytest.raises(InvalidChlorophyllResponseError):
        parse_chlorophyll_flag_metadata(masks, meanings)


@pytest.mark.asyncio
async def test_open_ocean_ordinary_nearest_grid_centre_is_not_exact() -> None:
    response = await make_service().get_chlorophyll(
        latitude=18.025,
        longitude=70.525,
        at=NOW,
    )
    assert response.sampling_quality == "nearest_grid_cell"
    assert response.sample_distance_km == pytest.approx(0.639, abs=0.002)
    assert response.chlorophyll_a.value == pytest.approx(0.3887)


@pytest.mark.asyncio
async def test_exact_grid_quality_requires_at_most_one_metre() -> None:
    exact = cell(latitude=18.025, longitude=70.525)
    response = await make_service(FakeProvider(result([exact]))).get_chlorophyll(
        latitude=18.025, longitude=70.525, at=NOW
    )
    assert response.sampling_quality == "exact_grid_cell"


@pytest.mark.asyncio
async def test_coastal_land_cell_is_rejected_for_nearest_valid_water_fallback() -> None:
    land = cell(
        latitude=20.5208320618,
        longitude=72.8958435059,
        chlorophyll=None,
        uncertainty=None,
        flag=3,
    )
    water = cell(
        latitude=20.5208320618,
        longitude=72.8541717529,
        chlorophyll=6.6455025673,
        uncertainty=72.169998,
        flag=2,
    )
    response = await make_service(
        FakeProvider(result([land, water]))
    ).get_chlorophyll(latitude=20.5, longitude=72.9, at=NOW)
    assert response.sampling_quality == "nearest_valid_water_cell"
    assert response.sample_distance_km == pytest.approx(5.305, abs=0.002)
    assert response.quality.land is False
    assert response.quality.interpolated is True
    assert any("grid cell was land" in warning for warning in response.warnings)


@pytest.mark.asyncio
async def test_land_takes_precedence_when_both_flag_bits_are_set() -> None:
    provider = FakeProvider(result([cell(flag=3)]))
    with pytest.raises(NoValidChlorophyllCellError):
        await make_service(provider).get_chlorophyll(
            latitude=18.025, longitude=70.525, at=NOW
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "provenance", "degraded"),
    [
        (0, "multi_sensor_merged_satellite_pixel", False),
        (2, "space_time_interpolated_gap_fill", True),
    ],
)
async def test_water_flag_provenance(flag: int, provenance: str, degraded: bool) -> None:
    response = await make_service(
        FakeProvider(result([cell(flag=flag, uncertainty=10)]))
    ).get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)
    assert response.data_provenance == provenance
    assert (response.quality.evidence_quality == "degraded") is degraded


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("uncertainty", "flag", "quality", "warning_count"),
    [
        (49.99, 0, "normal", 0),
        (50.0, 0, "degraded", 1),
        (10.0, 2, "degraded", 1),
        (70.62, 2, "degraded", 2),
        (None, 0, "degraded", 1),
        (math.nan, 0, "degraded", 1),
        (math.inf, 0, "degraded", 1),
    ],
)
async def test_uncertainty_evidence_policy(
    uncertainty: float | None,
    flag: int,
    quality: str,
    warning_count: int,
) -> None:
    response = await make_service(
        FakeProvider(result([cell(flag=flag, uncertainty=uncertainty)]))
    ).get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)
    assert response.quality.evidence_quality == quality
    evidence_warnings = [
        warning
        for warning in response.warnings
        if "interpolation" in warning
        or "uncertainty" in warning
        or "unavailable" in warning
    ]
    assert len(evidence_warnings) == warning_count
    if uncertainty is None or not math.isfinite(uncertainty):
        assert response.quality.uncertainty_percent is None
    else:
        assert response.quality.uncertainty_percent == pytest.approx(uncertainty)


@pytest.mark.asyncio
async def test_toolbox_decoded_uncertainty_is_not_scaled_twice() -> None:
    response = await make_service(
        FakeProvider(result([cell(uncertainty=70.619998)]))
    ).get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)
    assert response.quality.uncertainty_percent == 70.62


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_value",
    [None, math.nan, math.inf, -math.inf, -999.0, -0.01, 1000.01],
)
async def test_invalid_chlorophyll_values_are_rejected(invalid_value) -> None:
    with pytest.raises(NoValidChlorophyllCellError):
        await make_service(
            FakeProvider(result([cell(chlorophyll=invalid_value)]))
        ).get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)


@pytest.mark.asyncio
async def test_radius_boundary_is_inclusive_and_values_beyond_it_are_excluded() -> None:
    angular_degrees = math.degrees(10.0 / 6371.0088)
    boundary = cell(latitude=angular_degrees, longitude=0)
    included = await make_service(
        FakeProvider(result([boundary])), max_radius_km=10.0
    ).get_chlorophyll(latitude=0, longitude=0, at=NOW)
    assert included.sample_distance_km == pytest.approx(10.0, abs=0.001)

    outside = cell(latitude=angular_degrees + 0.0001, longitude=0)
    with pytest.raises(NoValidChlorophyllCellError):
        await make_service(
            FakeProvider(result([outside])), max_radius_km=10.0
        ).get_chlorophyll(latitude=0, longitude=0, at=NOW)


@pytest.mark.asyncio
async def test_full_precision_distance_and_coordinate_tie_breaking_are_deterministic() -> None:
    west = cell(latitude=0, longitude=-0.05)
    east = cell(latitude=0, longitude=0.05)
    response = await make_service(
        FakeProvider(result([east, west])), max_radius_km=10
    ).get_chlorophyll(latitude=0, longitude=0, at=NOW)
    assert response.sampled_location.longitude == pytest.approx(-0.05)


@pytest.mark.asyncio
async def test_longitude_normalization_and_antimeridian_bounding() -> None:
    provider = FakeProvider(result([cell(latitude=0, longitude=-179.99)]))
    response = await make_service(provider, max_radius_km=10).get_chlorophyll(
        latitude=0, longitude=180, at=NOW
    )
    assert response.requested_location.longitude == -180
    assert response.sample_distance_km == pytest.approx(
        haversine_distance_km(0, -180, 0, -179.99), abs=0.001
    )
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_latest_analysis_not_later_than_requested_time_is_selected() -> None:
    older = cell(analysis_time=ANALYSIS - timedelta(days=1), chlorophyll=0.2)
    latest = cell(analysis_time=ANALYSIS, chlorophyll=0.4)
    future = cell(analysis_time=NOW + timedelta(hours=1), chlorophyll=0.9)
    response = await make_service(
        FakeProvider(result([older, latest, future]))
    ).get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)
    assert response.analysis_time == ANALYSIS
    assert response.chlorophyll_a.value == 0.4
    assert any("latest daily" in warning for warning in response.warnings)


@pytest.mark.asyncio
async def test_future_request_and_stale_analysis_are_rejected() -> None:
    service = make_service()
    with pytest.raises(InvalidChlorophyllTimeError):
        await service.get_chlorophyll(
            latitude=18.025,
            longitude=70.525,
            at=NOW + timedelta(minutes=6),
        )
    old = cell(analysis_time=NOW - timedelta(hours=72, seconds=1))
    with pytest.raises(ChlorophyllDataUnavailableError):
        await make_service(FakeProvider(result([old]))).get_chlorophyll(
            latitude=18.025, longitude=70.525, at=NOW
        )


@pytest.mark.asyncio
async def test_timezone_naive_service_time_is_rejected() -> None:
    with pytest.raises(InvalidChlorophyllTimeError):
        await make_service().get_chlorophyll(
            latitude=18.025,
            longitude=70.525,
            at=datetime(2026, 8, 30),
        )


@pytest.mark.asyncio
async def test_identical_configuration_hits_fresh_cache_without_provider_call() -> None:
    cache = MemoryJsonCache()
    first_provider = FakeProvider()
    await make_service(first_provider, cache).get_chlorophyll(
        latitude=18.025, longitude=70.525, at=NOW
    )
    second_provider = FakeProvider()
    response = await make_service(second_provider, cache).get_chlorophyll(
        latitude=18.025, longitude=70.525, at=NOW
    )
    assert response.cache_status == "fresh"
    assert second_provider.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        {"max_radius_km": 11.0},
        {"dataset_version": "202312"},
        {"chlorophyll_variable": "CHL_NEW"},
        {"freshness_hours": 73.0},
        {"high_uncertainty_percent": 60.0},
        {"adapter_schema_version": "2"},
    ],
)
async def test_material_configuration_change_forces_cache_miss(changed: dict) -> None:
    cache = MemoryJsonCache()
    await make_service(cache=cache).get_chlorophyll(
        latitude=18.025, longitude=70.525, at=NOW
    )
    provider = FakeProvider()
    await make_service(provider, cache, **changed).get_chlorophyll(
        latitude=18.025, longitude=70.525, at=NOW
    )
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_matching_stale_data_is_used_only_for_source_unavailability() -> None:
    ticks = [0.0]
    cache = MemoryJsonCache(clock=lambda: ticks[0])
    await make_service(
        FakeProvider(), cache, fresh_ttl_seconds=1, max_stale_seconds=100
    ).get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)
    ticks[0] = 2
    provider = FakeProvider(error=ChlorophyllSourceUnavailableError("private"))
    response = await make_service(
        provider, cache, fresh_ttl_seconds=1, max_stale_seconds=100
    ).get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)
    assert response.cache_status == "stale"
    assert any("stale data" in warning for warning in response.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ChlorophyllAuthenticationError("private"),
        ChlorophyllDependencyMissingError("private"),
        InvalidChlorophyllResponseError("private"),
        NoValidChlorophyllCellError("private"),
    ],
)
async def test_stale_fallback_is_not_used_for_ineligible_errors(error) -> None:
    ticks = [0.0]
    cache = MemoryJsonCache(clock=lambda: ticks[0])
    await make_service(
        FakeProvider(), cache, fresh_ttl_seconds=1, max_stale_seconds=100
    ).get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)
    ticks[0] = 2
    with pytest.raises(type(error)):
        await make_service(
            FakeProvider(error=error),
            cache,
            fresh_ttl_seconds=1,
            max_stale_seconds=100,
        ).get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)


@pytest.mark.asyncio
async def test_identical_concurrent_misses_use_single_flight() -> None:
    provider = BlockingFakeProvider()
    service = make_service(provider)
    first = asyncio.create_task(
        service.get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)
    )
    second = asyncio.create_task(
        service.get_chlorophyll(latitude=18.025, longitude=70.525, at=NOW)
    )
    await asyncio.sleep(0)
    assert len(provider.calls) == 1
    provider.release.set()
    responses = await asyncio.gather(first, second)
    assert [response.cache_status for response in responses] == [
        "refreshed",
        "fresh",
    ]
    assert len(provider.calls) == 1


def test_missing_copernicus_dependency_is_typed_and_lazy(monkeypatch) -> None:
    def missing_import(name: str):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(
        "app.clients.copernicus_chlorophyll.import_module", missing_import
    )
    with pytest.raises(ChlorophyllDependencyMissingError):
        load_copernicus_chlorophyll_cells(
            dataset_id="dataset",
            chlorophyll_variable="CHL",
            uncertainty_variable="CHL_uncertainty",
            flags_variable="flags",
            minimum_latitude=18,
            maximum_latitude=19,
            minimum_longitude=70,
            maximum_longitude=71,
            start_datetime=ANALYSIS,
            end_datetime=NOW,
        )


def test_loader_closes_remote_dataset_after_structural_validation_failure(
    monkeypatch,
) -> None:
    class FakeDataset:
        def __init__(self) -> None:
            self.coords = {}
            self.closed = False

        def load(self) -> None:
            return None

        def __contains__(self, name: str) -> bool:
            return False

        def close(self) -> None:
            self.closed = True

    dataset = FakeDataset()

    class FakeCopernicus:
        @staticmethod
        def open_dataset(**kwargs):
            return dataset

    def fake_import(name: str):
        if name == "copernicusmarine":
            return FakeCopernicus()
        if name == "pandas":
            return object()
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(
        "app.clients.copernicus_chlorophyll.import_module", fake_import
    )
    with pytest.raises(InvalidChlorophyllResponseError):
        load_copernicus_chlorophyll_cells(
            dataset_id="dataset",
            chlorophyll_variable="CHL",
            uncertainty_variable="CHL_uncertainty",
            flags_variable="flags",
            minimum_latitude=18,
            maximum_latitude=19,
            minimum_longitude=70,
            maximum_longitude=71,
            start_datetime=ANALYSIS,
            end_datetime=NOW,
        )
    assert dataset.closed is True


class FakeAPIService:
    def __init__(self, response: ChlorophyllResponse | None = None, error=None):
        self.response = response
        self.error = error
        self.received = None

    async def get_chlorophyll(self, **kwargs):
        self.received = kwargs
        if self.error is not None:
            raise self.error
        return self.response


def sample_response() -> ChlorophyllResponse:
    return ChlorophyllResponse.model_validate(
        {
            "dataset_id": "cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
            "dataset_version": "202311",
            "variable": "CHL",
            "requested_location": {"latitude": 18.025, "longitude": 70.525},
            "sampled_location": {"latitude": 18.0208321, "longitude": 70.5208435},
            "sample_distance_km": 0.639,
            "chlorophyll_a": {"value": 0.3887},
            "analysis_time": "2026-08-30T00:00:00Z",
            "retrieved_at": "2026-08-31T20:50:56Z",
            "spatial_resolution_km": 4.638312,
            "sampling_quality": "nearest_grid_cell",
            "data_provenance": "space_time_interpolated_gap_fill",
            "quality": {
                "flag_value": 2,
                "land": False,
                "interpolated": True,
                "uncertainty_percent": 70.62,
                "evidence_quality": "degraded",
            },
            "cache_status": "refreshed",
        }
    )


def test_typed_endpoint_accepts_decimals_and_openapi_declares_numbers() -> None:
    fake = FakeAPIService(sample_response())
    with TestClient(app) as client:
        app.state.chlorophyll_service = fake
        response = client.get(
            "/v1/marine/chlorophyll",
            params={
                "latitude": 18.025,
                "longitude": 70.525,
                "at": "2026-08-30T12:00:00Z",
            },
        )
        operation = client.get("/openapi.json").json()["paths"][
            "/v1/marine/chlorophyll"
        ]["get"]
    assert response.status_code == 200
    assert fake.received["latitude"] == 18.025
    assert fake.received["longitude"] == 70.525
    coordinate_schemas = {
        parameter["name"]: parameter["schema"]
        for parameter in operation["parameters"]
        if parameter["name"] in {"latitude", "longitude"}
    }
    assert coordinate_schemas["latitude"]["type"] == "number"
    assert coordinate_schemas["longitude"]["type"] == "number"


def test_endpoint_rejects_naive_time_and_invalid_coordinates() -> None:
    with TestClient(app) as client:
        app.state.chlorophyll_service = FakeAPIService(sample_response())
        naive = client.get(
            "/v1/marine/chlorophyll",
            params={"latitude": 18, "longitude": 70, "at": "2026-08-30T12:00:00"},
        )
        invalid = client.get(
            "/v1/marine/chlorophyll",
            params={"latitude": 91, "longitude": 70},
        )
    assert naive.status_code == 422
    assert invalid.status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (InvalidChlorophyllTimeError("private"), 422, "INVALID_CHLOROPHYLL_TIME"),
        (ChlorophyllDataUnavailableError("private"), 404, "CHLOROPHYLL_DATA_UNAVAILABLE"),
        (NoValidChlorophyllCellError("private"), 404, "NO_VALID_CHLOROPHYLL_CELL"),
        (InvalidChlorophyllResponseError("private"), 502, "INVALID_CHLOROPHYLL_RESPONSE"),
        (ChlorophyllDependencyMissingError("private"), 503, "CHLOROPHYLL_DEPENDENCY_MISSING"),
        (ChlorophyllAuthenticationError("private"), 503, "CHLOROPHYLL_AUTHENTICATION_FAILED"),
        (ChlorophyllSourceNotConfiguredError("private"), 503, "CHLOROPHYLL_SOURCE_NOT_CONFIGURED"),
        (ChlorophyllSourceUnavailableError("private"), 503, "CHLOROPHYLL_SOURCE_UNAVAILABLE"),
    ],
)
def test_endpoint_maps_safe_typed_errors(error, status_code: int, code: str) -> None:
    with TestClient(app) as client:
        app.state.chlorophyll_service = FakeAPIService(error=error)
        response = client.get(
            "/v1/marine/chlorophyll",
            params={"latitude": 18.025, "longitude": 70.525, "at": "2026-08-30T12:00:00Z"},
        )
    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert "private" not in response.json()["detail"]["message"]
