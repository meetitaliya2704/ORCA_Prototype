import asyncio
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.performance import (
    InstrumentedJsonCache,
    InstrumentedAsyncProxy,
    PerformanceMiddleware,
    PerformanceRecorder,
    current_trace,
    performance_span,
    safe_report_value,
)
from app.schemas.marine import SourceResult, SourceStatus
from app.services.cache import MemoryJsonCache
from app.services.marine import MarineConditionsService


class FakeClock:
    def __init__(self) -> None:
        self.value = 1_000_000_000

    def __call__(self) -> int:
        return self.value

    def advance_ms(self, value: float) -> None:
        self.value += int(value * 1_000_000)


@pytest.mark.asyncio
async def test_nested_spans_use_injected_monotonic_clock_and_parent_relationships():
    clock = FakeClock()
    recorder = PerformanceRecorder(clock=clock)
    async with recorder.trace(route="/v1/marine/sst", source="sst") as trace:
        with performance_span("service.total"):
            clock.advance_ms(2)
            with performance_span("provider.load"):
                clock.advance_ms(3)
            clock.advance_ms(1)

    parent, child = trace.spans
    assert parent.duration_ns == 6_000_000
    assert child.duration_ns == 3_000_000
    assert child.parent_identifier == parent.identifier
    assert trace.duration_ns >= parent.duration_ns


@pytest.mark.asyncio
async def test_duplicate_span_names_are_retained_as_separate_records():
    recorder = PerformanceRecorder()
    async with recorder.trace(route="/v1/marine/sst", source="sst") as trace:
        with performance_span("cache.lookup"):
            pass
        with performance_span("cache.lookup"):
            pass
    assert [item.name for item in trace.spans] == ["cache.lookup", "cache.lookup"]


def test_concurrent_or_nested_phase_wall_time_is_not_reported_as_a_sum():
    clock = FakeClock()
    trace = PerformanceRecorder(clock=clock)

    async def build():
        async with trace.trace(route="/v1/marine/conditions", source="conditions") as item:
            item.record_interval("provider.load", item.start_ns, item.start_ns + 10_000_000)
            item.record_interval("provider.open", item.start_ns + 2_000_000, item.start_ns + 8_000_000)
            return item

    item = asyncio.run(build())
    assert item.aggregate_ms()["provider.load"] == 10
    assert item.aggregate_ms()["provider.open"] == 6
    assert item.wall_time_ms("provider.") == 10


@pytest.mark.asyncio
async def test_exception_and_cancellation_close_spans():
    recorder = PerformanceRecorder()
    with pytest.raises(RuntimeError):
        async with recorder.trace(route="/v1/marine/sst", source="sst") as trace:
            with performance_span("provider.load"):
                raise RuntimeError("private provider detail")
    assert trace.spans[0].outcome == "error"
    assert trace.spans[0].end_ns is not None

    with pytest.raises(asyncio.CancelledError):
        async with recorder.trace(route="/v1/marine/sst", source="sst") as cancelled:
            with performance_span("provider.load"):
                raise asyncio.CancelledError
    assert cancelled.spans[0].outcome == "cancelled"


@pytest.mark.asyncio
async def test_concurrent_requests_keep_separate_context_traces():
    recorder = PerformanceRecorder()

    async def run(source: str):
        async with recorder.trace(route=f"/v1/marine/{source}", source=source) as trace:
            await asyncio.sleep(0)
            with performance_span(f"provider.{source}"):
                await asyncio.sleep(0)
            assert current_trace() is trace
            return trace

    left, right = await asyncio.gather(run("sst"), run("waves"))
    assert {span.name for span in left.spans} == {"provider.sst"}
    assert {span.name for span in right.spans} == {"provider.waves"}


def _test_app(*, diagnostics: bool, server_timing: bool) -> FastAPI:
    app = FastAPI()
    app.state.performance_diagnostics_enabled = diagnostics
    app.state.performance_server_timing_enabled = server_timing
    app.state.performance_recorder = PerformanceRecorder()
    app.add_middleware(PerformanceMiddleware)

    @app.get("/v1/test")
    async def endpoint():
        with performance_span("provider.load"):
            return {"unchanged": True}

    return app


def test_diagnostics_and_server_timing_are_absent_by_default():
    app = _test_app(diagnostics=False, server_timing=False)
    with TestClient(app) as client:
        response = client.get("/v1/test", params={"latitude": "18.025"})
    assert response.json() == {"unchanged": True}
    assert "server-timing" not in response.headers
    assert not app.state.performance_recorder.completed


