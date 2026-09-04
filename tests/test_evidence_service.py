import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.evidence import EvidenceRequest
from app.schemas.marine import RefreshAcceptedResponse
from app.services.evidence import MarineEvidenceService
from tests.test_marine import (
    chlorophyll_response,
    ecmwf_forecast_response,
    sst_response,
    wave_response,
    wind_response,
)
from tests.test_copernicus_currents import service as current_service
from tests.test_pfz_api import nearest_service


NOW = datetime(2026, 9, 3, 12, tzinfo=UTC)


def request_for(*sources: str, at: datetime | None = NOW) -> EvidenceRequest:
    included = {
        "include_pfz": False,
        "include_sst": False,
        "include_chlorophyll": False,
        "include_waves": False,
        "include_wind": False,
        "include_currents": False,
        "include_sea_level": False,
    }
    for source in sources:
        included[f"include_{source}"] = True
    return EvidenceRequest(latitude=20.5, longitude=72.9, at=at, **included)


class FakeService:
    def __init__(self, method: str, result=None, error: Exception | None = None):
        self.method = method
        self.result = result
        self.error = error
        self.calls: list[dict] = []

    def __getattr__(self, name: str):
        if name != self.method:
            raise AttributeError(name)

        async def call(**kwargs):
            self.calls.append(kwargs)
            if self.error:
                raise self.error
            return self.result

        return call


@pytest.mark.asyncio
async def test_complete_bundle_preserves_typed_provenance_and_degraded_evidence():
    sst = sst_response(requested_latitude=20.5, requested_longitude=72.9)
    chlorophyll = chlorophyll_response()
    service = MarineEvidenceService(
        sst_service=FakeService("get_sst", sst),
        chlorophyll_service=FakeService("get_chlorophyll", chlorophyll),
        now=lambda: NOW,
    )

    result = await service.aggregate(request_for("sst", "chlorophyll"))

    assert result.status == "complete"
    assert result.summary.available_sources == 1
    assert result.summary.degraded_sources == 1
    assert result.evidence.sst.data.source.dataset_id == sst.source.dataset_id
    assert result.evidence.chlorophyll.data.quality.flag_value == 2
    assert result.evidence.chlorophyll.data.quality.uncertainty_percent == 70.62
    assert result.evidence.chlorophyll.state == "degraded"


@pytest.mark.asyncio
async def test_partial_and_unavailable_status_and_sanitized_failures():
    private = RuntimeError("token=secret https://provider.example/private")
    partial = MarineEvidenceService(
        sst_service=FakeService("get_sst", sst_response()),
        wave_service=FakeService("get_waves", error=private),
        now=lambda: NOW,
    )
    partial_result = await partial.aggregate(request_for("sst", "waves"))
    assert partial_result.status == "partial"
    assert partial_result.evidence.sst.state == "available"
    assert partial_result.evidence.waves.state == "unavailable"
    assert partial_result.failures[0].code == "WAVE_SOURCE_UNAVAILABLE"
    assert "secret" not in partial_result.failures[0].message
    assert "provider.example" not in partial_result.failures[0].message

    unavailable = MarineEvidenceService(now=lambda: NOW)
    unavailable_result = await unavailable.aggregate(request_for("sst", "waves"))
    assert unavailable_result.status == "unavailable"
    assert unavailable_result.summary.unavailable_sources == 2


@pytest.mark.asyncio
async def test_pending_snapshot_is_distinct_from_failure():
    pending = RefreshAcceptedResponse(
        source="sst", job_id="safe-job", tile={"id": "sst:9:125"}
    )
    manager = FakeService("get_sst", pending)
    service = MarineEvidenceService(sst_snapshot_manager=manager, now=lambda: NOW)

    result = await service.aggregate(request_for("sst"))

    assert result.status == "unavailable"
    assert result.evidence.sst.state == "pending"
    assert result.summary.pending_sources == 1
    assert result.failures[0].refresh_job_id == "safe-job"


