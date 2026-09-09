from __future__ import annotations

from typing import Protocol

from app.schemas.assistant import AssistantRequest, IntentRoutingResult


class IntentRouter(Protocol):
    async def route(self, request: AssistantRequest) -> IntentRoutingResult:
        """Return intent data only; capability availability is application-owned."""


class IntentRouterNotConfigured(RuntimeError):
    pass


class StubIntentRouter:
    async def route(self, request: AssistantRequest) -> IntentRoutingResult:
        del request
        raise IntentRouterNotConfigured(
            "The production intent router is not configured"
        )
