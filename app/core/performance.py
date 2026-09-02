from __future__ import annotations

import json
import asyncio
import logging
import math
import re
import time
from functools import wraps
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Protocol

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class NanosecondClock(Protocol):
    def __call__(self) -> int: ...


SAFE_NAME = re.compile(r"^[a-z0-9_.-]+$")
_current_trace: ContextVar[PerformanceTrace | None] = ContextVar(
    "orca_performance_trace", default=None
)
_span_stack: ContextVar[tuple[int, ...]] = ContextVar(
    "orca_performance_span_stack", default=()
)


@dataclass(slots=True)
class PerformanceSpan:
    identifier: int
    name: str
    start_ns: int
    parent_identifier: int | None
    end_ns: int | None = None
    outcome: str = "success"

    @property
    def duration_ns(self) -> int:
        end = self.end_ns if self.end_ns is not None else self.start_ns
        return max(0, end - self.start_ns)


@dataclass(slots=True)
class SourceTimeline:
    source: str
    start_ns: int
    end_ns: int | None = None
    outcome: str = "success"


@dataclass(slots=True)
class PerformanceTrace:
    route: str
    source: str
    clock: NanosecondClock = time.perf_counter_ns
    start_ns: int = field(init=False)
    end_ns: int | None = None
    outcome: str = "success"
    cache_status: str | None = None
    spans: list[PerformanceSpan] = field(default_factory=list)
    source_timeline: list[SourceTimeline] = field(default_factory=list)
    maximum_concurrency: int = 0
    maximum_heavy_concurrency: int = 0
    _active_sources: int = 0
    _active_heavy: int = 0

    def __post_init__(self) -> None:
        self.start_ns = self.clock()

    @property
    def duration_ns(self) -> int:
        end = self.end_ns if self.end_ns is not None else self.clock()
        return max(0, end - self.start_ns)

    @contextmanager
    def span(self, name: str) -> Iterator[PerformanceSpan]:
        safe_name = sanitize_phase_name(name)
        stack = _span_stack.get()
        record = PerformanceSpan(
            identifier=len(self.spans),
            name=safe_name,
            start_ns=self.clock(),
            parent_identifier=stack[-1] if stack else None,
        )
        self.spans.append(record)
        token = _span_stack.set((*stack, record.identifier))
        try:
            yield record
        except BaseException as exc:
            record.outcome = "cancelled" if type(exc).__name__ == "CancelledError" else "error"
            raise
        finally:
            record.end_ns = max(record.start_ns, self.clock())
            _span_stack.reset(token)

    @contextmanager
    def source_span(self, source: str) -> Iterator[None]:
        safe_source = sanitize_phase_name(source)
        item = SourceTimeline(source=safe_source, start_ns=self.clock())
        self.source_timeline.append(item)
        self._active_sources += 1
        self.maximum_concurrency = max(self.maximum_concurrency, self._active_sources)
        try:
            with self.span(f"combined.source.{safe_source}"):
                yield
        except BaseException as exc:
            item.outcome = "cancelled" if type(exc).__name__ == "CancelledError" else "error"
            raise
        finally:
            item.end_ns = max(item.start_ns, self.clock())
            self._active_sources = max(0, self._active_sources - 1)

    def finish(self, *, outcome: str | None = None) -> None:
        if outcome is not None:
            self.outcome = outcome
        self.end_ns = max(self.start_ns, self.clock())

    def heavy_started(self) -> None:
        self._active_heavy += 1
        self.maximum_heavy_concurrency = max(
            self.maximum_heavy_concurrency, self._active_heavy
        )

    def heavy_finished(self) -> None:
        self._active_heavy = max(0, self._active_heavy - 1)

    def record_interval(
        self, name: str, start_ns: int, end_ns: int, parent_identifier: int | None = None
    ) -> PerformanceSpan:
        record = PerformanceSpan(
            identifier=len(self.spans),
            name=sanitize_phase_name(name),
            start_ns=start_ns,
            end_ns=max(start_ns, end_ns),
            parent_identifier=parent_identifier,
        )
        self.spans.append(record)
        return record

    def aggregate_ms(self) -> dict[str, float]:
        totals: dict[str, int] = {}
        for span in self.spans:
            totals[span.name] = totals.get(span.name, 0) + span.duration_ns
        return {name: value / 1_000_000 for name, value in totals.items()}

    def wall_time_ms(self, prefix: str) -> float:
        intervals = sorted(
            (span.start_ns, span.end_ns)
            for span in self.spans
            if span.name.startswith(prefix) and span.end_ns is not None
        )
        if not intervals:
            return 0.0
        merged: list[tuple[int, int]] = []
        for start, end in intervals:
            assert end is not None
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return sum(max(0, end - start) for start, end in merged) / 1_000_000

    def safe_record(self) -> dict[str, Any]:
        durations = self.aggregate_ms()
        return {
            "event": "orca_performance_trace",
            "route": sanitize_route(self.route),
            "source": sanitize_phase_name(self.source),
            "outcome": self.outcome,
            "cache_status": self.cache_status,
            "total_ms": self.duration_ns / 1_000_000,
            "durations_ms": durations,
            "provider_wall_ms": self.wall_time_ms("provider."),
            "normalization_wall_ms": self.wall_time_ms("normalize."),
            "maximum_concurrency": self.maximum_concurrency,
            "maximum_heavy_concurrency": self.maximum_heavy_concurrency,
            "source_timeline": [
                {
                    "source": item.source,
                    "start_offset_ms": max(0, item.start_ns - self.start_ns) / 1_000_000,
                    "duration_ms": max(0, (item.end_ns or item.start_ns) - item.start_ns) / 1_000_000,
                    "outcome": item.outcome,
                }
                for item in self.source_timeline
            ],
        }


