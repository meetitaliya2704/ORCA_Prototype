from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.clients.copernicus_sst import (
    InvalidSSTResponseError,
    SSTAuthenticationError,
    SSTSourceNotConfiguredError,
    SSTSourceUnavailableError,
)
from app.clients.demo import DemoMarineSource
from app.main import app
from app.schemas.marine import SSTResponse
from app.services.cache import MemoryJsonCache
from app.services.marine import MarineConditionsService
from app.services.sst import CopernicusSSTMarineSource, NoValidSSTError


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


def test_marine_conditions_and_cache() -> None:
    with TestClient(app) as client:
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
