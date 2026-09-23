from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any

from app.services.geospatial import line_intersects_polygon, point_to_segment_distance_km
from app.schemas.assessment import (
    AssessmentOutcome,
    AssessmentReason,
    EvidenceConfidence,
    OperationalLimits,
    OperationalRuleResult,
    RuleEvidenceQuality,
    RuleOutcome,
)
from app.schemas.evidence import EvidenceItem, EvidenceState, MarineEvidenceResponse
from app.schemas.marine import ECMWFWindForecastResponse, WindResponse


OFFICIAL_WARNING_NOTICE = (
    "Official meteorological and maritime warnings are not integrated. "
    "Verify current authority-issued advisories before making "
    "operational decisions."
)
ASSESSMENT_NOTICE = (
    "Within configured limits is not a navigation approval or a statement that "
    "all marine hazards are absent."
)


@dataclass(frozen=True)
class _RuleDefinition:
    rule_id: str
    parameter: str
    unit: str
    evidence_name: str
    exceeded_code: str
    near_code: str
    missing_code: str


RULES = (
    _RuleDefinition(
        "wave_height_limit",
        "significant_wave_height",
        "m",
        "waves",
        "WAVE_LIMIT_EXCEEDED",
        "WAVE_NEAR_LIMIT",
        "WAVE_EVIDENCE_MISSING",
    ),
    _RuleDefinition(
        "wind_speed_limit",
        "wind_speed",
        "m/s",
        "wind",
        "WIND_LIMIT_EXCEEDED",
        "WIND_NEAR_LIMIT",
        "WIND_EVIDENCE_MISSING",
    ),
    _RuleDefinition(
        "surface_current_limit",
        "total_surface_current_speed",
        "m/s",
        "currents",
        "CURRENT_LIMIT_EXCEEDED",
        "CURRENT_NEAR_LIMIT",
        "CURRENT_EVIDENCE_MISSING",
    ),
)


@dataclass(frozen=True)
class RuleEvaluation:
    outcome: AssessmentOutcome
    evidence_confidence: EvidenceConfidence
    rules: tuple[OperationalRuleResult, ...]
    reasons: tuple[AssessmentReason, ...]
    missing_critical_evidence: tuple[str, ...]


def _limit_for(definition: _RuleDefinition, limits: OperationalLimits) -> float | None:
    return {
        "waves": limits.maximum_significant_wave_height_m,
        "wind": limits.maximum_wind_speed_m_s,
        "currents": limits.maximum_surface_current_speed_m_s,
    }[definition.evidence_name]


def _measurement(
    definition: _RuleDefinition,
    item: EvidenceItem,
) -> tuple[float | None, str | None, datetime | None]:
    data = item.data
    if data is None:
        return None, None, None
    if definition.evidence_name == "waves":
        return data.significant_wave_height.value, "copernicus_marine", data.valid_time
    if definition.evidence_name == "wind":
        if isinstance(data, WindResponse):
            return data.wind_speed.value, "copernicus_marine", data.valid_time
        if isinstance(data, ECMWFWindForecastResponse):
            return data.wind_speed_mps, "ecmwf", data.valid_time
        return None, None, None
    return data.total_current.speed_mps, "copernicus_marine", data.valid_time


def _individual_outcome(
    value: float,
    limit: float,
    near_limit_percentage: float | None,
) -> RuleOutcome:
    if value > limit:
        return RuleOutcome.EXCEEDED
    if value == limit:
        return RuleOutcome.WITHIN_LIMIT
    if near_limit_percentage is not None:
        lower_bound = limit * (1.0 - near_limit_percentage / 100.0)
        if value >= lower_bound:
            return RuleOutcome.NEAR_LIMIT
    return RuleOutcome.WITHIN_LIMIT


