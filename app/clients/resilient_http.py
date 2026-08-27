import asyncio
from typing import Any

import httpx

from app.core.config import get_settings


RETRYABLE_STATUS_CODES = {429, 502, 503, 504}


class SourceUnavailableError(RuntimeError):
    """Raised after all safe retry attempts have failed."""


async def get_json_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    attempts: int | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if attempts is None:
        attempts = get_settings().http_retry_attempts
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            response = await client.get(url, params=params)

            if response.status_code in RETRYABLE_STATUS_CODES:
                raise httpx.HTTPStatusError(
                    "Temporary upstream failure",
                    request=response.request,
                    response=response,
                )

            response.raise_for_status()
            payload = response.json()

            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")

            return payload

        except (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.HTTPStatusError,
            ValueError,
        ) as exc:
            last_error = exc

            if attempt == attempts - 1:
                break

            await asyncio.sleep(2**attempt)

    raise SourceUnavailableError(f"Source unavailable: {url}") from last_error
