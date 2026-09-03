from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.api.routes.marine import router
from tests.test_sst_snapshots import make_manager


def snapshot_app(manager):
    application = FastAPI()
    application.include_router(router, prefix="/v1")
    application.state.sst_service = manager.point_service
    application.state.sst_snapshot_manager = manager
    return application


@pytest.mark.asyncio
async def test_missing_snapshot_returns_typed_202_then_fresh_200():
    manager, provider, _ = make_manager()
    app = snapshot_app(manager)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/v1/marine/sst", params={"latitude": 18.025, "longitude": 70.525})
        assert first.status_code == 202
        payload = first.json()
        assert payload["code"] == "MARINE_DATA_REFRESH_IN_PROGRESS"
        assert "detail" not in payload
        await manager.jobs.wait(payload["job_id"], 1)
        second = await client.get("/v1/marine/sst", params={"latitude": 18.025, "longitude": 70.525})
        assert second.status_code == 200
        assert second.json()["snapshot"]["status"] == "fresh"
        assert second.json()["cache_status"] == "fresh"
        assert provider.calls == 1


@pytest.mark.asyncio
async def test_job_status_and_unknown_job_contract():
    manager, _, _ = make_manager()
    app = snapshot_app(manager)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        accepted = await client.get("/v1/marine/sst", params={"latitude": 18.025, "longitude": 70.525})
        job_id = accepted.json()["job_id"]
        status = await client.get(f"/v1/marine/refresh/jobs/{job_id}")
        assert status.status_code == 200
        assert status.json()["source"] == "sst"
        missing = await client.get("/v1/marine/refresh/jobs/not-a-job")
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "REFRESH_JOB_NOT_FOUND"


def test_snapshot_openapi_keeps_decimal_coordinates_and_two_success_shapes():
    manager, _, _ = make_manager()
    schema = snapshot_app(manager).openapi()
    operation = schema["paths"]["/v1/marine/sst"]["get"]
    coordinates = {
        item["name"]: item["schema"] for item in operation["parameters"]
        if item["name"] in {"latitude", "longitude"}
    }
    assert coordinates["latitude"]["type"] == "number"
    assert coordinates["longitude"]["type"] == "number"
    assert "202" in operation["responses"]
