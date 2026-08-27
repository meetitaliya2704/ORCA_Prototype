import asyncio
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.parsers.pfz_html import is_valid_pfz_sector_html


class PFZSourceUnavailableError(RuntimeError):
    """Raised after a fresh-session retry also fails."""


@dataclass(frozen=True)
class PFZPageBundle:
    sector_code: str
    home_html: str
    sector_html: str
    source_url: str


ClientFactory = Callable[[], httpx.AsyncClient]


class IncoisPFZClient:
    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 20.0,
        session_attempts: int = 2,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.session_attempts = max(1, session_attempts)
        self.client_factory = client_factory

    def _new_client(self) -> httpx.AsyncClient:
        if self.client_factory is not None:
            return self.client_factory()

        timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=10.0,
            pool=5.0,
        )
        transport = httpx.AsyncHTTPTransport(retries=1)
        return httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
            headers={
                "User-Agent": "ORCA-Academic-Prototype/0.1",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-IN,en;q=0.9",
            },
        )

    async def fetch_sector(self, sector_code: str) -> PFZPageBundle:
        sector_code = sector_code.strip().upper()
        last_error: Exception | None = None

        for attempt in range(self.session_attempts):
            try:
                async with self._new_client() as client:
                    home_response = await client.get(
                        f"{self.base_url}/TextDataHome",
                        params={"mfid": "1", "request_locale": "en"},
                    )
                    home_response.raise_for_status()

                    sector_response = await client.get(
                        f"{self.base_url}/TextData",
                        params={"secid": sector_code},
                        headers={"Referer": str(home_response.url)},
                    )
                    sector_response.raise_for_status()

                    if not is_valid_pfz_sector_html(sector_response.text):
                        raise ValueError(
                            "Response is not a PFZ data page; session may be invalid"
                        )

                    return PFZPageBundle(
                        sector_code=sector_code,
                        home_html=home_response.text,
                        sector_html=sector_response.text,
                        source_url=str(sector_response.url),
                    )

            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < self.session_attempts - 1:
                    await asyncio.sleep(2**attempt)

        raise PFZSourceUnavailableError(
            f"INCOIS PFZ data unavailable for {sector_code} after "
            f"{self.session_attempts} session attempts"
        ) from last_error
