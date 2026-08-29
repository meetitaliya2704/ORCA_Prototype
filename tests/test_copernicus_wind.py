import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.clients.copernicus_wind import (
    WindProviderCell,
    WindProviderResult,
    WindSourceUnavailableError,
    extract_catalogue_time_bounds,
)
from app.services.cache import MemoryJsonCache
from app.services.wind import (
    COASTAL_CONTEXT_WARNING,
    CopernicusWindService,
    NoValidWindDataError,
    NoWindForecastAvailableError,
    WindDataTooOldError,
    wind_direction_from_deg,
    wind_speed_mps,
)


NOW = datetime(2026, 8, 29, 12, 45, tzinfo=UTC)
VALID_TIME = datetime(2026, 8, 28, 23, tzinfo=UTC)


def test_official_catalogue_time_bounds_are_extracted() -> None:
    catalogue = {
        "products": [
            {
                "datasets": [
                    {
                        "dataset_id": "dataset",
                        "versions": [
                            {
                                "label": "202207",
                                "parts": [
                                    {
                                        "services": [
                                            {
                                                "service_short_name": "timeseries",
                                                "variables": [
                                                    {
                                                        "short_name": "eastward_wind",
                                                        "coordinates": [
                                                            {
                                                                "coordinate_id": "time",
                                                                "minimum_value": 0,
                                                                "maximum_value": 3_600_000,
                                                            }
                                                        ],
                                                    }
                                                ],
                                            }
                                        ]
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ]
    }
    assert extract_catalogue_time_bounds(
        catalogue,
        dataset_id="dataset",
        dataset_version="202207",
        variable="eastward_wind",
    ) == (
        datetime(1970, 1, 1, tzinfo=UTC),
        datetime(1970, 1, 1, 1, tzinfo=UTC),
    )


def cell(
    *,
    latitude: float = 18.025,
    longitude: float = 70.525,
    valid_time: datetime = VALID_TIME,
    eastward: float | None = 10.24,
    northward: float | None = 3.77,
) -> WindProviderCell:
    return WindProviderCell(
        latitude=latitude,
        longitude=longitude,
        valid_time=valid_time,
        eastward_wind_mps=eastward,
        northward_wind_mps=northward,
    )


class FakeProvider:
    def __init__(
        self,
        cells=None,
        error: Exception | None = None,
        warnings: tuple[str, ...] = (),
    ) -> None:
        self.cells = cells if cells is not None else [cell()]
        self.error = error
        self.warnings = warnings
        self.calls: list[dict] = []

    async def fetch_cells(self, **kwargs):
        self.calls.append(kwargs)
        await asyncio.sleep(0)
        if self.error is not None:
            raise self.error
        return WindProviderResult(cells=self.cells, warnings=self.warnings)


def make_service(
    provider: FakeProvider,
    *,
    cache: MemoryJsonCache | None = None,
    radius: float = 50,
    max_age: float = 30,
    now=NOW,
) -> CopernicusWindService:
    return CopernicusWindService(
        provider=provider,
        cache=cache or MemoryJsonCache(),
        dataset_id="cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H",
        dataset_version="202207",
        eastward_variable="eastward_wind",
        northward_variable="northward_wind",
        search_radius_km=radius,
        max_age_hours=max_age,
        fresh_ttl_seconds=3600,
        stale_ttl_seconds=21600,
        now=lambda: now,
    )


@pytest.mark.asyncio
async def test_verified_components_are_decoded_once_and_derived() -> None:
    result = await make_service(FakeProvider()).get_wind(
        latitude=18.025,
        longitude=70.525,
        at=NOW,
    )

    assert result.eastward_wind.value == 10.24
    assert result.northward_wind.value == 3.77
    assert result.wind_speed.value == pytest.approx(10.911943)
    assert result.wind_direction_from.value == pytest.approx(249.788106)
    assert result.wind_direction_from.compass == "W"
    assert result.source.data_type == "near_real_time_blended_analysis"
    assert result.source.forecast_available is False
    assert result.data_age_hours == 13.75


@pytest.mark.parametrize(
    ("eastward", "northward", "expected"),
    [
        (-1.0, -1.0, 45.0),
        (1.0, -1.0, 315.0),
        (1.0, 1.0, 225.0),
        (-1.0, 1.0, 135.0),
    ],
)
def test_direction_from_all_component_quadrants(
    eastward: float,
    northward: float,
    expected: float,
) -> None:
    assert wind_direction_from_deg(eastward, northward) == pytest.approx(expected)


def test_calm_wind_has_no_direction() -> None:
    assert wind_speed_mps(0, 0) == 0
    assert wind_direction_from_deg(0, 0) is None


@pytest.mark.asyncio
async def test_calm_response_has_null_direction_and_compass() -> None:
    result = await make_service(
        FakeProvider([cell(eastward=0, northward=0)])
    ).get_wind(latitude=18.025, longitude=70.525, at=NOW)

    assert result.wind_speed.value == 0
    assert result.wind_direction_from.value is None
    assert result.wind_direction_from.compass is None


@pytest.mark.asyncio
async def test_invalid_components_and_documented_bounds_are_filtered() -> None:
    provider = FakeProvider(
        [
            cell(latitude=18.025, eastward=None),
            cell(latitude=18.03, northward=float("nan")),
            cell(latitude=18.04, eastward=float("inf")),
            cell(latitude=18.05, eastward=50.0001),
            cell(latitude=18.06, northward=-50.0001),
            cell(latitude=18.07, eastward=50.0, northward=-50.0),
        ]
    )
    result = await make_service(provider).get_wind(
        latitude=18.025,
        longitude=70.525,
        at=NOW,
    )

    assert result.sampled_location.latitude == 18.07
    assert result.eastward_wind.value == 50.0


@pytest.mark.asyncio
async def test_exact_and_nearest_quality_never_claim_ocean_cell() -> None:
    exact = await make_service(FakeProvider()).get_wind(
        latitude=18.025,
        longitude=70.525,
        at=NOW,
    )
    nearest = await make_service(
        FakeProvider([cell(latitude=18.0625, longitude=70.5625)])
    ).get_wind(latitude=18.025, longitude=70.525, at=NOW)

    assert exact.quality == "exact_grid_cell"
    assert nearest.quality == "nearest_valid_grid_cell"
    assert "ocean" not in nearest.quality
    assert COASTAL_CONTEXT_WARNING in exact.warnings
    assert COASTAL_CONTEXT_WARNING in nearest.warnings


@pytest.mark.asyncio
async def test_spatial_tie_break_is_latitude_then_longitude(monkeypatch) -> None:
    provider = FakeProvider(
        [
            cell(latitude=18.1, longitude=70.6),
            cell(latitude=18.0, longitude=70.7),
            cell(latitude=18.0, longitude=70.4),
        ]
    )
    monkeypatch.setattr("app.services.wind.haversine_distance_km", lambda *args: 10)
    result = await make_service(provider).get_wind(
        latitude=18.025,
        longitude=70.525,
        at=NOW,
    )

    assert result.sampled_location.latitude == 18.0
    assert result.sampled_location.longitude == 70.4


@pytest.mark.asyncio
async def test_maximum_radius_is_enforced() -> None:
    with pytest.raises(NoValidWindDataError):
        await make_service(
            FakeProvider([cell(latitude=19.0)]), radius=10
        ).get_wind(latitude=18.025, longitude=70.525, at=NOW)


@pytest.mark.asyncio
async def test_latest_timestamp_not_later_than_at_is_selected() -> None:
    provider = FakeProvider(
        [
            cell(valid_time=VALID_TIME - timedelta(hours=1), eastward=1),
            cell(valid_time=VALID_TIME, eastward=2),
            cell(valid_time=NOW + timedelta(hours=1), eastward=3),
        ]
    )
    result = await make_service(provider).get_wind(
        latitude=18.025,
        longitude=70.525,
        at=NOW,
    )

    assert result.valid_time == VALID_TIME
    assert result.eastward_wind.value == 2


@pytest.mark.asyncio
async def test_thirty_hour_freshness_boundary_is_inclusive() -> None:
    query = VALID_TIME + timedelta(hours=30)
    result = await make_service(FakeProvider(), now=query).get_wind(
        latitude=18.025,
        longitude=70.525,
        at=query,
    )
    assert result.data_age_hours == 30


@pytest.mark.asyncio
async def test_data_older_than_thirty_hours_is_rejected() -> None:
    query = VALID_TIME + timedelta(hours=30, seconds=1)
    with pytest.raises(WindDataTooOldError):
        await make_service(FakeProvider(), now=query).get_wind(
            latitude=18.025,
            longitude=70.525,
            at=query,
        )


@pytest.mark.asyncio
async def test_future_request_is_rejected_before_provider_call() -> None:
    provider = FakeProvider()
    with pytest.raises(NoWindForecastAvailableError):
        await make_service(provider).get_wind(
            latitude=18.025,
            longitude=70.525,
            at=NOW + timedelta(minutes=6),
        )
    assert provider.calls == []


@pytest.mark.asyncio
async def test_fresh_cache_hit_prevents_provider_call() -> None:
    provider = FakeProvider()
    service = make_service(provider)
    refreshed = await service.get_wind(latitude=18.025, longitude=70.525, at=NOW)
    fresh = await service.get_wind(latitude=18.025, longitude=70.525, at=NOW)

    assert refreshed.cache_status == "refreshed"
    assert fresh.cache_status == "fresh"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_matching_stale_fallback_is_allowed_while_current() -> None:
    cache = MemoryJsonCache()
    provider = FakeProvider()
    service = make_service(provider, cache=cache)
    original = await service.get_wind(latitude=18.025, longitude=70.525, at=NOW)
    fresh_key = next(key for key in cache._values if key.endswith(":fresh"))
    cache._values.pop(fresh_key)
    provider.error = WindSourceUnavailableError("private")

    stale = await service.get_wind(latitude=18.025, longitude=70.525, at=NOW)
    assert stale.cache_status == "stale"
    assert stale.valid_time == original.valid_time
    assert any("matching stale data" in warning for warning in stale.warnings)


@pytest.mark.asyncio
async def test_stale_fallback_is_rejected_when_cached_value_is_too_old() -> None:
    cache = MemoryJsonCache()
    provider = FakeProvider()
    service = make_service(provider, cache=cache)
    await service.get_wind(latitude=18.025, longitude=70.525, at=NOW)
    fresh_key = next(key for key in cache._values if key.endswith(":fresh"))
    cache._values.pop(fresh_key)
    stale_key = next(key for key in cache._values if key.endswith(":last_success"))
    payload, expires = cache._values[stale_key]
    payload["valid_time"] = (NOW - timedelta(hours=31)).isoformat()
    cache._values[stale_key] = (payload, expires)
    provider.error = WindSourceUnavailableError("private")

    with pytest.raises(WindDataTooOldError):
        await service.get_wind(latitude=18.025, longitude=70.525, at=NOW)


@pytest.mark.asyncio
async def test_temporal_and_spatial_cache_keys_are_isolated() -> None:
    provider = FakeProvider(
        [
            cell(latitude=18.025, longitude=70.525),
            cell(latitude=-18.025, longitude=-70.525),
        ]
    )
    service = make_service(provider)
    await service.get_wind(latitude=18.025, longitude=70.525, at=NOW)
    await service.get_wind(latitude=-18.025, longitude=-70.525, at=NOW)
    await service.get_wind(
        latitude=18.025,
        longitude=70.525,
        at=NOW - timedelta(hours=1),
    )
    assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_simultaneous_misses_make_one_provider_call() -> None:
    provider = FakeProvider()
    service = make_service(provider)
    results = await asyncio.gather(
        *(service.get_wind(latitude=18.025, longitude=70.525, at=NOW) for _ in range(5))
    )
    assert len(provider.calls) == 1
    assert sum(result.cache_status == "refreshed" for result in results) == 1
    assert sum(result.cache_status == "fresh" for result in results) == 4


@pytest.mark.asyncio
async def test_provider_warning_is_propagated_safely() -> None:
    warning = "Copernicus wind dataset is actively updating"
    result = await make_service(
        FakeProvider(warnings=(warning,))
    ).get_wind(latitude=18.025, longitude=70.525, at=NOW)
    assert warning in result.warnings
