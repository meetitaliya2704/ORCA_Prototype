from fastapi.testclient import TestClient

from app.main import app


def test_configured_frontend_origin_is_allowed_and_unknown_origin_is_not() -> None:
    with TestClient(app) as client:
        allowed = client.options(
            "/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        rejected = client.options(
            "/v1/health",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in rejected.headers
