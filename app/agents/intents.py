from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import SecretStr, ValidationError

from app.agents.capabilities import AssistantIntent
from app.schemas.assistant import (
    AssistantRequest,
    AssistantWarning,
    IntentRoutingResult,
    RequiredInformation,
    RoutingMode,
)


@dataclass(frozen=True, slots=True)
class RouterOutcome:
    routing: IntentRoutingResult
    mode: RoutingMode
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    warning: AssistantWarning | None = None


class IntentRouter(Protocol):
    async def route(self, request: AssistantRequest) -> RouterOutcome:
        """Return intent data only; capability availability is application-owned."""


class IntentRouterNotConfigured(RuntimeError):
    pass


class GeminiRouterError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__("The assistant intent router is unavailable")
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class GeminiRouterOutputError(GeminiRouterError):
    def __init__(self) -> None:
        super().__init__("ASSISTANT_ROUTER_INVALID_OUTPUT", retryable=False)


def required_information_for(
    request: AssistantRequest, intent: AssistantIntent
) -> tuple[RequiredInformation, ...]:
    required: list[RequiredInformation] = []
    location_required = intent in {
        AssistantIntent.NEAREST_PFZ,
        AssistantIntent.MARINE_CONDITIONS,
        AssistantIntent.OPERATIONAL_CONDITIONS,
        AssistantIntent.OFFICIAL_ALERTS,
        AssistantIntent.HABITAT_SCREENING,
        AssistantIntent.LOWER_RISK_ROUTE,
        AssistantIntent.PRODUCTIVITY_ANALYSIS,
        AssistantIntent.AVOIDANCE_ZONES,
    }
    if location_required and request.latitude is None:
        required.append(RequiredInformation.LOCATION)
    if (
        intent == AssistantIntent.OPERATIONAL_CONDITIONS
        and request.requested_time is None
    ):
        required.append(RequiredInformation.REQUESTED_TIME)
    if (
        intent == AssistantIntent.OPERATIONAL_CONDITIONS
        and request.operational_limits.supplied_count() == 0
    ):
        required.append(RequiredInformation.OPERATIONAL_LIMITS)
    return tuple(required)


def validated_required_information(
    request: AssistantRequest,
    intent: AssistantIntent,
    proposed: tuple[RequiredInformation, ...],
) -> tuple[RequiredInformation, ...]:
    """Accept only canonical fields that are genuinely absent from the request."""
    if intent != AssistantIntent.CLARIFICATION_REQUIRED:
        return required_information_for(request, intent)
    genuinely_missing = {
        RequiredInformation.LOCATION: request.latitude is None,
        RequiredInformation.REQUESTED_TIME: request.requested_time is None,
        RequiredInformation.OPERATIONAL_LIMITS: (
            request.operational_limits.supplied_count() == 0
        ),
    }
    proposed_set = set(proposed)
    return tuple(
        field
        for field in RequiredInformation
        if field in proposed_set and genuinely_missing[field]
    )


