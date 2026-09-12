from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.capabilities import (
    AssistantIntent,
    CapabilityAvailability,
)
from app.agents.coordinator import capability_guard_node, coordinator_node
from app.agents.errors import AssistantExecutionError
from app.agents.evidence import (
    safe_message,
    summarize_assessment,
    summarize_evidence,
    summarize_pfz,
)
from app.agents.explainer import LLMResponseExplainer
from app.agents.intents import (
    IntentRouter,
    RouterOutcome,
    validated_required_information,
)
from app.agents.state import ORCAAgentState
from app.db.models import AssistantRunStatus, ConversationMode, EvidenceQuality
from app.schemas.assessment import (
    AssessmentOutcome,
    AssessmentRequest,
    EvidenceConfidence,
    MarineAssessmentResponse,
)
from app.schemas.assistant import (
    AssistantDemoFixture,
    AssistantDemonstrationMetadata,
    AssistantEvidenceStatus,
    AssistantEvidenceSummary,
    AssistantMode,
    AssistantRequest,
    AssistantResponse,
    AssistantResponseStatus,
    AssistantSourceSummary,
    AssistantWarning,
    IntentRoutingResult,
    RoutingMode,
)
from app.schemas.evidence import EvidenceRequest, MarineEvidenceResponse
from app.schemas.pfz import NearestPFZResponse
from app.schemas.pfz_journey import (
    JourneyLocation,
    JourneyStatus,
    PFZJourneyRequest,
    PFZJourneyResponse,
)
from app.domain.coastal_boundaries import decimal_to_dms, is_land_coordinate
from app.agents.multilingual import (
    detect_language,
    format_assessment_response,
    format_clarification_answer,
    format_default_greeting,
    format_inland_prefix_for_pfz,
    format_land_notice,
    format_marine_conditions_response,
    format_pfz_bulletin,
    format_planned_answer,
    translate_marine_reading,
)
from app.services.assistant_store import (
    AssistantPersistencePort,
)


@dataclass(frozen=True, slots=True)
class AssistantServices:
    pfz_nearest: Any
    evidence: Any
    assessment: Any
    pfz_journey: Any | None = None


@dataclass(frozen=True, slots=True)
class ServiceFailure:
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class LandLocationResult:
    latitude: float
    longitude: float
    nearest_coast: str
    distance_to_coast_km: float
    requested_capability: str


