from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.clients import resilient_http
from app.clients.resilient_http import SourceUnavailableError


@pytest.mark.asyncio
async def test_retry_helper_uses_configured_attempt_count(monkeypatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, request=request)

    monkeypatch.setattr(
        resilient_http,
        "get_settings",
        lambda: SimpleNamespace(http_retry_attempts=2),
    )
    monkeypatch.setattr(resilient_http.asyncio, "sleep", AsyncMock())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(SourceUnavailableError):
            await resilient_http.get_json_with_retry(
                client,
                "https://source.test/data",
            )

    assert calls == 2
