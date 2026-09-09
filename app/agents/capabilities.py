from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class AssistantIntent(StrEnum):
    NEAREST_PFZ = "nearest_pfz"
    OPERATIONAL_CONDITIONS = "operational_conditions"
    MARINE_CONDITIONS = "marine_conditions"
    OFFICIAL_ALERTS = "official_alerts"
    HABITAT_SCREENING = "habitat_screening"
    LOWER_RISK_ROUTE = "lower_risk_route"
    PRODUCTIVITY_ANALYSIS = "productivity_analysis"
    AVOIDANCE_ZONES = "avoidance_zones"
    SOURCE_EXPLANATION = "source_explanation"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"


class CapabilityAvailability(StrEnum):
    AVAILABLE = "available"
    PLANNED_OR_PARTIAL = "planned_or_partial"
    PLANNED = "planned"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class Capability:
    intent: AssistantIntent
    availability: CapabilityAvailability
    service_boundary: str | None


_REGISTRY = {
    AssistantIntent.NEAREST_PFZ: Capability(
        AssistantIntent.NEAREST_PFZ,
        CapabilityAvailability.AVAILABLE,
        "PFZNearestService",
    ),
    AssistantIntent.MARINE_CONDITIONS: Capability(
        AssistantIntent.MARINE_CONDITIONS,
        CapabilityAvailability.AVAILABLE,
        "MarineEvidenceService",
    ),
    AssistantIntent.OPERATIONAL_CONDITIONS: Capability(
        AssistantIntent.OPERATIONAL_CONDITIONS,
        CapabilityAvailability.AVAILABLE,
        "MarineAssessmentService",
    ),
    AssistantIntent.SOURCE_EXPLANATION: Capability(
        AssistantIntent.SOURCE_EXPLANATION,
        CapabilityAvailability.AVAILABLE,
        "MarineEvidenceService",
    ),
    AssistantIntent.OFFICIAL_ALERTS: Capability(
        AssistantIntent.OFFICIAL_ALERTS,
        CapabilityAvailability.PLANNED_OR_PARTIAL,
        None,
    ),
    AssistantIntent.HABITAT_SCREENING: Capability(
        AssistantIntent.HABITAT_SCREENING,
        CapabilityAvailability.PLANNED_OR_PARTIAL,
        None,
    ),
    AssistantIntent.PRODUCTIVITY_ANALYSIS: Capability(
        AssistantIntent.PRODUCTIVITY_ANALYSIS,
        CapabilityAvailability.PLANNED_OR_PARTIAL,
        None,
    ),
    AssistantIntent.LOWER_RISK_ROUTE: Capability(
        AssistantIntent.LOWER_RISK_ROUTE,
        CapabilityAvailability.PLANNED,
        None,
    ),
    AssistantIntent.AVOIDANCE_ZONES: Capability(
        AssistantIntent.AVOIDANCE_ZONES,
        CapabilityAvailability.PLANNED,
        None,
    ),
    AssistantIntent.CLARIFICATION_REQUIRED: Capability(
        AssistantIntent.CLARIFICATION_REQUIRED,
        CapabilityAvailability.NOT_APPLICABLE,
        None,
    ),
    AssistantIntent.UNSUPPORTED: Capability(
        AssistantIntent.UNSUPPORTED,
        CapabilityAvailability.NOT_APPLICABLE,
        None,
    ),
}

CAPABILITY_REGISTRY: Mapping[AssistantIntent, Capability] = MappingProxyType(_REGISTRY)


def get_capability(intent: AssistantIntent) -> Capability:
    """Return application-owned availability; model claims are never accepted."""
    return CAPABILITY_REGISTRY[intent]
