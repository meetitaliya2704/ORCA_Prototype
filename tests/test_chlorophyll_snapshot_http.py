from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.api.routes.marine import router
from app.clients.copernicus_chlorophyll import ChlorophyllAuthenticationError
from tests.test_chlorophyll_snapshots import FakeRegionalChlorophyllProvider, make_manager


def snapshot_app(manager):
    application = FastAPI()
    application.include_router(router, prefix="/v1")
    application.state.chlorophyll_service = manager.point_service
    application.state.chlorophyll_snapshot_manager = manager
    application.state.snapshot_job_manager = manager.jobs
    return application


@pytest.mark.asyncio
async def test_chlorophyll_missing_202_then_fresh_200_and_shared_job_status():
    manager, provider, _ = make_manager()
    async with AsyncClient(
        transport=ASGITransport(app=snapshot_app(manager)), base_url="http://test"
    ) as client:
        first = await client.get(
            "/v1/marine/chlorophyll",
            params={"latitude": 18.025, "longitude": 70.525},
        )
        assert first.status_code == 202
        assert first.json()["source"] == "chlorophyll"
        job_id = first.json()["job_id"]
        await manager.jobs.wait(job_id, 1)
        job = await client.get(f"/v1/marine/refresh/jobs/{job_id}")
        assert job.status_code == 200
        assert job.json()["source"] == "chlorophyll"
        second = await client.get(
            "/v1/marine/chlorophyll",
            params={"latitude": 18.025, "longitude": 70.525},
        )
        assert second.status_code == 200
        assert second.json()["snapshot"]["status"] == "fresh"
        assert provider.calls == 1


@pytest.mark.asyncio
async def test_blocked_auth_failure_returns_503_not_a_false_202():
    provider = FakeRegionalChlorophyllProvider(
        error=ChlorophyllAuthenticationError("secret")
    )
    manager, _, _ = make_manager(provider)
    async with AsyncClient(
        transport=ASGITransport(app=snapshot_app(manager)), base_url="http://test"
    ) as client:
        first = await client.get(
            "/v1/marine/chlorophyll",
            params={"latitude": 18.025, "longitude": 70.525},
        )
        await manager.jobs.wait(first.json()["job_id"], 1)
        second = await client.get(
            "/v1/marine/chlorophyll",
            params={"latitude": 18.025, "longitude": 70.525},
        )
        assert second.status_code == 503
        assert second.json()["detail"]["code"] == "CHLOROPHYLL_AUTHENTICATION_FAILED"
        assert "secret" not in second.text


def test_chlorophyll_snapshot_openapi_has_decimal_coordinates_and_202():
    manager, _, _ = make_manager()
    operation = snapshot_app(manager).openapi()["paths"]["/v1/marine/chlorophyll"]["get"]
    coordinates = {
        item["name"]: item["schema"]
        for item in operation["parameters"]
        if item["name"] in {"latitude", "longitude"}
    }
    assert coordinates["latitude"]["type"] == "number"
    assert coordinates["longitude"]["type"] == "number"
    assert "202" in operation["responses"]

