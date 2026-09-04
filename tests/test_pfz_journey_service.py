import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.clients.incois_pfz import PFZSourceUnavailableError
from app.schemas.assessment import OperationalLimits
from app.schemas.evidence import EvidenceFailure, EvidenceItem
from app.schemas.pfz_journey import PFZJourneyRequest
from app.services.assessment import MarineAssessmentService
from app.services.pfz import NoValidPFZError
from app.services.pfz_journey import PFZJourneyService, PFZRefreshPendingError
from tests.test_pfz_api import nearest_service
from tests.test_risk_rules import critical_bundle


AT = datetime(2026, 8, 27, 12, tzinfo=UTC)
ORIGIN = (21.6417, 69.6293)


class FakePFZService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def get_nearest(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class LocationEvidenceService:
    def __init__(self, origin, destination, *, origin_error=None, destination_error=None):
        self.origin = origin
        self.destination = destination
        self.origin_error = origin_error
        self.destination_error = destination_error
        self.calls = []

    async def aggregate(self, request):
        self.calls.append(request)
        is_origin = (
            request.latitude == ORIGIN[0] and request.longitude == ORIGIN[1]
        )
        error = self.origin_error if is_origin else self.destination_error
        if error:
            raise error
        bundle = self.origin if is_origin else self.destination
        return bundle.model_copy(update={
            "request": bundle.request.model_copy(update={
                "latitude": request.latitude,
                "longitude": request.longitude,
                "at": request.at,
            })
        })


async def pfz_response(at=AT):
    return await nearest_service(now=at).get_nearest(
        latitude=ORIGIN[0], longitude=ORIGIN[1], at=at
    )


def journey_request(**updates):
    values = {
        "origin": {"latitude": ORIGIN[0], "longitude": ORIGIN[1]},
        "at": AT,
        "operational_limits": {"maximum_significant_wave_height_m": 2.0},
        "include_origin_evidence": True,
        "include_destination_evidence": True,
        "include_geojson": True,
    }
    values.update(updates)
    return PFZJourneyRequest.model_validate(values)


async def journey_service(
    *,
    origin_wave=1.0,
    destination_wave=1.0,
    origin_pending=False,
    destination_pending=False,
    pfz_error=None,
    origin_error=None,
    destination_error=None,
):
    origin = await critical_bundle(
        wave_height=origin_wave,
        pending={"waves"} if origin_pending else set(),
    )
    destination = await critical_bundle(
        wave_height=destination_wave,
        pending={"waves"} if destination_pending else set(),
    )
    evidence = LocationEvidenceService(
        origin,
        destination,
        origin_error=origin_error,
        destination_error=destination_error,
    )
    pfz = FakePFZService(
        result=None if pfz_error else await pfz_response(), error=pfz_error
    )
    assessment = MarineAssessmentService(evidence_service=evidence, now=lambda: AT)
    return (
        PFZJourneyService(
            pfz_service=pfz,
            evidence_service=evidence,
            assessment_service=assessment,
            now=lambda: AT,
        ),
        evidence,
        pfz,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("origin", "destination", "near", "expected"),
    [
        (1.0, 1.0, None, "PFZ_AVAILABLE_WITHIN_CONFIGURED_LIMITS"),
        (3.0, 1.0, None, "PFZ_AVAILABLE_LIMIT_EXCEEDED"),
        (1.0, 3.0, None, "PFZ_AVAILABLE_LIMIT_EXCEEDED"),
        (3.0, 4.0, None, "PFZ_AVAILABLE_LIMIT_EXCEEDED"),
        (1.9, 1.0, 10.0, "PFZ_AVAILABLE_CAUTION"),
        (1.0, 1.9, 10.0, "PFZ_AVAILABLE_CAUTION"),
        (None, 1.0, None, "PFZ_AVAILABLE_INSUFFICIENT_EVIDENCE"),
        (1.0, None, None, "PFZ_AVAILABLE_INSUFFICIENT_EVIDENCE"),
    ],
)
async def test_journey_status_precedence(origin, destination, near, expected):
    service, _, _ = await journey_service(
        origin_wave=origin, destination_wave=destination
    )
    result = await service.run(journey_request(near_limit_percentage=near))
    assert result.journey_status == expected


@pytest.mark.asyncio
async def test_origin_and_destination_are_assessed_separately_without_averaging():
    service, evidence, _ = await journey_service(
        origin_wave=3.0, destination_wave=0.5
    )
    result = await service.run(journey_request())
    assert len(evidence.calls) == 2
    assert result.origin.evidence.request.latitude == ORIGIN[0]
    assert result.destination.evidence.request.latitude == result.pfz.nearest_pfz.latitude
    assert result.origin.assessment.rules[0].observed_value == 3.0
    assert result.destination.assessment.rules[0].observed_value == 0.5
    assert result.origin.assessment.policy == result.destination.assessment.policy


@pytest.mark.asyncio
async def test_pending_required_and_non_required_evidence_behave_differently():
    required, _, _ = await journey_service(origin_pending=True)
    required_result = await required.run(journey_request())
    assert required_result.journey_status == "PFZ_AVAILABLE_INSUFFICIENT_EVIDENCE"

    normal, _, _ = await journey_service()
    normal.evidence_service.origin = normal.evidence_service.origin.model_copy(update={
        "evidence": normal.evidence_service.origin.evidence.model_copy(update={
            "chlorophyll": EvidenceItem(state="pending")
        })
    })
    non_required_result = await normal.run(journey_request())
    assert non_required_result.journey_status == "PFZ_AVAILABLE_WITHIN_CONFIGURED_LIMITS"
    assert non_required_result.origin.evidence.evidence.chlorophyll.state == "pending"


@pytest.mark.asyncio
async def test_partial_e1_failure_is_preserved_in_location_assessment():
    service, evidence, _ = await journey_service()
    evidence.origin.failures.append(EvidenceFailure(
        source="chlorophyll",
        state="unavailable",
        code="CHLOROPHYLL_SOURCE_UNAVAILABLE",
        message="Chlorophyll evidence is unavailable",
        retryable=True,
    ))
    result = await service.run(journey_request())
    assert result.origin.assessment.source_failures[0].code == "CHLOROPHYLL_SOURCE_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status", "reason"),
    [
        (NoValidPFZError("expired"), "NO_VALID_PFZ", "NO_VALID_PFZ"),
        (
            PFZSourceUnavailableError("private provider URL and token"),
            "PFZ_SOURCE_UNAVAILABLE",
            "PFZ_DATA_UNAVAILABLE",
        ),
    ],
)
async def test_expected_pfz_failures_are_typed_and_sanitized(error, status, reason):
    service, _, _ = await journey_service(pfz_error=error)
    result = await service.run(journey_request())
    assert result.journey_status == status
    assert result.reason_codes[0] == reason
    assert result.destination is None and result.pfz is None
    dumped = result.model_dump_json()
    assert "private" not in dumped and "token" not in dumped


