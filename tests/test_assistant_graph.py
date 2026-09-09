import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agents.capabilities import AssistantIntent
from app.agents.evidence import safe_message
from app.agents.graph import (
    AssistantExecutionError,
    AssistantServices,
    ORCAAssistantGraph,
)
from app.agents.intents import (
    DeterministicIntentRouter,
    FallbackIntentRouter,
    GeminiRouterError,
    RouterOutcome,
)
from app.schemas.assessment import AssessmentRequest
from app.schemas.assistant import AssistantRequest, IntentRoutingResult, RoutingMode
from app.services.assessment import MarineAssessmentService
from app.services.assistant_store import AssistantTurnReferences
from tests.test_pfz_api import nearest_service
from tests.test_pfz_journey_service import journey_request, journey_service
from tests.test_risk_rules import critical_bundle

NOW = datetime(2026, 8, 27, 12, tzinfo=UTC)


class MemoryPersistence:
    def __init__(self, previous_sources=None, previous_intent=None):
        self.previous_sources = previous_sources or {}
        self.previous_intent = previous_intent
        self.begun = []
        self.finalized = []
        self.failed = []

    async def begin_turn(self, **kwargs):
        self.begun.append(kwargs)
        return AssistantTurnReferences(uuid4(), uuid4(), uuid4())

    async def finalize_turn(self, **kwargs):
        self.finalized.append(kwargs)
        return uuid4()

    async def fail_turn(self, **kwargs):
        self.failed.append(kwargs)

    async def latest_sources(self, conversation_id):
        return self.previous_sources

    async def latest_intent(self, conversation_id):
        return self.previous_intent


class FixedRouter:
    def __init__(self, intent, *, mode=RoutingMode.DETERMINISTIC):
        self.intent = AssistantIntent(intent)
        self.mode = mode
        self.calls = 0

    async def route(self, request):
        self.calls += 1
        return RouterOutcome(
            routing=IntentRoutingResult(
                intent=self.intent,
                confidence=0.9,
                required_information=(),
            ),
            mode=self.mode,
            model="gemini-3.7-flash" if self.mode == RoutingMode.GEMINI else None,
        )


class FakeService:
    def __init__(self, method, result):
        self.method = method
        self.result = result
        self.calls = []

    def __getattr__(self, name):
        if name != self.method:
            raise AttributeError(name)

        async def call(*args, **kwargs):
            self.calls.append((args, kwargs))
            if isinstance(self.result, BaseException):
                raise self.result
            return self.result

        return call


async def service_results():
    evidence = await critical_bundle()
    evidence_service = FakeService("aggregate", evidence)
    assessment = await MarineAssessmentService(
        evidence_service=evidence_service, now=lambda: NOW
    ).assess(
        AssessmentRequest(
            latitude=20.5,
            longitude=72.9,
            at=NOW,
            operational_limits={"maximum_significant_wave_height_m": 2.0},
        )
    )
    pfz = await nearest_service(now=NOW).get_nearest(
        latitude=21.6417, longitude=69.6293, at=NOW
    )
    return pfz, evidence, assessment


def request_for(intent):
    values = {
        "message": str(intent),
        "latitude": 20.5,
        "longitude": 72.9,
        "requested_time": NOW,
    }
    if intent == "operational_conditions":
        values["operational_limits"] = {"maximum_significant_wave_height_m": 2.0}
    return AssistantRequest.model_validate(values)


@pytest.mark.parametrize(
    ("intent", "called"),
    [
        ("nearest_pfz", "pfz"),
        ("marine_conditions", "evidence"),
        ("operational_conditions", "assessment"),
        ("source_explanation", None),
    ],
)
async def test_each_available_intent_routes_only_to_required_service(intent, called):
    pfz, evidence, assessment = await service_results()
    pfz_service = FakeService("get_nearest", pfz)
    evidence_service = FakeService("aggregate", evidence)
    assessment_service = FakeService("assess", assessment)
    previous = {
        "waves": {
            "source": "waves",
            "state": "available",
            "provider": "saved provider",
        }
    }
    persistence = MemoryPersistence(previous_sources=previous)
    graph = ORCAAssistantGraph(
        router=FixedRouter(intent),
        persistence=persistence,
        services=AssistantServices(pfz_service, evidence_service, assessment_service),
        model=None,
        now=lambda: NOW,
    )
    request = request_for(intent)
    if intent == "source_explanation":
        request = request.model_copy(update={"conversation_id": uuid4()})
    result = await graph.query(request)

    assert result.detected_intent == intent
    assert result.capability_status == "available"
    assert len(pfz_service.calls) == int(called == "pfz")
    assert len(evidence_service.calls) == int(called == "evidence")
    assert len(assessment_service.calls) == int(called == "assessment")
    assert persistence.finalized[0]["intent"] == intent
    assert persistence.failed == []


