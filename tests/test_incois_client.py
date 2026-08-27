import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from app.clients.incois_pfz import IncoisPFZClient
from app.parsers.pfz_html import PFZParseError


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_client_creates_new_session_and_succeeds_on_retry(
    monkeypatch,
) -> None:
    home_calls = 0
    sector_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal home_calls, sector_calls

        if request.url.path.endswith("TextDataHome"):
            home_calls += 1
            return httpx.Response(
                200,
                text=load_fixture("incois_home.html"),
                headers={"set-cookie": f"JSESSIONID=session-{home_calls}; Path=/"},
            )

        sector_calls += 1
        assert request.headers.get("cookie") == (
            f"JSESSIONID=session-{sector_calls}"
        )
        fixture = "invalid_session.html" if sector_calls == 1 else "incois_sec001.html"
        return httpx.Response(200, text=load_fixture(fixture))

    transport = httpx.MockTransport(handler)

    def client_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=transport,
            base_url="https://incois.test",
            follow_redirects=True,
        )

    client = IncoisPFZClient(
        base_url="https://incois.test",
        client_factory=client_factory,
    )
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    result = await client.fetch_sector("SEC001")

    assert result.sector_code == "SEC001"
    assert home_calls == 2
    assert sector_calls == 2


@pytest.mark.asyncio
async def test_batch_uses_one_session_fetches_all_and_bounds_concurrency() -> None:
    home_calls = 0
    requested_sectors: list[str] = []
    active_requests = 0
    maximum_active_requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal home_calls, active_requests, maximum_active_requests

        if request.url.path.endswith("TextDataHome"):
            home_calls += 1
            return httpx.Response(
                200,
                text=load_fixture("incois_home_sectors.html"),
                headers={"set-cookie": "JSESSIONID=batch-session; Path=/"},
            )

        requested_sectors.append(request.url.params["secid"])
        assert request.headers.get("cookie") == "JSESSIONID=batch-session"
        active_requests += 1
        maximum_active_requests = max(maximum_active_requests, active_requests)
        await asyncio.sleep(0)
        active_requests -= 1
        return httpx.Response(200, text=load_fixture("incois_sec001.html"))

    transport = httpx.MockTransport(handler)
    client = IncoisPFZClient(
        base_url="https://incois.test",
        fetch_concurrency=2,
        client_factory=lambda: httpx.AsyncClient(
            transport=transport,
            base_url="https://incois.test",
            follow_redirects=True,
        ),
    )

    result = await client.fetch_batch_once()

    assert home_calls == 1
    assert requested_sectors == ["SEC001", "SEC003", "SEC004"]
    assert maximum_active_requests == 2
    assert [
        item.discovered_sector.sector_code for item in result.sector_results
    ] == ["SEC001", "SEC003", "SEC004"]


@pytest.mark.asyncio
async def test_failure_logging_contains_safe_structural_metadata(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("TextDataHome"):
            return httpx.Response(
                200,
                text=load_fixture("incois_home.html"),
                headers={"set-cookie": "session=sensitive-cookie-value"},
            )
        return httpx.Response(
            200,
            text=load_fixture("invalid_session.html"),
            headers={"content-type": "text/html;charset=UTF-8"},
        )

    client = IncoisPFZClient(
        base_url="https://incois.test",
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://incois.test",
            follow_redirects=True,
        ),
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(PFZParseError):
            await client.fetch_sector_once_fresh("SEC001")

    message = caplog.messages[-1]
    assert '"stage": "page_marker_validation"' in message
    assert '"sector_code": "SEC001"' in message
    assert '"error_code": "INVALID_PFZ_RESPONSE"' in message
    assert '"http_status": 200' in message
    assert '"final_url": "https://incois.test/TextData?secid=SEC001"' in message
    assert '"content_type": "text/html;charset=UTF-8"' in message
    assert '"response_length":' in message
    assert '"has_forecastdata": false' in message
    assert '"has_satmsg": false' in message
    assert '"has_sectorname": false' in message
    assert '"exception_class": "PFZParseError"' in message
    assert "sensitive-cookie-value" not in message
    assert "cookie" not in message.lower()
    assert "authorization" not in message.lower()