class PerformanceRecorder:
    def __init__(
        self,
        *,
        clock: NanosecondClock = time.perf_counter_ns,
        max_completed: int = 100,
    ) -> None:
        self.clock = clock
        self.completed: deque[PerformanceTrace] = deque(maxlen=max_completed)

    @asynccontextmanager
    async def trace(self, *, route: str, source: str) -> AsyncIterator[PerformanceTrace]:
        trace = PerformanceTrace(route=route, source=source, clock=self.clock)
        trace_token: Token[PerformanceTrace | None] = _current_trace.set(trace)
        stack_token = _span_stack.set(())
        try:
            yield trace
        except BaseException as exc:
            trace.finish(
                outcome="cancelled" if type(exc).__name__ == "CancelledError" else "error"
            )
            raise
        finally:
            if trace.end_ns is None:
                trace.finish()
            self.completed.append(trace)
            _span_stack.reset(stack_token)
            _current_trace.reset(trace_token)


def current_trace() -> PerformanceTrace | None:
    return _current_trace.get()


@contextmanager
def performance_span(name: str) -> Iterator[PerformanceSpan | None]:
    trace = current_trace()
    if trace is None:
        yield None
        return
    with trace.span(name) as span:
        yield span


def measured_async(name: str):
    """Decorator for service boundaries; it is a no-op without an active trace."""

    def decorate(function: Callable[..., Any]):
        @wraps(function)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            trace = current_trace()
            if trace is not None and not any(
                span.name == "http.validation" for span in trace.spans
            ):
                trace.record_interval("http.validation", trace.start_ns, trace.clock())
            with performance_span(name):
                return await function(*args, **kwargs)

        return wrapped

    return decorate


def measured_sync(name: str):
    def decorate(function: Callable[..., Any]):
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with performance_span(name):
                return function(*args, **kwargs)

        return wrapped

    return decorate


@contextmanager
def source_timing(source: str) -> Iterator[SourceTimeline | None]:
    trace = current_trace()
    if trace is None:
        yield None
        return
    with trace.source_span(source):
        yield trace.source_timeline[-1]


def annotate_trace(*, cache_status: str | None = None, outcome: str | None = None) -> None:
    trace = current_trace()
    if trace is None:
        return
    if cache_status is not None:
        trace.cache_status = sanitize_phase_name(cache_status)
    if outcome is not None:
        trace.outcome = sanitize_phase_name(outcome)


