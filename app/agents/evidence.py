from __future__ import annotations

import re
from typing import Any, cast

from app.schemas.assessment import MarineAssessmentResponse
from app.schemas.assistant import (
    AssistantEvidenceStatus,
    AssistantEvidenceSummary,
    AssistantSourceName,
    AssistantSourceState,
    AssistantSourceSummary,
    AssistantWarning,
)
from app.schemas.evidence import EvidenceItem, MarineEvidenceResponse
from app.schemas.pfz import NearestPFZResponse

SOURCE_NAMES: tuple[AssistantSourceName, ...] = (
    "pfz",
    "sst",
    "chlorophyll",
    "waves",
    "wind",
    "currents",
    "sea_level",
)


def safe_message(value: str) -> str:
    value = re.sub(r"https?://\S+", "[provider reference removed]", value)
    value = re.sub(
        r"(?i)(?:[a-z]:\\[^\s]+|/(?:users|home|tmp|var/tmp)/[^\s]+)",
        "[local path removed]",
        value,
    )
    value = re.sub(
        r"(?i)(token|password|secret|api[_-]?key)\s*[=:]\s*\S+",
        r"\1=[redacted]",
        value,
    )
    return value[:500]


def _value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def _source_summary(
    source: AssistantSourceName, item: EvidenceItem[Any]
) -> AssistantSourceSummary | None:
    if item.state.value == "not_requested":
        return None
    if item.data is None:
        return AssistantSourceSummary(
            source=source,
            state=cast(AssistantSourceState, item.state.value),
        )
    data = item.data.model_dump(mode="python")
    source_metadata = data.get("source")
    if not isinstance(source_metadata, dict):
        source_metadata = {}
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}
    valid_time = _value(data, "valid_time", "analysis_time", "forecast_valid_time")
    if source == "pfz":
        valid_time = data.get("valid_until")
    return AssistantSourceSummary(
        source=source,
        state=cast(AssistantSourceState, item.state.value),
        provider=_value(data, "provider") or source_metadata.get("name"),
        product_id=_value(data, "product_id") or source_metadata.get("product_id"),
        dataset_id=_value(data, "dataset_id") or source_metadata.get("dataset_id"),
        valid_time=valid_time,
        freshness=(
            str(_value(data, "cache_status", "freshness") or snapshot.get("status"))
            if _value(data, "cache_status", "freshness") or snapshot.get("status")
            else None
        ),
    )


def _item_warnings(
    source: AssistantSourceName, item: EvidenceItem[Any]
) -> tuple[AssistantWarning, ...]:
    if item.data is None:
        return ()
    values = getattr(item.data, "warnings", None) or []
    return tuple(
        AssistantWarning(
            code=f"{source.upper()}_EVIDENCE_WARNING",
            message=safe_message(str(value)),
        )
        for value in values[:10]
    )


def summarize_evidence(
    evidence: MarineEvidenceResponse,
) -> tuple[
    AssistantEvidenceSummary,
    tuple[AssistantSourceSummary, ...],
    tuple[AssistantWarning, ...],
]:
    summaries = tuple(
        summary
        for source in SOURCE_NAMES
        if (summary := _source_summary(source, getattr(evidence.evidence, source)))
        is not None
    )
    failure_warnings = tuple(
        AssistantWarning(
            code=failure.code,
            message=safe_message(failure.message),
            retryable=failure.retryable,
            retry_after_seconds=failure.retry_after_seconds,
        )
        for failure in evidence.failures
    )
    source_warnings = tuple(
        warning
        for source in SOURCE_NAMES
        for warning in _item_warnings(source, getattr(evidence.evidence, source))
    )
    warnings = (
        *failure_warnings,
        *source_warnings,
        AssistantWarning(
            code="DECISION_SUPPORT_NOTICE",
            message="Decision-support information; not certified navigation advice.",
        ),
    )
    return (
        AssistantEvidenceSummary(
            status=AssistantEvidenceStatus(evidence.status.value),
            available_sources=evidence.summary.available_sources,
            degraded_sources=evidence.summary.degraded_sources,
            pending_sources=evidence.summary.pending_sources,
            unavailable_sources=evidence.summary.unavailable_sources,
        ),
        summaries,
        warnings,
    )