@pytest.mark.asyncio
async def test_pfz_pending_is_typed_and_does_not_claim_a_completed_refresh():
    service, _, _ = await journey_service(
        pfz_error=PFZRefreshPendingError(job_id="safe-job", retry_after_seconds=7)
    )
    result = await service.run(journey_request())
    assert result.journey_status == "PFZ_REFRESH_PENDING"
    assert result.pfz_resolution.failure.refresh_job_id == "safe-job"
    assert result.pfz_resolution.failure.retry_after_seconds == 7


@pytest.mark.asyncio
async def test_validity_exact_end_is_accepted_and_expired_time_is_rejected():
    initial = await pfz_response()
    real_pfz = nearest_service(now=initial.valid_until)
    origin = await critical_bundle(wave_height=1.0)
    evidence = LocationEvidenceService(origin, origin)
    service = PFZJourneyService(
        pfz_service=real_pfz,
        evidence_service=evidence,
        assessment_service=MarineAssessmentService(
            evidence_service=evidence, now=lambda: initial.valid_until
        ),
        now=lambda: initial.valid_until,
    )
    boundary = await service.run(journey_request(at=initial.valid_until))
    assert boundary.pfz_resolution.status == "PFZ_FOUND"

    expired = await service.run(
        journey_request(at=initial.valid_until + timedelta(microseconds=1))
    )
    assert expired.journey_status == "NO_VALID_PFZ"


@pytest.mark.asyncio
async def test_distance_bearing_and_geojson_use_official_pfz_coordinates():
    service, _, _ = await journey_service()
    result = await service.run(journey_request())
    selected = result.pfz.nearest_pfz
    assert result.distance.kilometres == selected.distance_km
    assert result.distance.bearing_degrees == selected.bearing_deg
    assert result.distance.direction == selected.direction
    origin, destination, line = result.geojson.features
    assert origin.geometry.coordinates == (ORIGIN[1], ORIGIN[0])
    assert destination.geometry.coordinates == (selected.longitude, selected.latitude)
    assert line.geometry.coordinates == (
        (ORIGIN[1], ORIGIN[0]),
        (selected.longitude, selected.latitude),
    )
    assert line.properties.label == "reference_line_not_evaluated_route"
    assert line.properties.navigable_route is False
    assert line.properties.route_evaluated is False
    assert line.properties.geofences_evaluated is False


