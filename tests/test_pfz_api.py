from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clients.incois_pfz import PFZSourceUnavailableError
from app.main import app
from app.parsers.pfz_html import (
    NoSectorsDiscoveredError,
    PFZParseError,
    parse_pfz_advisory,
)
from app.schemas.pfz import PFZSnapshot
from app.services.pfz import PFZNearestService


FIXTURES = Path(__file__).parent / "fixtures"


class FakePFZService:
    async def preview_sector(self, sector_code: str):
        return parse_pfz_advisory(
            home_html=(FIXTURES / "incois_home.html").read_text(encoding="utf-8"),
            sector_html=(FIXTURES / "incois_sec001.html").read_text(
                encoding="utf-8"
            ),
            sector_code=sector_code,
            source_url=f"https://incois.test/TextData?secid={sector_code}",
        )


def snapshot_payload() -> PFZSnapshot:
    advisory = parse_pfz_advisory(
        home_html=(FIXTURES / "incois_home.html").read_text(encoding="utf-8"),
        sector_html=(FIXTURES / "incois_sec001.html").read_text(
            encoding="utf-8"
        ),
        sector_code="SEC001",
        source_url="https://incois.test/TextData?secid=SEC001",
    )
    return PFZSnapshot.model_validate(
        {
            "generated_at": "2026-08-27T12:00:00Z",
            "retrieved_at": "2026-08-27T12:00:00Z",
            "discovered_sector_count": 1,
            "successful_sector_count": 1,
            "failed_sector_count": 0,
            "discovered_sectors": [
                {
                    "sector_code": "SEC001",
                    "display_label": "Discovery Gujarat",
                }
            ],
            "successful_sectors": [
                {
                    "discovered_sector": {
                        "sector_code": "SEC001",
                        "display_label": "Discovery Gujarat",
                    },
                    "advisory": advisory,
                }
            ],
            "failed_sectors": [],
            "total_location_count": 1,
            "completeness": "complete",
            "cache_status": "refreshed",
            "warnings": advisory.parse_warnings,
            "source_name": "INCOIS",
            "source_url": "https://incois.test/TextDataHome",
        }
    )


class FakeSnapshotService:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or snapshot_payload()
        self.error = error

    async def get_snapshot(self):
        if self.error is not None:
            raise self.error
        return self.result


def nearest_service(
    *,
    snapshot: PFZSnapshot | None = None,
    error: Exception | None = None,
    now: datetime = datetime(2026, 8, 27, 12, tzinfo=UTC),
) -> PFZNearestService:
    return PFZNearestService(
        snapshot_service=FakeSnapshotService(snapshot, error),
        now=lambda: now,
    )


class RecordingNearestService:
    def __init__(self) -> None:
        self.delegate = nearest_service()
        self.received: dict[str, object] = {}

    async def get_nearest(self, **kwargs):
        self.received = kwargs
        return await self.delegate.get_nearest(**kwargs)