def evaluate_operational_limits(
    evidence: MarineEvidenceResponse,
    limits: OperationalLimits,
    near_limit_percentage: float | None,
) -> RuleEvaluation:
    results: list[OperationalRuleResult] = []
    reasons: list[AssessmentReason] = []
    missing: list[str] = []

    for definition in RULES:
        limit = _limit_for(definition, limits)
        if limit is None:
            continue
        item = getattr(evidence.evidence, definition.evidence_name)
        usable = item.state in {EvidenceState.AVAILABLE, EvidenceState.DEGRADED}
        value, source, valid_time = _measurement(definition, item) if usable else (None, None, None)
        if value is None or not math.isfinite(value):
            value = None
            source = None
            valid_time = None
            outcome = RuleOutcome.UNKNOWN
            quality = RuleEvidenceQuality.INSUFFICIENT
            missing.append(definition.evidence_name)
            reasons.append(AssessmentReason(
                code=definition.missing_code,
                message=f"{definition.evidence_name.title()} evidence required by the configured limit is unavailable.",
                rule_id=definition.rule_id,
                evidence_item=definition.evidence_name,
            ))
        else:
            outcome = _individual_outcome(value, limit, near_limit_percentage)
            quality = (
                RuleEvidenceQuality.DEGRADED
                if item.state == EvidenceState.DEGRADED
                else RuleEvidenceQuality.NORMAL
            )
            if outcome == RuleOutcome.EXCEEDED:
                reasons.append(AssessmentReason(
                    code=definition.exceeded_code,
                    message=f"{definition.parameter.replace('_', ' ').title()} exceeds the configured limit.",
                    rule_id=definition.rule_id,
                ))
            elif outcome == RuleOutcome.NEAR_LIMIT:
                reasons.append(AssessmentReason(
                    code=definition.near_code,
                    message=f"{definition.parameter.replace('_', ' ').title()} is within the configured near-limit band.",
                    rule_id=definition.rule_id,
                ))
            if quality == RuleEvidenceQuality.DEGRADED:
                reasons.append(AssessmentReason(
                    code="EVIDENCE_DEGRADED",
                    message=f"Evidence for {definition.parameter.replace('_', ' ')} is degraded.",
                    rule_id=definition.rule_id,
                    evidence_item=definition.evidence_name,
                ))
        results.append(OperationalRuleResult(
            rule_id=definition.rule_id,
            parameter=definition.parameter,
            observed_value=value,
            unit=definition.unit,
            configured_limit=limit,
            outcome=outcome,
            evidence_source=source,
            evidence_valid_time=valid_time,
            evidence_quality=quality,
        ))

    outcomes = {result.outcome for result in results}
    if not results:
        aggregate = AssessmentOutcome.POLICY_NOT_CONFIGURED
        confidence = EvidenceConfidence.INSUFFICIENT
    elif RuleOutcome.EXCEEDED in outcomes:
        aggregate = AssessmentOutcome.LIMIT_EXCEEDED
        confidence = (
            EvidenceConfidence.INSUFFICIENT
            if RuleOutcome.UNKNOWN in outcomes
            else EvidenceConfidence.DEGRADED
            if any(result.evidence_quality == RuleEvidenceQuality.DEGRADED for result in results)
            else EvidenceConfidence.NORMAL
        )
    elif RuleOutcome.UNKNOWN in outcomes:
        aggregate = AssessmentOutcome.INSUFFICIENT_EVIDENCE
        confidence = EvidenceConfidence.INSUFFICIENT
    elif RuleOutcome.NEAR_LIMIT in outcomes:
        aggregate = AssessmentOutcome.CAUTION
        confidence = (
            EvidenceConfidence.DEGRADED
            if any(result.evidence_quality == RuleEvidenceQuality.DEGRADED for result in results)
            else EvidenceConfidence.NORMAL
        )
    else:
        aggregate = AssessmentOutcome.WITHIN_CONFIGURED_LIMITS
        confidence = (
            EvidenceConfidence.DEGRADED
            if any(result.evidence_quality == RuleEvidenceQuality.DEGRADED for result in results)
            else EvidenceConfidence.NORMAL
        )

    reasons.append(AssessmentReason(
        code="OFFICIAL_WARNINGS_NOT_INTEGRATED",
        message=OFFICIAL_WARNING_NOTICE,
        evidence_item="official_warnings",
    ))
    return RuleEvaluation(
        outcome=aggregate,
        evidence_confidence=confidence,
        rules=tuple(results),
        reasons=tuple(reasons),
        missing_critical_evidence=tuple(missing),
    )