def summarize_assessment(
    assessment: MarineAssessmentResponse,
) -> tuple[
    AssistantEvidenceSummary,
    tuple[AssistantSourceSummary, ...],
    tuple[AssistantWarning, ...],
]:
    named_items: dict[AssistantSourceName, EvidenceItem[Any]] = {
        "waves": assessment.critical_evidence.waves,
        "wind": assessment.critical_evidence.wind,
        "currents": assessment.critical_evidence.currents,
        "pfz": assessment.context.pfz,
        "sst": assessment.context.sst,
        "chlorophyll": assessment.context.chlorophyll,
        "sea_level": assessment.context.sea_level,
    }
    summaries = tuple(
        summary
        for source in SOURCE_NAMES
        if (summary := _source_summary(source, named_items[source])) is not None
    )
    available = sum(source.state == "available" for source in summaries)
    degraded = sum(source.state == "degraded" for source in summaries)
    pending = sum(source.state == "pending" for source in summaries)
    unavailable = sum(source.state == "unavailable" for source in summaries)
    status = (
        AssistantEvidenceStatus.COMPLETE
        if not pending and not unavailable
        else AssistantEvidenceStatus.PARTIAL
        if available or degraded
        else AssistantEvidenceStatus.UNAVAILABLE
    )
    failure_warnings = tuple(
        AssistantWarning(
            code=failure.code,
            message=safe_message(failure.message),
            retryable=failure.retryable,
            retry_after_seconds=failure.retry_after_seconds,
        )
        for failure in assessment.source_failures
    )
    source_warnings = tuple(
        warning
        for source in SOURCE_NAMES
        for warning in _item_warnings(source, named_items[source])
    )
    warnings = (
        *failure_warnings,
        *source_warnings,
        AssistantWarning(
            code="OFFICIAL_WARNINGS_NOT_INTEGRATED",
            message=(
                "Official meteorological and maritime warnings are not integrated. "
                "Verify current authority-issued advisories independently."
            ),
        ),
    )
    return (
        AssistantEvidenceSummary(
            status=status,
            available_sources=available,
            degraded_sources=degraded,
            pending_sources=pending,
            unavailable_sources=unavailable,
            assessment_outcome=assessment.outcome,
            evidence_confidence=assessment.evidence_confidence,
        ),
        summaries,
        warnings,
    )


def summarize_pfz(
    pfz: NearestPFZResponse,
) -> tuple[
    AssistantEvidenceSummary,
    tuple[AssistantSourceSummary, ...],
    tuple[AssistantWarning, ...],
]:
    state: AssistantSourceState = (
        "degraded" if pfz.completeness.value == "partial" else "available"
    )
    summary = AssistantSourceSummary(
        source="pfz",
        state=state,
        provider=pfz.source.name,
        valid_time=pfz.valid_until,
        freshness=pfz.cache_status.value,
    )
    warnings = tuple(
        AssistantWarning(code="PFZ_EVIDENCE_WARNING", message=safe_message(message))
        for message in pfz.warnings[:10]
    ) + (
        AssistantWarning(
            code="PFZ_DOES_NOT_GUARANTEE_FISH_PRESENCE",
            message="A valid PFZ advisory does not guarantee fish presence.",
        ),
    )
    return (
        AssistantEvidenceSummary(
            status=(
                AssistantEvidenceStatus.PARTIAL
                if state == "degraded"
                else AssistantEvidenceStatus.COMPLETE
            ),
            available_sources=int(state == "available"),
            degraded_sources=int(state == "degraded"),
        ),
        (summary,),
        warnings,
    )
