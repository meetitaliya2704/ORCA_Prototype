from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.clients.copernicus_sst import (
    InvalidSSTResponseError,
    SSTAuthenticationError,
    SSTSourceNotConfiguredError,
    SSTSourceUnavailableError,
)
from app.clients.copernicus_waves import (
    InvalidWaveResponseError,
    WaveAuthenticationError,
    WaveSourceNotConfiguredError,
    WaveSourceUnavailableError,
)
from app.clients.copernicus_wind import (
    InvalidWindResponseError,
    WindAuthenticationError,
    WindSourceNotConfiguredError,
    WindSourceUnavailableError,
)
from app.clients.demo import DemoMarineSource
from app.main import app
from app.schemas.marine import SSTResponse, WaveResponse, WindResponse
from app.services.cache import MemoryJsonCache
from app.services.marine import MarineConditionsService
from app.services.sst import CopernicusSSTMarineSource, NoValidSSTError
from app.services.waves import (
    CopernicusWaveMarineSource,
    NoValidWaveDataError,
    NoWaveTimeAvailableError,
)
from app.services.wind import (
    CopernicusWindMarineSource,
    NoValidWindDataError,
    NoWindForecastAvailableError,
    WindDataTooOldError,
)


def sst_response(
    *,
    requested_latitude: float = 18.025,
    requested_longitude: float = 70.525,
) -> SSTResponse:
    return SSTResponse.model_validate(
        {
            "requested_location": {
                "latitude": requested_latitude,
                "longitude": requested_longitude,
            },
            "sampled_location": {"latitude": 18.025, "longitude": 70.525},
            "sample_distance_km": 0,
            "value": 28.32,
            "source_value": 301.469993,
            "analysis_time": "2026-08-27T00:00:00Z",
            "retrieved_at": "2026-08-28T13:49:42Z",
            "source": {
                "product_id": "SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001",
                "dataset_id": "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2",
                "variable": "analysed_sst",
            },
            "quality": "exact_grid_cell",
            "cache_status": "refreshed",
        }
    )


class FakeSSTService:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or sst_response()
        self.error = error
        self.received = None

    async def get_sst(self, **kwargs):
        self.received = kwargs
        if self.error is not None:
            raise self.error
        return self.result


def wave_response() -> WaveResponse:
    return WaveResponse.model_validate(
        {
            "requested_location": {"latitude": 18.025, "longitude": 70.525},
            "sampled_location": {"latitude": 18.0, "longitude": 70.5},
            "sample_distance_km": 3.8,
            "requested_time": "2026-08-29T00:00:00Z",
            "valid_time": "2026-08-29T00:00:00Z",
            "forecast_reference_time": "2026-08-28T00:00:00Z",
            "forecast_lead_hours": 24,
            "time_classification": "forecast",
            "significant_wave_height": {"value": 2.79, "unit": "m"},
            "mean_wave_period": {"value": 6.07, "unit": "s"},
            "mean_wave_direction_from": {"value": 247.85, "unit": "degree"},
            "retrieved_at": "2026-08-28T17:36:51Z",
            "source": {
                "dataset_id": "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
                "dataset_version": "202411",
            },
            "quality": "nearest_valid_ocean_cell",
            "cache_status": "refreshed",
        }
    )


class FakeWaveService:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or wave_response()
        self.error = error
        self.received = None

    async def get_waves(self, **kwargs):
        self.received = kwargs
        if self.error is not None:
            raise self.error
        return self.result


def wind_response() -> WindResponse:
    return WindResponse.model_validate(
        {
            "requested_location": {"latitude": 18.025, "longitude": 70.525},
            "sampled_location": {"latitude": 18.0625, "longitude": 70.5625},
            "sample_distance_km": 5.8,
            "requested_time": "2026-08-29T12:45:00Z",
            "valid_time": "2026-08-28T23:00:00Z",
            "data_age_hours": 13.75,
            "eastward_wind": {"value": 10.24},
            "northward_wind": {"value": 3.77},
            "wind_speed": {"value": 10.911943},
            "wind_direction_from": {
                "value": 249.788106,
                "unit": "degree",
                "compass": "W",
            },
            "retrieved_at": "2026-08-29T12:45:00Z",
            "source": {
                "dataset_id": "cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H"
            },
            "quality": "nearest_valid_grid_cell",
            "cache_status": "refreshed",
        }
    )


