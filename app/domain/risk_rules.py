from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

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
    "Official meteorological and maritime warnings are not integrated into this "
    "prototype. Verify current authority-issued advisories before making "
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
