import asyncio
import math
from datetime import UTC, datetime, timedelta

import httpx

from app.clients.copernicus_wind import (
    COPERNICUS_WIND_DATASET_VERSION,
    COPERNICUS_WIND_PRODUCT_ID,
    InvalidWindResponseError,
    WindAuthenticationError,
    WindProvider,
    WindProviderCell,
    WindProviderError,
    WindSourceNotConfiguredError,
    WindSourceUnavailableError,
)
from app.schemas.marine import (
    SSTLocation,
    SourceResult,
    SourceStatus,
    WindCacheStatus,
    WindDirectionFrom,
    WindQuality,
    WindResponse,
    WindSourceMetadata,
    WindValue,
)
from app.services.cache import JsonCache
from app.services.geospatial import compass_direction, haversine_distance_km
from app.services.sst import EXACT_GRID_CELL_TOLERANCE_KM


COASTAL_CONTEXT_WARNING = (
    "Wind components may include uncorrected model values over land or coastal cells."
)
DECODED_COMPONENT_LIMIT_MPS = 50.0
FUTURE_CLOCK_SKEW = timedelta(minutes=5)


class NoValidWindDataError(WindProviderError):
    pass


class NoWindForecastAvailableError(WindProviderError):
    pass


class WindDataTooOldError(WindProviderError):
    pass


def wind_error_code(exc: Exception) -> str:
    if isinstance(exc, NoValidWindDataError):
        return "NO_VALID_WIND_DATA"
    if isinstance(exc, NoWindForecastAvailableError):
        return "NO_WIND_FORECAST_AVAILABLE"
    if isinstance(exc, WindDataTooOldError):
        return "WIND_DATA_TOO_OLD"
    if isinstance(exc, InvalidWindResponseError):
        return "INVALID_WIND_RESPONSE"
    if isinstance(exc, WindAuthenticationError):
        return "WIND_AUTHENTICATION_FAILED"
    if isinstance(exc, WindSourceNotConfiguredError):
        return "WIND_SOURCE_NOT_CONFIGURED"
    return "WIND_SOURCE_UNAVAILABLE"


def wind_speed_mps(eastward_mps: float, northward_mps: float) -> float:
    return math.hypot(eastward_mps, northward_mps)


def wind_direction_from_deg(
    eastward_mps: float,
    northward_mps: float,
) -> float | None:
    """Return meteorological direction-from; calm wind has no direction."""
    if eastward_mps == 0.0 and northward_mps == 0.0:
        return None
    return (270.0 - math.degrees(math.atan2(northward_mps, eastward_mps))) % 360.0


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("wind query time must be timezone-aware")
    return value.astimezone(UTC)


