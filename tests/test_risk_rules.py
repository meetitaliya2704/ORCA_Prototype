from datetime import UTC, datetime

import pytest

from app.domain.risk_rules import evaluate_operational_limits
from app.schemas.assessment import OperationalLimits
from app.schemas.evidence import EvidenceItem, EvidenceRequest, EvidenceState
from app.schemas.marine import WaveValue, WindValue
from app.services.evidence import MarineEvidenceService
from tests.test_copernicus_currents import T22, service as current_service
from tests.test_evidence_service import FakeService
from tests.test_marine import wave_response, wind_response


NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)


async def critical_bundle(
    *,
    wave_height: float | None = 2.0,
    wind_speed: float | None = 8.0,
    current_speed: float | None = 0.5,
    degraded: set[str] | None = None,
    pending: set[str] | None = None,
):
    degraded = degraded or set()
    pending = pending or set()
    wave = wave_response().model_copy(update={
        "significant_wave_height": WaveValue(value=wave_height or 0.0, unit="m")
    })
    wind = wind_response().model_copy(update={
        "wind_speed": WindValue(value=wind_speed or 0.0)
    })
    current = await current_service(now=lambda: T22).get_current(
        latitude=18.025, longitude=70.525, at=T22
    )
    current = current.model_copy(update={
        "total_current": current.total_current.model_copy(
            update={"speed_mps": current_speed or 0.0}
        )
    })
    service = MarineEvidenceService(
        wave_service=FakeService("get_waves", wave),
        recent_wind_service=FakeService("get_wind", wind),
        current_service=FakeService("get_current", current),
        now=lambda: NOW,
    )
    bundle = await service.aggregate(EvidenceRequest(
        latitude=18.025,
        longitude=70.525,
        at=NOW,
        include_pfz=False,
        include_sst=False,
        include_chlorophyll=False,
        include_waves=True,
        include_wind=True,
        include_currents=True,
        include_sea_level=False,
    ))
    updates = {}
    for source in degraded:
        updates[source] = getattr(bundle.evidence, source).model_copy(
            update={"state": EvidenceState.DEGRADED}
        )
    for source in pending:
        updates[source] = EvidenceItem(state=EvidenceState.PENDING)
    if wave_height is None:
        updates["waves"] = EvidenceItem(state=EvidenceState.UNAVAILABLE)
    if wind_speed is None:
        updates["wind"] = EvidenceItem(state=EvidenceState.UNAVAILABLE)
    if current_speed is None:
        updates["currents"] = EvidenceItem(state=EvidenceState.UNAVAILABLE)
    if updates:
        bundle = bundle.model_copy(
            update={"evidence": bundle.evidence.model_copy(update=updates)}
        )
    return bundle


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected"),
    [(1.9, "within_limit"), (2.0, "within_limit"), (2.1, "exceeded")],
)
async def test_wave_below_equal_and_above_limit(value, expected):
    evidence = await critical_bundle(wave_height=value)
    result = evaluate_operational_limits(
        evidence,
        OperationalLimits(maximum_significant_wave_height_m=2.0),
        None,
    )
    assert result.rules[0].outcome == expected
    assert result.outcome == (
        "LIMIT_EXCEEDED" if expected == "exceeded" else "WITHIN_CONFIGURED_LIMITS"
    )


@pytest.mark.asyncio
async def test_wind_and_current_rules_use_correct_values_and_units():
    evidence = await critical_bundle(wind_speed=12.0, current_speed=0.7)
    result = evaluate_operational_limits(
        evidence,
        OperationalLimits(
            maximum_wind_speed_m_s=10.0,
            maximum_surface_current_speed_m_s=0.8,
        ),
        None,
    )
    assert [rule.parameter for rule in result.rules] == [
        "wind_speed", "total_surface_current_speed"
    ]
    assert [rule.observed_value for rule in result.rules] == [12.0, 0.7]
    assert [rule.unit for rule in result.rules] == ["m/s", "m/s"]
    assert result.outcome == "LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_one_exceeded_rule_controls_without_weighted_average():
    evidence = await critical_bundle(wave_height=3.0, wind_speed=1.0, current_speed=0.1)
    result = evaluate_operational_limits(
        evidence,
        OperationalLimits(
            maximum_significant_wave_height_m=2.0,
            maximum_wind_speed_m_s=20.0,
            maximum_surface_current_speed_m_s=2.0,
        ),
        None,
    )
    assert result.outcome == "LIMIT_EXCEEDED"
    assert [rule.outcome for rule in result.rules] == [
        "exceeded", "within_limit", "within_limit"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["missing", "pending"])