class ORCAAssistantGraph:
    def __init__(
        self,
        *,
        router: IntentRouter,
        persistence: AssistantPersistencePort,
        services: AssistantServices,
        model: str | None,
        graph_timeout_seconds: float = 45.0,
        max_scientific_service_calls: int = 4,
        now: Callable[[], datetime] | None = None,
        demo_fixture: AssistantDemoFixture | None = None,
        explainer: LLMResponseExplainer | None = None,
    ) -> None:
        self.router = router
        self.persistence = persistence
        self.services = services
        self.model = model
        self.graph_timeout_seconds = graph_timeout_seconds
        self.max_scientific_service_calls = max_scientific_service_calls
        self._now = now or (lambda: datetime.now(UTC))
        self.demo_fixture = demo_fixture or load_demonstration_fixture()
        self.explainer = explainer
        self.graph = self._compile_graph()

    def _compile_graph(self):
        graph = StateGraph(ORCAAgentState)
        graph.add_node("coordinator", coordinator_node)
        graph.add_node("intent_router", self._intent_router_node)
        graph.add_node("capability_guard", capability_guard_node)
        graph.add_node("pfz_agent", self._deterministic_service_node)
        graph.add_node("marine_evidence_agent", self._deterministic_service_node)
        graph.add_node("operational_assessment_agent", self._deterministic_service_node)
        graph.add_node("source_explanation_agent", self._deterministic_service_node)
        graph.add_node("demonstration_agent", self._deterministic_service_node)
        graph.add_node("evidence_validator", self._evidence_validator_node)
        graph.add_node("operational_assessor", self._operational_assessor_node)
        graph.add_node("response_formatter", self._response_formatter_node)
        graph.add_node("persistence_finalizer", self._persistence_finalizer_node)
        graph.add_edge(START, "coordinator")
        graph.add_edge("coordinator", "intent_router")
        graph.add_edge("intent_router", "capability_guard")
        graph.add_conditional_edges(
            "capability_guard",
            self._after_guard,
            {
                "pfz_agent": "pfz_agent",
                "marine_evidence_agent": "marine_evidence_agent",
                "operational_assessment_agent": "operational_assessment_agent",
                "source_explanation_agent": "source_explanation_agent",
                "demonstration_agent": "demonstration_agent",
                "respond": "evidence_validator",
            },
        )
        for specialist in (
            "pfz_agent",
            "marine_evidence_agent",
            "operational_assessment_agent",
            "source_explanation_agent",
            "demonstration_agent",
        ):
            graph.add_edge(specialist, "evidence_validator")
        graph.add_edge("evidence_validator", "operational_assessor")
        graph.add_edge("operational_assessor", "response_formatter")
        graph.add_edge("response_formatter", "persistence_finalizer")
        graph.add_edge("persistence_finalizer", END)
        return graph.compile()

    async def query(self, request: AssistantRequest) -> AssistantResponse:
        integration = (
            "demonstration_fixture"
            if request.mode == AssistantMode.DEMONSTRATION
            else "gemini_function_call_with_deterministic_fallback"
        )
        try:
            references = await self.persistence.begin_turn(
                conversation_id=request.conversation_id,
                content=request.message,
                language=request.preferred_language.value,
                mode=ConversationMode(request.mode.value),
                model=self.model if request.mode == AssistantMode.LIVE else None,
                integration=integration,
            )
        except Exception as exc:  # noqa: BLE001 - convert persistence failures safely
            code = getattr(exc, "code", "ASSISTANT_PERSISTENCE_UNAVAILABLE")
            retryable = bool(getattr(exc, "retryable", False))
            http_status = {
                "PERSISTENCE_RECORD_NOT_FOUND": 404,
                "PERSISTENCE_VALIDATION_FAILED": 409,
                "DATABASE_CONSTRAINT_VIOLATION": 409,
            }.get(code, 503 if retryable else 500)
            raise AssistantExecutionError(
                code,
                (
                    "The requested assistant conversation was not found"
                    if code == "PERSISTENCE_RECORD_NOT_FOUND"
                    else "Assistant persistence is unavailable"
                ),
                retryable=retryable,
                http_status=http_status,
            ) from None
        try:
            previous_sources = (
                await self.persistence.latest_sources(references.conversation_id)
                if request.conversation_id is not None
                else {}
            )
            previous_intent = (
                await self.persistence.latest_intent(references.conversation_id)
                if request.conversation_id is not None
                else None
            )
        except Exception:  # noqa: BLE001 - persistence details remain private
            await self.persistence.fail_turn(
                references=references,
                error_code="ASSISTANT_PERSISTENCE_UNAVAILABLE",
                latency_ms=0,
            )
            raise AssistantExecutionError(
                "ASSISTANT_PERSISTENCE_UNAVAILABLE",
                "Assistant persistence is unavailable",
                retryable=True,
                http_status=503,
            ) from None
        state: ORCAAgentState = {
            "request": request,
            "references": references,
            "started_at_ns": perf_counter_ns(),
            "step_count": 0,
            "service_call_count": 0,
            "previous_sources": previous_sources,
            "previous_intent": previous_intent,
        }
        try:
            async with asyncio.timeout(self.graph_timeout_seconds):
                result = await self.graph.ainvoke(state)
            return result["response"]
        except asyncio.CancelledError:
            await self.persistence.fail_turn(
                references=references,
                error_code="ASSISTANT_REQUEST_CANCELLED",
                latency_ms=self._latency_ms(state["started_at_ns"]),
                cancelled=True,
            )
            raise
        except TimeoutError:
            await self.persistence.fail_turn(
                references=references,
                error_code="ASSISTANT_GRAPH_TIMEOUT",
                latency_ms=self._latency_ms(state["started_at_ns"]),
            )
            raise AssistantExecutionError(
                "ASSISTANT_GRAPH_TIMEOUT",
                "The assistant request timed out",
                retryable=True,
                http_status=503,
            ) from None
        except AssistantExecutionError as exc:
            await self.persistence.fail_turn(
                references=references,
                error_code=exc.code,
                latency_ms=self._latency_ms(state["started_at_ns"]),
            )
            raise
        except Exception:  # noqa: BLE001 - unexpected graph failures are sanitized
            await self.persistence.fail_turn(
                references=references,
                error_code="ASSISTANT_EXECUTION_FAILED",
                latency_ms=self._latency_ms(state["started_at_ns"]),
            )
            raise AssistantExecutionError(
                "ASSISTANT_EXECUTION_FAILED",
                "The assistant request could not be completed",
            ) from None

    async def _intent_router_node(self, state: ORCAAgentState) -> dict[str, object]:
        request = state["request"]
        if request.mode == AssistantMode.DEMONSTRATION:
            outcome = RouterOutcome(
                routing=IntentRoutingResult(
                    intent=self.demo_fixture.intent,
                    confidence=1.0,
                    required_information=(),
                ),
                mode=RoutingMode.DEMONSTRATION,
            )
        else:
            outcome = await self.router.route(request)
            if (
                outcome.routing.intent
                in {
                    AssistantIntent.UNSUPPORTED,
                    AssistantIntent.CLARIFICATION_REQUIRED,
                }
                and state["previous_intent"] is not None
            ):
                outcome = RouterOutcome(
                    routing=outcome.routing.model_copy(
                        update={"intent": state["previous_intent"]}
                    ),
                    mode=outcome.mode,
                    model=outcome.model,
                    input_tokens=outcome.input_tokens,
                    output_tokens=outcome.output_tokens,
                    warning=outcome.warning,
                )
        # Application state derives or verifies every requested field.
        if request.mode == AssistantMode.LIVE:
            outcome = RouterOutcome(
                routing=outcome.routing.model_copy(
                    update={
                        "required_information": validated_required_information(
                            request,
                            outcome.routing.intent,
                            outcome.routing.required_information,
                        )
                    }
                ),
                mode=outcome.mode,
                model=outcome.model,
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
                warning=outcome.warning,
            )
        return {
            "routing_outcome": outcome,
            "step_count": state["step_count"] + 1,
        }

    @staticmethod
    def _after_guard(state: ORCAAgentState) -> str:
        routed = state["routing_outcome"].routing
        if state["request"].mode == AssistantMode.DEMONSTRATION:
            return "demonstration_agent"
        if routed.required_information or (
            state["capability_status"] != CapabilityAvailability.AVAILABLE
        ):
            return "respond"
        return {
            AssistantIntent.NEAREST_PFZ: "pfz_agent",
            AssistantIntent.MARINE_CONDITIONS: "marine_evidence_agent",
            AssistantIntent.OPERATIONAL_CONDITIONS: "operational_assessment_agent",
            AssistantIntent.SOURCE_EXPLANATION: "source_explanation_agent",
        }.get(routed.intent, "respond")

    async def _deterministic_service_node(
        self, state: ORCAAgentState
    ) -> dict[str, object]:
        request = state["request"]
        if request.mode == AssistantMode.DEMONSTRATION:
            return {
                "deterministic_result": self.demo_fixture,
                "step_count": state["step_count"] + 1,
            }
        intent = state["routing_outcome"].routing.intent
        calls = state["service_call_count"]
        if intent != AssistantIntent.SOURCE_EXPLANATION:
            calls += 1
            if calls > self.max_scientific_service_calls:
                raise AssistantExecutionError(
                    "ASSISTANT_SERVICE_CALL_LIMIT_EXCEEDED",
                    "The assistant service-call limit was exceeded",
                )
        try:
            result = await self._call_service(
                intent, request, state["previous_sources"]
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - source failures become typed evidence
            result = _safe_service_failure(intent, exc)
        return {
            "deterministic_result": result,
            "service_call_count": calls,
            "step_count": state["step_count"] + 1,
        }

    async def _call_service(
        self,
        intent: AssistantIntent,
        request: AssistantRequest,
        previous_sources: dict[str, Any],
    ) -> Any:
        latitude = request.latitude
        longitude = request.longitude
        if intent in {
            AssistantIntent.NEAREST_PFZ,
            AssistantIntent.MARINE_CONDITIONS,
            AssistantIntent.OPERATIONAL_CONDITIONS,
        } and (latitude is None or longitude is None):
            raise AssistantExecutionError(
                "ASSISTANT_LOCATION_REQUIRED",
                "A location is required for this assistant capability",
            )

        if latitude is not None and longitude is not None:
            is_land, nearest_coast, coast_dist = is_land_coordinate(latitude, longitude)
            if is_land and intent in {
                AssistantIntent.MARINE_CONDITIONS,
                AssistantIntent.OPERATIONAL_CONDITIONS,
            }:
                return LandLocationResult(
                    latitude=latitude,
                    longitude=longitude,
                    nearest_coast=nearest_coast,
                    distance_to_coast_km=coast_dist,
                    requested_capability=intent.value,
                )

        if intent == AssistantIntent.NEAREST_PFZ:
            if (
                request.operational_limits.supplied_count() > 0
                and self.services.pfz_journey is not None
            ):
                return await self.services.pfz_journey.run(
                    PFZJourneyRequest(
                        origin=JourneyLocation(
                            latitude=latitude,
                            longitude=longitude,
                        ),
                        at=request.requested_time,
                        operational_limits=request.operational_limits,
                    )
                )
            return await self.services.pfz_nearest.get_nearest(
                latitude=latitude,
                longitude=longitude,
                at=request.requested_time,
            )
        if intent == AssistantIntent.MARINE_CONDITIONS:
            return await self.services.evidence.aggregate(
                EvidenceRequest(
                    latitude=latitude,
                    longitude=longitude,
                    at=request.requested_time,
                    include_pfz=True,
                )
            )
        if intent == AssistantIntent.OPERATIONAL_CONDITIONS:
            return await self.services.assessment.assess(
                AssessmentRequest(
                    latitude=latitude,
                    longitude=longitude,
                    at=request.requested_time,
                    operational_limits=request.operational_limits,
                )
            )
        if intent == AssistantIntent.SOURCE_EXPLANATION:
            return previous_sources
        raise AssistantExecutionError(
            "ASSISTANT_CAPABILITY_NOT_EXECUTABLE",
            "The selected assistant capability is not executable",
        )

    async def _evidence_validator_node(
        self, state: ORCAAgentState
    ) -> dict[str, object]:
        result = state.get("deterministic_result")
        summary = AssistantEvidenceSummary()
        sources: tuple[AssistantSourceSummary, ...] = ()
        warnings: tuple[AssistantWarning, ...] = ()
        if isinstance(result, AssistantDemoFixture):
            summary, sources, warnings = (
                result.evidence_summary,
                result.sources,
                result.warnings,
            )
        elif isinstance(result, MarineEvidenceResponse):
            summary, sources, warnings = summarize_evidence(result)
        elif isinstance(result, MarineAssessmentResponse):
            summary, sources, warnings = summarize_assessment(result)
        elif isinstance(result, NearestPFZResponse):
            summary, sources, warnings = summarize_pfz(result)
        elif isinstance(result, PFZJourneyResponse):
            summary, sources, warnings = _summarize_journey(result)
        elif isinstance(result, LandLocationResult):
            summary = AssistantEvidenceSummary(
                status=AssistantEvidenceStatus.NOT_COLLECTED,
                available_sources=0,
                unavailable_sources=0,
            )
            warnings = (
                AssistantWarning(
                    code="LOCATION_ON_LAND",
                    message=(
                        f"Position ({result.latitude:.4f}°N, {result.longitude:.4f}°E) is located inland on land, "
                        f"{result.distance_to_coast_km:.0f} km from the nearest coast ({result.nearest_coast}). "
                        "Marine conditions (waves, sea level, tides, currents, SST) are only defined for ocean waters."
                    ),
                    retryable=False,
                ),
            )
        elif isinstance(result, ServiceFailure):
            summary = AssistantEvidenceSummary(
                status=AssistantEvidenceStatus.UNAVAILABLE,
                unavailable_sources=1,
            )
            warnings = (
                AssistantWarning(
                    code=result.code,
                    message=result.message,
                    retryable=result.retryable,
                ),
            )
        elif isinstance(result, dict):
            sources = tuple(
                AssistantSourceSummary.model_validate(item)
                for item in result.values()
                if isinstance(item, dict)
            )
            if sources:
                summary = AssistantEvidenceSummary(
                    status=AssistantEvidenceStatus.COMPLETE,
                    available_sources=sum(s.state == "available" for s in sources),
                    degraded_sources=sum(s.state == "degraded" for s in sources),
                    pending_sources=sum(s.state == "pending" for s in sources),
                    unavailable_sources=sum(s.state == "unavailable" for s in sources),
                )
        router_warning = state["routing_outcome"].warning
        if router_warning is not None:
            warnings = (router_warning, *warnings)
        return {
            "evidence_summary": summary,
            "sources": sources,
            "warnings": warnings,
            "step_count": state["step_count"] + 1,
        }

    async def _operational_assessor_node(
        self, state: ORCAAgentState
    ) -> dict[str, object]:
        result = state.get("deterministic_result")
        request = state["request"]
        updates: dict[str, object] = {"step_count": state["step_count"] + 1}
        if (
            isinstance(result, MarineEvidenceResponse)
            and request.operational_limits.supplied_count() > 0
        ):
            if request.latitude is None or request.longitude is None:
                raise AssistantExecutionError(
                    "ASSISTANT_LOCATION_REQUIRED",
                    "A location is required for operational assessment",
                )
            request_at = result.request.at
            result = self.services.assessment.assess_evidence(
                request=AssessmentRequest(
                    latitude=request.latitude,
                    longitude=request.longitude,
                    at=request_at,
                    operational_limits=request.operational_limits,
                ),
                evidence=result,
                request_at=request_at,
                evaluated_at=self._utc(self._now()),
            )
            summary, sources, assessment_warnings = summarize_assessment(result)
            updates.update(
                deterministic_result=result,
                evidence_summary=summary,
                sources=sources,
                warnings=(*state["warnings"], *assessment_warnings),
            )
        # E2 owns all comparisons. This node invokes that pure boundary when
        # limits accompany E1 evidence, then verifies controlled terminology.
        if (
            isinstance(result, MarineAssessmentResponse)
            and "SAFE" in result.outcome.value
        ):
            raise AssistantExecutionError(
                "ASSISTANT_TERMINOLOGY_VIOLATION",
                "The deterministic result used unsupported terminology",
            )
        return updates

    async def _response_formatter_node(
        self, state: ORCAAgentState
    ) -> dict[str, object]:
        request = state["request"]
        routed = state["routing_outcome"].routing
        capability = state["capability_status"]
        result = state.get("deterministic_result")
        lang = detect_language(request.message, request.preferred_language)

        if (
            routed.intent == AssistantIntent.CLARIFICATION_REQUIRED
            and routed.required_information
        ):
            status = AssistantResponseStatus.CLARIFICATION_REQUIRED
            answer = format_clarification_answer(lang, routed.required_information)
        elif capability != CapabilityAvailability.AVAILABLE:
            status = AssistantResponseStatus.CAPABILITY_NOT_AVAILABLE
            answer = format_planned_answer(lang, routed.intent)
        elif routed.required_information:
            status = AssistantResponseStatus.CLARIFICATION_REQUIRED
            answer = format_clarification_answer(lang, routed.required_information)
        elif isinstance(result, ServiceFailure):
            status = AssistantResponseStatus.FAILED
            answer = result.message
        elif isinstance(result, AssistantDemoFixture):
            status = AssistantResponseStatus.PARTIAL
            answer = result.answer
        elif isinstance(result, LandLocationResult):
            status = AssistantResponseStatus.COMPLETED
            answer = format_land_notice(
                lang,
                result.latitude,
                result.longitude,
                result.nearest_coast,
                result.distance_to_coast_km,
            )
        elif isinstance(result, NearestPFZResponse):
            status = AssistantResponseStatus.COMPLETED
            location = result.nearest_pfz
            date_str = (
                result.valid_until.strftime("%d %b %Y %H:%M UTC")
                if result.valid_until
                else "Active"
            )

            dist_min = location.distance_from_coast_km.minimum
            dist_max = location.distance_from_coast_km.maximum
            if dist_min is not None and dist_max is not None:
                dist_coast_str = f"{dist_min:.0f} - {dist_max:.0f} km"
            elif dist_min is not None:
                dist_coast_str = f"{dist_min:.0f} km"
            elif dist_max is not None:
                dist_coast_str = f"Up to {dist_max:.0f} km"
            else:
                dist_coast_str = "N/A"

            depth_min = location.depth_m.minimum
            depth_max = location.depth_m.maximum
            if depth_min is not None and depth_max is not None:
                depth_str = f"{depth_min:.0f} - {depth_max:.0f} m"
            elif depth_min is not None:
                depth_str = f"{depth_min:.0f} m"
            elif depth_max is not None:
                depth_str = f"Up to {depth_max:.0f} m"
            else:
                depth_str = "N/A"

            lat_dms = decimal_to_dms(location.latitude, is_lat=True)
            lon_dms = decimal_to_dms(location.longitude, is_lat=False)

            land_prefix = ""
            if request.latitude is not None and request.longitude is not None:
                is_land, nearest_coast, coast_dist = is_land_coordinate(
                    request.latitude, request.longitude
                )
                if is_land:
                    land_prefix = format_inland_prefix_for_pfz(
                        lang, coast_dist, nearest_coast, location.landing_centre
                    )

            answer = format_pfz_bulletin(
                lang=lang,
                landing_centre=location.landing_centre,
                direction=location.direction,
                bearing_deg=location.bearing_deg,
                dist_coast_str=dist_coast_str,
                depth_str=depth_str,
                lat_dms=lat_dms,
                lat_num=location.latitude,
                lon_dms=lon_dms,
                lon_num=location.longitude,
                sector_code=location.sector_code,
                region_name=location.region_name,
                distance_km=location.distance_km,
                date_str=date_str,
                land_prefix=land_prefix,
            )
        elif isinstance(result, PFZJourneyResponse):
            status = (
                AssistantResponseStatus.PARTIAL
                if "INSUFFICIENT" in result.journey_status.value
                else AssistantResponseStatus.COMPLETED
            )
            outcome = result.journey_status.value.replace("_", " ").title()
            pfz_str = ""
            if result.pfz and result.pfz.nearest_pfz:
                p = result.pfz.nearest_pfz
                lat_dms = decimal_to_dms(p.latitude, is_lat=True)
                lon_dms = decimal_to_dms(p.longitude, is_lat=False)
                dist_min = p.distance_from_coast_km.minimum
                dist_max = p.distance_from_coast_km.maximum
                dist_coast_str = (
                    f"{dist_min:.0f} - {dist_max:.0f} km"
                    if dist_min is not None and dist_max is not None
                    else f"{p.distance_km:.1f} km"
                )
                depth_min = p.depth_m.minimum
                depth_max = p.depth_m.maximum
                depth_str = (
                    f"{depth_min:.0f} - {depth_max:.0f} m"
                    if depth_min is not None and depth_max is not None
                    else "N/A"
                )
                pfz_str = (
                    f"\n\nDestination INCOIS PFZ Advisory:\n"
                    f"• Landing Centre: {p.landing_centre} (Sector {p.sector_code}, {p.region_name})\n"
                    f"• Direction: {p.direction} | Bearing: {p.bearing_deg:.0f}°\n"
                    f"• Distance (km) From - To: {dist_coast_str}\n"
                    f"• Depth (mtr) From - To: {depth_str}\n"
                    f"• Coordinates: {lat_dms}, {lon_dms}\n"
                    f"• Transit Distance: {result.distance.kilometres:.1f} km {result.distance.direction}"
                )

            origin_readings = []
            if result.origin and result.origin.assessment:
                origin_readings = _extract_marine_readings(
                    waves_data=result.origin.assessment.critical_evidence.waves.data,
                    wind_data=result.origin.assessment.critical_evidence.wind.data,
                    currents_data=result.origin.assessment.critical_evidence.currents.data,
                    sst_data=result.origin.assessment.context.sst.data,
                    chlorophyll_data=result.origin.assessment.context.chlorophyll.data,
                    sea_level_data=result.origin.assessment.context.sea_level.data,
                    rules=result.origin.assessment.rules,
                )
            if origin_readings:
                bullet_list = "\n".join(f"• {r}" for r in origin_readings)
                answer = (
                    f"PFZ Journey evaluation: {outcome}.{pfz_str}\n\n"
                    f"Origin marine conditions:\n{bullet_list}"
                )
            else:
                answer = (
                    f"PFZ Journey evaluation: {outcome}.{pfz_str}\n\n"
                    "Origin and destination marine conditions were evaluated against your configured limits."
                )
        elif isinstance(result, MarineAssessmentResponse):
            status = (
                AssistantResponseStatus.PARTIAL
                if result.evidence_confidence.value != "NORMAL"
                else AssistantResponseStatus.COMPLETED
            )
            outcome = result.outcome.value.replace("_", " ").title()
            confidence = result.evidence_confidence.value.lower()
            readings = _extract_marine_readings(
                waves_data=result.critical_evidence.waves.data,
                wind_data=result.critical_evidence.wind.data,
                currents_data=result.critical_evidence.currents.data,
                sst_data=result.context.sst.data,
                chlorophyll_data=result.context.chlorophyll.data,
                sea_level_data=result.context.sea_level.data,
                rules=result.rules,
            )
            answer = format_assessment_response(
                lang=lang,
                outcome=outcome,
                confidence=confidence,
                readings=readings,
            )
        elif isinstance(result, MarineEvidenceResponse):
            status = (
                AssistantResponseStatus.COMPLETED
                if result.status.value == "complete"
                else AssistantResponseStatus.PARTIAL
            )
            readings = _extract_marine_readings(
                waves_data=result.evidence.waves.data,
                wind_data=result.evidence.wind.data,
                currents_data=result.evidence.currents.data,
                sst_data=result.evidence.sst.data,
                chlorophyll_data=result.evidence.chlorophyll.data,
                sea_level_data=result.evidence.sea_level.data,
            )
            answer = format_marine_conditions_response(
                lang=lang,
                readings=readings,
                status_str=result.status.value,
                sources_count=result.summary.available_sources,
            )
        elif routed.intent == AssistantIntent.SOURCE_EXPLANATION:
            status = AssistantResponseStatus.COMPLETED
            if lang == "hi":
                answer = (
                    "सूचीबद्ध प्रदाता और डेटासेट इस सत्र के नवीनतम सत्यापित समुद्री साक्ष्यों से आते हैं।"
                    if state["sources"]
                    else "इस सत्र में अभी तक कोई समुद्री साक्ष्य एकत्र नहीं किया गया है। स्रोत देखने के लिए समुद्री स्थिति या PFZ क्वेरी चलाएं।"
                )
            elif lang == "gu":
                answer = (
                    "સૂચિબદ્ધ પ્રદાતાઓ અને ડેટાસેટ આ સત્રના સૌથી તાજેતરના ચકાસાયેલ દરિયાઈ પુરાવાઓમાંથી આવે છે."
                    if state["sources"]
                    else "આ સત્રમાં હજી સુધી કોઈ પુરાવા એકત્રિત થયા નથી. સ્રોત જોવા માટે દરિયાઈ સ્થિતિ અથવા PFZ તપાસ કરો."
                )
            elif lang == "mr":
                answer = (
                    "सूचीबद्ध प्रदाते आणि डेटासेट या सत्रातील नवीनतम सत्यापित सागरी पुराव्यांमधून आले आहेत."
                    if state["sources"]
                    else "या सत्रात अद्याप कोणताही पुरावा गोळा केलेला नाही. अधिकृत स्त्रोत पाहण्यासाठी सागरी स्थिती किंवा PFZ क्वेरी चालवा."
                )
            elif lang == "ta":
                answer = (
                    "பட்டியலிடப்பட்ட வழங்குநர்கள் மற்றும் தரவுத்தொகுப்புகள் இந்த அமர்வின் சமீபத்திய சரிபார்க்கப்பட்ட கடல்சார் சான்றுகளிலிருந்து வருகின்றன."
                    if state["sources"]
                    else "இந்த அமர்வில் இதுவரை சான்றுகள் சேகரிக்கப்படவில்லை. மூலங்களை ஆய்வு செய்ய கடல் நிலை அல்லது PFZ வினவலை இயக்கவும்."
                )
            elif lang == "te":
                answer = (
                    "జాబితా చేయబడిన ప్రొవైడర్లు మరియు డేటాసెట్‌లు ఈ సెషన్‌లో ఇటీవల ధృవీకరించబడిన సముద్ర ఆధారాల నుండి వచ్చాయి."
                    if state["sources"]
                    else "ఈ సెషన్‌లో ఇంకా ఆధారాలు సేకరించబడలేదు. అధికారిక మూలాలను పరిశీలించడానికి సముద్ర పరిస్థితులు లేదా PFZ ప్రశ్నను అమలు చేయండి."
                )
            elif lang == "ml":
                answer = (
                    "ലിസ്റ്റുചെയ്ത വിവരങ്ങൾ ഈ സെഷനിലെ ഏറ്റവും പുതിയ സ്ഥിരീകരിച്ച സമുദ്ര തെളിവുകളിൽ നിന്നാണ് വരുന്നത്."
                    if state["sources"]
                    else "ഈ സെഷനിൽ ഇതുവരെ തെളിവുകൾ ശേഖരിച്ചിട്ടില്ല. വിവരങ്ങൾ കാണാൻ സമുദ്ര അവസ്ഥ അല്ലെങ്കിൽ PFZ അന്വേഷണം നടത്തുക."
                )
            elif lang == "bn":
                answer = (
                    "তালিকাভুক্ত সরবরাহকারী এবং ডেটাসেটগুলি এই সেশনের সাম্প্রতিক যাচাইকৃত সামুদ্রিক প্রমাণ থেকে এসেছে।"
                    if state["sources"]
                    else "এই সেশনে এখনও কোনো প্রমাণ সংগৃহীত হয়নি। সামুদ্রিক অবস্থা বা PFZ কোয়েরি চালিয়ে অফিসিয়াল উৎস পরীক্ষা করুন।"
                )
            else:
                answer = (
                    "The listed providers and datasets come from the most recent verified marine "
                    "evidence in this session."
                    if state["sources"]
                    else "No collected evidence exists in this session yet. Run a marine conditions or PFZ query to inspect official source provenance."
                )
        else:
            status = AssistantResponseStatus.COMPLETED
            answer = format_default_greeting(lang)

        if self.explainer is not None and request.mode == AssistantMode.LIVE:
            try:
                natural_answer = await self.explainer.explain(
                    message=request.message,
                    language=lang,
                    intent=routed.intent,
                    deterministic_answer=answer,
                    status=status,
                    recent_messages=request.recent_messages,
                )
                if natural_answer and natural_answer.strip():
                    answer = natural_answer.strip()
            except Exception:
                pass

        return {
            "completion_status": status,
            "answer": answer,
            "step_count": state["step_count"] + 1,
        }

    async def _persistence_finalizer_node(
        self, state: ORCAAgentState
    ) -> dict[str, object]:
        request = state["request"]
        routing = state["routing_outcome"]
        references = state["references"]
        generated_at = self._utc(self._now())
        summary = state["evidence_summary"]
        warnings = state["warnings"]
        result = state.get("deterministic_result")
        geojson = (
            result.geojson
            if isinstance(
                result,
                (AssistantDemoFixture, NearestPFZResponse, PFZJourneyResponse),
            )
            else None
        )
        quality = _persistence_quality(summary)
        latency_ms = self._latency_ms(state["started_at_ns"])
        assistant_message_id = await self.persistence.finalize_turn(
            references=references,
            assistant_content=state["answer"],
            intent=routing.routing.intent,
            run_status=(
                AssistantRunStatus.FAILED
                if state["completion_status"] == AssistantResponseStatus.FAILED
                else AssistantRunStatus.SUCCEEDED
            ),
            latency_ms=latency_ms,
            input_tokens=routing.input_tokens,
            output_tokens=routing.output_tokens,
            evidence_quality=quality,
            result={
                "intent": routing.routing.intent.value,
                "completion_status": state["completion_status"].value,
                "evidence_summary": summary.model_dump(mode="json"),
                "geojson": geojson.model_dump(mode="json") if geojson else None,
            },
            sources={
                source.source: source.model_dump(mode="json")
                for source in state["sources"]
            },
            warnings=[warning.model_dump(mode="json") for warning in warnings],
            demonstration=request.mode == AssistantMode.DEMONSTRATION,
            retrieved_at=generated_at,
            valid_at=(
                self.demo_fixture.original_retrieval_time
                if request.mode == AssistantMode.DEMONSTRATION
                else request.requested_time
            ),
        )
        response = AssistantResponse(
            conversation_id=references.conversation_id,
            user_message_id=references.user_message_id,
            assistant_message_id=assistant_message_id,
            run_id=references.run_id,
            detected_intent=routing.routing.intent,
            capability_status=state["capability_status"],
            completion_status=state["completion_status"],
            answer=state["answer"],
            required_information=routing.routing.required_information,
            evidence_summary=summary,
            sources=state["sources"],
            warnings=warnings,
            geojson=geojson,
            routing_mode=routing.mode,
            model=routing.model,
            demonstration=(
                AssistantDemonstrationMetadata(
                    original_retrieval_time=self.demo_fixture.original_retrieval_time,
                    created_at=self.demo_fixture.created_at,
                )
                if request.mode == AssistantMode.DEMONSTRATION
                else None
            ),
            generated_at=generated_at,
        )
        return {"response": response, "step_count": state["step_count"] + 1}

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise AssistantExecutionError(
                "ASSISTANT_CLOCK_INVALID", "The assistant clock is invalid"
            )
        return value.astimezone(UTC)

    @staticmethod
    def _latency_ms(started_at_ns: int) -> int:
        return max(0, round((perf_counter_ns() - started_at_ns) / 1_000_000))


def _safe_service_failure(
    intent: AssistantIntent, exc: BaseException
) -> ServiceFailure:
    code_by_intent = {
        AssistantIntent.NEAREST_PFZ: "PFZ_SOURCE_UNAVAILABLE",
        AssistantIntent.MARINE_CONDITIONS: "MARINE_EVIDENCE_UNAVAILABLE",
        AssistantIntent.OPERATIONAL_CONDITIONS: "OPERATIONAL_ASSESSMENT_UNAVAILABLE",
        AssistantIntent.SOURCE_EXPLANATION: "SOURCE_EXPLANATION_UNAVAILABLE",
    }
    retryable = type(exc).__name__ not in {"NoValidPFZError", "ValueError"}
    return ServiceFailure(
        code=code_by_intent.get(intent, "ASSISTANT_SERVICE_UNAVAILABLE"),
        message="The requested deterministic ORCA service is unavailable",
        retryable=retryable,
    )


def _summarize_journey(
    journey: PFZJourneyResponse,
) -> tuple[
    AssistantEvidenceSummary,
    tuple[AssistantSourceSummary, ...],
    tuple[AssistantWarning, ...],
]:
    """Collapse E3 provenance without merging its location measurements."""
    by_source: dict[str, AssistantSourceSummary] = {}
    warnings: list[AssistantWarning] = []
    qualities: list[EvidenceConfidence] = []
    state_rank = {"available": 0, "degraded": 1, "pending": 2, "unavailable": 3}

    if journey.pfz is not None:
        _, pfz_sources, pfz_warnings = summarize_pfz(journey.pfz)
        by_source.update((source.source, source) for source in pfz_sources)
        warnings.extend(pfz_warnings)

    for location in (journey.origin, journey.destination):
        if location is None or location.assessment is None:
            continue
        _, location_sources, location_warnings = summarize_assessment(
            location.assessment
        )
        qualities.append(location.assessment.evidence_confidence)
        warnings.extend(location_warnings)
        for source in location_sources:
            existing = by_source.get(source.source)
            if (
                existing is None
                or state_rank[source.state] > state_rank[existing.state]
            ):
                by_source[source.source] = source

    for reason in journey.reasons:
        warnings.append(
            AssistantWarning(
                code=reason.code.value, message=safe_message(reason.message)
            )
        )
    sources = tuple(
        by_source[name]
        for name in (
            "pfz",
            "sst",
            "chlorophyll",
            "waves",
            "wind",
            "currents",
            "sea_level",
        )
        if name in by_source
    )
    available = sum(source.state == "available" for source in sources)
    degraded = sum(source.state == "degraded" for source in sources)
    pending = sum(source.state == "pending" for source in sources)
    unavailable = sum(source.state == "unavailable" for source in sources)
    usable = available + degraded
    evidence_status = (
        AssistantEvidenceStatus.COMPLETE
        if sources and not pending and not unavailable
        else AssistantEvidenceStatus.PARTIAL
        if usable
        else AssistantEvidenceStatus.UNAVAILABLE
    )
    outcome_by_status = {
        JourneyStatus.PFZ_AVAILABLE_WITHIN_CONFIGURED_LIMITS: AssessmentOutcome.WITHIN_CONFIGURED_LIMITS,
        JourneyStatus.PFZ_AVAILABLE_CAUTION: AssessmentOutcome.CAUTION,
        JourneyStatus.PFZ_AVAILABLE_LIMIT_EXCEEDED: AssessmentOutcome.LIMIT_EXCEEDED,
        JourneyStatus.PFZ_AVAILABLE_INSUFFICIENT_EVIDENCE: AssessmentOutcome.INSUFFICIENT_EVIDENCE,
        JourneyStatus.POLICY_NOT_CONFIGURED: AssessmentOutcome.POLICY_NOT_CONFIGURED,
    }
    confidence = (
        EvidenceConfidence.INSUFFICIENT
        if EvidenceConfidence.INSUFFICIENT in qualities
        else EvidenceConfidence.DEGRADED
        if EvidenceConfidence.DEGRADED in qualities
        else EvidenceConfidence.NORMAL
        if qualities
        else None
    )
    return (
        AssistantEvidenceSummary(
            status=evidence_status,
            available_sources=available,
            degraded_sources=degraded,
            pending_sources=pending,
            unavailable_sources=unavailable,
            assessment_outcome=outcome_by_status.get(journey.journey_status),
            evidence_confidence=confidence,
            pfz_status=journey.pfz_resolution.status,
        ),
        sources,
        tuple(warnings),
    )


def _extract_marine_readings(
    waves_data: Any = None,
    wind_data: Any = None,
    currents_data: Any = None,
    sst_data: Any = None,
    chlorophyll_data: Any = None,
    sea_level_data: Any = None,
    rules: Any = None,
) -> list[str]:
    limits_map: dict[str, str] = {}
    if rules:
        for r in rules:
            if getattr(r, "configured_limit", None) is not None:
                param = getattr(r, "parameter", "")
                unit = getattr(r, "unit", "")
                limits_map[param] = f"{r.configured_limit:g} {unit}".strip()

    readings: list[str] = []

    # Significant wave height
    if waves_data is not None:
        swh = getattr(waves_data, "significant_wave_height", None)
        v = getattr(swh, "value", None) if swh is not None else getattr(waves_data, "value", None)
        if v is not None:
            lim = limits_map.get("significant_wave_height")
            lim_suffix = f" (limit: {lim})" if lim else ""
            readings.append(f"Significant wave height: {v:.1f} m{lim_suffix}")

    # Wind speed
    if wind_data is not None:
        ws = getattr(wind_data, "wind_speed", None)
        v = getattr(ws, "value", None) if ws is not None else getattr(wind_data, "wind_speed_mps", None)
        if v is not None:
            lim = limits_map.get("wind_speed")
            lim_suffix = f" (limit: {lim})" if lim else ""
            readings.append(f"Wind speed: {v:.1f} m/s{lim_suffix}")

    # Surface currents
    if currents_data is not None:
        tc = getattr(currents_data, "total_current", None)
        v = getattr(tc, "speed_mps", None) if tc is not None else getattr(currents_data, "speed_mps", None)
        if v is not None:
            lim = limits_map.get("total_surface_current_speed")
            lim_suffix = f" (limit: {lim})" if lim else ""
            readings.append(f"Surface current: {v:.2f} m/s{lim_suffix}")

    # Sea Surface Temperature (SST)
    if sst_data is not None:
        v = getattr(sst_data, "value", None)
        if v is not None:
            readings.append(f"Sea Surface Temperature (SST): {v:.1f}°C")

    # Chlorophyll-a
    if chlorophyll_data is not None:
        ca = getattr(chlorophyll_data, "chlorophyll_a", None)
        v = getattr(ca, "value", None) if ca is not None else getattr(chlorophyll_data, "value", None)
        if v is not None:
            readings.append(f"Chlorophyll-a: {v:.2f} mg/m³")

    # Sea level
    if sea_level_data is not None:
        v = getattr(sea_level_data, "total_modelled_sea_level_m", None) or getattr(sea_level_data, "astronomical_tide_elevation_m", None)
        if v is not None:
            readings.append(f"Sea level / Tide: {v:.2f} m")

    return readings


def _clarification_answer(request: AssistantRequest, required: tuple[Any, ...]) -> str:
    lang = detect_language(request.message, request.preferred_language)
    return format_clarification_answer(lang, required)


def _planned_answer(request: AssistantRequest, intent: AssistantIntent) -> str:
    lang = detect_language(request.message, request.preferred_language)
    return format_planned_answer(lang, intent)


def _persistence_quality(summary: AssistantEvidenceSummary) -> EvidenceQuality | None:
    if summary.status == AssistantEvidenceStatus.NOT_COLLECTED:
        return None
    if summary.status == AssistantEvidenceStatus.UNAVAILABLE:
        return EvidenceQuality.INSUFFICIENT
    if (
        summary.degraded_sources
        or summary.pending_sources
        or summary.unavailable_sources
    ):
        return EvidenceQuality.DEGRADED
    return EvidenceQuality.NORMAL


def load_demonstration_fixture(path: Path | None = None) -> AssistantDemoFixture:
    fixture_path = (
        path or Path(__file__).resolve().parents[1] / "fixtures" / "assistant_demo.json"
    )
    try:
        return AssistantDemoFixture.model_validate_json(
            fixture_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError):
        raise AssistantExecutionError(
            "ASSISTANT_DEMONSTRATION_INVALID",
            "The saved assistant demonstration is unavailable",
        ) from None
