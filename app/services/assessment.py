from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

from app.domain.risk_rules import (
    ASSESSMENT_NOTICE,
    OFFICIAL_WARNING_NOTICE,
    evaluate_operational_limits,
)
from app.schemas.assessment import (
    AssessmentContext,
    AssessmentPolicy,
    AssessmentRequest,
    AssessmentRequestMetadata,
    CriticalEvidence,
    MarineAssessmentResponse,
    NearLimitPolicy,
)
from app.schemas.evidence import EvidenceRequest


CONTEXT_NOTICE = (
    "PFZ, SST, chlorophyll, and sea-level values are context only and do not "
    "change this operational-limit assessment."
)


class MarineAssessmentService:
    def __init__(self, *, evidence_service, now: Callable[[], datetime] | None = None):
        self.evidence_service = evidence_service
        self._now = now or (lambda: datetime.now(UTC))

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("assessment time must be timezone-aware")
        return value.astimezone(UTC)

    async def assess(self, request: AssessmentRequest) -> MarineAssessmentResponse:
        request_at = self._utc(request.at) if request.at is not None else self._utc(self._now())
        limits = request.operational_limits
        evidence = await self.evidence_service.aggregate(EvidenceRequest(
            latitude=request.latitude,
            longitude=request.longitude,
            at=request_at,
            include_pfz=request.include_pfz_context,
            include_sst=True,
            include_chlorophyll=True,
            include_waves=limits.maximum_significant_wave_height_m is not None,
            include_wind=limits.maximum_wind_speed_m_s is not None,
            include_currents=limits.maximum_surface_current_speed_m_s is not None,
            include_sea_level=True,
        ))
        evaluated_at = self._utc(self._now())
        evaluation = evaluate_operational_limits(
            evidence,
            limits,
            request.near_limit_percentage,
        )
        return MarineAssessmentResponse(
            request=AssessmentRequestMetadata(
                latitude=request.latitude,
                longitude=request.longitude,
                at=request_at,
                operational_limits=limits,
                near_limit_percentage=request.near_limit_percentage,
                include_pfz_context=request.include_pfz_context,
            ),
            generated_at=evaluated_at,
            outcome=evaluation.outcome,
            evidence_confidence=evaluation.evidence_confidence,
            policy=AssessmentPolicy(
                near_limit=NearLimitPolicy(
                    enabled=request.near_limit_percentage is not None,
                    percentage=request.near_limit_percentage,
                ),
                evaluated_at=evaluated_at,
            ),
            rules=list(evaluation.rules),
            reasons=list(evaluation.reasons),
            missing_critical_evidence=list(evaluation.missing_critical_evidence),
            critical_evidence=CriticalEvidence(
                waves=evidence.evidence.waves,
                wind=evidence.evidence.wind,
                currents=evidence.evidence.currents,
            ),
            context=AssessmentContext(
                pfz=evidence.evidence.pfz,
                sst=evidence.evidence.sst,
                chlorophyll=evidence.evidence.chlorophyll,
                sea_level=evidence.evidence.sea_level,
            ),
            source_failures=evidence.failures,
            notices=[OFFICIAL_WARNING_NOTICE, ASSESSMENT_NOTICE, CONTEXT_NOTICE],
        )