async def test_missing_or_pending_required_evidence_is_insufficient(state):
    evidence = await critical_bundle(
        wave_height=None if state == "missing" else 2.0,
        pending={"waves"} if state == "pending" else set(),
    )
    result = evaluate_operational_limits(
        evidence,
        OperationalLimits(maximum_significant_wave_height_m=3.0),
        None,
    )
    assert result.rules[0].outcome == "unknown"
    assert result.outcome == "INSUFFICIENT_EVIDENCE"
    assert result.evidence_confidence == "INSUFFICIENT"
    assert result.missing_critical_evidence == ("waves",)


@pytest.mark.asyncio
async def test_non_finite_source_value_is_unusable_evidence():
    evidence = await critical_bundle(wave_height=float("nan"))
    result = evaluate_operational_limits(
        evidence,
        OperationalLimits(maximum_significant_wave_height_m=3.0),
        None,
    )
    assert result.rules[0].observed_value is None
    assert result.rules[0].outcome == "unknown"
    assert result.outcome == "INSUFFICIENT_EVIDENCE"


@pytest.mark.asyncio
async def test_degraded_usable_evidence_changes_confidence_not_comparison():
    evidence = await critical_bundle(wave_height=1.0, degraded={"waves"})
    result = evaluate_operational_limits(
        evidence,
        OperationalLimits(maximum_significant_wave_height_m=2.0),
        None,
    )
    assert result.outcome == "WITHIN_CONFIGURED_LIMITS"
    assert result.evidence_confidence == "DEGRADED"
    assert result.rules[0].evidence_quality == "degraded"
    assert "EVIDENCE_DEGRADED" in [reason.code for reason in result.reasons]


@pytest.mark.asyncio
async def test_near_limit_is_explicit_with_exact_boundaries():
    evidence = await critical_bundle(wave_height=1.8)
    enabled = evaluate_operational_limits(
        evidence,
        OperationalLimits(maximum_significant_wave_height_m=2.0),
        10.0,
    )
    disabled = evaluate_operational_limits(
        evidence,
        OperationalLimits(maximum_significant_wave_height_m=2.0),
        None,
    )
    equal = await critical_bundle(wave_height=2.0)
    equal_result = evaluate_operational_limits(
        equal,
        OperationalLimits(maximum_significant_wave_height_m=2.0),
        10.0,
    )
    assert enabled.rules[0].outcome == "near_limit"
    assert enabled.outcome == "CAUTION"
    assert disabled.rules[0].outcome == "within_limit"
    assert equal_result.rules[0].outcome == "within_limit"


@pytest.mark.asyncio
async def test_reason_order_is_rule_order_then_official_warning_notice():
    evidence = await critical_bundle(wave_height=3.0, wind_speed=None, current_speed=0.95)
    result = evaluate_operational_limits(
        evidence,
        OperationalLimits(
            maximum_significant_wave_height_m=2.0,
            maximum_wind_speed_m_s=10.0,
            maximum_surface_current_speed_m_s=1.0,
        ),
        10.0,
    )
    assert result.outcome == "LIMIT_EXCEEDED"
    assert result.evidence_confidence == "INSUFFICIENT"
    assert [reason.code for reason in result.reasons] == [
        "WAVE_LIMIT_EXCEEDED",
        "WIND_EVIDENCE_MISSING",
        "CURRENT_NEAR_LIMIT",
        "OFFICIAL_WARNINGS_NOT_INTEGRATED",
    ]