class FakeWindService:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or wind_response()
        self.error = error
        self.received = None

    async def get_wind(self, **kwargs):
        self.received = kwargs
        if self.error is not None:
            raise self.error
        return self.result


class FakeConditionsService:
    def __init__(self) -> None:
        self.received = None

    async def get_conditions(
        self,
        latitude: float,
        longitude: float,
        at: datetime | None = None,
    ):
        self.received = {
            "latitude": latitude,
            "longitude": longitude,
            "at": at,
        }
        return {
            "latitude": latitude,
            "longitude": longitude,
            "generated_at": datetime(2026, 8, 29, tzinfo=UTC),
            "sources": {},
        }


def install_coordinate_service(path: str):
    if path.endswith("/conditions"):
        service = FakeConditionsService()
        app.state.marine_service = service
    elif path.endswith("/sst"):
        service = FakeSSTService()
        app.state.sst_service = service
    elif path.endswith("/waves"):
        service = FakeWaveService()
        app.state.wave_service = service
    else:
        service = FakeWindService()
        app.state.wind_service = service
    return service


MARINE_COORDINATE_ENDPOINTS = [
    "/v1/marine/conditions",
    "/v1/marine/sst",
    "/v1/marine/waves",
    "/v1/marine/wind",
]


@pytest.mark.parametrize("path", MARINE_COORDINATE_ENDPOINTS)
@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (18.025, 70.525),
        (-18.025, -70.525),
        (18, 70),
        (-90.0, -180.0),
        (90.0, 180.0),
    ],
)
def test_all_marine_endpoints_accept_float_coordinates_without_precision_loss(
    path: str,
    latitude: float,
    longitude: float,
) -> None:
    with TestClient(app) as client:
        service = install_coordinate_service(path)
        response = client.get(
            path,
            params={"latitude": latitude, "longitude": longitude},
        )

    assert response.status_code == 200
    assert service.received["latitude"] == float(latitude)
    assert service.received["longitude"] == float(longitude)
    assert isinstance(service.received["latitude"], float)
    assert isinstance(service.received["longitude"], float)


@pytest.mark.parametrize("path", MARINE_COORDINATE_ENDPOINTS)
@pytest.mark.parametrize("latitude", [-90.0001, 90.0001])
def test_all_marine_endpoints_reject_latitude_outside_range(
    path: str,
    latitude: float,
) -> None:
    with TestClient(app) as client:
        install_coordinate_service(path)
        response = client.get(
            path,
            params={"latitude": latitude, "longitude": 0},
        )

    assert response.status_code == 422


@pytest.mark.parametrize("path", MARINE_COORDINATE_ENDPOINTS)
@pytest.mark.parametrize("longitude", [-180.0001, 180.0001])
def test_all_marine_endpoints_reject_longitude_outside_range(
    path: str,
    longitude: float,
) -> None:
    with TestClient(app) as client:
        install_coordinate_service(path)
        response = client.get(
            path,
            params={"latitude": 0, "longitude": longitude},
        )

    assert response.status_code == 422


def test_all_coordinate_query_parameters_are_openapi_numbers() -> None:
    schema = app.openapi()
    for path in [*MARINE_COORDINATE_ENDPOINTS, "/v1/pfz/nearest"]:
        operation = schema["paths"][path]["get"]
        parameters = {
            parameter["name"]: parameter["schema"]
            for parameter in operation["parameters"]
        }
        for name in ("latitude", "longitude"):
            assert parameters[name]["type"] == "number"
            assert parameters[name]["format"] == "double"
            assert "decimal degrees" in parameters[name]["description"]


