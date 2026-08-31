import asyncio
import math
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import httpx

from app.clients.base import MarineSource
from app.clients.ecmwf_wind import (
    ECMWF_WIND_MODEL,
    ECMWF_WIND_RESOLUTION,
    ECMWF_WIND_RESOLUTION_DEGREES,
    ECMWF_WIND_U_PARAMETER,
    ECMWF_WIND_V_PARAMETER,
    ECMWFCycleAvailability,
    ECMWFWindCorruptDownloadError,
    ECMWFWindCycleUnavailableError,
    ECMWFWindDataNotFoundError,
    ECMWFWindDependencyMissingError,
    ECMWFWindDownloadTooLargeError,
    ECMWFWindError,
    ECMWFWindField,
    ECMWFWindForecastOutOfRangeError,
    ECMWFWindNotConfiguredError,
    ECMWFWindProvider,
    ECMWFWindSourceUnavailableError,
    ECMWFWindStepUnavailableError,
    InvalidECMWFWindResponseError,
)
from app.schemas.marine import (
    ECMWFWindCacheStatus,
    ECMWFWindForecastResponse,
    ECMWFWindFreshness,
    ECMWFWindQuality,
    ECMWFWindSourceMetadata,
    SSTLocation,
    SourceResult,
    SourceStatus,
)
from app.services.cache import JsonCache
from app.services.geospatial import compass_direction, haversine_distance_km
from app.services.sst import EXACT_GRID_CELL_TOLERANCE_KM
from app.services.wind import wind_direction_from_deg, wind_speed_mps


ECMWF_ATTRIBUTION = (
    "This service is based on data and products of the European Centre for "
    "Medium-Range Weather Forecasts (ECMWF)."
)
ECMWF_COPYRIGHT = (
    "This service is based on data and products of the European Centre for "
    "Medium-Range Weather Forecasts (ECMWF)."
)
ECMWF_DISCLAIMER = (
    "ECMWF does not accept any liability whatsoever for any error or omission "
    "in the data, their availability, or for any loss or damage arising from "
    "their use."
)
ECMWF_MODIFICATION_NOTICE = (
    "ORCA derived point sampling, distance, wind speed, meteorological "
    "direction-from, and compass direction from ECMWF 10u/10v fields."
)
ECMWF_WIND_ADAPTER_VERSION = "1"


class ECMWFWindPastRequestError(ECMWFWindError):
    pass


@dataclass(frozen=True, slots=True)
class ForecastSelection:
    forecast_reference_time: datetime
    forecast_step_hours: int
    valid_time: datetime


def forecast_steps(cycle_hour: int) -> tuple[int, ...]:
    if cycle_hour not in {0, 6, 12, 18}:
        raise ECMWFWindCycleUnavailableError("Unsupported ECMWF cycle hour")
    short = tuple(range(0, 145, 3))
    if cycle_hour in {0, 12}:
        return short + tuple(range(150, 361, 6))
    return short


def normalize_longitude(longitude: float) -> float:
    normalized = (longitude + 180.0) % 360.0 - 180.0
    return -180.0 if normalized == 180.0 else normalized


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("ECMWF wind forecast time must be timezone-aware")
    return value.astimezone(UTC)


def select_forecast(
    at: datetime,
    availability: ECMWFCycleAvailability,
    *,
    max_horizon_hours: int = 360,
) -> ForecastSelection:
    query_time = _utc(at)
    latest_short = _utc(availability.latest_short_cycle)
    latest_long = (
        _utc(availability.latest_long_cycle)
        if availability.latest_long_cycle is not None
        else None
    )
    cycles = [latest_short - timedelta(hours=6 * offset) for offset in range(12)]
    if latest_long is not None and latest_long not in cycles:
        cycles.append(latest_long)

    candidates: list[tuple[datetime, float, datetime, int]] = []
    for cycle in cycles:
        if cycle > latest_short or cycle.hour not in {0, 6, 12, 18}:
            continue
        if cycle.hour in {0, 12} and latest_long is not None and cycle > latest_long:
            continue
        for step in forecast_steps(cycle.hour):
            if step > max_horizon_hours:
                continue
            if step > 144 and latest_long is None:
                continue
            valid_time = cycle + timedelta(hours=step)
            if valid_time < query_time:
                continue
            tolerance = 3 if step <= 144 else 6
            delta_hours = (valid_time - query_time).total_seconds() / 3600
            if delta_hours <= tolerance:
                candidates.append((valid_time, -cycle.timestamp(), cycle, step))
            break

    if not candidates:
        horizons = [latest_short + timedelta(hours=144)]
        if latest_long is not None:
            horizons.append(
                latest_long + timedelta(hours=min(360, max_horizon_hours))
            )
        if query_time > max(horizons):
            raise ECMWFWindForecastOutOfRangeError(
                "Requested time exceeds the available IFS horizon"
            )
        raise ECMWFWindStepUnavailableError(
            "No ECMWF forecast step satisfies the requested time"
        )

    valid_time, _, cycle, step = min(candidates)
    if valid_time != cycle + timedelta(hours=step):
        raise InvalidECMWFWindResponseError(
            "Forecast reference, lead, and valid time were inconsistent"
        )
    return ForecastSelection(cycle, step, valid_time)