class CopernicusWindService:
    def __init__(
        self,
        *,
        provider: WindProvider,
        cache: JsonCache,
        dataset_id: str,
        dataset_version: str,
        eastward_variable: str,
        northward_variable: str,
        search_radius_km: float,
        max_age_hours: float,
        fresh_ttl_seconds: int,
        stale_ttl_seconds: int,
        now=None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.dataset_id = dataset_id
        self.dataset_version = dataset_version
        self.eastward_variable = eastward_variable
        self.northward_variable = northward_variable
        self.search_radius_km = search_radius_km
        self.max_age = timedelta(hours=max_age_hours)
        self.fresh_ttl_seconds = fresh_ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._locks: dict[str, asyncio.Lock] = {}

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

    def _cache_base(
        self,
        latitude: float,
        longitude: float,
        query_time: datetime,
    ) -> str:
        bucket = query_time.replace(minute=0, second=0, microsecond=0).isoformat()
        return (
            f"wind:{self.dataset_id}:{self.eastward_variable}:"
            f"{self.northward_variable}:{latitude:.6f}:{longitude:.6f}:{bucket}"
        )

    def _age(self, query_time: datetime, valid_time: datetime) -> timedelta:
        return query_time - _utc(valid_time)

    async def _cached(
        self,
        key: str,
        status: WindCacheStatus,
        query_time: datetime,
        warning: str | None = None,
    ) -> WindResponse | None:
        value = await self.cache.get(key)
        if value is None:
            return None
        try:
            response = WindResponse.model_validate(value)
        except Exception:
            return None
        age = self._age(query_time, response.valid_time)
        if age < timedelta(0):
            return None
        if age > self.max_age:
            if status == WindCacheStatus.STALE:
                raise WindDataTooOldError(
                    "Matching stale wind data exceeds the configured maximum age"
                )
            return None
        warnings = [*response.warnings]
        if warning is not None and warning not in warnings:
            warnings.append(warning)
        return response.model_copy(
            update={
                "requested_time": query_time,
                "data_age_hours": round(age.total_seconds() / 3600, 3),
                "cache_status": status,
                "warnings": warnings,
            }
        )

    def _select_time(
        self,
        cells: list[WindProviderCell],
        query_time: datetime,
    ) -> datetime:
        valid_times: set[datetime] = set()
        for cell in cells:
            try:
                valid_time = _utc(cell.valid_time)
            except ValueError as exc:
                raise InvalidWindResponseError(
                    "Copernicus wind data contained a timezone-naive timestamp"
                ) from exc
            if valid_time <= query_time:
                valid_times.add(valid_time)
        selected = max(valid_times, default=None)
        if selected is None:
            raise NoValidWindDataError(
                "No wind timestamp exists at or before the requested time"
            )
        if query_time - selected > self.max_age:
            raise WindDataTooOldError(
                "Latest wind data exceeds the configured maximum age"
            )
        return selected

    def _normalize(
        self,
        *,
        cells: list[WindProviderCell],
        provider_warnings: tuple[str, ...],
        latitude: float,
        longitude: float,
        query_time: datetime,
        retrieved_at: datetime,
    ) -> WindResponse:
        selected_time = self._select_time(cells, query_time)
        candidates: list[tuple[float, float, float, WindProviderCell]] = []
        for cell in cells:
            if _utc(cell.valid_time) != selected_time:
                continue
            u = cell.eastward_wind_mps
            v = cell.northward_wind_mps
            if (
                u is None
                or v is None
                or not math.isfinite(u)
                or not math.isfinite(v)
                or not -DECODED_COMPONENT_LIMIT_MPS <= u <= DECODED_COMPONENT_LIMIT_MPS
                or not -DECODED_COMPONENT_LIMIT_MPS <= v <= DECODED_COMPONENT_LIMIT_MPS
            ):
                continue
            distance = haversine_distance_km(
                latitude,
                longitude,
                cell.latitude,
                cell.longitude,
            )
            if distance <= self.search_radius_km:
                candidates.append((distance, cell.latitude, cell.longitude, cell))
        if not candidates:
            raise NoValidWindDataError(
                "No valid wind component pair exists within the configured radius"
            )

        raw_distance, _, _, selected = min(
            candidates,
            key=lambda item: (item[0], item[1], item[2]),
        )
        quality = (
            WindQuality.EXACT_GRID_CELL
            if raw_distance <= EXACT_GRID_CELL_TOLERANCE_KM
            else WindQuality.NEAREST_VALID_GRID_CELL
        )
        warnings = list(dict.fromkeys((*provider_warnings, COASTAL_CONTEXT_WARNING)))
        if quality == WindQuality.NEAREST_VALID_GRID_CELL:
            warnings.append(
                "Nearest valid wind grid cell within the configured radius was used"
            )

        u = selected.eastward_wind_mps
        v = selected.northward_wind_mps
        assert u is not None and v is not None
        raw_speed = wind_speed_mps(u, v)
        raw_direction = wind_direction_from_deg(u, v)
        age_hours = (query_time - selected_time).total_seconds() / 3600
        return WindResponse(
            requested_location=SSTLocation(latitude=latitude, longitude=longitude),
            sampled_location=SSTLocation(
                latitude=selected.latitude,
                longitude=selected.longitude,
            ),
            sample_distance_km=round(raw_distance, 3),
            requested_time=query_time,
            valid_time=selected_time,
            data_age_hours=round(age_hours, 3),
            eastward_wind=WindValue(value=round(u, 6)),
            northward_wind=WindValue(value=round(v, 6)),
            wind_speed=WindValue(value=round(raw_speed, 6)),
            wind_direction_from=WindDirectionFrom(
                value=round(raw_direction, 6) if raw_direction is not None else None,
                compass=(
                    compass_direction(raw_direction)
                    if raw_direction is not None
                    else None
                ),
            ),
            retrieved_at=retrieved_at,
            source=WindSourceMetadata(
                product_id=COPERNICUS_WIND_PRODUCT_ID,
                dataset_id=self.dataset_id,
                dataset_version=self.dataset_version,
            ),
            quality=quality,
            cache_status=WindCacheStatus.REFRESHED,
            warnings=warnings,
        )

    async def get_wind(
        self,
        *,
        latitude: float,
        longitude: float,
        at: datetime | None = None,
    ) -> WindResponse:
        current_time = _utc(self._now())
        query_time = _utc(at) if at is not None else current_time
        if query_time > current_time + FUTURE_CLOCK_SKEW:
            raise NoWindForecastAvailableError(
                "The near-real-time wind product does not contain forecasts"
            )

        cache_base = self._cache_base(latitude, longitude, query_time)
        fresh_key = f"{cache_base}:fresh"
        last_success_key = f"{cache_base}:last_success"
        cached = await self._cached(fresh_key, WindCacheStatus.FRESH, query_time)
        if cached is not None:
            return cached

        lock = self._locks.setdefault(cache_base, asyncio.Lock())
        async with lock:
            cached = await self._cached(fresh_key, WindCacheStatus.FRESH, query_time)
            if cached is not None:
                return cached

            bounds = self._bounds(latitude, longitude)
            try:
                result = await self.provider.fetch_cells(
                    dataset_id=self.dataset_id,
                    dataset_version=self.dataset_version,
                    eastward_variable=self.eastward_variable,
                    northward_variable=self.northward_variable,
                    minimum_latitude=bounds[0],
                    maximum_latitude=bounds[1],
                    minimum_longitude=bounds[2],
                    maximum_longitude=bounds[3],
                    start_datetime=query_time - self.max_age - timedelta(hours=24),
                    end_datetime=query_time,
                )
                response = self._normalize(
                    cells=result.cells,
                    provider_warnings=result.warnings,
                    latitude=latitude,
                    longitude=longitude,
                    query_time=query_time,
                    retrieved_at=_utc(self._now()),
                )
            except (
                NoValidWindDataError,
                WindDataTooOldError,
                InvalidWindResponseError,
            ):
                raise
            except WindProviderError:
                stale = await self._cached(
                    last_success_key,
                    WindCacheStatus.STALE,
                    query_time,
                    "Copernicus wind refresh failed; returning matching stale data",
                )
                if stale is not None:
                    return stale
                raise

            serialized = response.model_dump(mode="json")
            await self.cache.set(fresh_key, serialized, self.fresh_ttl_seconds)
            await self.cache.set(last_success_key, serialized, self.stale_ttl_seconds)
            return response


class CopernicusWindMarineSource:
    name = "wind"

    def __init__(self, service: CopernicusWindService) -> None:
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
            response = await self.service.get_wind(
                latitude=latitude,
                longitude=longitude,
                at=at,
            )
        except WindProviderError as exc:
            return SourceResult(
                source="Copernicus Marine",
                status=(
                    SourceStatus.INVALID
                    if isinstance(exc, InvalidWindResponseError)
                    else SourceStatus.UNAVAILABLE
                ),
                error=wind_error_code(exc),
            )

        status = {
            WindCacheStatus.FRESH: SourceStatus.CACHED,
            WindCacheStatus.REFRESHED: SourceStatus.FRESH,
            WindCacheStatus.STALE: SourceStatus.STALE,
        }[response.cache_status]
        return SourceResult(
            source="Copernicus Marine",
            status=status,
            data=response.model_dump(mode="json"),
            fetched_at=response.retrieved_at,
            cached=response.cache_status != WindCacheStatus.REFRESHED,
        )
