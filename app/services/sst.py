import asyncio
import math
from datetime import UTC, datetime, timedelta

import httpx

from app.clients.copernicus_sst import (
    COPERNICUS_SST_PRODUCT_ID,
    InvalidSSTResponseError,
    SSTAuthenticationError,
    SSTProvider,
    SSTProviderCell,
    SSTProviderError,
    SSTSourceNotConfiguredError,
    SSTSourceUnavailableError,
)
from app.schemas.marine import (
    SSTCacheStatus,
    SSTLocation,
    SSTQuality,
    SSTResponse,
    SSTSourceMetadata,
    SourceResult,
    SourceStatus,
)
from app.services.cache import JsonCache
from app.core.performance import measured_async, measured_lock, measured_sync
from app.services.geospatial import haversine_distance_km


# Copernicus grid coordinates may arrive as float32 values (for example,
# 18.0249996185 for the nominal 18.025 grid centre). A sub-metre difference is
# coordinate representation noise, not a coastal fallback. This affects only
# the quality label; selection always uses the full raw Haversine distance.
EXACT_GRID_CELL_TOLERANCE_KM = 0.001


class NoValidSSTError(SSTProviderError):
    pass


def sst_error_code(exc: Exception) -> str:
    if isinstance(exc, NoValidSSTError):
        return "NO_VALID_SST"
    if isinstance(exc, InvalidSSTResponseError):
        return "INVALID_SST_RESPONSE"
    if isinstance(exc, SSTAuthenticationError):
        return "SST_AUTHENTICATION_FAILED"
    if isinstance(exc, SSTSourceNotConfiguredError):
        return "SST_SOURCE_NOT_CONFIGURED"
    return "SST_SOURCE_UNAVAILABLE"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("SST query time must be timezone-aware")
    return value.astimezone(UTC)


