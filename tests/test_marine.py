from fastapi.testclient import TestClient

from app.main import app


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
