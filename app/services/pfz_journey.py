from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Callable

from app.clients.incois_pfz import PFZSourceUnavailableError
from app.domain.risk_rules import OFFICIAL_WARNING_NOTICE, evaluate_corridor_imd_hazards
from app.parsers.pfz_html import NoSectorsDiscoveredError, PFZParseError
from app.schemas.assessment import AssessmentOutcome, AssessmentRequest
from app.schemas.evidence import EvidenceRequest, MarineEvidenceResponse
from app.schemas.pfz import NearestPFZResponse
from app.schemas.pfz_journey import (
    DestinationFeature,
    DestinationFeatureProperties,
    JourneyDistance,
    JourneyFeatureCollection,
    JourneyLineGeometry,
    JourneyLimitations,
    JourneyLocation,
    JourneyLocationFailure,
    JourneyLocationResult,
    JourneyLocationState,
    JourneyPointGeometry,
    JourneyReason,
    JourneyReasonCode,
    JourneyStatus,
    OriginFeature,
    PFZJourneyRequest,
    PFZJourneyRequestMetadata,
    PFZJourneyResponse,
    PFZResolution,
    PFZResolutionFailure,
    PFZResolutionStatus,
    ReferenceLineFeature,
)
from app.services.pfz import NoValidPFZError


ROUTE_NOTICE = (
    "The displayed straight line is a geographic reference only; route-level "
    "hazards, navigability, and restricted zones have not been evaluated."
)
PFZ_NOTICE = (
    "A valid PFZ advisory identifies a potential fishing zone; it does not "
    "guarantee fish presence or acceptable operational conditions."
)


class PFZRefreshPendingError(RuntimeError):
    """Future-compatible service signal for a real in-process PFZ refresh."""

    def __init__(
        self,
        *,
        job_id: str,
        retry_after_seconds: int = 5,
    ) -> None:
        super().__init__("PFZ refresh is in progress")
        self.job_id = job_id
        self.retry_after_seconds = retry_after_seconds


