from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.parsers.pfz_html import parse_pfz_advisory


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