class DeterministicIntentRouter:
    """Conservative multilingual fallback for obvious supported requests."""

    _KEYWORDS: tuple[tuple[AssistantIntent, tuple[str, ...]], ...] = (
        (
            AssistantIntent.SOURCE_EXPLANATION,
            (
                "source",
                "provider",
                "dataset",
                "provenance",
                "evidence support",
                "explain source",
                "explain evidence",
                "data source",
                "स्रोत",
                "डेटासेट",
                "સ્ત્રોત",
                "ડેટાસેટ",
            ),
        ),
        (
            AssistantIntent.OFFICIAL_ALERTS,
            (
                "cyclone",
                "lightning",
                "official alert",
                "official warning",
                "चक्रवात",
                "बिजली",
                "ચક્રવાત",
                "વીજળી",
            ),
        ),
        (
            AssistantIntent.LOWER_RISK_ROUTE,
            (
                "safest route",
                "lower-risk route",
                "lower risk route",
                "safe route",
                "सुरक्षित मार्ग",
                "સલામત માર્ગ",
            ),
        ),
        (
            AssistantIntent.AVOIDANCE_ZONES,
            (
                "avoidance zone",
                "zones should be avoided",
                "restricted zone",
                "prohibited zone",
                "प्रतिबंधित क्षेत्र",
                "પ્રતિબંધિત વિસ્તાર",
            ),
        ),
        (
            AssistantIntent.PRODUCTIVITY_ANALYSIS,
            (
                "productivity declined",
                "historical productivity",
                "fish productivity",
                "उत्पादकता",
                "ઉત્પાદકતા",
            ),
        ),
        (
            AssistantIntent.HABITAT_SCREENING,
            (
                "favourable sst",
                "favorable sst",
                "high chlorophyll",
                "habitat screening",
                "क्लोरोफिल",
                "ક્લોરોફિલ",
            ),
        ),
        (
            AssistantIntent.NEAREST_PFZ,
            (
                "pfz",
                "potential fishing zone",
                "fishing zone",
                "fishing area",
                "nearest pfz",
                "find pfz",
                "where to fish",
                "best fishing",
                "fish zone",
                "fish",
                "fishing",
                "पीएफजेड",
                "पीएफ़ज़ेड",
                "पीएफ़ज़ेड",
                "पीएफ़जेड",
                "मछली पकड़ने",
                "मत्स्य क्षेत्र",
                "मछली",
                "પીએફઝેડ",
                "માછીમારી",
                "દરિયામાં માછલી",
                "मासेमारी क्षेत्र",
                "मासेमारी",
                "मासे",
                "पीएफझेड",
                "மீன்பிடி மண்டலம்",
                "மீன்பிடி",
                "மீன் பிடிக்கும்",
                "பி.எஃப்.இசட்",
                "பிஎப்இசட்",
                "చేపల వేట జోన్",
                "చేపల వేట",
                "చేపలు",
                "పి.ఎఫ్.జెడ్",
                "పిఎఫ్జెడ్",
                "മത്സ്യബന്ധന മേഖല",
                "മത്സ്യബന്ധനം",
                "മീൻപിടുത്തം",
                "പി.എഫ്.ഇസഡ്",
                "പിഎഫ്ഇസഡ്",
                "মাছ ধরার এলাকা",
                "মাছ ধরার অঞ্চল",
                "মৎস্য অঞ্চল",
                "পিএফজেড",
            ),
        ),
        (
            AssistantIntent.OPERATIONAL_CONDITIONS,
            (
                "configured limit",
                "vessel limit",
                "limit exceeded",
                "within my limit",
                "safe to venture",
                "operational condition",
                "assess limit",
                "check limit",
                "operational limit",
                "जहाज की सीमा",
                "सीमा",
                "सुरक्षित",
                "સીમા ઓળંગે",
                "મર્યાદા",
                "સલામત",
                "मर्यादा",
                "बोटीची मर्यादा",
                "வரம்பு",
                "பாதுகாப்பான",
                "పరిమితి",
                "సురక్షితం",
                "പരിധി",
                "സുരക്ഷിതം",
                "সীমা",
                "নিরাপদ",
            ),
        ),
        (
            AssistantIntent.MARINE_CONDITIONS,
            (
                "marine condition",
                "sea condition",
                "ocean condition",
                "tide and sea",
                "marine weather",
                "ocean weather",
                "sea weather",
                "sea state",
                "ocean state",
                "wave",
                "waves",
                "wind",
                "winds",
                "current",
                "currents",
                "sst",
                "water temp",
                "sea temperature",
                "water condition",
                "check condition",
                "check marine",
                "conditions",
                "weather",
                "समुद्र की स्थिति",
                "समुद्री स्थिति",
                "समुद्र",
                "लहरें",
                "मौसम",
                "સમુદ્રની સ્થિતિ",
                "દરિયાની સ્થિતિ",
                "દરિયો",
                "મોજાં",
                "સાબરી परिस्थिती",
                "सागरी परिस्थिती",
                "लाटा",
                "கடல் நிலை",
                "கடல் வானிலை",
                "கடல்",
                "அலைகள்",
                "சముద్ర పరిస్థితులు",
                "సముద్ర పరిస్థితులు",
                "సముద్రం",
                "సముద్ర వాతావరణం",
                "സമുദ്ര സാഹചര്യങ്ങൾ",
                "സമുദ്ര കാലാവസ്ഥ",
                "കടൽ",
                "തിരമാലകൾ",
                "সামুদ্রিক অবস্থা",
                "সমুদ্রের আবহাওয়া",
                "সমুদ্র",
                "ঢেউ",
            ),
        ),
    )

    async def route(self, request: AssistantRequest) -> RouterOutcome:
        normalized = " ".join(request.message.casefold().split())
        intent = AssistantIntent.UNSUPPORTED
        for candidate, keywords in self._KEYWORDS:
            if any(keyword in normalized for keyword in keywords):
                intent = candidate
                break
        required = required_information_for(request, intent)
        if required and intent == AssistantIntent.UNSUPPORTED:
            intent = AssistantIntent.CLARIFICATION_REQUIRED
        return RouterOutcome(
            routing=IntentRoutingResult(
                intent=intent,
                confidence=0.95 if intent != AssistantIntent.UNSUPPORTED else 0.0,
                required_information=required,
            ),
            mode=RoutingMode.DETERMINISTIC,
        )