@pytest.mark.asyncio
async def test_requested_sources_execute_concurrently_and_failure_does_not_cancel_peer():
    entered = 0
    both_entered = asyncio.Event()

    class CoordinatedService:
        def __init__(self, method, result=None, error=None):
            self.method = method
            self.result = result
            self.error = error

        def __getattr__(self, name):
            if name != self.method:
                raise AttributeError(name)

            async def call(**kwargs):
                nonlocal entered
                entered += 1
                if entered == 2:
                    both_entered.set()
                await asyncio.wait_for(both_entered.wait(), timeout=1)
                if self.error:
                    raise self.error
                return self.result

            return call

    service = MarineEvidenceService(
        sst_service=CoordinatedService("get_sst", sst_response()),
        wave_service=CoordinatedService("get_waves", error=RuntimeError("down")),
        max_concurrent_sources=2,
        now=lambda: NOW,
    )
    result = await service.aggregate(request_for("sst", "waves"))
    assert entered == 2
    assert result.status == "partial"
    assert result.evidence.sst.data is not None


@pytest.mark.asyncio
async def test_unrequested_sources_are_not_invoked_and_omitted_time_is_captured_once():
    clock_calls = 0

    def clock():
        nonlocal clock_calls
        clock_calls += 1
        return NOW + timedelta(seconds=clock_calls - 1)

    sst = FakeService("get_sst", sst_response())
    waves = FakeService("get_waves", wave_response())
    wind = FakeService("get_wind", wind_response())
    service = MarineEvidenceService(
        sst_service=sst,
        wave_service=waves,
        recent_wind_service=wind,
        now=clock,
    )
    result = await service.aggregate(request_for("sst", "waves", at=None))
    assert not wind.calls
    assert sst.calls[0]["at"] == waves.calls[0]["at"] == NOW
    assert result.request.at == NOW
    assert clock_calls == 2  # one request instant and one generated-at instant


@pytest.mark.asyncio
async def test_wind_provider_selection_is_deterministic_without_fallback():
    recent = FakeService("get_wind", wind_response())
    forecast = FakeService("get_forecast", ecmwf_forecast_response())
    service = MarineEvidenceService(
        recent_wind_service=recent,
        forecast_wind_service=forecast,
        now=lambda: NOW,
    )
    present = await service.aggregate(request_for("wind", at=NOW))
    assert present.evidence.wind.data.source.name == "Copernicus Marine"
    assert len(recent.calls) == 1 and not forecast.calls

    future = await service.aggregate(request_for("wind", at=NOW + timedelta(hours=1)))
    assert future.evidence.wind.data.source.source_mirror == "ecmwf"
    assert len(forecast.calls) == 1

    failing_forecast = FakeService("get_forecast", error=RuntimeError("offline"))
    service.forecast_wind_service = failing_forecast
    failed = await service.aggregate(request_for("wind", at=NOW + timedelta(hours=2)))
    assert failed.evidence.wind.state == "unavailable"
    assert len(recent.calls) == 1


@pytest.mark.asyncio
async def test_wave_direction_from_semantics_survive_aggregation():
    wave = wave_response()
    service = MarineEvidenceService(
        wave_service=FakeService("get_waves", wave), now=lambda: NOW
    )
    result = await service.aggregate(request_for("waves"))
    assert result.evidence.waves.data.mean_wave_direction_from.value == 247.85
    dumped = result.model_dump(mode="json")
    assert "mean_wave_direction_from" in dumped["evidence"]["waves"]["data"]
    assert "mean_wave_direction_toward" not in dumped["evidence"]["waves"]["data"]


@pytest.mark.asyncio
async def test_pfz_validity_and_current_direction_toward_survive_aggregation():
    pfz_time = datetime(2026, 8, 27, 12, tzinfo=UTC)
    pfz = nearest_service(now=pfz_time)
    current = current_service(now=lambda: NOW)
    pfz_result = await MarineEvidenceService(
        pfz_service=pfz,
        now=lambda: pfz_time,
    ).aggregate(request_for("pfz", at=pfz_time))
    current_result = await MarineEvidenceService(
        current_service=current, now=lambda: NOW
    ).aggregate(EvidenceRequest(
        latitude=18.025,
        longitude=70.525,
        at=datetime(2026, 8, 31, 22, tzinfo=UTC),
        include_pfz=False,
        include_sst=False,
        include_chlorophyll=False,
        include_waves=False,
        include_wind=False,
        include_currents=True,
        include_sea_level=False,
    ))

    assert pfz_result.evidence.pfz.data.valid_until.tzinfo is not None
    assert pfz_result.evidence.pfz.data.forecast_date.isoformat() == "2026-08-27"
    current_data = current_result.evidence.currents.data
    assert current_data.source_classification.observation is False
    dumped = current_data.model_dump(mode="json")
    assert "direction_toward_deg" in dumped["total_current"]
    assert "direction_from_deg" not in dumped["total_current"]