class PFZJourneyService:
    def __init__(
        self,
        *,
        pfz_service,
        evidence_service,
        assessment_service,
        imd_service=None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.pfz_service = pfz_service
        self.evidence_service = evidence_service
        self.assessment_service = assessment_service
        self.imd_service = imd_service
        self._now = now or (lambda: datetime.now(UTC))

    async def _fetch_hazards(self):
        if self.imd_service is None:
            return None, None
        try:
            hazard_coll = await self.imd_service.build_hazard_feature_collection()
            bulletin_resp, _ = await self.imd_service.get_coastal_bulletins()
            return hazard_coll, bulletin_resp
        except Exception:
            return None, None

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("journey time must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _evidence_request(
        *,
        location: JourneyLocation,
        at: datetime,
        request: PFZJourneyRequest,
    ) -> EvidenceRequest:
        limits = request.operational_limits
        return EvidenceRequest(
            latitude=location.latitude,
            longitude=location.longitude,
            at=at,
            include_pfz=False,
            include_sst=True,
            include_chlorophyll=True,
            include_waves=limits.maximum_significant_wave_height_m is not None,
            include_wind=limits.maximum_wind_speed_m_s is not None,
            include_currents=limits.maximum_surface_current_speed_m_s is not None,
            include_sea_level=True,
        )

    async def _collect(
        self,
        *,
        location: JourneyLocation,
        at: datetime,
        request: PFZJourneyRequest,
    ) -> MarineEvidenceResponse | Exception:
        try:
            return await self.evidence_service.aggregate(
                self._evidence_request(location=location, at=at, request=request)
            )
        except Exception as exc:
            return exc

    def _location_result(
        self,
        *,
        location: JourneyLocation,
        collected: MarineEvidenceResponse | Exception,
        request: PFZJourneyRequest,
        request_at: datetime,
        evaluated_at: datetime,
        expose_evidence: bool,
    ) -> JourneyLocationResult:
        if isinstance(collected, Exception):
            return JourneyLocationResult(
                location=location,
                state=JourneyLocationState.UNAVAILABLE,
                failure=JourneyLocationFailure(),
            )
        assessment = self.assessment_service.assess_evidence(
            request=AssessmentRequest(
                latitude=location.latitude,
                longitude=location.longitude,
                at=request_at,
                operational_limits=request.operational_limits,
                near_limit_percentage=request.near_limit_percentage,
                include_pfz_context=False,
            ),
            evidence=collected,
            request_at=request_at,
            evaluated_at=evaluated_at,
        )
        return JourneyLocationResult(
            location=location,
            state=JourneyLocationState.AVAILABLE,
            evidence=collected if expose_evidence else None,
            assessment=assessment,
        )

    @staticmethod
    def _reason(code: JourneyReasonCode) -> JourneyReason:
        messages = {
            JourneyReasonCode.VALID_PFZ_FOUND: "A valid PFZ advisory was found.",
            JourneyReasonCode.NO_VALID_PFZ: "No PFZ advisory is valid at the requested time.",
            JourneyReasonCode.PFZ_DATA_PENDING: "PFZ data is currently being refreshed.",
            JourneyReasonCode.PFZ_DATA_UNAVAILABLE: "PFZ advisory data is unavailable.",
            JourneyReasonCode.ORIGIN_LIMIT_EXCEEDED: "One or more configured limits were exceeded at the origin.",
            JourneyReasonCode.DESTINATION_LIMIT_EXCEEDED: "One or more configured limits were exceeded at the PFZ location.",
            JourneyReasonCode.ORIGIN_EVIDENCE_INSUFFICIENT: "Critical operational evidence is incomplete at the origin.",
            JourneyReasonCode.DESTINATION_EVIDENCE_INSUFFICIENT: "Critical operational evidence is incomplete at the PFZ location.",
            JourneyReasonCode.ORIGIN_CAUTION: "At least one origin condition is within the configured near-limit band.",
            JourneyReasonCode.DESTINATION_CAUTION: "At least one PFZ-location condition is within the configured near-limit band.",
            JourneyReasonCode.WITHIN_CONFIGURED_LIMITS_AT_CHECKED_LOCATIONS: "Available conditions at both checked locations were within the supplied operational limits.",
            JourneyReasonCode.ROUTE_NOT_EVALUATED: "The reference line is not an evaluated or navigable route.",
            JourneyReasonCode.GEOFENCES_NOT_EVALUATED: "Restricted zones and route geofences have not been evaluated.",
            JourneyReasonCode.OFFICIAL_WARNINGS_NOT_INTEGRATED: OFFICIAL_WARNING_NOTICE,
            JourneyReasonCode.OFFICIAL_IMD_PORT_WARNING: "Port Danger Signal hoisted by IMD along or near the navigation corridor.",
            JourneyReasonCode.OFFICIAL_IMD_FISHERMEN_WARNING: "Official IMD bulletin: Fishermen advised NOT to venture into deep sea.",
            JourneyReasonCode.OFFICIAL_IMD_CYCLONE_WARNING: "Active IMD Cyclone Cone or Warning in sea corridor. Operation not recommended.",
            JourneyReasonCode.ROUTE_HAZARD_INTERSECTION: "Navigation corridor intersects an active official maritime hazard zone.",
            JourneyReasonCode.PFZ_DOES_NOT_GUARANTEE_FISH_PRESENCE: "A valid PFZ advisory does not guarantee fish presence.",
        }
        return JourneyReason(code=code, message=messages[code])

    @classmethod
    def _limitation_reasons(cls, imd_active: bool = False) -> list[JourneyReason]:
        reasons = [
            cls._reason(JourneyReasonCode.ROUTE_NOT_EVALUATED),
            cls._reason(JourneyReasonCode.GEOFENCES_NOT_EVALUATED),
        ]
        if not imd_active:
            reasons.append(cls._reason(JourneyReasonCode.OFFICIAL_WARNINGS_NOT_INTEGRATED))
        return reasons

    @staticmethod
    def _status_and_assessment_reasons(
        origin: JourneyLocationResult,
        destination: JourneyLocationResult,
    ) -> tuple[JourneyStatus, list[JourneyReasonCode]]:
        origin_outcome = origin.assessment.outcome if origin.assessment else None
        destination_outcome = (
            destination.assessment.outcome if destination.assessment else None
        )
        outcomes = (origin_outcome, destination_outcome)
        codes: list[JourneyReasonCode] = []
        if origin_outcome == AssessmentOutcome.LIMIT_EXCEEDED:
            codes.append(JourneyReasonCode.ORIGIN_LIMIT_EXCEEDED)
        if destination_outcome == AssessmentOutcome.LIMIT_EXCEEDED:
            codes.append(JourneyReasonCode.DESTINATION_LIMIT_EXCEEDED)
        if origin_outcome in {None, AssessmentOutcome.INSUFFICIENT_EVIDENCE}:
            codes.append(JourneyReasonCode.ORIGIN_EVIDENCE_INSUFFICIENT)
        if destination_outcome in {None, AssessmentOutcome.INSUFFICIENT_EVIDENCE}:
            codes.append(JourneyReasonCode.DESTINATION_EVIDENCE_INSUFFICIENT)
        if origin_outcome == AssessmentOutcome.CAUTION:
            codes.append(JourneyReasonCode.ORIGIN_CAUTION)
        if destination_outcome == AssessmentOutcome.CAUTION:
            codes.append(JourneyReasonCode.DESTINATION_CAUTION)

        if AssessmentOutcome.POLICY_NOT_CONFIGURED in outcomes:
            return JourneyStatus.POLICY_NOT_CONFIGURED, codes
        if AssessmentOutcome.LIMIT_EXCEEDED in outcomes:
            return JourneyStatus.PFZ_AVAILABLE_LIMIT_EXCEEDED, codes
        if None in outcomes or AssessmentOutcome.INSUFFICIENT_EVIDENCE in outcomes:
            return JourneyStatus.PFZ_AVAILABLE_INSUFFICIENT_EVIDENCE, codes
        if AssessmentOutcome.CAUTION in outcomes:
            return JourneyStatus.PFZ_AVAILABLE_CAUTION, codes
        codes.append(JourneyReasonCode.WITHIN_CONFIGURED_LIMITS_AT_CHECKED_LOCATIONS)
        return JourneyStatus.PFZ_AVAILABLE_WITHIN_CONFIGURED_LIMITS, codes

    @staticmethod
    def _geojson(
        origin: JourneyLocation,
        pfz: NearestPFZResponse,
    ) -> JourneyFeatureCollection:
        destination = pfz.nearest_pfz
        origin_coordinates = (origin.longitude, origin.latitude)
        destination_coordinates = (destination.longitude, destination.latitude)
        return JourneyFeatureCollection(features=(
            OriginFeature(
                geometry=JourneyPointGeometry(coordinates=origin_coordinates)
            ),
            DestinationFeature(
                geometry=JourneyPointGeometry(coordinates=destination_coordinates),
                properties=DestinationFeatureProperties(
                    sector_code=destination.sector_code,
                    region_name=destination.region_name,
                    landing_centre=destination.landing_centre,
                ),
            ),
            ReferenceLineFeature(
                geometry=JourneyLineGeometry(
                    coordinates=(origin_coordinates, destination_coordinates)
                )
            ),
        ))

    def _base_response(
        self,
        *,
        request: PFZJourneyRequest,
        request_at: datetime,
        generated_at: datetime,
        journey_status: JourneyStatus,
        pfz_resolution: PFZResolution,
        origin: JourneyLocationResult,
        pfz: NearestPFZResponse | None = None,
        destination: JourneyLocationResult | None = None,
        reasons: list[JourneyReason],
        imd_active: bool = False,
    ) -> PFZJourneyResponse:
        distance = None
        geojson = None
        if pfz is not None:
            selected = pfz.nearest_pfz
            distance = JourneyDistance(
                kilometres=selected.distance_km,
                bearing_degrees=selected.bearing_deg,
                direction=selected.direction,
            )
            if request.include_geojson:
                geojson = self._geojson(request.origin, pfz)
        notices = (
            ["Official IMD warnings active and verified for sea corridor.", ROUTE_NOTICE, PFZ_NOTICE]
            if imd_active
            else [OFFICIAL_WARNING_NOTICE, ROUTE_NOTICE, PFZ_NOTICE]
        )
        return PFZJourneyResponse(
            request=PFZJourneyRequestMetadata(
                origin=request.origin,
                at=request_at,
                operational_limits=request.operational_limits,
                near_limit_percentage=request.near_limit_percentage,
                include_origin_evidence=request.include_origin_evidence,
                include_destination_evidence=request.include_destination_evidence,
                include_geojson=request.include_geojson,
            ),
            generated_at=generated_at,
            journey_status=journey_status,
            pfz_resolution=pfz_resolution,
            pfz=pfz,
            origin=origin,
            destination=destination,
            distance=distance,
            reasons=reasons,
            reason_codes=[reason.code for reason in reasons],
            notices=notices,
            limitations=JourneyLimitations(
                route_evaluated=True if imd_active else False,
                geofences_evaluated=False,
                official_warning_coverage="imd_active" if imd_active else "not_integrated",
            ),
            geojson=geojson,
        )

    async def run(self, request: PFZJourneyRequest) -> PFZJourneyResponse:
        workflow_now = self._utc(self._now())
        request_at = self._utc(request.at) if request.at is not None else workflow_now
        origin_task = asyncio.create_task(self._collect(
            location=request.origin, at=request_at, request=request
        ))
        pfz_task = asyncio.create_task(self.pfz_service.get_nearest(
            latitude=request.origin.latitude,
            longitude=request.origin.longitude,
            at=request_at,
        ))
        hazard_task = asyncio.create_task(self._fetch_hazards())

        pfz: NearestPFZResponse | None = None
        resolution: PFZResolution
        failure_reason: JourneyReason
        try:
            pfz = await pfz_task
        except PFZRefreshPendingError as exc:
            resolution = PFZResolution(
                status=PFZResolutionStatus.PFZ_REFRESH_PENDING,
                failure=PFZResolutionFailure(
                    code="PFZ_DATA_PENDING",
                    message="PFZ data is currently being refreshed",
                    retryable=True,
                    retry_after_seconds=exc.retry_after_seconds,
                    refresh_job_id=exc.job_id,
                ),
            )
            failure_reason = self._reason(JourneyReasonCode.PFZ_DATA_PENDING)
        except NoValidPFZError:
            resolution = PFZResolution(
                status=PFZResolutionStatus.NO_VALID_PFZ,
                failure=PFZResolutionFailure(
                    code="NO_VALID_PFZ",
                    message="No PFZ advisory is valid at the requested time",
                    retryable=False,
                ),
            )
            failure_reason = self._reason(JourneyReasonCode.NO_VALID_PFZ)
        except (PFZSourceUnavailableError, NoSectorsDiscoveredError, PFZParseError):
            resolution = PFZResolution(
                status=PFZResolutionStatus.PFZ_SOURCE_UNAVAILABLE,
                failure=PFZResolutionFailure(
                    code="PFZ_DATA_UNAVAILABLE",
                    message="PFZ advisory data is unavailable",
                    retryable=True,
                ),
            )
            failure_reason = self._reason(JourneyReasonCode.PFZ_DATA_UNAVAILABLE)
        except BaseException:
            if not origin_task.done():
                origin_task.cancel()
            if not hazard_task.done():
                hazard_task.cancel()
            await asyncio.gather(origin_task, hazard_task, return_exceptions=True)
            raise
        else:
            resolution = PFZResolution(status=PFZResolutionStatus.PFZ_FOUND)

        destination_task = None
        destination_location = None
        if pfz is not None:
            destination_location = JourneyLocation(
                latitude=pfz.nearest_pfz.latitude,
                longitude=pfz.nearest_pfz.longitude,
            )
            if destination_location == request.origin:
                destination_task = origin_task
            else:
                destination_task = asyncio.create_task(self._collect(
                    location=destination_location,
                    at=request_at,
                    request=request,
                ))

        origin_collected = await origin_task
        generated_at = workflow_now
        origin_result = self._location_result(
            location=request.origin,
            collected=origin_collected,
            request=request,
            request_at=request_at,
            evaluated_at=generated_at,
            expose_evidence=request.include_origin_evidence,
        )

        if pfz is None:
            if not hazard_task.done():
                hazard_task.cancel()
            await asyncio.gather(hazard_task, return_exceptions=True)
            journey_status = {
                PFZResolutionStatus.PFZ_REFRESH_PENDING: JourneyStatus.PFZ_REFRESH_PENDING,
                PFZResolutionStatus.NO_VALID_PFZ: JourneyStatus.NO_VALID_PFZ,
                PFZResolutionStatus.PFZ_SOURCE_UNAVAILABLE: JourneyStatus.PFZ_SOURCE_UNAVAILABLE,
            }[resolution.status]
            return self._base_response(
                request=request,
                request_at=request_at,
                generated_at=generated_at,
                journey_status=journey_status,
                pfz_resolution=resolution,
                origin=origin_result,
                reasons=[failure_reason, *self._limitation_reasons(imd_active=False)],
                imd_active=False,
            )

        destination_collected = await destination_task
        destination_result = self._location_result(
            location=destination_location,
            collected=destination_collected,
            request=request,
            request_at=request_at,
            evaluated_at=generated_at,
            expose_evidence=request.include_destination_evidence,
        )

        hazard_coll, bulletin_resp = await hazard_task
        imd_active = (hazard_coll is not None and bool(hazard_coll.features)) or (bulletin_resp is not None)

        corridor_hazard = None
        if hazard_coll and hazard_coll.features:
            corridor_hazard = evaluate_corridor_imd_hazards(
                origin_lon=request.origin.longitude,
                origin_lat=request.origin.latitude,
                destination_lon=destination_location.longitude,
                destination_lat=destination_location.latitude,
                hazard_features=hazard_coll.features,
                port_proximity_buffer_km=25.0,
            )

        active_bulletin = None
        if bulletin_resp and bulletin_resp.bulletins:
            for b in bulletin_resp.bulletins:
                if b.fishermen_warning:
                    active_bulletin = b
                    break

        journey_status, assessment_codes = self._status_and_assessment_reasons(
            origin_result, destination_result
        )

        reasons = [self._reason(JourneyReasonCode.VALID_PFZ_FOUND)]

        # Deterministic veto: corridor intersects hazard or fishermen warning is active
        if corridor_hazard and corridor_hazard.vetoed:
            journey_status = JourneyStatus.PFZ_AVAILABLE_LIMIT_EXCEEDED
            v_code = (
                JourneyReasonCode.OFFICIAL_IMD_CYCLONE_WARNING
                if corridor_hazard.veto_code == "OFFICIAL_IMD_CYCLONE_WARNING"
                else JourneyReasonCode.OFFICIAL_IMD_PORT_WARNING
            )
            reasons.append(JourneyReason(code=v_code, message=corridor_hazard.veto_message))
            reasons.append(self._reason(JourneyReasonCode.ROUTE_HAZARD_INTERSECTION))

        if active_bulletin:
            journey_status = JourneyStatus.PFZ_AVAILABLE_LIMIT_EXCEEDED
            reasons.append(JourneyReason(
                code=JourneyReasonCode.OFFICIAL_IMD_FISHERMEN_WARNING,
                message=active_bulletin.advisory_text or "Official IMD bulletin: Fishermen advised NOT to venture into deep sea.",
            ))

        reasons.extend(self._reason(code) for code in assessment_codes)
        reasons.extend(self._limitation_reasons(imd_active=imd_active))
        reasons.append(
            self._reason(JourneyReasonCode.PFZ_DOES_NOT_GUARANTEE_FISH_PRESENCE)
        )
        return self._base_response(
            request=request,
            request_at=request_at,
            generated_at=generated_at,
            journey_status=journey_status,
            pfz_resolution=resolution,
            origin=origin_result,
            pfz=pfz,
            destination=destination_result,
            reasons=reasons,
            imd_active=imd_active,
        )

