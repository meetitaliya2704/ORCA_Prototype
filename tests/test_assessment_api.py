from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.assessment import AssessmentRequest, OperationalLimits
from app.services.assessment import MarineAssessmentService
from tests.test_assessment_service import FakeEvidenceService
from tests.test_risk_rules import critical_bundle


NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)


def payload(**updates):
    value = {
        "latitude": 20.5,
        "longitude": 72.9,
        "at": NOW.isoformat(),
        "operational_limits": {"maximum_significant_wave_height_m": 2.0},
        "include_pfz_context": True,
    }
    value.update(updates)
    return value


@pytest.mark.asyncio
async def test_assessment_endpoint_and_openapi_are_typed():
    bundle = await critical_bundle(wave_height=1.0)
    service = MarineAssessmentService(
        evidence_service=FakeEvidenceService(bundle), now=lambda: NOW
    )
    with TestClient(app) as client:
        app.state.assessment_service = service
        response = client.post("/v1/decision-support/assessment", json=payload())
        schema = client.get("/openapi.json").json()
    assert response.status_code == 200
    assert response.json()["outcome"] == "WITHIN_CONFIGURED_LIMITS"
    operation = schema["paths"]["/v1/decision-support/assessment"]["post"]
    assert operation["tags"] == ["decision-support"]
    request_schema = schema["components"]["schemas"]["AssessmentRequest"]
    assert request_schema["properties"]["latitude"]["type"] == "number"
    assert request_schema["properties"]["longitude"]["type"] == "number"
    assert "OperationalLimits" in schema["components"]["schemas"]
    assert "OperationalRuleResult" in schema["components"]["schemas"]
    assert set(schema["components"]["schemas"]["AssessmentOutcome"]["enum"]) == {
        "WITHIN_CONFIGURED_LIMITS", "CAUTION", "LIMIT_EXCEEDED",
        "INSUFFICIENT_EVIDENCE", "POLICY_NOT_CONFIGURED",
    }


@pytest.mark.parametrize(
    "limits",
    [
        {},
        {"maximum_wind_speed_m_s": 0},
        {"maximum_wind_speed_m_s": -1},
        {"maximum_wind_speed_m_s": "NaN"},
        {"maximum_wind_speed_m_s": "Infinity"},
    ],
)
def test_missing_non_positive_and_non_finite_limits_are_rejected(limits):
    with TestClient(app) as client:
        response = client.post(
            "/v1/decision-support/assessment",
            json=payload(operational_limits=limits),
        )
    assert response.status_code == 422


def test_naive_time_and_non_finite_coordinates_are_rejected():
    with TestClient(app) as client:
        naive = client.post(
            "/v1/decision-support/assessment",
            json=payload(at="2026-09-04T12:00:00"),
        )
        coordinate = client.post(
            "/v1/decision-support/assessment",
            json=payload(latitude="NaN"),
        )
    assert naive.status_code == 422
    assert coordinate.status_code == 422


def test_assessment_request_records_request_supplied_limits_only():
    request = AssessmentRequest.model_validate(payload())
    assert request.operational_limits.maximum_significant_wave_height_m == 2.0
    assert request.near_limit_percentage is None


def test_unconfigured_assessment_has_stable_error():
    with TestClient(app) as client:
        app.state.assessment_service = None
        response = client.post("/v1/decision-support/assessment", json=payload())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ASSESSMENT_NOT_CONFIGURED"
