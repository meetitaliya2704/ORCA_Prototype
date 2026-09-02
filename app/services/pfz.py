import asyncio
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta, timezone

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
    NearestPFZLocation,
    NearestPFZQueryResult,
    NearestPFZResponse,
    PFZAdvisory,
    PFZCacheStatus,
    PFZGeoJSONFeature,
    PFZGeoJSONGeometry,
    PFZGeoJSONProperties,
    PFZLocation,
    PFZSectorErrorCode,
    PFZSnapshot,
    PFZSnapshotCompleteness,
    PFZSourceMetadata,
    PFZValueRange,
    SuccessfulPFZSector,
)
from app.services.cache import JsonCache
from app.core.performance import annotate_trace, measured_async, measured_lock, performance_span
from app.services.geospatial import (
    compass_direction,
    haversine_distance_km,
    initial_bearing_deg,
)


PFZ_FRESH_CACHE_KEY = "pfz:snapshot:fresh"
PFZ_LAST_SUCCESS_CACHE_KEY = "pfz:snapshot:last_success"
ASIA_KOLKATA = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")


class NoValidPFZError(LookupError):
    """Raised when no stored snapshot advisory is valid for the query time."""


def normalize_pfz_validity(
    forecast_date: date | None,
    valid_until_date: date | None,
) -> tuple[datetime, datetime] | None:
    """Interpret inclusive INCOIS calendar dates in Asia/Kolkata.

    Asia/Kolkata is UTC+05:30 for contemporary INCOIS advisories. A fixed
    standard-library timezone keeps this deterministic on systems without the
    optional IANA timezone database.
    """
    if (
        forecast_date is None
        or valid_until_date is None
        or valid_until_date < forecast_date
    ):
        return None

    valid_from = datetime.combine(
        forecast_date,
        time.min,
        tzinfo=ASIA_KOLKATA,
    ).astimezone(UTC)
    valid_until = datetime.combine(
        valid_until_date,
        time.max,
        tzinfo=ASIA_KOLKATA,
    ).astimezone(UTC)
    return valid_from, valid_until


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
        with performance_span("provider.parsing"):
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
            async with measured_lock(self._retry_semaphore, "semaphore.wait"):
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
        with performance_span("normalize.sectors"):
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

    @measured_async("service.total")
    async def get_snapshot(self) -> PFZSnapshot:
        cached = await self._load_cached(PFZ_FRESH_CACHE_KEY)
        if cached is not None:
            annotate_trace(cache_status="fresh")
            return cached.model_copy(
                update={"cache_status": PFZCacheStatus.FRESH}
            )

        with performance_span("singleflight.wait"):
            await self._refresh_lock.acquire()
        try:
            cached = await self._load_cached(PFZ_FRESH_CACHE_KEY)
            if cached is not None:
                annotate_trace(cache_status="fresh")
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
            annotate_trace(cache_status="refreshed")
            return snapshot
        finally:
            self._refresh_lock.release()


class PFZNearestService:
    def __init__(
        self,
        *,
        snapshot_service: PFZSnapshotService,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.snapshot_service = snapshot_service
        self._now = now or (lambda: datetime.now(UTC))

    def _query_time(self, supplied: datetime | None) -> datetime:
        value = supplied if supplied is not None else self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("query time must be timezone-aware")
        return value.astimezone(UTC)

    async def get_nearest(
        self,
        *,
        latitude: float,
        longitude: float,
        at: datetime | None = None,
    ) -> NearestPFZResponse:
        query_time = self._query_time(at)
        snapshot = await self.snapshot_service.get_snapshot()
        validity_warnings: list[str] = []
        candidates: list[
            tuple[
                tuple[float, str, str, float, float],
                SuccessfulPFZSector,
                PFZLocation,
                datetime,
                datetime,
                float,
            ]
        ] = []

        for sector in snapshot.successful_sectors:
            advisory = sector.advisory
            validity = normalize_pfz_validity(
                advisory.forecast_date,
                advisory.valid_until,
            )
            if validity is None:
                validity_warnings.append(
                    f"{advisory.sector_code}: excluded advisory with unusable validity"
                )
                continue

            valid_from, valid_until = validity
            if not valid_from <= query_time <= valid_until:
                continue

            for location in advisory.locations:
                raw_distance = haversine_distance_km(
                    latitude,
                    longitude,
                    location.latitude,
                    location.longitude,
                )
                tie_break = (
                    raw_distance,
                    advisory.sector_code,
                    location.landing_centre,
                    location.latitude,
                    location.longitude,
                )
                candidates.append(
                    (
                        tie_break,
                        sector,
                        location,
                        valid_from,
                        valid_until,
                        raw_distance,
                    )
                )

        if not candidates:
            raise NoValidPFZError(
                "No PFZ advisory is valid for the requested time"
            )

        (
            _,
            selected_sector,
            selected_location,
            valid_from,
            valid_until,
            raw_distance,
        ) = min(candidates, key=lambda candidate: candidate[0])
        advisory = selected_sector.advisory
        raw_bearing = initial_bearing_deg(
            latitude,
            longitude,
            selected_location.latitude,
            selected_location.longitude,
        )
        rounded_distance = round(raw_distance, 3)
        rounded_bearing = round(raw_bearing, 2) % 360
        direction = compass_direction(raw_bearing)

        warnings = [*snapshot.warnings, *validity_warnings]
        partial_warning = (
            "Nearest PFZ is based on a partial snapshot; some sectors were "
            "unavailable or invalid."
        )
        if (
            snapshot.completeness == PFZSnapshotCompleteness.PARTIAL
            and partial_warning not in warnings
        ):
            warnings.append(partial_warning)

        nearest = NearestPFZLocation(
            sector_code=advisory.sector_code,
            region_name=advisory.region_name,
            landing_centre=selected_location.landing_centre,
            latitude=selected_location.latitude,
            longitude=selected_location.longitude,
            distance_km=rounded_distance,
            bearing_deg=rounded_bearing,
            direction=direction,
            distance_from_coast_km=PFZValueRange(
                minimum=selected_location.distance_min_km,
                maximum=selected_location.distance_max_km,
            ),
            depth_m=PFZValueRange(
                minimum=selected_location.depth_min_m,
                maximum=selected_location.depth_max_m,
            ),
        )
        properties = PFZGeoJSONProperties(
            sector_code=nearest.sector_code,
            region_name=nearest.region_name,
            landing_centre=nearest.landing_centre,
            distance_km=nearest.distance_km,
            bearing_deg=nearest.bearing_deg,
            direction=nearest.direction,
        )

        return NearestPFZResponse(
            query=NearestPFZQueryResult(
                latitude=latitude,
                longitude=longitude,
                at=query_time,
            ),
            nearest_pfz=nearest,
            valid_from=valid_from,
            valid_until=valid_until,
            forecast_date=advisory.forecast_date,
            source=PFZSourceMetadata(
                name=advisory.source,
                url=advisory.source_url,
                retrieved_at=snapshot.retrieved_at,
            ),
            cache_status=snapshot.cache_status,
            completeness=snapshot.completeness,
            failed_sectors=snapshot.failed_sectors,
            warnings=warnings,
            geojson=PFZGeoJSONFeature(
                geometry=PFZGeoJSONGeometry(
                    coordinates=(nearest.longitude, nearest.latitude),
                ),
                properties=properties,
            ),
        )