def test_marine_conditions_and_cache() -> None:
    with TestClient(app) as client:
        app.state.marine_service = MarineConditionsService(
            client=app.state.marine_service.client,
            cache=MemoryJsonCache(),
            sources=[
                DemoMarineSource("sst", "SST", 29.4, "degC"),
                DemoMarineSource("waves", "WAVE_HEIGHT", 1.6, "m"),
                DemoMarineSource("wind", "WIND_SPEED", 18.0, "km/h"),
            ],
            cache_ttl=300,
        )
        first = client.get(
            "/v1/marine/conditions",
            params={"latitude": 20.5, "longitude": 72.9},
        )
        second = client.get(
            "/v1/marine/conditions",
            params={"latitude": 20.5, "longitude": 72.9},
        )

    assert first.status_code == 200
    assert first.json()["sources"]["sst"]["status"] == "fresh"
    assert first.json()["sources"]["sst"]["data"]["quality"] == "demo"
    assert first.json()["sources"]["waves"]["data"]["quality"] == "demo"
    assert second.json()["sources"]["sst"]["status"] == "cached"


def test_invalid_latitude_is_rejected() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/v1/marine/conditions",
            params={"latitude": 120, "longitude": 72.9},
        )

    assert response.status_code == 422


def test_websocket_progress_finishes() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/v1/ws/ingestion") as websocket:
            messages = [websocket.receive_json() for _ in range(5)]

    assert messages[0]["stage"] == "starting"
    assert messages[-1] == {"progress": 100, "stage": "completed"}


def test_typed_sst_endpoint_accepts_decimal_and_negative_coordinates() -> None:
    service = FakeSSTService(
        result=sst_response(
            requested_latitude=-18.025,
            requested_longitude=-70.525,
        )
    )
    with TestClient(app) as client:
        app.state.sst_service = service
        response = client.get(
            "/v1/marine/sst",
            params={
                "latitude": -18.025,
                "longitude": -70.525,
                "at": "2026-08-27T12:00:00Z",
            },
        )

    assert response.status_code == 200
    assert response.json()["value"] == 28.32
    assert response.json()["source"]["name"] == "Copernicus Marine"
    assert service.received["latitude"] == -18.025
    assert service.received["longitude"] == -70.525
    assert service.received["at"] == datetime(2026, 8, 27, 12, tzinfo=UTC)


def test_sst_endpoint_rejects_timezone_naive_at() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/v1/marine/sst",
            params={
                "latitude": 18.025,
                "longitude": 70.525,
                "at": "2026-08-27T00:00:00",
            },
        )

    assert response.status_code == 422