def test_server_timing_uses_only_sanitized_low_cardinality_names():
    app = _test_app(diagnostics=False, server_timing=True)
    with TestClient(app) as client:
        response = client.get("/v1/test", params={"latitude": "18.025"})
    header = response.headers["server-timing"]
    assert header.startswith("total;dur=")
    assert "provider;dur=" in header
    assert "18.025" not in header


def test_structured_log_and_report_sanitization_exclude_sensitive_values(caplog):
    unsafe = {
        "warning": "password=secret token=abc",
        "path": r"C:\Users\private\credentials.json",
        "duration": float("inf"),
    }
    safe = safe_report_value(unsafe)
    encoded = json.dumps(safe)
    assert "secret" not in encoded
    assert "credentials.json" not in encoded
    assert "Infinity" not in encoded

    app = _test_app(diagnostics=True, server_timing=False)
    with caplog.at_level(logging.INFO, logger="orca.performance"):
        with TestClient(app) as client:
            client.get("/v1/test?latitude=18.025")
    message = caplog.records[-1].message
    assert "18.025" not in message
    assert "token" not in message


@pytest.mark.asyncio
async def test_cache_instrumentation_does_not_change_calls_or_cache_values():
    class CountingCache(MemoryJsonCache):
        calls = 0

        async def get(self, key):
            self.calls += 1
            return await super().get(key)

    inner = CountingCache()
    cache = InstrumentedJsonCache(inner)
    await cache.set("private:key", {"ok": True}, 60)
    assert await cache.get("private:key") == {"ok": True}
    assert inner.calls == 1


@pytest.mark.asyncio
async def test_profile_provider_proxy_bounds_heavy_concurrency_without_extra_calls():
    active = maximum = calls = 0
    gate = asyncio.Event()

    class Provider:
        async def fetch_cells(self):
            nonlocal active, maximum, calls
            calls += 1
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0)
            active -= 1
            return []

    proxy = InstrumentedAsyncProxy(
        Provider(), {"fetch_cells": "provider.load"}, asyncio.Semaphore(2)
    )
    recorder = PerformanceRecorder()
    async with recorder.trace(route="/v1/marine/conditions", source="conditions") as trace:
        await asyncio.gather(*(proxy.fetch_cells() for _ in range(4)))
    assert calls == 4
    assert maximum <= 2
    assert trace.maximum_heavy_concurrency == 2


@pytest.mark.asyncio
async def test_combined_conditions_timeline_proves_concurrency_and_critical_path():
    active = 0
    maximum = 0
    gate = asyncio.Event()
    both_started = asyncio.Event()

    class Source:
        def __init__(self, name):
            self.name = name

        async def fetch(self, client, latitude, longitude, at=None):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                both_started.set()
            await gate.wait()
            active -= 1
            return SourceResult(source=self.name, status=SourceStatus.FRESH)

    service = MarineConditionsService(
        client=None,
        cache=MemoryJsonCache(),
        sources=[Source("sst"), Source("waves")],
        cache_ttl=60,
    )
    recorder = PerformanceRecorder()
    async with recorder.trace(route="/v1/marine/conditions", source="conditions") as trace:
        task = asyncio.create_task(service.get_conditions(18.025, 70.525))
        await asyncio.wait_for(both_started.wait(), timeout=1)
        gate.set()
        response = await task
    assert set(response.sources) == {"sst", "waves"}
    assert maximum == 2
    assert trace.maximum_concurrency == 2
    assert {item.source for item in trace.source_timeline} == {"sst", "waves"}


@pytest.mark.asyncio
async def test_combined_source_failure_is_recorded_without_erasing_success():
    class Source:
        def __init__(self, name, fail=False):
            self.name, self.fail = name, fail

        async def fetch(self, client, latitude, longitude, at=None):
            if self.fail:
                raise RuntimeError("provider failed")
            return SourceResult(source=self.name, status=SourceStatus.FRESH)

    service = MarineConditionsService(
        client=None,
        cache=MemoryJsonCache(),
        sources=[Source("sst"), Source("waves", True)],
        cache_ttl=60,
    )
    recorder = PerformanceRecorder()
    async with recorder.trace(route="/v1/marine/conditions", source="conditions") as trace:
        response = await service.get_conditions(18.025, 70.525)
    assert response.sources["sst"].status == SourceStatus.FRESH
    assert response.sources["waves"].status == SourceStatus.UNAVAILABLE
    assert len(trace.source_timeline) == 2
