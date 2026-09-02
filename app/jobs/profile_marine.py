from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.performance import PerformanceTrace, safe_report_value


SOURCES = (
    "pfz",
    "sst",
    "chlorophyll",
    "waves",
    "wind",
    "wind_forecast",
    "currents",
    "sea_level",
    "sea_level_events",
    "conditions",
)


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def parse_datetime(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--at must include a timezone offset")
    return parsed.astimezone(UTC)


def build_request(
    source: str, latitude: float, longitude: float, at: datetime
) -> tuple[str, dict[str, Any]]:
    coordinates = {"latitude": latitude, "longitude": longitude}
    instant = at.isoformat().replace("+00:00", "Z")
    if source == "pfz":
        return "/v1/pfz/snapshot", {}
    if source == "wind_forecast":
        forecast_at = max(at, datetime.now(UTC) + timedelta(hours=24))
        return "/v1/marine/wind/forecast", {
            **coordinates,
            "at": forecast_at.isoformat().replace("+00:00", "Z"),
        }
    if source == "sea_level_events":
        return "/v1/marine/sea-level/events", {
            **coordinates,
            "start": instant,
            "hours": 48,
        }
    path = {
        "sst": "/v1/marine/sst",
        "chlorophyll": "/v1/marine/chlorophyll",
        "waves": "/v1/marine/waves",
        "wind": "/v1/marine/wind",
        "currents": "/v1/marine/currents",
        "sea_level": "/v1/marine/sea-level",
        "conditions": "/v1/marine/conditions",
    }[source]
    return path, {**coordinates, "at": instant}


def _enabled(source: str, settings: Any) -> bool:
    flag = {
        "sst": "copernicus_sst_enabled",
        "chlorophyll": "chlorophyll_enabled",
        "waves": "copernicus_waves_enabled",
        "wind": "copernicus_wind_enabled",
        "wind_forecast": "ecmwf_wind_enabled",
        "currents": "copernicus_currents_enabled",
        "sea_level": "copernicus_tides_enabled",
        "sea_level_events": "copernicus_tides_enabled",
    }.get(source)
    return flag is None or bool(getattr(settings, flag))


def _trace_report(trace: PerformanceTrace) -> dict[str, Any]:
    phases = trace.aggregate_ms()
    provider_calls = sum(1 for span in trace.spans if span.name == "provider.load")
    timeline = trace.safe_record()["source_timeline"]
    critical = max(timeline, key=lambda item: item["duration_ms"], default=None)
    return {
        "total_ms": round(trace.duration_ns / 1_000_000, 3),
        "phase_durations_ms": {key: round(value, 3) for key, value in phases.items()},
        "phase_duration_semantics": (
            "per-name cumulative durations; use wall fields for overlapping spans"
        ),
        "provider_wall_ms": round(trace.wall_time_ms("provider."), 3),
        "normalization_wall_ms": round(trace.wall_time_ms("normalize."), 3),
        "provider_calls": provider_calls,
        "static_calls": sum(1 for span in trace.spans if span.name == "provider.static_mask"),
        "metadata_calls": sum(
            1
            for span in trace.spans
            if span.name in {"provider.metadata", "provider.availability", "provider.latest_cycle"}
        ),
        "maximum_observed_concurrency": trace.maximum_concurrency,
        "maximum_heavy_provider_concurrency": trace.maximum_heavy_concurrency,
        "critical_path_source": critical["source"] if critical else None,
        "source_timeline": timeline,
    }


def _cache_status(payload: Any) -> str | None:
    if isinstance(payload, dict):
        value = payload.get("cache_status")
        return value if isinstance(value, str) else None
    return None


def profile_source(
    client: TestClient,
    recorder: Any,
    *,
    source: str,
    latitude: float,
    longitude: float,
    at: datetime,
    source_layers_pre_warmed: bool = False,
) -> dict[str, Any]:
    path, params = build_request(source, latitude, longitude, at)
    records: list[dict[str, Any]] = []
    for cache_state in ("cold", "warm"):
        before = len(recorder.completed)
        response = client.get(path, params=params)
        trace = recorder.completed[-1] if len(recorder.completed) > before else None
        payload = response.json()
        layer_state = cache_state
        if source == "conditions" and cache_state == "cold" and source_layers_pre_warmed:
            layer_state = "warm"
        record: dict[str, Any] = {
            "result": "success" if response.is_success else "failure",
            "http_status": response.status_code,
            "cache_status": _cache_status(payload),
            "cache_layers": {
                "availability": layer_state,
                "metadata": layer_state,
                "static": layer_state,
                "field": layer_state,
                "point": cache_state,
            },
        }
        if trace is not None:
            record.update(_trace_report(trace))
            if record["cache_status"] is None:
                record["cache_status"] = trace.cache_status
        records.append(record)
    return {
        "source": source,
        "cold_total_ms": records[0].get("total_ms"),
        "warm_total_ms": records[1].get("total_ms"),
        "cold_cache_layers": records[0]["cache_layers"],
        "warm_cache_layers": records[1]["cache_layers"],
        "cold": records[0],
        "warm": records[1],
        "result": records[0]["result"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile ORCA marine cold and warm paths")
    parser.add_argument("--latitude", type=float, default=18.025)
    parser.add_argument("--longitude", type=float, default=70.525)
    parser.add_argument("--at")
    parser.add_argument("--source", choices=(*SOURCES, "all"), default="all")
    parser.add_argument("--mode", choices=("cold", "warm"), default="cold")
    parser.add_argument("--output", type=Path)
    return parser


def run_profile(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    # Import after argument validation so module loading itself is not counted.
    from app.main import app, settings

    at = parse_datetime(args.at)
    selected = SOURCES if args.source == "all" else (args.source,)
    app.state.performance_diagnostics_enabled = True
    app.state.performance_server_timing_enabled = False
    app.state.performance_isolated_cache = True
    app.state.performance_recorder.completed.clear()

    source_reports: list[dict[str, Any]] = []
    with TestClient(app) as client:
        profiled_sources: set[str] = set()
        for source in selected:
            if not _enabled(source, settings):
                source_reports.append(
                    {"source": source, "result": "skipped", "reason": "feature_disabled"}
                )
                continue
            source_reports.append(
                profile_source(
                    client,
                    app.state.performance_recorder,
                    source=source,
                    latitude=args.latitude,
                    longitude=args.longitude,
                    at=at,
                    source_layers_pre_warmed=(
                        source == "conditions" and bool(profiled_sources)
                    ),
                )
            )
            profiled_sources.add(source)

    conditions = next(
        (item for item in source_reports if item["source"] == "conditions"), None
    )
    report = {
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.system(),
            "fastapi_version": _package_version("fastapi"),
            "single_process": True,
            "worker_count": 1,
            "maximum_profile_provider_concurrency": (
                settings.performance_profile_max_provider_concurrency
            ),
        },
        "profile_mode": args.mode,
        "profile_reference_time": at.isoformat().replace("+00:00", "Z"),
        "cold_definition": "isolated profiling process and in-memory cache namespace",
        "warm_definition": "identical repeat in the same profiling process and cache namespace",
        "sources": source_reports,
        "combined_conditions": conditions,
    }
    safe = safe_report_value(report)
    failures = [item for item in source_reports if item.get("result") == "failure"]
    return safe, 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report, exit_code = run_profile(args)
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
