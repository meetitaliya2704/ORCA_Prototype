from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.clients.imd_client import IMDClient
from app.domain.risk_rules import RuleEvaluation, apply_official_imd_warnings
from app.schemas.assessment import AssessmentOutcome, EvidenceConfidence
from app.services.imd_marine import IMDMarineService

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "imd"


@pytest.mark.asyncio
async def test_imd_service_cache_and_stale_fallback():
    sample_ports = json.loads((FIXTURES_DIR / "port_warnings_sample.json").read_text(encoding="utf-8"))

    class FakeIMDClient:
        def __init__(self):
            self.calls = 0
            self.should_fail = False

        async def get_port_warnings(self):
            self.calls += 1
            if self.should_fail:
                raise RuntimeError("IMD Gateway 504 Gateway Timeout")
            return sample_ports

    fake_client = FakeIMDClient()
    service = IMDMarineService(client=fake_client, port_ttl_seconds=60)

    # 1. Miss -> Refreshed
    resp1, status1 = await service.get_port_warnings()
    assert status1 == "refreshed"
    assert len(resp1.warnings) == 3
    assert fake_client.calls == 1

    # 2. Hit -> Fresh (no client hit)
    resp2, status2 = await service.get_port_warnings()
    assert status2 == "fresh"
    assert fake_client.calls == 1

    # 3. Simulate client failure with stale cache
    fake_client.should_fail = True
    # Expire the cache entry manually
    service._port_cache.expires_at = service._port_cache.created_at
    resp3, status3 = await service.get_port_warnings()
    assert status3 == "stale"
    assert len(resp3.warnings) == 3


def test_deterministic_imd_warning_veto():
    base_eval = RuleEvaluation(
        outcome=AssessmentOutcome.WITHIN_CONFIGURED_LIMITS,
        evidence_confidence=EvidenceConfidence.NORMAL,
        rules=(),
        reasons=(),
        missing_critical_evidence=(),
    )

    # Port warning signal 3 (squally weather) triggers deterministic veto
    eval_vetoed = apply_official_imd_warnings(
        base_evaluation=base_eval,
        port_warning_signals=[1, 3],
        fishermen_warning_active=False,
    )
    assert eval_vetoed.outcome == AssessmentOutcome.LIMIT_EXCEEDED
    assert any(r.code == "OFFICIAL_IMD_PORT_WARNING" for r in eval_vetoed.reasons)

    # Fishermen warning triggers veto
    eval_fish_vetoed = apply_official_imd_warnings(
        base_evaluation=base_eval,
        fishermen_warning_active=True,
    )
    assert eval_fish_vetoed.outcome == AssessmentOutcome.LIMIT_EXCEEDED
    assert any(r.code == "OFFICIAL_IMD_FISHERMEN_WARNING" for r in eval_fish_vetoed.reasons)

    # Cyclone warning triggers veto
    eval_cyclone_vetoed = apply_official_imd_warnings(
        base_evaluation=base_eval,
        cyclone_warning_active=True,
        warning_details="Severe Cyclonic Storm approaching",
    )
    assert eval_cyclone_vetoed.outcome == AssessmentOutcome.LIMIT_EXCEEDED
    assert any(r.code == "OFFICIAL_IMD_CYCLONE_WARNING" for r in eval_cyclone_vetoed.reasons)

    # Low signal (Signal 1 - distant cautionary) does not trigger severe veto
    eval_caution = apply_official_imd_warnings(
        base_evaluation=base_eval,
        port_warning_signals=[1],
    )
    assert eval_caution.outcome == AssessmentOutcome.WITHIN_CONFIGURED_LIMITS

