from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import Any
import httpx
from pydantic import SecretStr

logger = logging.getLogger(__name__)


class IMDClientError(Exception):
    """Base exception for IMD API client errors."""


class IMDAuthenticationError(IMDClientError):
    """Authentication failed (invalid credentials, expired key, IP mismatch)."""


class IMDQuotaExceededError(IMDClientError):
    """Daily or hourly rate limit / quota exceeded."""


class IMDSourceUnavailableError(IMDClientError):
    """IMD server down, 5xx, or network timeout."""


class IMDClient:
    """Client for official India Meteorological Department (api.imd.gov.in) API.
    
    Adheres strictly to AGENTS.md and IMD Terms:
    - Dual auth: X-API-KEY and Bearer JWT
    - JWT lifecycle management (1 hour expiry, proactive renewal at 50 min)
    - Concurrency throttle via asyncio.Semaphore
    - Bounded retries (max 1) for transient network/5xx errors
    - Never logs secrets, passwords, or full bearer tokens
    """

    def __init__(
        self,
        base_url: str = "https://api.imd.gov.in",
        api_key: SecretStr | str | None = None,
        email: str | None = None,
        password: SecretStr | str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
        max_concurrency: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self._email = email
        self._password = password.get_secret_value() if isinstance(password, SecretStr) else password
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrency)

        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(timeout, connect=5.0),
            headers={"User-Agent": "ORCA-Marine-Platform/1.0"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> IMDClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def get_access_token(self, force_refresh: bool = False) -> str:
        """Fetch or return cached JWT token with proactive renewal."""
        now = datetime.now(UTC)
        if (
            not force_refresh
            and self._token
            and self._token_expires_at
            and now < self._token_expires_at
        ):
            return self._token

        if not self._email or not self._password:
            raise IMDAuthenticationError("IMD email and password are required for JWT authentication")

        token_url = f"{self.base_url}/api/oauth/token.php"
        try:
            response = await self._client.post(
                token_url,
                json={"email": self._email, "password": self._password},
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise IMDSourceUnavailableError(f"Failed to connect to IMD OAuth server: {exc}") from exc

        if response.status_code in (401, 403):
            raise IMDAuthenticationError(f"IMD OAuth rejected credentials (status {response.status_code})")
        if response.status_code >= 500:
            raise IMDSourceUnavailableError(f"IMD OAuth server error (status {response.status_code})")

        data = response.json()
        token = data.get("access_token")
        if not token:
            raise IMDAuthenticationError("IMD OAuth response missing 'access_token'")

        expires_in = data.get("expires_in", 3600)
        # Proactively refresh 10 minutes prior to expiration
        margin = min(600, max(60, expires_in // 6))
        self._token = token
        self._token_expires_at = now + timedelta(seconds=(expires_in - margin))
        return token

    async def _request(self, method: str, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send authenticated request with X-API-KEY and Bearer token."""
        if not self._api_key:
            raise IMDAuthenticationError("IMD API key is not configured")

        token = await self.get_access_token()
        headers = {
            "X-API-KEY": self._api_key,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        async with self._semaphore:
            # Bounded retry: try once, retry at most once on 401 (token refresh) or transient 5xx
            for attempt in range(2):
                try:
                    response = await self._client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                    )
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    raise IMDSourceUnavailableError(f"IMD request timed out or network failed: {exc}") from exc

                # Token might have been invalidated early on server side
                if response.status_code == 401 and attempt == 0:
                    token = await self.get_access_token(force_refresh=True)
                    headers["Authorization"] = f"Bearer {token}"
                    continue

                if response.status_code == 429:
                    raise IMDQuotaExceededError("IMD API quota or rate limit exceeded")
                if response.status_code in (401, 403):
                    raise IMDAuthenticationError(
                        f"IMD request unauthorized (HTTP {response.status_code}). Check API key, IP binding, or credentials."
                    )
                if response.status_code >= 500:
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    raise IMDSourceUnavailableError(f"IMD server returned HTTP {response.status_code}")

                try:
                    return response.json()
                except Exception as exc:
                    raise IMDSourceUnavailableError("Invalid JSON returned by IMD API") from exc

            raise IMDSourceUnavailableError("IMD request exhausted retry attempts")

    async def get_port_warnings(self) -> dict[str, Any]:
        """Fetch port warnings from /api/v1/portwarning."""
        return await self._request("GET", "api/v1/portwarning")

    async def get_coastal_bulletin(self) -> dict[str, Any]:
        """Fetch coastal bulletin from /api/v1/coastalbulletin."""
        return await self._request("GET", "api/v1/coastalbulletin")

    async def get_cyclone_cone(self) -> dict[str, Any]:
        """Fetch cyclone cone of uncertainty GeoJSON from /api/v1/cyclone_cou."""
        return await self._request("GET", "api/v1/cyclone_cou")

