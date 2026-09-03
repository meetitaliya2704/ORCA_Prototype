import pytest

from app.jobs import warm_snapshots
from app.jobs.warm_snapshots import _parser


def test_warm_cli_accepts_only_sst_and_safe_point_arguments():
    args = _parser().parse_args([
        "--source", "sst", "--latitude", "18.025", "--longitude", "70.525",
        "--retry-failed", "--wait", "--status"
    ])
    assert args.source == "sst"
    assert args.latitude == 18.025
    assert args.longitude == 70.525
    assert args.wait is True
    assert args.status is True
    assert args.retry_failed is True


def test_warm_cli_rejects_unmigrated_sources():
    with pytest.raises(SystemExit):
        _parser().parse_args(["--source", "waves"])


def test_warm_cli_accepts_chlorophyll_server_mode():
    args = _parser().parse_args([
        "--source", "chlorophyll", "--latitude", "18.025",
        "--longitude", "70.525", "--wait", "--status",
    ])
    assert args.source == "chlorophyll"
    assert args.server_url == "http://127.0.0.1:8000"
    assert args.isolated is False


@pytest.mark.asyncio
async def test_chlorophyll_server_mode_uses_running_server_not_local_manager(
    monkeypatch, capsys
):
    calls = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"snapshot": {"status": "fresh", "tile_id": "safe-tile"}}

    class Client:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs["base_url"]))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, path, params=None):
            calls.append(("get", path, params))
            return Response()

    monkeypatch.setattr(warm_snapshots.httpx, "AsyncClient", Client)
    args = _parser().parse_args([
        "--source", "chlorophyll", "--latitude", "18.025",
        "--longitude", "70.525",
    ])
    assert await warm_snapshots._run(args) == 0
    assert calls[1][1] == "/v1/marine/chlorophyll"
    assert "succeeded" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_server_mode_polls_shared_job_then_rerequests_chlorophyll(
    monkeypatch
):
    calls = []

    class Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    responses = iter((
        Response(202, {"job_id": "safejob", "tile": {"id": "tile"}}),
        Response(200, {"state": "succeeded"}),
        Response(200, {"snapshot": {"status": "fresh", "tile_id": "tile"}}),
    ))

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, path, params=None):
            calls.append(path)
            return next(responses)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(warm_snapshots.httpx, "AsyncClient", Client)
    monkeypatch.setattr(warm_snapshots.asyncio, "sleep", no_sleep)
    args = _parser().parse_args([
        "--source", "chlorophyll", "--latitude", "18.025",
        "--longitude", "70.525", "--wait", "--poll-seconds", "0.05",
    ])
    assert await warm_snapshots._run(args) == 0
    assert calls == [
        "/v1/marine/chlorophyll",
        "/v1/marine/refresh/jobs/safejob",
        "/v1/marine/chlorophyll",
    ]