def test_pfz_preview_endpoint() -> None:
    with TestClient(app) as client:
        app.state.pfz_service = FakePFZService()
        response = client.get(
            "/v1/pfz/preview",
            params={"sector_code": "SEC001"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["sector_code"] == "SEC001"
    assert body["region_name"] == "Gujarat"
    assert body["locations"][0]["longitude"] == 68.95


def test_pfz_preview_rejects_invalid_sector_format() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/v1/pfz/preview",
            params={"sector_code": "GUJARAT"},
        )

    assert response.status_code == 422


def test_pfz_snapshot_endpoint_returns_typed_response() -> None:
    with TestClient(app) as client:
        app.state.pfz_snapshot_service = FakeSnapshotService()
        response = client.get("/v1/pfz/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["cache_status"] == "refreshed"
    assert body["completeness"] == "complete"
    assert body["successful_sectors"][0]["advisory"]["region_name"] == "Gujarat"
    assert body["total_location_count"] == 1


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            NoSectorsDiscoveredError(),
            502,
            "NO_SECTORS_DISCOVERED",
        ),
        (
            PFZParseError("private invalid detail"),
            502,
            "INVALID_PFZ_RESPONSE",
        ),
        (
            PFZSourceUnavailableError("private transport detail"),
            503,
            "SOURCE_UNAVAILABLE",
        ),
    ],
)
def test_pfz_snapshot_maps_typed_failures(
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    with TestClient(app) as client:
        app.state.pfz_snapshot_service = FakeSnapshotService(error=error)
        response = client.get("/v1/pfz/snapshot")

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert "private" not in response.json()["detail"]["message"]


def test_pfz_nearest_endpoint_returns_typed_json_and_geojson() -> None:
    with TestClient(app) as client:
        app.state.pfz_nearest_service = nearest_service()
        response = client.get(
            "/v1/pfz/nearest",
            params={
                "latitude": 21.6417,
                "longitude": 69.6293,
                "at": "2026-08-27T12:00:00Z",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["query"]["at"] == "2026-08-27T12:00:00Z"
    assert body["nearest_pfz"]["sector_code"] == "SEC001"
    assert body["cache_status"] == "refreshed"
    assert body["valid_from"] == "2026-08-26T18:30:00Z"
    assert body["valid_until"] == "2026-08-28T18:29:59.999999Z"
    assert body["geojson"]["type"] == "Feature"
    assert body["geojson"]["geometry"]["coordinates"] == [68.95, 22.7166667]


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (21.6417, 69.6293),
        (-21.6417, -69.6293),
        (-90.0, -180.0),
        (90.0, 180.0),
        (21, 69),
    ],
)
def test_pfz_nearest_accepts_decimal_integer_and_boundary_coordinates(
    latitude: float,
    longitude: float,
) -> None:
    service = RecordingNearestService()
    with TestClient(app) as client:
        app.state.pfz_nearest_service = service
        response = client.get(
            "/v1/pfz/nearest",
            params={"latitude": latitude, "longitude": longitude},
        )

    assert response.status_code == 200
    assert service.received["latitude"] == float(latitude)
    assert service.received["longitude"] == float(longitude)
    assert isinstance(service.received["latitude"], float)
    assert isinstance(service.received["longitude"], float)


def test_pfz_nearest_preserves_decimal_query_precision_to_service() -> None:
    service = RecordingNearestService()
    with TestClient(app) as client:
        app.state.pfz_nearest_service = service
        response = client.get(
            "/v1/pfz/nearest",
            params={
                "latitude": "21.641712345678",
                "longitude": "69.629312345678",
            },
        )

    assert response.status_code == 200
    assert service.received["latitude"] == 21.641712345678
    assert service.received["longitude"] == 69.629312345678
    assert response.json()["query"]["latitude"] == 21.641712345678
    assert response.json()["query"]["longitude"] == 69.629312345678


@pytest.mark.parametrize("latitude", [-90.0001, 90.0001])
def test_pfz_nearest_rejects_latitude_outside_range(latitude: float) -> None:
    with TestClient(app) as client:
        response = client.get(
            "/v1/pfz/nearest",
            params={"latitude": latitude, "longitude": 0},
        )

    assert response.status_code == 422


@pytest.mark.parametrize("longitude", [-180.0001, 180.0001])
def test_pfz_nearest_rejects_longitude_outside_range(longitude: float) -> None:
    with TestClient(app) as client:
        response = client.get(
            "/v1/pfz/nearest",
            params={"latitude": 0, "longitude": longitude},
        )

    assert response.status_code == 422


def test_pfz_nearest_openapi_coordinates_are_numbers() -> None:
    operation = app.openapi()["paths"]["/v1/pfz/nearest"]["get"]
    schemas = {
        parameter["name"]: parameter["schema"]
        for parameter in operation["parameters"]
    }

    assert schemas["latitude"]["type"] == "number"
    assert schemas["latitude"]["format"] == "double"
    assert schemas["latitude"]["minimum"] == -90.0
    assert schemas["latitude"]["maximum"] == 90.0
    assert schemas["longitude"]["type"] == "number"
    assert schemas["longitude"]["format"] == "double"
    assert schemas["longitude"]["minimum"] == -180.0
    assert schemas["longitude"]["maximum"] == 180.0


def test_pfz_nearest_rejects_timezone_naive_at() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/v1/pfz/nearest",
            params={
                "latitude": 0,
                "longitude": 0,
                "at": "2026-08-27T12:00:00",
            },
        )

    assert response.status_code == 422


def test_pfz_nearest_omitted_at_uses_injected_utc_now() -> None:
    with TestClient(app) as client:
        app.state.pfz_nearest_service = nearest_service()
        response = client.get(
            "/v1/pfz/nearest",
            params={"latitude": 21.6417, "longitude": 69.6293},
        )

    assert response.status_code == 200
    assert response.json()["query"]["at"] == "2026-08-27T12:00:00Z"


def test_pfz_nearest_converts_supplied_offset_to_utc() -> None:
    with TestClient(app) as client:
        app.state.pfz_nearest_service = nearest_service()
        response = client.get(
            "/v1/pfz/nearest",
            params={
                "latitude": 21.6417,
                "longitude": 69.6293,
                "at": "2026-08-27T17:30:00+05:30",
            },
        )

    assert response.status_code == 200
    assert response.json()["query"]["at"] == "2026-08-27T12:00:00Z"


def test_pfz_nearest_returns_404_when_no_advisory_is_valid() -> None:
    with TestClient(app) as client:
        app.state.pfz_nearest_service = nearest_service()
        response = client.get(
            "/v1/pfz/nearest",
            params={
                "latitude": 0,
                "longitude": 0,
                "at": "2027-01-01T00:00:00Z",
            },
        )

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "NO_VALID_PFZ",
            "message": "No PFZ advisory is valid for the requested time",
        }
    }


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            PFZParseError("private invalid detail"),
            502,
            "INVALID_PFZ_RESPONSE",
        ),
        (
            PFZSourceUnavailableError("private transport detail"),
            503,
            "SOURCE_UNAVAILABLE",
        ),
    ],
)
def test_pfz_nearest_preserves_snapshot_failures(
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    with TestClient(app) as client:
        app.state.pfz_nearest_service = nearest_service(error=error)
        response = client.get(
            "/v1/pfz/nearest",
            params={"latitude": 0, "longitude": 0},
        )

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
