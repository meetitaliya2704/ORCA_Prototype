import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.core.performance import performance_span

from app.parsers.pfz_html import (
    PFZParseError,
    is_valid_pfz_sector_html,
    parse_pfz_sector_options,
    pfz_marker_presence,
)
from app.schemas.pfz import DiscoveredPFZSector


class PFZSourceUnavailableError(RuntimeError):
    """Raised when INCOIS cannot be reached for a PFZ request."""


logger = logging.getLogger(__name__)


def _safe_source_url(value: str | httpx.URL) -> str:
    """Remove credentials and server-managed path/query state from a URL."""
    parsed = urlsplit(str(value))
    safe_path = re.sub(r";[^/]*", "", parsed.path)
    safe_query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query)
            if key.lower() in {"mfid", "request_locale", "secid"}
        ]
    )
    return urlunsplit(
        (parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], safe_path, safe_query, "")
    )


def log_pfz_failure(
    *,
    stage: str,
    error_code: str,
    exception: BaseException,
    sector_code: str | None = None,
    response: httpx.Response | None = None,
    pages: "PFZPageBundle | None" = None,
) -> None:
    if response is not None:
        markers = pfz_marker_presence(response.text)
        http_status = response.status_code
        final_url = _safe_source_url(response.url)
        response_length = len(response.content)
        content_type = response.headers.get("content-type")
    elif pages is not None:
        markers = pfz_marker_presence(pages.sector_html)
        http_status = pages.http_status
        final_url = pages.source_url
        response_length = pages.response_length
        content_type = pages.content_type
    else:
        markers = {
            "has_forecastdata": False,
            "has_satmsg": False,
            "has_sectorname": False,
        }
        http_status = None
        final_url = None
        response_length = None
        content_type = None

    diagnostic = {
        "stage": stage,
        "sector_code": sector_code,
        "error_code": error_code,
        "http_status": http_status,
        "final_url": final_url,
        "response_length": response_length,
        "content_type": content_type,
        **markers,
        "exception_class": type(exception).__name__,
    }
    logger.warning("PFZ failure: %s", json.dumps(diagnostic, sort_keys=True))


@dataclass(frozen=True)
class PFZPageBundle:
    sector_code: str
    home_html: str
    sector_html: str
    source_url: str
    http_status: int | None = None
    response_length: int | None = None
    content_type: str | None = None


@dataclass(frozen=True)
class PFZBatchSectorResult:
    discovered_sector: DiscoveredPFZSector
    pages: PFZPageBundle | None = None
    error: PFZSourceUnavailableError | PFZParseError | None = None


@dataclass(frozen=True)
class PFZBatchPageBundle:
    discovered_sectors: tuple[DiscoveredPFZSector, ...]
    sector_results: tuple[PFZBatchSectorResult, ...]


ClientFactory = Callable[[], httpx.AsyncClient]


