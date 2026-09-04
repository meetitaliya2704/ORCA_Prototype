from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app
from app.services.evidence import MarineEvidenceService
from tests.test_evidence_service import FakeService
from tests.test_marine import sst_response


NOW = datetime(2026, 9, 3, 12, tzinfo=UTC)


def sst_only_payload(**updates):
    payload = {
        "latitude": 20.5,
        "longitude": 72.9,
        "at": NOW.isoformat(),
        "include_pfz": False,
        "include_sst": True,
        "include_chlorophyll": False,
        "include_waves": False,
        "include_wind": False,
        "include_currents": False,
        "include_sea_level": False,
    }
    payload.update(updates)
    return payload


def test_evidence_endpoint_is_typed_and_supports_decimal_coordinates():
    service = MarineEvidenceService(
        sst_service=FakeService("get_sst", sst_response()), now=lambda: NOW
    )
    with TestClient(app) as client:
        app.state.evidence_service = service
        response = client.post("/v1/decision-support/evidence", json=sst_only_payload())
        schema = client.get("/openapi.json").json()

    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    operation = schema["paths"]["/v1/decision-support/evidence"]["post"]
    assert "decision-support" in operation["tags"]
    request_schema = schema["components"]["schemas"]["EvidenceRequest"]
    assert request_schema["properties"]["latitude"]["type"] == "number"
    assert request_schema["properties"]["longitude"]["type"] == "number"
    assert operation["requestBody"]
    assert operation["responses"]["200"]


def test_evidence_endpoint_rejects_naive_time_non_finite_and_empty_source_set():
    with TestClient(app) as client:
        app.state.evidence_service = MarineEvidenceService(now=lambda: NOW)
        naive = client.post(
            "/v1/decision-support/evidence",
            json=sst_only_payload(at="2026-09-03T12:00:00"),
        )
        non_finite = client.post(
            "/v1/decision-support/evidence",
            json=sst_only_payload(latitude="NaN"),
        )
        empty = client.post(
            "/v1/decision-support/evidence",
            json=sst_only_payload(include_sst=False),
        )
    assert naive.status_code == 422
    assert non_finite.status_code == 422
    assert empty.status_code == 422


def test_disabled_evidence_aggregation_has_stable_error():
    with TestClient(app) as client:
        app.state.evidence_service = None
        response = client.post("/v1/decision-support/evidence", json=sst_only_payload())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "EVIDENCE_AGGREGATION_NOT_CONFIGURED"


def test_evidence_configuration_defaults_and_concurrency_bounds():
    settings = Settings(_env_file=None)
    assert settings.evidence_aggregation_enabled is True
    assert settings.evidence_max_concurrent_sources == 7
    with pytest.raises(ValidationError):
        Settings(_env_file=None, evidence_max_concurrent_sources=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, evidence_max_concurrent_sources=8)
