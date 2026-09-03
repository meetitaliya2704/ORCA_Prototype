from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

import httpx

from app.main import app
from app.snapshots.jobs import RefreshBlockedError


ISOLATED_WARNING = (
    "This isolated snapshot exists only for this command and does not warm a "
    "running FastAPI process."
)
_SAFE_CODE = re.compile(r"^[A-Z0-9_]{1,80}$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Warm snapshots in a running ORCA server")
    parser.add_argument("--source", choices=("sst", "chlorophyll"), default="sst")
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--server-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    return parser


def _safe_code(payload: object, fallback: str) -> str:
    if isinstance(payload, dict):
        detail = payload.get("detail", payload)
        if isinstance(detail, dict):
            value = detail.get("code")
            if isinstance(value, str) and _SAFE_CODE.fullmatch(value):
                return value
    return fallback


async def _run_server(args: argparse.Namespace) -> int:
    if args.retry_failed:
        print(json.dumps({"status": "failed", "code": "RETRY_FAILED_REQUIRES_ISOLATED_MODE"}))
        return 2
    endpoint = f"/v1/marine/{args.source}"
    params = {
        "latitude": args.latitude,
        "longitude": args.longitude,
        "wait_for_refresh": "false",
    }
    deadline = time.monotonic() + args.timeout_seconds
    try:
        async with httpx.AsyncClient(base_url=args.server_url, timeout=10.0) as client:
            response = await client.get(endpoint, params=params)
            if response.status_code == 200:
                snapshot = response.json().get("snapshot", {})
                print(json.dumps({
                    "status": "succeeded", "source": args.source,
                    "snapshot_status": snapshot.get("status"),
                    "tile_id": snapshot.get("tile_id"),
                }))
                return 0
            if response.status_code != 202:
                print(json.dumps({
                    "status": "failed",
                    "code": _safe_code(response.json(), "SNAPSHOT_WARM_FAILED"),
                }))
                return 1
            accepted = response.json()
            job_id = accepted.get("job_id")
            if not isinstance(job_id, str) or not job_id:
                print(json.dumps({"status": "failed", "code": "INVALID_REFRESH_RESPONSE"}))
                return 1
            if not args.wait:
                print(json.dumps({
                    "status": "queued", "source": args.source, "job_id": job_id,
                    "tile_id": accepted.get("tile", {}).get("id"),
                }))
                return 0
            final_job = None
            while time.monotonic() < deadline:
                await asyncio.sleep(max(0.05, args.poll_seconds))
                status_response = await client.get(f"/v1/marine/refresh/jobs/{job_id}")
                if status_response.status_code != 200:
                    print(json.dumps({
                        "status": "failed",
                        "code": _safe_code(status_response.json(), "REFRESH_JOB_UNAVAILABLE"),
                    }))
                    return 1
                final_job = status_response.json()
                if final_job.get("state") in {"succeeded", "failed", "cancelled"}:
                    break
            if not final_job or final_job.get("state") != "succeeded":
                print(json.dumps({
                    "status": "failed",
                    "code": _safe_code(final_job or {}, "REFRESH_WAIT_TIMEOUT"),
                }))
                return 1
            final_response = await client.get(endpoint, params=params)
            if final_response.status_code != 200:
                print(json.dumps({"status": "failed", "code": "SNAPSHOT_NOT_AVAILABLE"}))
                return 1
            snapshot = final_response.json().get("snapshot", {})
            print(json.dumps({
                "status": "succeeded", "source": args.source, "job_id": job_id,
                "snapshot_status": snapshot.get("status"),
                "tile_id": snapshot.get("tile_id"),
            }))
            return 0
    except (httpx.HTTPError, ValueError):
        print(json.dumps({"status": "failed", "code": "SNAPSHOT_SERVER_UNAVAILABLE"}))
        return 1


async def _run_isolated(args: argparse.Namespace) -> int:
    print(ISOLATED_WARNING)
    async with app.router.lifespan_context(app):
        manager = getattr(app.state, f"{args.source}_snapshot_manager", None)
        if manager is None:
            print(json.dumps({"status": "skipped", "code": "SNAPSHOTS_NOT_CONFIGURED"}))
            return 2
        try:
            if args.source == "sst":
                job = await manager.queue(
                    args.latitude, args.longitude, retry_failed=args.retry_failed
                )
            else:
                job = await manager.queue(args.latitude, args.longitude)
        except RefreshBlockedError as exc:
            print(json.dumps({
                "state": "failed", "source": args.source,
                "error_code": exc.gate.error_code,
                "retryable": exc.gate.classification.value == "retryable",
            }))
            return 1
        if args.wait:
            job = await manager.jobs.wait(job.job_id, manager.wait_timeout_seconds)
        if args.status:
            print((await manager.job_status(job.job_id)).model_dump_json())
        else:
            print(json.dumps({
                "job_id": job.job_id, "source": job.source,
                "tile_id": job.tile_id, "state": job.state.value,
            }))
        return 0 if not args.wait or job.state.value == "succeeded" else 1


async def _run(args: argparse.Namespace) -> int:
    if args.latitude is None or args.longitude is None:
        raise SystemExit("--latitude and --longitude are required")
    return await (_run_isolated(args) if args.isolated else _run_server(args))


def main() -> int:
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
