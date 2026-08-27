import asyncio
import re
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from app.clients.incois_pfz import (
    IncoisPFZClient,
    PFZBatchSectorResult,
    PFZPageBundle,
    PFZSourceUnavailableError,
    log_pfz_failure,
)
from app.parsers.pfz_html import PFZParseError, parse_pfz_advisory
from app.schemas.pfz import (
    FailedPFZSector,
    PFZAdvisory,
    PFZCacheStatus,
    PFZSectorErrorCode,
    PFZSnapshot,
    PFZSnapshotCompleteness,
    SuccessfulPFZSector,
)
from app.services.cache import JsonCache


PFZ_FRESH_CACHE_KEY = "pfz:snapshot:fresh"
PFZ_LAST_SUCCESS_CACHE_KEY = "pfz:snapshot:last_success"


class PFZPreviewService:
    def __init__(self, client: IncoisPFZClient) -> None:
        self.client = client

    async def preview_sector(self, sector_code: str) -> PFZAdvisory:
        normalized = sector_code.strip().upper()
        if re.fullmatch(r"SEC\d{3}", normalized) is None:
            raise ValueError("sector_code must use the format SEC001")

        pages = await self.client.fetch_sector(normalized)
        return parse_pfz_advisory(
            sector_html=pages.sector_html,
            home_html=pages.home_html,
            sector_code=pages.sector_code,
            source_url=pages.source_url,
        )