async def test_nearest_pfz_with_limits_reuses_existing_e3_journey_service():
    journey, _, _ = await journey_service()
    journey_result = await journey.run(journey_request())
    journey_boundary = FakeService("run", journey_result)
    direct_pfz = FakeService("get_nearest", None)
    graph = ORCAAssistantGraph(
        router=FixedRouter("nearest_pfz"),
        persistence=MemoryPersistence(),
        services=AssistantServices(
            direct_pfz,
            None,
            None,
            pfz_journey=journey_boundary,
        ),
        model=None,
        now=lambda: NOW,
    )

    result = await graph.query(
        AssistantRequest(
            message="Find the nearest PFZ and compare my wave limit",
            latitude=21.6417,
            longitude=69.6293,
            requested_time=NOW,
            operational_limits={"maximum_significant_wave_height_m": 2.0},
        )
    )

    assert result.evidence_summary.assessment_outcome == "WITHIN_CONFIGURED_LIMITS"
    assert result.geojson is not None
    assert len(journey_boundary.calls) == 1
    assert direct_pfz.calls == []


async def test_marine_evidence_with_limits_uses_e2_without_a_second_provider_call():
    evidence = await critical_bundle()
    evidence_service = FakeService("aggregate", evidence)
    assessment_service = MarineAssessmentService(
        evidence_service=evidence_service,
        now=lambda: NOW,
    )
    graph = ORCAAssistantGraph(
        router=FixedRouter("marine_conditions"),
        persistence=MemoryPersistence(),
        services=AssistantServices(None, evidence_service, assessment_service),
        model=None,
        now=lambda: NOW,
    )

    result = await graph.query(
        AssistantRequest(
            message="Show conditions against my wave limit",
            latitude=20.5,
            longitude=72.9,
            requested_time=NOW,
            operational_limits={"maximum_significant_wave_height_m": 2.0},
        )
    )

    assert result.evidence_summary.assessment_outcome == "WITHIN_CONFIGURED_LIMITS"
    assert len(evidence_service.calls) == 1


async def test_missing_information_returns_clarification_without_service_call():
    services = [
        FakeService("get_nearest", None),
        FakeService("aggregate", None),
        FakeService("assess", None),
    ]
    persistence = MemoryPersistence()
    graph = ORCAAssistantGraph(
        router=FixedRouter("operational_conditions"),
        persistence=persistence,
        services=AssistantServices(*services),
        model=None,
        now=lambda: NOW,
    )
    result = await graph.query(AssistantRequest(message="Is it within my limits?"))
    assert result.completion_status == "clarification_required"
    assert result.required_information == (
        "location",
        "requested_time",
        "operational_limits",
    )
    assert all(not service.calls for service in services)


async def test_conversation_continuation_reuses_previous_intent_without_guessing():
    pfz, _, _ = await service_results()
    pfz_service = FakeService("get_nearest", pfz)
    graph = ORCAAssistantGraph(
        router=FixedRouter("unsupported"),
        persistence=MemoryPersistence(previous_intent=AssistantIntent.NEAREST_PFZ),
        services=AssistantServices(pfz_service, None, None),
        model=None,
        now=lambda: NOW,
    )
    result = await graph.query(
        AssistantRequest(
            conversation_id=uuid4(),
            message="Use these structured coordinates",
            latitude=21.6417,
            longitude=69.6293,
        )
    )

    assert result.detected_intent == "nearest_pfz"
    assert result.completion_status == "completed"
    assert len(pfz_service.calls) == 1


@pytest.mark.parametrize(
    "intent",
    [
        "official_alerts",
        "habitat_screening",
        "productivity_analysis",
        "lower_risk_route",
        "avoidance_zones",
    ],
)
async def test_planned_capability_never_invokes_service_or_claims_availability(intent):
    services = [
        FakeService("get_nearest", None),
        FakeService("aggregate", None),
        FakeService("assess", None),
    ]
    graph = ORCAAssistantGraph(
        router=FixedRouter(intent),
        persistence=MemoryPersistence(),
        services=AssistantServices(*services),
        model=None,
        now=lambda: NOW,
    )
    result = await graph.query(request_for(intent))
    assert result.capability_status in {"planned", "planned_or_partial"}
    assert result.completion_status == "capability_not_available"
    assert result.geofences_evaluated is False
    assert all(not service.calls for service in services)
    assert "safe route" not in result.answer.casefold()


async def test_planned_capability_does_not_request_unusable_parameters():
    graph = ORCAAssistantGraph(
        router=FixedRouter("official_alerts"),
        persistence=MemoryPersistence(),
        services=AssistantServices(None, None, None),
        model=None,
        now=lambda: NOW,
    )
    result = await graph.query(AssistantRequest(message="Any official alerts?"))

    assert result.completion_status == "capability_not_available"
    assert result.capability_status == "planned_or_partial"
    assert "not available" in result.answer.casefold()