class BoundedWindFieldCache:
    """Process-local TTL/LRU cache for immutable decoded global fields."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_entries: int,
        max_bytes: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._clock = clock
        self._values: OrderedDict[str, tuple[ECMWFWindField, float]] = OrderedDict()
        self._bytes = 0

    def _valid(self, field: ECMWFWindField) -> bool:
        expected = field.ni * field.nj * 8
        return (
            field.approximate_bytes <= self.max_bytes
            and len(field.u_values) == expected
            and len(field.v_values) == expected
        )

    def get(self, key: str) -> ECMWFWindField | None:
        cached = self._values.get(key)
        if cached is None:
            return None
        field, expires_at = cached
        if self._clock() >= expires_at or not self._valid(field):
            self.delete(key)
            return None
        self._values.move_to_end(key)
        return field

    def set(self, key: str, field: ECMWFWindField) -> bool:
        if not self._valid(field):
            return False
        self.delete(key)
        self._values[key] = (field, self._clock() + self.ttl_seconds)
        self._bytes += field.approximate_bytes
        while len(self._values) > self.max_entries or self._bytes > self.max_bytes:
            _, (evicted, _) = self._values.popitem(last=False)
            self._bytes -= evicted.approximate_bytes
        return key in self._values

    def delete(self, key: str) -> None:
        cached = self._values.pop(key, None)
        if cached is not None:
            self._bytes -= cached[0].approximate_bytes


class ECMWFWindForecastService:
    def __init__(
        self,
        *,
        provider: ECMWFWindProvider,
        point_cache: JsonCache,
        field_cache: BoundedWindFieldCache,
        primary_source: str,
        fallback_source: str | None,
        cycle_cache_ttl_seconds: int,
        cycle_stale_ttl_seconds: int,
        point_cache_ttl_seconds: int,
        point_stale_ttl_seconds: int,
        max_stale_cycle_age_hours: float,
        calm_threshold_mps: float = 0.001,
        max_horizon_hours: int = 360,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.provider = provider
        self.point_cache = point_cache
        self.field_cache = field_cache
        self.primary_source = primary_source
        self.fallback_source = fallback_source
        self.cycle_cache_ttl_seconds = cycle_cache_ttl_seconds
        self.cycle_stale_ttl_seconds = cycle_stale_ttl_seconds
        self.point_cache_ttl_seconds = point_cache_ttl_seconds
        self.point_stale_ttl_seconds = point_stale_ttl_seconds
        self.max_stale_cycle_age = timedelta(hours=max_stale_cycle_age_hours)
        self.calm_threshold_mps = calm_threshold_mps
        self.max_horizon_hours = max_horizon_hours
        self._now = now or (lambda: datetime.now(UTC))
        self._monotonic = monotonic
        self._cycle_cache: tuple[ECMWFCycleAvailability, float, float] | None = None
        self._cycle_lock = asyncio.Lock()
        self._field_locks: dict[str, asyncio.Lock] = {}
        self._point_locks: dict[str, asyncio.Lock] = {}

    def _field_key(self, selection: ForecastSelection) -> str:
        return (
            f"v{ECMWF_WIND_ADAPTER_VERSION}:{ECMWF_WIND_MODEL}:"
            f"{ECMWF_WIND_RESOLUTION}:"
            f"{selection.forecast_reference_time.isoformat()}:"
            f"{selection.forecast_step_hours}:"
            f"{ECMWF_WIND_U_PARAMETER},{ECMWF_WIND_V_PARAMETER}"
        )

    def _point_base(
        self,
        selection: ForecastSelection,
        latitude: float,
        longitude: float,
    ) -> str:
        return (
            f"ecmwf-wind:v{ECMWF_WIND_ADAPTER_VERSION}:{ECMWF_WIND_MODEL}:"
            f"{selection.forecast_reference_time.isoformat()}:"
            f"{selection.forecast_step_hours}:{selection.valid_time.isoformat()}:"
            f"h{self.max_horizon_hours}:calm{self.calm_threshold_mps:.6f}:"
            f"{latitude:.6f}:{normalize_longitude(longitude):.6f}"
        )

    async def _discover(self) -> tuple[ECMWFCycleAvailability, bool]:
        current = self._monotonic()
        if self._cycle_cache is not None and current < self._cycle_cache[1]:
            return self._cycle_cache[0], False
        async with self._cycle_lock:
            current = self._monotonic()
            if self._cycle_cache is not None and current < self._cycle_cache[1]:
                return self._cycle_cache[0], False
            failure: Exception | None = None
            for source in (self.primary_source, self.fallback_source):
                if not source:
                    continue
                try:
                    availability = await self.provider.discover_cycles(source)
                    self._cycle_cache = (
                        availability,
                        current + self.cycle_cache_ttl_seconds,
                        current + self.cycle_stale_ttl_seconds,
                    )
                    return availability, False
                except ECMWFWindSourceUnavailableError as exc:
                    failure = exc
            if self._cycle_cache is not None and current < self._cycle_cache[2]:
                return self._cycle_cache[0], True
            raise ECMWFWindCycleUnavailableError(
                "No ECMWF forecast cycle could be discovered"
            ) from failure

    async def _retrieve(self, selection: ForecastSelection) -> ECMWFWindField:
        key = self._field_key(selection)
        cached = self.field_cache.get(key)
        if cached is not None:
            return cached
        lock = self._field_locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self.field_cache.get(key)
            if cached is not None:
                return cached
            last_error: Exception | None = None
            for source in (self.primary_source, self.fallback_source):
                if not source:
                    continue
                try:
                    field = await self.provider.retrieve_field(
                        source,
                        selection.forecast_reference_time,
                        selection.forecast_step_hours,
                    )
                    if not self.field_cache.set(key, field):
                        raise InvalidECMWFWindResponseError(
                            "Decoded ECMWF field exceeded cache bounds"
                        )
                    return field
                except ECMWFWindSourceUnavailableError as exc:
                    last_error = exc
                except ECMWFWindCorruptDownloadError as exc:
                    raise InvalidECMWFWindResponseError(
                        "ECMWF returned invalid wind data"
                    ) from exc
            raise ECMWFWindSourceUnavailableError(
                "All configured ECMWF wind sources are unavailable"
            ) from last_error

    def _sample(
        self,
        field: ECMWFWindField,
        latitude: float,
        longitude: float,
    ) -> tuple[float, float, float, float, float]:
        u_values = memoryview(field.u_values).cast("d")
        v_values = memoryview(field.v_values).cast("d")
        best: tuple[float, float, float, float, float] | None = None
        latitude_sign = 1.0 if field.latitude_scans_positive else -1.0
        longitude_sign = -1.0 if field.longitude_scans_negative else 1.0
        for row in range(field.nj):
            cell_latitude = field.latitude_first + (
                latitude_sign * row * field.latitude_increment
            )
            for column in range(field.ni):
                index = row * field.ni + column
                u = float(u_values[index])
                v = float(v_values[index])
                if not math.isfinite(u) or not math.isfinite(v):
                    continue
                cell_longitude = normalize_longitude(
                    field.longitude_first
                    + longitude_sign * column * field.longitude_increment
                )
                distance = haversine_distance_km(
                    latitude,
                    normalize_longitude(longitude),
                    cell_latitude,
                    cell_longitude,
                )
                candidate = (distance, cell_latitude, cell_longitude, u, v)
                if best is None or candidate[:3] < best[:3]:
                    best = candidate
        if best is None:
            raise ECMWFWindDataNotFoundError(
                "ECMWF wind field contained no valid component pair"
            )
        return best

    def _normalize(
        self,
        *,
        field: ECMWFWindField,
        selection: ForecastSelection,
        latitude: float,
        longitude: float,
        requested_time: datetime,
        warnings: list[str],
    ) -> ECMWFWindForecastResponse:
        distance, sampled_lat, sampled_lon, u, v = self._sample(
            field, latitude, longitude
        )
        speed = wind_speed_mps(u, v)
        direction = (
            None
            if speed <= self.calm_threshold_mps
            else wind_direction_from_deg(u, v)
        )
        return ECMWFWindForecastResponse(
            selected_mirror=field.source_mirror,
            requested_latitude=latitude,
            requested_longitude=normalize_longitude(longitude),
            sampled_latitude=sampled_lat,
            sampled_longitude=sampled_lon,
            requested_location=SSTLocation(
                latitude=latitude,
                longitude=normalize_longitude(longitude),
            ),
            sampled_location=SSTLocation(
                latitude=sampled_lat,
                longitude=sampled_lon,
            ),
            distance_km=round(distance, 3),
            eastward_wind_mps=round(u, 6),
            northward_wind_mps=round(v, 6),
            speed_mps=round(speed, 6),
            wind_speed_mps=round(speed, 6),
            direction_from_degrees=(
                round(direction, 6) if direction is not None else None
            ),
            wind_direction_from_deg=(
                round(direction, 6) if direction is not None else None
            ),
            compass_direction_from=(
                compass_direction(direction) if direction is not None else None
            ),
            forecast_reference_time=selection.forecast_reference_time,
            forecast_step=selection.forecast_step_hours,
            forecast_lead_hours=selection.forecast_step_hours,
            valid_time=selection.valid_time,
            requested_at=requested_time,
            requested_time=requested_time,
            retrieved_at=field.retrieved_at,
            source=ECMWFWindSourceMetadata(
                source_mirror=field.source_mirror,
                copyright_statement=ECMWF_COPYRIGHT,
                attribution=ECMWF_ATTRIBUTION,
                disclaimer=ECMWF_DISCLAIMER,
                modification_notice=ECMWF_MODIFICATION_NOTICE,
            ),
            quality=(
                ECMWFWindQuality.EXACT_GRID_CELL
                if distance <= EXACT_GRID_CELL_TOLERANCE_KM
                else ECMWFWindQuality.NEAREST_VALID_GRID_CELL
            ),
            freshness=ECMWFWindFreshness.CURRENT_CYCLE,
            cache_status=ECMWFWindCacheStatus.REFRESHED,
            warnings=warnings,
        )

    async def _cached_point(
        self,
        key: str,
        *,
        cache_status: ECMWFWindCacheStatus,
        warning: str | None = None,
    ) -> ECMWFWindForecastResponse | None:
        raw = await self.point_cache.get(key)
        if raw is None:
            return None
        try:
            response = ECMWFWindForecastResponse.model_validate(raw)
        except Exception:
            return None
        warnings = list(response.warnings)
        if warning and warning not in warnings:
            warnings.append(warning)
        return response.model_copy(
            update={
                "cache_status": cache_status,
                "freshness": (
                    ECMWFWindFreshness.STALE_CYCLE
                    if cache_status == ECMWFWindCacheStatus.STALE
                    else response.freshness
                ),
                "warnings": warnings,
            }
        )

    async def get_forecast(
        self,
        *,
        latitude: float,
        longitude: float,
        at: datetime,
    ) -> ECMWFWindForecastResponse:
        query_time = _utc(at)
        now = _utc(self._now())
        if query_time <= now:
            raise ECMWFWindPastRequestError(
                "The ECMWF endpoint accepts future forecast times only"
            )
        availability, discovery_stale = await self._discover()
        selection = select_forecast(
            query_time,
            availability,
            max_horizon_hours=self.max_horizon_hours,
        )
        base = self._point_base(selection, latitude, longitude)
        fresh_key = f"{base}:fresh"
        stale_key = f"{base}:last-success"
        cached = await self._cached_point(
            fresh_key, cache_status=ECMWFWindCacheStatus.FRESH
        )
        if cached is not None:
            return cached
        lock = self._point_locks.setdefault(base, asyncio.Lock())
        async with lock:
            cached = await self._cached_point(
                fresh_key, cache_status=ECMWFWindCacheStatus.FRESH
            )
            if cached is not None:
                return cached
            warnings: list[str] = []
            if discovery_stale:
                warnings.append(
                    "ECMWF cycle discovery failed; using recent cached cycle metadata"
                )
            try:
                field = await self._retrieve(selection)
                response = await asyncio.to_thread(
                    self._normalize,
                    field=field,
                    selection=selection,
                    latitude=latitude,
                    longitude=longitude,
                    requested_time=query_time,
                    warnings=warnings,
                )
            except ECMWFWindSourceUnavailableError:
                stale = await self._cached_point(
                    stale_key,
                    cache_status=ECMWFWindCacheStatus.STALE,
                    warning=(
                        "ECMWF refresh failed; returning the matching forecast "
                        "from a previously retrieved cycle"
                    ),
                )
                if stale is not None:
                    cycle_age = now - stale.forecast_reference_time
                    if cycle_age <= self.max_stale_cycle_age:
                        return stale
                raise
            serialized = response.model_dump(mode="json")
            await self.point_cache.set(
                fresh_key, serialized, self.point_cache_ttl_seconds
            )
            await self.point_cache.set(
                stale_key, serialized, self.point_stale_ttl_seconds
            )
            return response


def ecmwf_wind_error_code(exc: Exception) -> str:
    if isinstance(exc, ECMWFWindNotConfiguredError):
        return "ECMWF_FORECAST_NOT_CONFIGURED"
    if isinstance(exc, ECMWFWindDependencyMissingError):
        return "ECMWF_DEPENDENCY_MISSING"
    if isinstance(exc, ECMWFWindCycleUnavailableError):
        return "ECMWF_SOURCE_UNAVAILABLE"
    if isinstance(exc, ECMWFWindForecastOutOfRangeError):
        return "FORECAST_OUT_OF_HORIZON"
    if isinstance(exc, ECMWFWindStepUnavailableError):
        return "FORECAST_STEP_UNAVAILABLE"
    if isinstance(exc, ECMWFWindDownloadTooLargeError):
        return "ECMWF_WIND_DOWNLOAD_TOO_LARGE"
    if isinstance(exc, InvalidECMWFWindResponseError):
        return "INVALID_ECMWF_RESPONSE"
    if isinstance(exc, ECMWFWindDataNotFoundError):
        return "NO_VALID_WIND_CELL"
    if isinstance(exc, ECMWFWindPastRequestError):
        return "INVALID_FORECAST_TIME"
    return "ECMWF_SOURCE_UNAVAILABLE"


class ECMWFWindMarineSource:
    name = "wind"

    def __init__(self, service: ECMWFWindForecastService) -> None:
        self.service = service

    async def fetch(
        self,
        client: httpx.AsyncClient,
        latitude: float,
        longitude: float,
        at: datetime | None = None,
    ) -> SourceResult:
        del client
        if at is None:
            return SourceResult(
                source="ECMWF",
                status=SourceStatus.UNAVAILABLE,
                error="ECMWF_WIND_FORECAST_TIME_REQUIRED",
            )
        try:
            response = await self.service.get_forecast(
                latitude=latitude, longitude=longitude, at=at
            )
        except ECMWFWindError as exc:
            return SourceResult(
                source="ECMWF",
                status=(
                    SourceStatus.INVALID
                    if isinstance(exc, InvalidECMWFWindResponseError)
                    else SourceStatus.UNAVAILABLE
                ),
                error=ecmwf_wind_error_code(exc),
            )
        status = {
            ECMWFWindCacheStatus.FRESH: SourceStatus.CACHED,
            ECMWFWindCacheStatus.REFRESHED: SourceStatus.FRESH,
            ECMWFWindCacheStatus.STALE: SourceStatus.STALE,
        }[response.cache_status]
        return SourceResult(
            source="ECMWF",
            status=status,
            data=response.model_dump(mode="json"),
            fetched_at=response.retrieved_at,
            cached=response.cache_status != ECMWFWindCacheStatus.REFRESHED,
        )


class TimeSelectingWindMarineSource:
    """Use ECMWF only for future requests; preserve the analysis source otherwise."""

    name = "wind"

    def __init__(
        self,
        analysis_source: MarineSource,
        forecast_source: ECMWFWindMarineSource,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.analysis_source = analysis_source
        self.forecast_source = forecast_source
        self._now = now or (lambda: datetime.now(UTC))

    async def fetch(
        self,
        client: httpx.AsyncClient,
        latitude: float,
        longitude: float,
        at: datetime | None = None,
    ) -> SourceResult:
        if at is not None and _utc(at) > _utc(self._now()):
            return await self.forecast_source.fetch(client, latitude, longitude, at)
        return await self.analysis_source.fetch(client, latitude, longitude, at)
