from datetime import UTC, datetime

import pytest

from app.schemas.assessment import AssessmentRequest, OperationalLimits
from app.schemas.evidence import EvidenceItem
from app.schemas.marine import SeaLevelResponse
from app.services.assessment import MarineAssessmentService
from tests.test_risk_rules import NOW, critical_bundle
from tests.test_marine import chlorophyll_response
from tests.test_pfz_api import nearest_service


class FakeEvidenceService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def aggregate(self, request):
        self.calls.append(request)
        return self.result


@pytest.mark.asyncio
async def test_assessment_calls_e1_once_and_requests_only_configured_critical_rules():
    bundle = await critical_bundle()
    evidence = FakeEvidenceService(bundle)
    service = MarineAssessmentService(evidence_service=evidence, now=lambda: NOW)
    result = await service.assess(AssessmentRequest(
        latitude=20.5,
        longitude=72.9,
        at=NOW,
        operational_limits=OperationalLimits(maximum_wind_speed_m_s=10.0),
        include_pfz_context=False,
    ))
    assert len(evidence.calls) == 1
    requested = evidence.calls[0]
    assert requested.include_wind is True
    assert requested.include_waves is False
    assert requested.include_currents is False
    assert requested.include_pfz is False
    assert requested.include_sst and requested.include_chlorophyll and requested.include_sea_level
    assert result.policy.limit_source == "request"
    assert result.policy.policy_version == "1"


@pytest.mark.asyncio
async def test_context_only_evidence_cannot_change_operational_outcome():
    bundle = await critical_bundle(wave_height=1.0)
    baseline = await MarineAssessmentService(
        evidence_service=FakeEvidenceService(bundle), now=lambda: NOW
    ).assess(AssessmentRequest(
        latitude=20.5,
        longitude=72.9,
        at=NOW,
        operational_limits=OperationalLimits(maximum_significant_wave_height_m=2.0),
    ))
    pfz_time = datetime(2026, 8, 27, 12, tzinfo=UTC)
    pfz = await nearest_service(now=pfz_time).get_nearest(
        latitude=21.6417, longitude=69.6293, at=pfz_time
    )
    sea_level = SeaLevelResponse.model_validate({
        "dataset_id": "cmems_mod_glo_phy_anfc_merged-sl_PT1H-i",
        "dataset_version": "202411",
        "requested_location": {"latitude": 20.5, "longitude": 72.9},
        "sampled_location": {"latitude": 20.5, "longitude": 72.8333},
        "distance_km": 6.94,
        "bathymetry_m": 10.0,
        "provider_surface_level_coordinate_m": 0.494140625,
        "valid_time": NOW,
        "time_classification": "unknown",
        "astronomical_tide_elevation_m": 9.0,
        "total_modelled_sea_level_m": 99.0,
        "components": {
            "non_tidal_dynamic_sea_level_m": 90.0,
            "inverse_barometer_m": 0.0,
            "global_mean_steric_variation_m": 0.0,
            "global_mean_mass_variation_m": 0.0,
            "tide_loading_m": 5.0,
        },
        "reconstructed_total_sea_level_m": 99.0,
        "decomposition_residual_m": 0.0,
        "sampling_quality": "nearest_valid_water_cell",
        "model_evidence_quality": "normal",
        "spatial_representativeness": "degraded",
        "decomposition_evidence_quality": "normal",
        "cache_status": "refreshed",
        "retrieved_at": NOW,
    })
    altered_context = bundle.model_copy(update={
        "evidence": bundle.evidence.model_copy(update={
            "pfz": EvidenceItem(state="available", data=pfz),
            "chlorophyll": EvidenceItem(
                state="degraded", data=chlorophyll_response()
            ),
            "sea_level": EvidenceItem(state="degraded", data=sea_level),
        })
    })
    comparison = await MarineAssessmentService(
        evidence_service=FakeEvidenceService(altered_context), now=lambda: NOW
    ).assess(AssessmentRequest(
        latitude=20.5,
        longitude=72.9,
        at=NOW,
        operational_limits=OperationalLimits(maximum_significant_wave_height_m=2.0),
    ))
    assert baseline.outcome == comparison.outcome == "WITHIN_CONFIGURED_LIMITS"
    assert baseline.rules == comparison.rules
    assert comparison.context.pfz.data is pfz
    assert comparison.context.chlorophyll.data.quality.evidence_quality == "degraded"
    assert comparison.context.sea_level.data.total_modelled_sea_level_m == 99.0
    assert [rule.parameter for rule in comparison.rules] == ["significant_wave_height"]


@pytest.mark.asyncio
async def test_official_warning_gap_and_direction_provenance_are_explicit():
    bundle = await critical_bundle()
    result = await MarineAssessmentService(
        evidence_service=FakeEvidenceService(bundle), now=lambda: NOW
    ).assess(AssessmentRequest(
        latitude=18.025,
        longitude=70.525,
        at=NOW,
        operational_limits=OperationalLimits(
            maximum_wind_speed_m_s=20.0,
            maximum_surface_current_speed_m_s=2.0,
        ),
    ))
    assert result.official_warning_coverage == "not_integrated"
    assert any(reason.code == "OFFICIAL_WARNINGS_NOT_INTEGRATED" for reason in result.reasons)
    assert result.critical_evidence.wind.data.wind_direction_from.value is not None
    assert result.critical_evidence.currents.data.total_current.direction_toward_deg is not None
    assert all("safe" not in notice.lower() for notice in result.notices)


@pytest.mark.asyncio
async def test_omitted_request_time_is_captured_once_before_e1_collection():
    bundle = await critical_bundle()
    evidence = FakeEvidenceService(bundle)
    times = iter((NOW, NOW.replace(second=1)))
    service = MarineAssessmentService(evidence_service=evidence, now=lambda: next(times))
    result = await service.assess(AssessmentRequest(
        latitude=20.5,
        longitude=72.9,
        operational_limits=OperationalLimits(maximum_wind_speed_m_s=20.0),
    ))
    assert evidence.calls[0].at == NOW
    assert result.request.at == NOW
    assert result.generated_at == NOW.replace(second=1)


@pytest.mark.asyncio
async def test_sanitized_e1_failures_are_preserved_without_raw_exception_details():
    bundle = await critical_bundle(wave_height=None)
    bundle.failures = [{
        "source": "waves",
        "state": "unavailable",
        "code": "WAVE_SOURCE_UNAVAILABLE",
        "message": "Wave evidence is unavailable",
        "retryable": True,
    }]
    result = await MarineAssessmentService(
        evidence_service=FakeEvidenceService(bundle), now=lambda: NOW
    ).assess(AssessmentRequest(
        latitude=20.5,
        longitude=72.9,
        at=NOW,
        operational_limits=OperationalLimits(maximum_significant_wave_height_m=2.0),
    ))
    dumped = result.model_dump_json()
    assert "WAVE_SOURCE_UNAVAILABLE" in dumped
    assert "token=" not in dumped and "provider.example" not in dumped