class PFZSnapshotService:
    def __init__(
        self,
        *,
        client: IncoisPFZClient,
        cache: JsonCache,
        fresh_ttl_seconds: int,
        stale_ttl_seconds: int,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self.cache = cache
        self.fresh_ttl_seconds = fresh_ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._refresh_lock = asyncio.Lock()
        self._retry_semaphore = asyncio.Semaphore(client.fetch_concurrency)

    async def _load_cached(self, key: str) -> PFZSnapshot | None:
        value = await self.cache.get(key)
        if value is None:
            return None
        try:
            return PFZSnapshot.model_validate(value)
        except ValidationError as exc:
            log_pfz_failure(
                stage="cache_deserialization",
                error_code="INVALID_CACHED_SNAPSHOT",
                exception=exc,
            )
            return None

    @staticmethod
    def _parse_pages(
        pages: PFZPageBundle,
        retrieved_at: datetime,
    ) -> PFZAdvisory:
        advisory = parse_pfz_advisory(
            sector_html=pages.sector_html,
            home_html=pages.home_html,
            sector_code=pages.sector_code,
            source_url=pages.source_url,
        )
        return advisory.model_copy(update={"fetched_at": retrieved_at})

    async def _normalize_sector(
        self,
        initial: PFZBatchSectorResult,
        retrieved_at: datetime,
    ) -> SuccessfulPFZSector | FailedPFZSector:
        if initial.pages is not None:
            try:
                advisory = self._parse_pages(initial.pages, retrieved_at)
                return SuccessfulPFZSector(
                    discovered_sector=initial.discovered_sector,
                    advisory=advisory,
                )
            except PFZParseError as exc:
                log_pfz_failure(
                    stage=exc.stage,
                    sector_code=initial.discovered_sector.sector_code,
                    error_code="INVALID_PFZ_RESPONSE",
                    exception=exc,
                    pages=initial.pages,
                )
                pass

        retry_pages: PFZPageBundle | None = None
        try:
            async with self._retry_semaphore:
                retry_pages = await self.client.fetch_sector_once_fresh(
                    initial.discovered_sector.sector_code
                )
            advisory = self._parse_pages(retry_pages, retrieved_at)
            return SuccessfulPFZSector(
                discovered_sector=initial.discovered_sector,
                advisory=advisory,
            )
        except PFZSourceUnavailableError:
            return FailedPFZSector(
                discovered_sector=initial.discovered_sector,
                code=PFZSectorErrorCode.SOURCE_UNAVAILABLE,
                message="INCOIS PFZ sector unavailable after one retry",
            )
        except PFZParseError as exc:
            if retry_pages is not None:
                log_pfz_failure(
                    stage=exc.stage,
                    sector_code=initial.discovered_sector.sector_code,
                    error_code="INVALID_PFZ_RESPONSE",
                    exception=exc,
                    pages=retry_pages,
                )
            return FailedPFZSector(
                discovered_sector=initial.discovered_sector,
                code=PFZSectorErrorCode.INVALID_PFZ_RESPONSE,
                message="INCOIS PFZ sector response invalid after one retry",
            )

    async def _refresh(self) -> PFZSnapshot:
        batch = await self.client.fetch_batch_once()
        retrieved_at = self._now()
        normalized = await asyncio.gather(
            *(
                self._normalize_sector(result, retrieved_at)
                for result in batch.sector_results
            )
        )

        successful = [
            result for result in normalized if isinstance(result, SuccessfulPFZSector)
        ]
        failed = [
            result for result in normalized if isinstance(result, FailedPFZSector)
        ]

        if not successful:
            if any(
                result.code == PFZSectorErrorCode.SOURCE_UNAVAILABLE
                for result in failed
            ):
                raise PFZSourceUnavailableError(
                    "INCOIS PFZ source unavailable after sector retries"
                )
            raise PFZParseError(
                "INCOIS returned no valid PFZ sector advisories"
            )

        warnings = [
            f"{result.discovered_sector.sector_code}: {warning}"
            for result in successful
            for warning in result.advisory.parse_warnings
        ]
        warnings.extend(
            f"{result.discovered_sector.sector_code}: {result.message}"
            for result in failed
        )

        try:
            return PFZSnapshot(
                generated_at=self._now(),
                retrieved_at=retrieved_at,
                discovered_sector_count=len(batch.discovered_sectors),
                successful_sector_count=len(successful),
                failed_sector_count=len(failed),
                discovered_sectors=list(batch.discovered_sectors),
                successful_sectors=successful,
                failed_sectors=failed,
                total_location_count=sum(
                    len(result.advisory.locations) for result in successful
                ),
                completeness=(
                    PFZSnapshotCompleteness.COMPLETE
                    if not failed
                    else PFZSnapshotCompleteness.PARTIAL
                ),
                cache_status=PFZCacheStatus.REFRESHED,
                warnings=warnings,
                source_url=self.client.home_url,
            )
        except ValidationError as exc:
            error = PFZParseError(
                "Normalized PFZ snapshot was invalid",
                stage="snapshot_construction",
            )
            log_pfz_failure(
                stage=error.stage,
                error_code="INVALID_PFZ_RESPONSE",
                exception=exc,
            )
            raise error from exc

    async def _stale_or_raise(
        self,
        error: PFZSourceUnavailableError | PFZParseError,
    ) -> PFZSnapshot:
        stale = await self._load_cached(PFZ_LAST_SUCCESS_CACHE_KEY)
        if stale is None:
            raise error

        warning = (
            "PFZ refresh failed; returning the last successful cached snapshot"
        )
        return stale.model_copy(
            update={
                "cache_status": PFZCacheStatus.STALE,
                "warnings": [*stale.warnings, warning],
            }
        )

    async def get_snapshot(self) -> PFZSnapshot:
        cached = await self._load_cached(PFZ_FRESH_CACHE_KEY)
        if cached is not None:
            return cached.model_copy(
                update={"cache_status": PFZCacheStatus.FRESH}
            )

        async with self._refresh_lock:
            cached = await self._load_cached(PFZ_FRESH_CACHE_KEY)
            if cached is not None:
                return cached.model_copy(
                    update={"cache_status": PFZCacheStatus.FRESH}
                )

            try:
                snapshot = await self._refresh()
            except (PFZSourceUnavailableError, PFZParseError) as exc:
                return await self._stale_or_raise(exc)

            try:
                payload = snapshot.model_dump(mode="json")
            except Exception as exc:
                log_pfz_failure(
                    stage="cache_serialization",
                    error_code="CACHE_SERIALIZATION_FAILED",
                    exception=exc,
                )
                raise
            await self.cache.set(
                PFZ_FRESH_CACHE_KEY,
                payload,
                self.fresh_ttl_seconds,
            )
            await self.cache.set(
                PFZ_LAST_SUCCESS_CACHE_KEY,
                payload,
                self.stale_ttl_seconds,
            )
            return snapshot