class GeminiFunctionIntentRouter:
    """Gemini Developer API router constrained to one forced function call."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str = "gemini-3.7-flash",
        timeout_seconds: float = 20.0,
        chat_model: Any | None = None,
        enable_cache: bool = True,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.enable_cache = enable_cache
        self._cache: dict[str, RouterOutcome] = {}
        if chat_model is None:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError:
                raise IntentRouterNotConfigured(
                    "Gemini routing dependency is not installed"
                ) from None
            chat_kwargs: dict[str, Any] = {
                "model": model,
                "google_api_key": api_key.get_secret_value(),
                "vertexai": False,
                "temperature": 0,
                "max_retries": 0,
                "timeout": timeout_seconds,
                "max_output_tokens": 150,
            }
            # Disable thinking reasoning tokens to minimize token usage and avoid rate limits
            try:
                chat_model = ChatGoogleGenerativeAI(**chat_kwargs, thinking_budget=0)
            except (TypeError, ValueError):
                chat_model = ChatGoogleGenerativeAI(**chat_kwargs)
        tool = {
            "name": "route_request",
            "description": "Classify an ORCA request; never provide evidence or availability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": [intent.value for intent in AssistantIntent],
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "required_information": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [item.value for item in RequiredInformation],
                        },
                        "maxItems": 3,
                    },
                },
                "required": [
                    "intent",
                    "confidence",
                    "required_information",
                ],
            },
        }
        self._bound = chat_model.bind_tools([tool], tool_choice="route_request")

    async def route(self, request: AssistantRequest) -> RouterOutcome:
        cache_key = (
            f"{request.message.strip().lower()}|"
            f"loc={request.latitude is not None}|"
            f"time={request.requested_time is not None}|"
            f"limits={request.operational_limits.supplied_count() > 0}"
        )
        if self.enable_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            return RouterOutcome(
                routing=cached.routing,
                mode=cached.mode,
                model=cached.model,
                input_tokens=0,
                output_tokens=0,
            )

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError:
            raise IntentRouterNotConfigured(
                "LangChain core dependency is not installed"
            ) from None
        policy = (
            "Invoke route_request exactly once. Classify intent only. Use only canonical "
            "required-information identifiers. Do not invent coordinates, measurements, "
            "alerts, evidence, or capability availability."
        )
        context = (
            f"location_supplied={request.latitude is not None}; "
            f"requested_time_supplied={request.requested_time is not None}; "
            f"operational_limits_supplied={request.operational_limits.supplied_count() > 0}.\n"
            f"User request: {request.message}"
        )
        try:
            async with asyncio.timeout(self.timeout_seconds):
                message = await self._bound.ainvoke(
                    [SystemMessage(content=policy), HumanMessage(content=context)]
                )
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise GeminiRouterError("ASSISTANT_ROUTER_TIMEOUT", retryable=True) from exc
        except Exception as exc:  # noqa: BLE001 - provider exceptions are sanitized
            raise _map_gemini_error(exc) from None

        calls = getattr(message, "tool_calls", None) or []
        if len(calls) != 1 or calls[0].get("name") != "route_request":
            raise GeminiRouterOutputError()
        try:
            routed = IntentRoutingResult.model_validate(calls[0].get("args"))
        except ValidationError:
            raise GeminiRouterOutputError() from None
        usage = getattr(message, "usage_metadata", None) or {}
        outcome = RouterOutcome(
            routing=routed,
            mode=RoutingMode.GEMINI,
            model=self.model,
            input_tokens=_safe_token(usage.get("input_tokens")),
            output_tokens=_safe_token(usage.get("output_tokens")),
        )
        if self.enable_cache:
            if len(self._cache) >= 256:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = outcome
        return outcome


def _safe_token(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _map_gemini_error(exc: BaseException) -> GeminiRouterError:
    current: BaseException | None = exc
    status_code: int | None = None
    for _ in range(8):
        if current is None:
            break
        candidate = getattr(current, "status_code", None) or getattr(
            current, "code", None
        )
        if isinstance(candidate, int):
            status_code = candidate
            break
        current = current.__cause__ or current.__context__

    exc_str = str(exc).upper()
    if (
        status_code == 429
        or "429" in exc_str
        or "RESOURCE_EXHAUSTED" in exc_str
        or "QUOTA" in exc_str
        or "RATE_LIMIT" in exc_str
    ):
        return GeminiRouterError(
            "ASSISTANT_ROUTER_RATE_LIMITED",
            retryable=True,
            retry_after_seconds=30,
        )
    if status_code in {401, 403} or "API_KEY" in exc_str or "UNAUTHENTICATED" in exc_str:
        return GeminiRouterError(
            "ASSISTANT_ROUTER_AUTHENTICATION_FAILED", retryable=False
        )
    if status_code == 503 or (status_code is not None and status_code >= 500):
        return GeminiRouterError("ASSISTANT_ROUTER_UNAVAILABLE", retryable=True)
    if status_code is not None and 400 <= status_code < 500:
        return GeminiRouterError("ASSISTANT_ROUTER_INVALID_REQUEST", retryable=False)
    return GeminiRouterError("ASSISTANT_ROUTER_UNAVAILABLE", retryable=True)


class FallbackIntentRouter:
    def __init__(self, primary: IntentRouter, fallback: IntentRouter) -> None:
        self.primary = primary
        self.fallback = fallback

    async def route(self, request: AssistantRequest) -> RouterOutcome:
        try:
            return await self.primary.route(request)
        except asyncio.CancelledError:
            raise
        except (GeminiRouterError, IntentRouterNotConfigured) as exc:
            outcome = await self.fallback.route(request)
            code = getattr(exc, "code", "ASSISTANT_ROUTER_NOT_CONFIGURED")
            retryable = bool(getattr(exc, "retryable", False))
            retry_after = getattr(exc, "retry_after_seconds", None)
            return RouterOutcome(
                routing=outcome.routing,
                mode=outcome.mode,
                warning=AssistantWarning(
                    code=code,
                    message=(
                        "Gemini intent routing was unavailable; a limited deterministic "
                        "router was used."
                    ),
                    retryable=retryable,
                    retry_after_seconds=retry_after,
                ),
            )


class StubIntentRouter:
    async def route(self, request: AssistantRequest) -> RouterOutcome:
        del request
        raise IntentRouterNotConfigured(
            "The production intent router is not configured"
        )