def test_disabled_sst_endpoint_is_not_configured() -> None:
    with TestClient(app) as client:
        app.state.sst_service = None
        response = client.get(
            "/v1/marine/sst",
            params={"latitude": 18.025, "longitude": 70.525},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SST_SOURCE_NOT_CONFIGURED"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (NoValidSSTError("private"), 404, "NO_VALID_SST"),
        (InvalidSSTResponseError("private"), 502, "INVALID_SST_RESPONSE"),
        (SSTSourceUnavailableError("private"), 503, "SST_SOURCE_UNAVAILABLE"),
        (SSTAuthenticationError("private"), 503, "SST_AUTHENTICATION_FAILED"),
        (
            SSTSourceNotConfiguredError("private"),
            503,
            "SST_SOURCE_NOT_CONFIGURED",
        ),
    ],
)
def test_sst_endpoint_maps_safe_typed_errors(
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    with TestClient(app) as client:
        app.state.sst_service = FakeSSTService(error=error)
        response = client.get(
            "/v1/marine/sst",
            params={"latitude": 18.025, "longitude": 70.525},
        )

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert "private" not in response.json()["detail"]["message"]


def test_conditions_preserves_partial_results_when_real_sst_fails() -> None:
    with TestClient(app) as client:
        app.state.marine_service = MarineConditionsService(
            client=app.state.marine_service.client,
            cache=MemoryJsonCache(),
            sources=[
                CopernicusSSTMarineSource(
                    FakeSSTService(
                        error=SSTSourceUnavailableError("private detail")
                    )
                ),
                DemoMarineSource("waves", "WAVE_HEIGHT", 1.6, "m"),
                DemoMarineSource("wind", "WIND_SPEED", 18.0, "km/h"),
            ],
            cache_ttl=300,
        )
        response = client.get(
            "/v1/marine/conditions",
            params={"latitude": 18.025, "longitude": 70.525},
        )

    assert response.status_code == 200
    assert response.json()["sources"]["sst"] == {
        "source": "Copernicus Marine",
        "status": "unavailable",
        "data": None,
        "error": "SST_SOURCE_UNAVAILABLE",
        "fetched_at": None,
        "cached": False,
    }
    assert response.json()["sources"]["waves"]["status"] == "fresh"
    assert response.json()["sources"]["wind"]["status"] == "fresh"


def test_typed_waves_endpoint_preserves_direction_from_and_time() -> None:
    service = FakeWaveService()
    with TestClient(app) as client:
        app.state.wave_service = service
        response = client.get(
            "/v1/marine/waves",
            params={
                "latitude": 18.025,
                "longitude": 70.525,
                "at": "2026-08-29T00:00:00Z",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["mean_wave_direction_from"] == {
        "value": 247.85,
        "unit": "degree",
    }
    assert body["forecast_lead_hours"] == 24
    assert service.received["at"] == datetime(2026, 8, 29, tzinfo=UTC)


def test_waves_endpoint_rejects_naive_time_and_invalid_coordinates() -> None:
    with TestClient(app) as client:
        naive = client.get(
            "/v1/marine/waves",
            params={
                "latitude": 18.025,
                "longitude": 70.525,
                "at": "2026-08-29T00:00:00",
            },
        )
        invalid = client.get(
            "/v1/marine/waves",
            params={"latitude": 91, "longitude": 181},
        )

    assert naive.status_code == 422
    assert invalid.status_code == 422


def test_disabled_waves_endpoint_is_not_configured() -> None:
    with TestClient(app) as client:
        app.state.wave_service = None
        response = client.get(
            "/v1/marine/waves",
            params={"latitude": 18.025, "longitude": 70.525},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "WAVE_SOURCE_NOT_CONFIGURED"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (NoValidWaveDataError("private"), 404, "NO_VALID_WAVE_DATA"),
        (NoWaveTimeAvailableError("private"), 404, "NO_WAVE_TIME_AVAILABLE"),
        (InvalidWaveResponseError("private"), 502, "INVALID_WAVE_RESPONSE"),
        (WaveSourceUnavailableError("private"), 503, "WAVE_SOURCE_UNAVAILABLE"),
        (WaveAuthenticationError("private"), 503, "WAVE_AUTHENTICATION_FAILED"),
        (
            WaveSourceNotConfiguredError("private"),
            503,
            "WAVE_SOURCE_NOT_CONFIGURED",
        ),
    ],
)
def test_waves_endpoint_maps_safe_typed_errors(
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    with TestClient(app) as client:
        app.state.wave_service = FakeWaveService(error=error)
        response = client.get(
            "/v1/marine/waves",
            params={"latitude": 18.025, "longitude": 70.525},
        )

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert "private" not in response.json()["detail"]["message"]


def test_conditions_preserves_partial_results_when_real_waves_fail() -> None:
    with TestClient(app) as client:
        app.state.marine_service = MarineConditionsService(
            client=app.state.marine_service.client,
            cache=MemoryJsonCache(),
            sources=[
                DemoMarineSource("sst", "SST", 29.4, "degC"),
                CopernicusWaveMarineSource(
                    FakeWaveService(
                        error=WaveSourceUnavailableError("private detail")
                    )
                ),
                DemoMarineSource("wind", "WIND_SPEED", 18.0, "km/h"),
            ],
            cache_ttl=300,
        )
        response = client.get(
            "/v1/marine/conditions",
            params={"latitude": 18.025, "longitude": 70.525},
        )

    assert response.status_code == 200
    assert response.json()["sources"]["waves"] == {
        "source": "Copernicus Marine",
        "status": "unavailable",
        "data": None,
        "error": "WAVE_SOURCE_UNAVAILABLE",
        "fetched_at": None,
        "cached": False,
    }
    assert response.json()["sources"]["sst"]["data"]["quality"] == "demo"
    assert response.json()["sources"]["wind"]["status"] == "fresh"


def test_typed_wind_endpoint_accepts_decimals_and_direction_from() -> None:
    service = FakeWindService()
    with TestClient(app) as client:
        app.state.wind_service = service
        response = client.get(
            "/v1/marine/wind",
            params={
                "latitude": 18.025,
                "longitude": 70.525,
                "at": "2026-08-29T12:45:00Z",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["wind_direction_from"] == {
        "value": 249.788106,
        "unit": "degree",
        "compass": "W",
    }
    assert body["source"]["forecast_available"] is False
    assert "ocean" not in body["quality"]
    assert service.received["latitude"] == 18.025
    assert service.received["longitude"] == 70.525


def test_wind_endpoint_rejects_naive_time_and_invalid_coordinates() -> None:
    with TestClient(app) as client:
        naive = client.get(
            "/v1/marine/wind",
            params={
                "latitude": 18.025,
                "longitude": 70.525,
                "at": "2026-08-29T12:45:00",
            },
        )
        invalid = client.get(
            "/v1/marine/wind",
            params={"latitude": 91, "longitude": 181},
        )
    assert naive.status_code == 422
    assert invalid.status_code == 422


def test_disabled_wind_endpoint_is_not_configured() -> None:
    with TestClient(app) as client:
        app.state.wind_service = None
        response = client.get(
            "/v1/marine/wind",
            params={"latitude": 18.025, "longitude": 70.525},
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "WIND_SOURCE_NOT_CONFIGURED"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (NoValidWindDataError("private"), 404, "NO_VALID_WIND_DATA"),
        (
            NoWindForecastAvailableError("private"),
            404,
            "NO_WIND_FORECAST_AVAILABLE",
        ),
        (InvalidWindResponseError("private"), 502, "INVALID_WIND_RESPONSE"),
        (WindSourceUnavailableError("private"), 503, "WIND_SOURCE_UNAVAILABLE"),
        (WindAuthenticationError("private"), 503, "WIND_AUTHENTICATION_FAILED"),
        (
            WindSourceNotConfiguredError("private"),
            503,
            "WIND_SOURCE_NOT_CONFIGURED",
        ),
        (WindDataTooOldError("private"), 503, "WIND_DATA_TOO_OLD"),
    ],
)
def test_wind_endpoint_maps_safe_typed_errors(
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    with TestClient(app) as client:
        app.state.wind_service = FakeWindService(error=error)
        response = client.get(
            "/v1/marine/wind",
            params={"latitude": 18.025, "longitude": 70.525},
        )
    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert "private" not in response.json()["detail"]["message"]


def test_conditions_keep_wave_result_when_future_wind_is_unavailable() -> None:
    future = datetime(2026, 8, 30, tzinfo=UTC)
    with TestClient(app) as client:
        app.state.marine_service = MarineConditionsService(
            client=app.state.marine_service.client,
            cache=MemoryJsonCache(),
            sources=[
                DemoMarineSource("sst", "SST", 29.4, "degC"),
                DemoMarineSource("waves", "WAVE_HEIGHT", 1.6, "m"),
                CopernicusWindMarineSource(
                    FakeWindService(
                        error=NoWindForecastAvailableError("private detail")
                    )
                ),
            ],
            cache_ttl=300,
        )
        response = client.get(
            "/v1/marine/conditions",
            params={
                "latitude": 18.025,
                "longitude": 70.525,
                "at": future.isoformat(),
            },
        )

    assert response.status_code == 200
    assert response.json()["sources"]["waves"]["status"] == "fresh"
    assert response.json()["sources"]["wind"]["status"] == "unavailable"
    assert (
        response.json()["sources"]["wind"]["error"]
        == "NO_WIND_FORECAST_AVAILABLE"
    )
