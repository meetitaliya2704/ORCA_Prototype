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