def apply_official_imd_warnings(
    base_evaluation: RuleEvaluation,
    port_warning_signals: list[int] | None = None,
    fishermen_warning_active: bool = False,
    cyclone_warning_active: bool = False,
    warning_details: str | None = None,
) -> RuleEvaluation:
    """Deterministically applies official IMD warnings.
    
    In accordance with AGENTS.md Rule 7: An active official warning must take precedence
    over a favorable model-derived score.
    """
    severe_signals = [sig for sig in (port_warning_signals or []) if sig >= 3]
    has_veto = bool(severe_signals or fishermen_warning_active or cyclone_warning_active)

    if not has_veto:
        return base_evaluation

    new_reasons = list(base_evaluation.reasons)
    # Remove the placeholder disclaimer if official warnings are now integrated
    new_reasons = [r for r in new_reasons if r.code != "OFFICIAL_WARNINGS_NOT_INTEGRATED"]

    if cyclone_warning_active:
        new_reasons.insert(0, AssessmentReason(
            code="OFFICIAL_IMD_CYCLONE_WARNING",
            message=warning_details or "Active IMD Cyclone Cone or Warning in sea corridor. Operation not recommended.",
            evidence_item="imd_cyclone",
        ))
    elif fishermen_warning_active:
        new_reasons.insert(0, AssessmentReason(
            code="OFFICIAL_IMD_FISHERMEN_WARNING",
            message=warning_details or "Official IMD bulletin: Fishermen advised NOT to venture into deep sea.",
            evidence_item="imd_coastal_bulletin",
        ))
    elif severe_signals:
        max_sig = max(severe_signals)
        new_reasons.insert(0, AssessmentReason(
            code="OFFICIAL_IMD_PORT_WARNING",
            message=warning_details or f"Port Danger Signal {max_sig} hoisted by IMD. Squally or severe weather active.",
            evidence_item="imd_port_warning",
        ))

    return RuleEvaluation(
        outcome=AssessmentOutcome.LIMIT_EXCEEDED,
        evidence_confidence=base_evaluation.evidence_confidence,
        rules=base_evaluation.rules,
        reasons=tuple(new_reasons),
        missing_critical_evidence=base_evaluation.missing_critical_evidence,
    )


@dataclass(frozen=True)
class CorridorHazardEvaluation:
    vetoed: bool
    veto_code: str | None
    veto_message: str | None
    hazard_title: str | None
    distance_km: float | None = None


def evaluate_corridor_imd_hazards(
    origin_lon: float,
    origin_lat: float,
    destination_lon: float,
    destination_lat: float,
    hazard_features: list[dict] | list[Any],
    port_proximity_buffer_km: float = 25.0,
) -> CorridorHazardEvaluation:
    """Deterministically checks if a navigation line intersects active official IMD hazards.
    
    1. Cyclone cone polygons: Vetoes if line intersects or endpoints lie inside the cone.
    2. Severe port warnings: Vetoes if any port with signal >= 3 lies within `port_proximity_buffer_km` (default 25km) of the corridor.
    """
    line = [(origin_lon, origin_lat), (destination_lon, destination_lat)]

    for feature in hazard_features:
        if hasattr(feature, "geometry"):
            geom = feature.geometry if isinstance(feature.geometry, dict) else feature.geometry.model_dump()
            props = feature.properties if isinstance(feature.properties, dict) else feature.properties.model_dump()
        elif isinstance(feature, dict):
            geom = feature.get("geometry", {})
            props = feature.get("properties", {})
        else:
            continue

        geom_type = geom.get("type")
        hazard_type = props.get("hazard_type")
        title = props.get("title", "Official IMD Hazard")

        # 1. Cyclone Cone Polygon
        if geom_type in ("Polygon", "MultiPolygon") or hazard_type == "cyclone_cone":
            if line_intersects_polygon(line, geom):
                return CorridorHazardEvaluation(
                    vetoed=True,
                    veto_code="OFFICIAL_IMD_CYCLONE_WARNING",
                    veto_message=f"Navigation corridor intersects {title}. Severe cyclonic conditions active.",
                    hazard_title=title,
                )

        # 2. Port Warning Points
        elif geom_type == "Point" or hazard_type == "port_warning":
            coords = geom.get("coordinates")
            signal_num = props.get("signal_number", 0)
            if coords and len(coords) >= 2 and signal_num >= 3:
                port_lon, port_lat = float(coords[0]), float(coords[1])
                dist_km = point_to_segment_distance_km(
                    port_lon, port_lat, origin_lon, origin_lat, destination_lon, destination_lat
                )
                if dist_km <= port_proximity_buffer_km:
                    return CorridorHazardEvaluation(
                        vetoed=True,
                        veto_code="OFFICIAL_IMD_PORT_WARNING",
                        veto_message=(
                            f"Navigation corridor passes within {dist_km:.1f} km of {title} (Signal {signal_num}). "
                            "Squally or dangerous sea conditions active."
                        ),
                        hazard_title=title,
                        distance_km=dist_km,
                    )

    return CorridorHazardEvaluation(
        vetoed=False,
        veto_code=None,
        veto_message=None,
        hazard_title=None,
    )