def sanitize_phase_name(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    return normalized if SAFE_NAME.fullmatch(normalized) else "unknown"


def sanitize_route(value: str) -> str:
    # Route paths are allow-listed structurally; query strings never reach here.
    if not value.startswith("/v1/") or "?" in value or not re.fullmatch(r"/[a-z0-9_./{}-]+", value):
        return "unknown"
    return value


def route_source(route: str) -> str:
    mapping = {
        "/v1/pfz/snapshot": "pfz",
        "/v1/marine/sst": "sst",
        "/v1/marine/chlorophyll": "chlorophyll",
        "/v1/marine/waves": "waves",
        "/v1/marine/wind": "wind",
        "/v1/marine/wind/forecast": "wind_forecast",
        "/v1/marine/currents": "currents",
        "/v1/marine/sea-level": "sea_level",
        "/v1/marine/sea-level/events": "sea_level_events",
        "/v1/marine/conditions": "conditions",
    }
    return mapping.get(route, "api")


def server_timing_header(trace: PerformanceTrace) -> str:
    provider = trace.wall_time_ms("provider.")
    normalize = trace.wall_time_ms("normalize.")
    entries = [("total", trace.duration_ns / 1_000_000)]
    if provider:
        entries.append(("provider", provider))
    if normalize:
        entries.append(("normalize", normalize))
    return ", ".join(f"{name};dur={max(0.0, value):.1f}" for name, value in entries)


def emit_trace_log(
    trace: PerformanceTrace,
    logger: logging.Logger | None = None,
    slow_request_ms: float = 1000.0,
) -> None:
    target = logger or logging.getLogger("orca.performance")
    payload = json.dumps(trace.safe_record(), separators=(",", ":"), sort_keys=True)
    method = target.warning if trace.duration_ns / 1_000_000 >= slow_request_ms else target.info
    method(payload)


class InstrumentedJsonCache:
    """Timing-only cache decorator; keys and values are never recorded."""

    def __init__(self, cache: Any) -> None:
        self._cache = cache

    async def get(self, key: str) -> dict[str, Any] | None:
        with performance_span("cache.lookup"):
            value = await self._cache.get(key)
        if value is not None:
            annotate_trace(cache_status="cache_hit")
        return value

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        with performance_span("cache.store"):
            await self._cache.set(key, value, ttl)
        annotate_trace(cache_status="refreshed")

    async def close(self) -> None:
        await self._cache.close()


class InstrumentedAsyncProxy:
    """Wrap selected async boundary methods without changing provider semantics."""

    def __init__(
        self,
        target: Any,
        phases: dict[str, str],
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self._target = target
        self._phases = phases
        self._semaphore = semaphore

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._target, name)
        phase = self._phases.get(name)
        if phase is None or not callable(attribute):
            return attribute

        async def measured(*args: Any, **kwargs: Any) -> Any:
            heavy = phase in {"provider.load", "provider.static_mask"}
            if self._semaphore is None or phase not in {
                "provider.load", "provider.static_mask"
            }:
                trace = current_trace()
                if heavy and trace is not None:
                    trace.heavy_started()
                try:
                    with performance_span(phase):
                        return await attribute(*args, **kwargs)
                finally:
                    if heavy and trace is not None:
                        trace.heavy_finished()
            with performance_span("semaphore.wait"):
                await self._semaphore.acquire()
            trace = current_trace()
            if trace is not None:
                trace.heavy_started()
            try:
                with performance_span(phase):
                    return await attribute(*args, **kwargs)
            finally:
                if trace is not None:
                    trace.heavy_finished()
                self._semaphore.release()

        return measured


def safe_report_value(value: Any) -> Any:
    """Recursively retain only report-safe primitives and bounded phase metadata."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        lowered = value.lower()
        if any(token in lowered for token in ("token=", "password", "authorization", "jsessionid")):
            return "[redacted]"
        if re.match(r"^[a-zA-Z]:[\\/]", value) or value.startswith(("/home/", "/users/")):
            return "[redacted-path]"
        return value[:500]
    if isinstance(value, dict):
        return {sanitize_phase_name(str(key)): safe_report_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_report_value(item) for item in value]
    return type(value).__name__


def _run_worker(function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    with performance_span("worker.execute"):
        return function(*args, **kwargs)


async def to_thread_timed(function: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Attribute queue plus worker time and worker execution separately."""
    with performance_span("worker.total"):
        return await asyncio.to_thread(_run_worker, function, args, kwargs)


@asynccontextmanager
async def measured_lock(lock: Any, name: str = "singleflight.wait") -> AsyncIterator[None]:
    with performance_span(name):
        await lock.acquire()
    try:
        yield
    finally:
        lock.release()


class PerformanceMiddleware:
    """Opt-in request tracing with no response-body contract changes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = scope["app"].state
        diagnostics = bool(getattr(state, "performance_diagnostics_enabled", False))
        server_timing = bool(getattr(state, "performance_server_timing_enabled", False))
        if not diagnostics and not server_timing:
            await self.app(scope, receive, send)
            return

        recorder: PerformanceRecorder = state.performance_recorder
        route = str(scope.get("path", "unknown"))
        trace: PerformanceTrace
        status_code = 500

        async def measured_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                service_ends = [
                    span.end_ns
                    for span in trace.spans
                    if span.name == "service.total" and span.end_ns is not None
                ]
                if service_ends:
                    trace.record_interval(
                        "response.serialization", max(service_ends), trace.clock()
                    )
                if server_timing:
                    headers = list(message.get("headers", []))
                    headers.append(
                        (b"server-timing", server_timing_header(trace).encode("ascii"))
                    )
                    message = {**message, "headers": headers}
            with performance_span("response.send"):
                await send(message)

        try:
            async with recorder.trace(route=route, source=route_source(route)) as trace:
                with trace.span("http.application"):
                    await self.app(scope, receive, measured_send)
                trace.outcome = "success" if status_code < 500 else "error"
        except BaseException:
            trace = recorder.completed[-1]
            if diagnostics:
                emit_trace_log(
                    trace,
                    slow_request_ms=float(
                        getattr(state, "performance_log_slow_request_ms", 1000.0)
                    ),
                )
            raise

        if diagnostics:
            emit_trace_log(
                trace,
                slow_request_ms=float(
                    getattr(state, "performance_log_slow_request_ms", 1000.0)
                ),
            )