@pytest.mark.asyncio
async def test_reason_order_and_limitations_are_stable():
    service, _, _ = await journey_service(origin_wave=3.0, destination_wave=None)
    result = await service.run(journey_request())
    assert result.reason_codes == [
        "VALID_PFZ_FOUND",
        "ORIGIN_LIMIT_EXCEEDED",
        "DESTINATION_EVIDENCE_INSUFFICIENT",
        "ROUTE_NOT_EVALUATED",
        "GEOFENCES_NOT_EVALUATED",
        "OFFICIAL_WARNINGS_NOT_INTEGRATED",
        "PFZ_DOES_NOT_GUARANTEE_FISH_PRESENCE",
    ]
    assert result.limitations.route_evaluated is False
    assert result.limitations.geofences_evaluated is False
    assert result.limitations.official_warning_coverage == "not_integrated"


@pytest.mark.asyncio
async def test_origin_evidence_collection_overlaps_pfz_lookup():
    entered = asyncio.Event()
    origin = await critical_bundle(wave_height=1.0)
    resolved = await pfz_response()

    class OverlapEvidence(LocationEvidenceService):
        async def aggregate(self, request):
            if request.latitude == ORIGIN[0]:
                entered.set()
            return await super().aggregate(request)

    class OverlapPFZ(FakePFZService):
        async def get_nearest(self, **kwargs):
            await asyncio.wait_for(entered.wait(), timeout=1)
            return await super().get_nearest(**kwargs)

    evidence = OverlapEvidence(origin, origin)
    pfz = OverlapPFZ(result=resolved)
    service = PFZJourneyService(
        pfz_service=pfz,
        evidence_service=evidence,
        assessment_service=MarineAssessmentService(
            evidence_service=evidence, now=lambda: AT
        ),
        now=lambda: AT,
    )
    result = await service.run(journey_request())
    assert result.pfz_resolution.status == "PFZ_FOUND"


@pytest.mark.asyncio
async def test_same_origin_and_destination_reuse_one_e1_bundle():
    service, evidence, pfz = await journey_service()
    response = pfz.result
    response = response.model_copy(update={
        "nearest_pfz": response.nearest_pfz.model_copy(update={
            "latitude": ORIGIN[0],
            "longitude": ORIGIN[1],
            "distance_km": 0.0,
            "bearing_deg": 0.0,
            "direction": "N",
        })
    })
    pfz.result = response
    result = await service.run(journey_request())
    assert len(evidence.calls) == 1
    assert result.origin.assessment.rules == result.destination.assessment.rules


@pytest.mark.asyncio
async def test_one_location_collection_failure_does_not_erase_the_other():
    service, _, _ = await journey_service(
        origin_error=RuntimeError("credential path C:/private/token"),
    )
    result = await service.run(journey_request())
    assert result.origin.state == "unavailable"
    assert result.destination.state == "available"
    assert result.journey_status == "PFZ_AVAILABLE_INSUFFICIENT_EVIDENCE"
    assert "private" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_omitted_time_is_captured_once_and_direction_semantics_survive():
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        return AT

    bundle = await critical_bundle(wave_height=1.0, wind_speed=8.0, current_speed=0.5)
    evidence = LocationEvidenceService(bundle, bundle)
    pfz = FakePFZService(result=await pfz_response())
    assessment = MarineAssessmentService(evidence_service=evidence, now=lambda: AT)
    service = PFZJourneyService(
        pfz_service=pfz,
        evidence_service=evidence,
        assessment_service=assessment,
        now=clock,
    )
    result = await service.run(journey_request(
        at=None,
        operational_limits={
            "maximum_significant_wave_height_m": 2.0,
            "maximum_wind_speed_m_s": 10.0,
            "maximum_surface_current_speed_m_s": 1.0,
        },
    ))
    assert calls == 1
    assert {request.at for request in evidence.calls} == {AT}
    assert pfz.calls[0]["at"] == AT
    assert result.request.at == AT
    assert result.origin.assessment.critical_evidence.wind.data.wind_direction_from.compass == "W"
    assert result.origin.assessment.critical_evidence.currents.data.total_current.direction_toward_compass == "E"


@pytest.mark.asyncio
async def test_optional_evidence_and_geojson_can_be_omitted_without_skipping_assessment():
    service, evidence, _ = await journey_service()
    result = await service.run(journey_request(
        include_origin_evidence=False,
        include_destination_evidence=False,
        include_geojson=False,
    ))
    assert len(evidence.calls) == 2
    assert result.origin.evidence is None
    assert result.destination.evidence is None
    assert result.origin.assessment is not None
    assert result.destination.assessment is not None
    assert result.geojson is None
