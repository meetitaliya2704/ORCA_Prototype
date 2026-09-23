from __future__ import annotations

import json
from pathlib import Path
import httpx
import pytest

from app.clients.imd_client import (
    IMDAuthenticationError,
    IMDClient,
    IMDQuotaExceededError,
    IMDSourceUnavailableError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "imd"


@pytest.mark.asyncio
async def test_imd_client_jwt_and_dual_auth():
    sample_ports = json.loads((FIXTURES_DIR / "port_warnings_sample.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        # 1. OAuth token request
        if request.url.path == "/api/oauth/token.php":
            payload = json.loads(request.content.decode("utf-8"))
            if payload.get("email") == "marine@orca.in" and payload.get("password") == "secret123":
                return httpx.Response(200, json={"access_token": "mock-jwt-token-xyz", "expires_in": 3600})
            return httpx.Response(401, json={"message": "Invalid credentials"})

        # 2. Port warning endpoint
        if request.url.path == "/api/v1/portwarning":
            assert request.headers.get("x-api-key") == "test-imd-api-key"
            assert request.headers.get("authorization") == "Bearer mock-jwt-token-xyz"
            return httpx.Response(200, json=sample_ports)

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with IMDClient(
        base_url="https://api.imd.gov.in",
        api_key="test-imd-api-key",
        email="marine@orca.in",
        password="secret123",
        transport=transport,
    ) as client:
        data = await client.get_port_warnings()
        assert data["status"] == "success"
        assert len(data["warnings"]) == 3


@pytest.mark.asyncio
async def test_imd_client_auth_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "IP Not Registered or Invalid Key"})

    transport = httpx.MockTransport(handler)
    async with IMDClient(
        base_url="https://api.imd.gov.in",
        api_key="test-imd-api-key",
        email="marine@orca.in",
        password="wrong_password",
        transport=transport,
    ) as client:
        with pytest.raises(IMDAuthenticationError):
            await client.get_access_token()


@pytest.mark.asyncio
async def test_imd_client_rate_limit_exceeded():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/oauth/token.php":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        if request.url.path == "/api/v1/coastalbulletin":
            return httpx.Response(429, json={"error": "Rate limit exceeded"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with IMDClient(
        base_url="https://api.imd.gov.in",
        api_key="test-imd-api-key",
        email="marine@orca.in",
        password="secret",
        transport=transport,
    ) as client:
        with pytest.raises(IMDQuotaExceededError):
            await client.get_coastal_bulletin()

