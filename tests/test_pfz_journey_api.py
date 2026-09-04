from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.assessment import MarineAssessmentService
from app.services.pfz_journey import PFZJourneyService, PFZRefreshPendingError
from tests.test_pfz_journey_service import (
    FakePFZService,
    LocationEvidenceService,
    ORIGIN,
    critical_bundle,
    journey_request,
    pfz_response,
)


AT = datetime(2026, 8, 27, 12, tzinfo=UTC)


async def api_service(*, pending=False):
    evidence_bundle = await critical_bundle(wave_height=1.0)
    evidence = LocationEvidenceService(evidence_bundle, evidence_bundle)
    pfz = FakePFZService(
        result=None if pending else await pfz_response(),
        error=PFZRefreshPendingError(job_id="job-1") if pending else None,
    )
    assessment = MarineAssessmentService(evidence_service=evidence, now=lambda: AT)
    return PFZJourneyService(
        pfz_service=pfz,
        evidence_service=evidence,
        assessment_service=assessment,
        now=lambda: AT,
    )


@pytest.mark.asyncio
async def test_journey_endpoint_and_openapi_are_typed():
    service = await api_service()
    with TestClient(app) as client:
        app.state.pfz_journey_service = service
        response = client.post(
            "/v1/decision-support/pfz-journey",
            json=journey_request().model_dump(mode="json"),
        )
        schema = client.get("/openapi.json").json()
    assert response.status_code == 200
    assert response.json()["journey_status"] == "PFZ_AVAILABLE_WITHIN_CONFIGURED_LIMITS"
    operation = schema["paths"]["/v1/decision-support/pfz-journey"]["post"]
    assert operation["tags"] == ["decision-support"]
    components = schema["components"]["schemas"]
    location = components["JourneyLocation"]["properties"]
    assert location["latitude"]["type"] == "number"
    assert location["longitude"]["type"] == "number"
    assert "OperationalLimits" in components
    assert "MarineEvidenceResponse" in components
    assert "MarineAssessmentResponse" in components
    assert "JourneyFeatureCollection" in components
    assert set(components["JourneyStatus"]["enum"]) >= {
        "PFZ_AVAILABLE_LIMIT_EXCEEDED",
        "NO_VALID_PFZ",
        "PFZ_REFRESH_PENDING",
    }


@pytest.mark.asyncio
async def test_http_202_is_used_only_for_genuine_pfz_pending_result():
    service = await api_service(pending=True)
    with TestClient(app) as client:
        app.state.pfz_journey_service = service
        response = client.post(
            "/v1/decision-support/pfz-journey",
            json=journey_request().model_dump(mode="json"),
        )
    assert response.status_code == 202
    assert response.json()["journey_status"] == "PFZ_REFRESH_PENDING"


@pytest.mark.parametrize(
    "change",
    [
        {"origin": {"latitude": "NaN", "longitude": 72.9}},
        {"origin": {"latitude": 20.5, "longitude": "Infinity"}},
        {"at": "2026-09-04T12:00:00"},
        {"operational_limits": {}},
        {"operational_limits": {"maximum_wind_speed_m_s": 0}},
        {"operational_limits": {"maximum_wind_speed_m_s": -1}},
        {"operational_limits": {"maximum_wind_speed_m_s": "NaN"}},
    ],
)
def test_invalid_journey_requests_return_422(change):
    payload = journey_request().model_dump(mode="json")
    payload.update(change)
    with TestClient(app) as client:
        response = client.post("/v1/decision-support/pfz-journey", json=payload)
    assert response.status_code == 422


def test_unconfigured_journey_has_stable_sanitized_error():
    with TestClient(app) as client:
        app.state.pfz_journey_service = None
        response = client.post(
            "/v1/decision-support/pfz-journey",
            json=journey_request().model_dump(mode="json"),
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PFZ_JOURNEY_NOT_CONFIGURED"