async def test_router_failure_uses_deterministic_fallback_without_model_change():
    class FailingRouter:
        async def route(self, request):
            raise GeminiRouterError(
                "ASSISTANT_ROUTER_RATE_LIMITED",
                retryable=True,
                retry_after_seconds=30,
            )

    pfz, _, _ = await service_results()
    graph = ORCAAssistantGraph(
        router=FallbackIntentRouter(FailingRouter(), DeterministicIntentRouter()),
        persistence=MemoryPersistence(),
        services=AssistantServices(FakeService("get_nearest", pfz), None, None),
        model="gemini-3.7-flash",
        now=lambda: NOW,
    )
    result = await graph.query(
        AssistantRequest(
            message="Where is the nearest PFZ?",
            latitude=21.6417,
            longitude=69.6293,
        )
    )
    assert result.routing_mode == "deterministic_fallback"
    assert result.model is None
    assert result.warnings[0].code == "ASSISTANT_ROUTER_RATE_LIMITED"
    assert result.warnings[0].retry_after_seconds == 30


@pytest.mark.parametrize(
    ("message", "language", "intent"),
    [
        ("Where is the nearest PFZ?", "en", "nearest_pfz"),
        ("आज मेरे पास सबसे नज़दीकी पीएफ़ज़ेड कहाँ है?", "hi", "nearest_pfz"),
        ("મારી નજીક સમુદ્રની સ્થિતિ કેવી છે?", "gu", "marine_conditions"),
    ],
)
async def test_multilingual_deterministic_routing(message, language, intent):
    router = DeterministicIntentRouter()
    outcome = await router.route(
        AssistantRequest(message=message, preferred_language=language)
    )
    assert outcome.routing.intent == intent
    assert "location" in outcome.routing.required_information


async def test_demonstration_is_explicit_and_calls_no_scientific_service():
    services = [
        FakeService("get_nearest", None),
        FakeService("aggregate", None),
        FakeService("assess", None),
    ]
    graph = ORCAAssistantGraph(
        router=FixedRouter("unsupported"),
        persistence=MemoryPersistence(),
        services=AssistantServices(*services),
        model=None,
        now=lambda: NOW,
    )
    result = await graph.query(
        AssistantRequest(message="Load demo", mode="demonstration")
    )
    assert result.routing_mode == "demonstration_fixture"
    assert result.demonstration.label == "Demonstration Snapshot"
    assert all(not service.calls for service in services)
    assert "not live" in result.warnings[0].message


async def test_service_call_limit_is_enforced_before_provider_invocation():
    graph = ORCAAssistantGraph(
        router=FixedRouter("nearest_pfz"),
        persistence=MemoryPersistence(),
        services=AssistantServices(FakeService("get_nearest", None), None, None),
        model=None,
        max_scientific_service_calls=4,
        now=lambda: NOW,
    )
    with pytest.raises(AssistantExecutionError, match="service-call limit"):
        await graph._deterministic_service_node(
            {
                "request": request_for("nearest_pfz"),
                "routing_outcome": await FixedRouter("nearest_pfz").route(
                    request_for("nearest_pfz")
                ),
                "service_call_count": 4,
                "step_count": 3,
                "previous_sources": {},
            }
        )


async def test_request_cancellation_propagates_and_marks_run_cancelled():
    started = asyncio.Event()

    class BlockingPFZ:
        async def get_nearest(self, **kwargs):
            del kwargs
            started.set()
            await asyncio.Event().wait()

    persistence = MemoryPersistence()
    graph = ORCAAssistantGraph(
        router=FixedRouter("nearest_pfz"),
        persistence=persistence,
        services=AssistantServices(BlockingPFZ(), None, None),
        model=None,
        now=lambda: NOW,
    )
    task = asyncio.create_task(
        graph.query(
            AssistantRequest(
                message="Nearest PFZ",
                latitude=20.5,
                longitude=72.9,
            )
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert persistence.finalized == []
    assert persistence.failed[0]["error_code"] == "ASSISTANT_REQUEST_CANCELLED"
    assert persistence.failed[0]["cancelled"] is True


async def test_provider_exception_details_are_not_returned_or_persisted():
    persistence = MemoryPersistence()
    failure = RuntimeError(
        "password=do-not-return https://provider.invalid/private?token=secret"
    )
    graph = ORCAAssistantGraph(
        router=FixedRouter("nearest_pfz"),
        persistence=persistence,
        services=AssistantServices(FakeService("get_nearest", failure), None, None),
        model=None,
        now=lambda: NOW,
    )
    result = await graph.query(
        AssistantRequest(
            message="Nearest PFZ",
            latitude=20.5,
            longitude=72.9,
        )
    )

    serialized = result.model_dump_json()
    persisted = str(persistence.finalized)
    assert result.completion_status == "failed"
    assert "do-not-return" not in serialized
    assert "provider.invalid" not in serialized
    assert "do-not-return" not in persisted
    assert "provider.invalid" not in persisted
    assert persistence.finalized[0]["run_status"].value == "failed"


def test_request_rejects_partial_coordinates_and_naive_time():
    with pytest.raises(ValueError):
        AssistantRequest(message="conditions", latitude=20.5)
    with pytest.raises(ValueError):
        AssistantRequest(message="conditions", requested_time="2026-08-27T12:00:00")


def test_warning_sanitizer_removes_urls_secrets_and_local_paths():
    sanitized = safe_message(
        "https://provider.invalid/private token=hidden C:\\Users\\person\\secret.json"
    )
    assert "provider.invalid" not in sanitized
    assert "hidden" not in sanitized
    assert "person" not in sanitized