class IncoisPFZClient:
    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout: float = 5.0,
        read_timeout: float = 20.0,
        fetch_concurrency: int = 4,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        if not 1 <= fetch_concurrency <= 20:
            raise ValueError("fetch_concurrency must be between 1 and 20")
        self.fetch_concurrency = fetch_concurrency
        self.client_factory = client_factory

    @property
    def home_url(self) -> str:
        return f"{self.base_url}/TextDataHome?mfid=1&request_locale=en"

    def _new_client(self) -> httpx.AsyncClient:
        if self.client_factory is not None:
            return self.client_factory()

        timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=10.0,
            pool=5.0,
        )
        # The only PFZ retry is the explicit fresh-session retry coordinated
        # by the service. A transport retry could reuse a failed session.
        transport = httpx.AsyncHTTPTransport(retries=0)
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

    async def _bootstrap(self, client: httpx.AsyncClient) -> httpx.Response:
        response: httpx.Response | None = None
        try:
            with performance_span("provider.session_bootstrap"):
                response = await client.get(
                    f"{self.base_url}/TextDataHome",
                    params={"mfid": "1", "request_locale": "en"},
                )
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            log_pfz_failure(
                stage="text_data_home_request",
                error_code="SOURCE_UNAVAILABLE",
                exception=exc,
                response=response,
            )
            raise PFZSourceUnavailableError(
                "INCOIS PFZ source unavailable during bootstrap"
            ) from exc

    async def _fetch_sector_with_session(
        self,
        client: httpx.AsyncClient,
        *,
        home_html: str,
        sector_code: str,
        semaphore: asyncio.Semaphore | None = None,
    ) -> PFZPageBundle:
        async def fetch() -> PFZPageBundle:
            response: httpx.Response | None = None
            try:
                with performance_span("provider.sector_retrieval"):
                    response = await client.get(
                        f"{self.base_url}/TextData",
                        params={"secid": sector_code},
                        headers={"Referer": self.home_url},
                    )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                log_pfz_failure(
                    stage="sector_request",
                    sector_code=sector_code,
                    error_code="SOURCE_UNAVAILABLE",
                    exception=exc,
                    response=response,
                )
                raise PFZSourceUnavailableError(
                    f"INCOIS PFZ sector {sector_code} unavailable"
                ) from exc

            assert response is not None
            with performance_span("provider.html_validation"):
                valid_page = is_valid_pfz_sector_html(response.text)
            if not valid_page:
                error = PFZParseError(
                    f"INCOIS PFZ sector {sector_code} is missing page markers",
                    stage="page_marker_validation",
                )
                log_pfz_failure(
                    stage=error.stage,
                    sector_code=sector_code,
                    error_code="INVALID_PFZ_RESPONSE",
                    exception=error,
                    response=response,
                )
                raise error

            return PFZPageBundle(
                sector_code=sector_code,
                home_html=home_html,
                sector_html=response.text,
                source_url=_safe_source_url(response.url),
                http_status=response.status_code,
                response_length=len(response.content),
                content_type=response.headers.get("content-type"),
            )

        if semaphore is None:
            return await fetch()
        with performance_span("semaphore.wait"):
            await semaphore.acquire()
        try:
            return await fetch()
        finally:
            semaphore.release()

    async def fetch_batch_once(self) -> PFZBatchPageBundle:
        """Bootstrap once and fetch all dynamically discovered sectors."""
        async with self._new_client() as client:
            home_response = await self._bootstrap(client)
            home_html = home_response.text
            try:
                with performance_span("provider.sector_discovery"):
                    discovered = tuple(parse_pfz_sector_options(home_html))
            except PFZParseError as exc:
                log_pfz_failure(
                    stage=exc.stage,
                    error_code=(
                        "NO_SECTORS_DISCOVERED"
                        if exc.stage == "sector_discovery"
                        else "INVALID_PFZ_RESPONSE"
                    ),
                    exception=exc,
                    response=home_response,
                )
                raise
            semaphore = asyncio.Semaphore(self.fetch_concurrency)

            raw_results = await asyncio.gather(
                *(
                    self._fetch_sector_with_session(
                        client,
                        home_html=home_html,
                        sector_code=sector.sector_code,
                        semaphore=semaphore,
                    )
                    for sector in discovered
                ),
                return_exceptions=True,
            )

        sector_results: list[PFZBatchSectorResult] = []
        for sector, result in zip(discovered, raw_results, strict=True):
            if isinstance(result, PFZPageBundle):
                sector_results.append(
                    PFZBatchSectorResult(
                        discovered_sector=sector,
                        pages=result,
                    )
                )
            elif isinstance(result, PFZParseError):
                sector_results.append(
                    PFZBatchSectorResult(
                        discovered_sector=sector,
                        error=result,
                    )
                )
            elif isinstance(result, PFZSourceUnavailableError):
                sector_results.append(
                    PFZBatchSectorResult(
                        discovered_sector=sector,
                        error=result,
                    )
                )
            else:
                sector_results.append(
                    PFZBatchSectorResult(
                        discovered_sector=sector,
                        error=PFZSourceUnavailableError(
                            f"INCOIS PFZ sector {sector.sector_code} unavailable"
                        ),
                    )
                )

        return PFZBatchPageBundle(
            discovered_sectors=discovered,
            sector_results=tuple(sector_results),
        )

    async def fetch_sector_once_fresh(
        self,
        sector_code: str,
    ) -> PFZPageBundle:
        """Retry one sector with a completely fresh bootstrapped session."""
        async with self._new_client() as client:
            home_html = (await self._bootstrap(client)).text
            return await self._fetch_sector_with_session(
                client,
                home_html=home_html,
                sector_code=sector_code,
            )

    async def fetch_sector(self, sector_code: str) -> PFZPageBundle:
        """Preserve the preview flow with exactly one fresh-session retry."""
        normalized = sector_code.strip().upper()
        last_error: PFZSourceUnavailableError | PFZParseError | None = None

        for attempt in range(2):
            try:
                return await self.fetch_sector_once_fresh(normalized)
            except (PFZSourceUnavailableError, PFZParseError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(1)

        assert last_error is not None
        raise last_error