class CopernicusSSTService:
    def __init__(
        self,
        *,
        provider: SSTProvider,
        cache: JsonCache,
        dataset_id: str,
        variable: str,
        search_radius_km: float,
        lookback_days: int,
        fresh_ttl_seconds: int,
        stale_ttl_seconds: int,
        now=None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.dataset_id = dataset_id
        self.variable = variable
        self.search_radius_km = search_radius_km
        self.lookback_days = lookback_days
        self.fresh_ttl_seconds = fresh_ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._locks: dict[str, asyncio.Lock] = {}

    def _cache_base(
        self,
        latitude: float,
        longitude: float,
        query_time: datetime,
    ) -> str:
        return (
            f"sst:{self.dataset_id}:{self.variable}:"
            f"{latitude:.6f}:{longitude:.6f}:{query_time.date().isoformat()}"
        )

    def _bounds(
        self,
        latitude: float,
        longitude: float,
    ) -> tuple[float, float, float, float]:
        latitude_delta = self.search_radius_km / 111.195
        cosine = abs(math.cos(math.radians(latitude)))
        longitude_delta = (
            180.0
            if cosine < 1e-12
            else min(180.0, self.search_radius_km / (111.195 * cosine))
        )
        return (
            max(-90.0, latitude - latitude_delta),
            min(90.0, latitude + latitude_delta),
            max(-180.0, longitude - longitude_delta),
            min(180.0, longitude + longitude_delta),
        )

    async def _cached(
        self,
        key: str,
        status: SSTCacheStatus,
        warning: str | None = None,
    ) -> SSTResponse | None:
        value = await self.cache.get(key)
        if value is None:
            return None
        try:
            response = SSTResponse.model_validate(value)
        except Exception:
            return None
        warnings = [*response.warnings]
        if warning is not None and warning not in warnings:
            warnings.append(warning)
        return response.model_copy(
            update={"cache_status": status, "warnings": warnings}
        )

    @measured_sync("normalize.selection")
    def _normalize(
        self,
        *,
        cells: list[SSTProviderCell],
        latitude: float,
        longitude: float,
        start_datetime: datetime,
        query_time: datetime,
        retrieved_at: datetime,
    ) -> SSTResponse:
        eligible: list[tuple[datetime, float, float, float, SSTProviderCell]] = []
        observed_cells: list[tuple[datetime, float, SSTProviderCell]] = []

        for cell in cells:
            try:
                analysis_time = _utc(cell.analysis_time)
            except ValueError as exc:
                raise InvalidSSTResponseError(
                    "Copernicus SST returned a timezone-naive analysis time"
                ) from exc
            if not start_datetime <= analysis_time <= query_time:
                continue

            distance = haversine_distance_km(
                latitude,
                longitude,
                cell.latitude,
                cell.longitude,
            )
            observed_cells.append((analysis_time, distance, cell))
            value = cell.value_kelvin
            if (
                value is None
                or not math.isfinite(value)
                or value == -32768.0
                or distance > self.search_radius_km
            ):
                continue
            eligible.append(
                (
                    analysis_time,
                    distance,
                    cell.latitude,
                    cell.longitude,
                    cell,
                )
            )

        if not eligible:
            raise NoValidSSTError(
                "No valid Copernicus SST cell exists within the configured radius"
            )

        latest_time = max(item[0] for item in eligible)
        latest_candidates = [item for item in eligible if item[0] == latest_time]
        _, raw_distance, _, _, selected = min(
            latest_candidates,
            key=lambda item: (item[1], item[2], item[3]),
        )

        nearest_observed = min(
            (item for item in observed_cells if item[0] == latest_time),
            key=lambda item: (item[1], item[2].latitude, item[2].longitude),
            default=None,
        )
        exact = raw_distance <= EXACT_GRID_CELL_TOLERANCE_KM
        warnings: list[str] = []
        if exact:
            quality = SSTQuality.EXACT_GRID_CELL
        else:
            quality = SSTQuality.NEAREST_VALID_OCEAN_CELL
            if (
                nearest_observed is not None
                and nearest_observed[2].mask is not None
                and nearest_observed[2].mask & 2
            ):
                warnings.append(
                    "Requested grid cell was land; nearest valid ocean cell was used"
                )
            else:
                warnings.append(
                    "Nearest valid ocean cell within the configured radius was used"
                )

        source_kelvin = selected.value_kelvin
        assert source_kelvin is not None
        celsius = source_kelvin - 273.15
        return SSTResponse(
            requested_location=SSTLocation(
                latitude=latitude,
                longitude=longitude,
            ),
            sampled_location=SSTLocation(
                latitude=selected.latitude,
                longitude=selected.longitude,
            ),
            sample_distance_km=round(raw_distance, 3),
            value=round(celsius, 3),
            source_value=round(source_kelvin, 6),
            analysis_time=latest_time,
            retrieved_at=retrieved_at,
            source=SSTSourceMetadata(
                product_id=COPERNICUS_SST_PRODUCT_ID,
                dataset_id=self.dataset_id,
                variable=self.variable,
            ),
            quality=quality,
            cache_status=SSTCacheStatus.REFRESHED,
            warnings=warnings,
        )

    @measured_async("service.total")
    async def get_sst(
        self,
        *,
        latitude: float,
        longitude: float,
        at: datetime | None = None,
    ) -> SSTResponse:
        query_time = _utc(at if at is not None else self._now())
        start_datetime = query_time - timedelta(days=self.lookback_days)
        cache_base = self._cache_base(latitude, longitude, query_time)
        fresh_key = f"{cache_base}:fresh"
        last_success_key = f"{cache_base}:last_success"

        cached = await self._cached(fresh_key, SSTCacheStatus.FRESH)
        if cached is not None:
            return cached

        lock = self._locks.setdefault(cache_base, asyncio.Lock())
        async with measured_lock(lock):
            cached = await self._cached(fresh_key, SSTCacheStatus.FRESH)
            if cached is not None:
                return cached

            minimum_latitude, maximum_latitude, minimum_longitude, maximum_longitude = (
                self._bounds(latitude, longitude)
            )
            try:
                cells = await self.provider.fetch_cells(
                    dataset_id=self.dataset_id,
                    variable=self.variable,
                    minimum_latitude=minimum_latitude,
                    maximum_latitude=maximum_latitude,
                    minimum_longitude=minimum_longitude,
                    maximum_longitude=maximum_longitude,
                    start_datetime=start_datetime,
                    end_datetime=query_time,
                )
                response = self._normalize(
                    cells=cells,
                    latitude=latitude,
                    longitude=longitude,
                    start_datetime=start_datetime,
                    query_time=query_time,
                    retrieved_at=_utc(self._now()),
                )
            except (NoValidSSTError, InvalidSSTResponseError):
                raise
            except SSTProviderError:
                stale = await self._cached(
                    last_success_key,
                    SSTCacheStatus.STALE,
                    "Copernicus SST refresh failed; returning matching stale data",
                )
                if stale is not None:
                    return stale
                raise

            serialized = response.model_dump(mode="json")
            await self.cache.set(fresh_key, serialized, self.fresh_ttl_seconds)
            await self.cache.set(
                last_success_key,
                serialized,
                self.stale_ttl_seconds,
            )
            return response


class CopernicusSSTMarineSource:
    name = "sst"

    def __init__(self, service: CopernicusSSTService) -> None:
        self.service = service

    async def fetch(
        self,
        client: httpx.AsyncClient,
        latitude: float,
        longitude: float,
        at: datetime | None = None,
    ) -> SourceResult:
        del client
        try:
            response = await self.service.get_sst(
                latitude=latitude,
                longitude=longitude,
                at=at,
            )
        except SSTProviderError as exc:
            return SourceResult(
                source="Copernicus Marine",
                status=(
                    SourceStatus.INVALID
                    if isinstance(exc, InvalidSSTResponseError)
                    else SourceStatus.UNAVAILABLE
                ),
                error=sst_error_code(exc),
            )

        status = {
            SSTCacheStatus.FRESH: SourceStatus.CACHED,
            SSTCacheStatus.REFRESHED: SourceStatus.FRESH,
            SSTCacheStatus.STALE: SourceStatus.STALE,
        }[response.cache_status]
        return SourceResult(
            source="Copernicus Marine",
            status=status,
            data=response.model_dump(mode="json"),
            fetched_at=response.retrieved_at,
            cached=response.cache_status != SSTCacheStatus.REFRESHED,
        )
