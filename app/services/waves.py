import asyncio
import math
from datetime import UTC, datetime, timedelta

import httpx

from app.clients.copernicus_waves import (
    COPERNICUS_WAVE_PRODUCT_ID,
    InvalidWaveResponseError,
    WaveAuthenticationError,
    WaveCycleResolver,
    WaveProvider,
    WaveProviderCell,
    WaveProviderError,
    WaveSourceNotConfiguredError,
    WaveSourceUnavailableError,
)
from app.schemas.marine import (
    SSTLocation,
    SourceResult,
    SourceStatus,
    WaveCacheStatus,
    WaveQuality,
    WaveResponse,
    WaveSourceMetadata,
    WaveTimeClassification,
    WaveValue,
)
from app.services.cache import JsonCache
from app.services.geospatial import haversine_distance_km
from app.services.sst import EXACT_GRID_CELL_TOLERANCE_KM


class NoValidWaveDataError(WaveProviderError):
    pass


class NoWaveTimeAvailableError(WaveProviderError):
    pass


def wave_error_code(exc: Exception) -> str:
    if isinstance(exc, NoValidWaveDataError):
        return "NO_VALID_WAVE_DATA"
    if isinstance(exc, NoWaveTimeAvailableError):
        return "NO_WAVE_TIME_AVAILABLE"
    if isinstance(exc, InvalidWaveResponseError):
        return "INVALID_WAVE_RESPONSE"
    if isinstance(exc, WaveAuthenticationError):
        return "WAVE_AUTHENTICATION_FAILED"
    if isinstance(exc, WaveSourceNotConfiguredError):
        return "WAVE_SOURCE_NOT_CONFIGURED"
    return "WAVE_SOURCE_UNAVAILABLE"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("wave query time must be timezone-aware")
    return value.astimezone(UTC)


class CopernicusWaveService:
    def __init__(
        self,
        *,
        provider: WaveProvider,
        cycle_resolver: WaveCycleResolver,
        cache: JsonCache,
        dataset_id: str,
        dataset_version: str,
        height_variable: str,
        period_variable: str,
        direction_variable: str,
        search_radius_km: float,
        time_tolerance_hours: int,
        fresh_ttl_seconds: int,
        stale_ttl_seconds: int,
        cycle_ttl_seconds: int,
        now=None,
    ) -> None:
        self.provider = provider
        self.cycle_resolver = cycle_resolver
        self.cache = cache
        self.dataset_id = dataset_id
        self.dataset_version = dataset_version
        self.height_variable = height_variable
        self.period_variable = period_variable
        self.direction_variable = direction_variable
        self.search_radius_km = search_radius_km
        self.time_tolerance = timedelta(hours=time_tolerance_hours)
        self.fresh_ttl_seconds = fresh_ttl_seconds
        self.stale_ttl_seconds = stale_ttl_seconds
        self.cycle_ttl_seconds = cycle_ttl_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._locks: dict[str, asyncio.Lock] = {}
        self._cycle_lock = asyncio.Lock()

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

    def _requested_bucket(self, query_time: datetime) -> datetime:
        bucket_seconds = 3 * 60 * 60
        timestamp = query_time.timestamp()
        bucket = math.ceil(timestamp / bucket_seconds) * bucket_seconds
        return datetime.fromtimestamp(bucket, tz=UTC)

    def _cache_base(
        self,
        latitude: float,
        longitude: float,
        query_time: datetime,
    ) -> str:
        variables = ":".join(
            (
                self.height_variable,
                self.period_variable,
                self.direction_variable,
            )
        )
        bucket = self._requested_bucket(query_time).isoformat()
        return (
            f"waves:{self.dataset_id}:{variables}:"
            f"{latitude:.6f}:{longitude:.6f}:{bucket}"
        )

    async def _cached(
        self,
        key: str,
        status: WaveCacheStatus,
        requested_time: datetime,
        warning: str | None = None,
    ) -> WaveResponse | None:
        value = await self.cache.get(key)
        if value is None:
            return None
        try:
            response = WaveResponse.model_validate(value)
        except Exception:
            return None
        warnings = [*response.warnings]
        if warning is not None and warning not in warnings:
            warnings.append(warning)
        return response.model_copy(
            update={
                "requested_time": requested_time,
                "cache_status": status,
                "warnings": warnings,
            }
        )

    async def _cycle_reference(self) -> tuple[datetime | None, str | None]:
        key = f"waves:cycle:{self.dataset_id}:{self.dataset_version}"
        cached = await self.cache.get(key)
        if isinstance(cached, dict) and "reference_time" in cached:
            value = cached["reference_time"]
            if value is None:
                return None, "Official wave cycle metadata could not be resolved"
            try:
                return _utc(datetime.fromisoformat(value)), None
            except (TypeError, ValueError):
                pass

        async with self._cycle_lock:
            cached = await self.cache.get(key)
            if isinstance(cached, dict) and "reference_time" in cached:
                value = cached["reference_time"]
                if value is None:
                    return None, "Official wave cycle metadata could not be resolved"
                try:
                    return _utc(datetime.fromisoformat(value)), None
                except (TypeError, ValueError):
                    pass

            try:
                reference = await self.cycle_resolver.resolve_cycle(
                    dataset_id=self.dataset_id,
                    dataset_version=self.dataset_version,
                    reference_time=_utc(self._now()),
                )
                if reference is not None:
                    reference = _utc(reference)
            except (WaveProviderError, ValueError):
                reference = None

            await self.cache.set(
                key,
                {
                    "reference_time": (
                        reference.isoformat() if reference is not None else None
                    )
                },
                self.cycle_ttl_seconds,
            )
            if reference is None:
                return None, "Official wave cycle metadata could not be resolved"
            return reference, None

    def _time_window(
        self,
        query_time: datetime,
        cycle_reference: datetime | None,
    ) -> tuple[datetime, datetime]:
        if cycle_reference is None:
            return (
                query_time - self.time_tolerance,
                query_time + self.time_tolerance,
            )
        horizon = cycle_reference + timedelta(days=10)
        if query_time > horizon:
            raise NoWaveTimeAvailableError(
                "Requested time is beyond the official forecast horizon"
            )
        if query_time <= cycle_reference:
            return query_time - self.time_tolerance, query_time
        return query_time, min(query_time + self.time_tolerance, horizon)

    def _select_time(
        self,
        cells: list[WaveProviderCell],
        query_time: datetime,
        cycle_reference: datetime | None,
    ) -> datetime:
        valid_times: set[datetime] = set()
        for cell in cells:
            try:
                valid_times.add(_utc(cell.valid_time))
            except ValueError as exc:
                raise InvalidWaveResponseError(
                    "Copernicus wave data contained a timezone-naive timestamp"
                ) from exc

        if cycle_reference is None:
            candidates = [
                value
                for value in valid_times
                if abs(value - query_time) <= self.time_tolerance
            ]
            if not candidates:
                raise NoWaveTimeAvailableError(
                    "No wave timestamp is close enough to the requested time"
                )
            return min(candidates, key=lambda value: (abs(value - query_time), value))

        horizon = cycle_reference + timedelta(days=10)
        if query_time <= cycle_reference:
            candidates = [
                value
                for value in valid_times
                if value <= query_time
                and query_time - value <= self.time_tolerance
            ]
            selected = max(candidates, default=None)
        else:
            candidates = [
                value
                for value in valid_times
                if query_time <= value <= horizon
                and value - query_time <= self.time_tolerance
            ]
            selected = min(candidates, default=None)
        if selected is None:
            raise NoWaveTimeAvailableError(
                "No wave timestamp satisfies the requested time policy"
            )
        return selected

    def _normalize(
        self,
        *,
        cells: list[WaveProviderCell],
        latitude: float,
        longitude: float,
        query_time: datetime,
        cycle_reference: datetime | None,
        cycle_warning: str | None,
        retrieved_at: datetime,
    ) -> WaveResponse:
        selected_time = self._select_time(cells, query_time, cycle_reference)
        candidates: list[tuple[float, float, float, WaveProviderCell]] = []
        for cell in cells:
            if _utc(cell.valid_time) != selected_time:
                continue
            values = (
                cell.significant_wave_height_m,
                cell.mean_wave_period_s,
                cell.mean_wave_direction_from_deg,
            )
            if any(
                value is None
                or not math.isfinite(value)
                or value == -32767.0
                for value in values
            ):
                continue
            distance = haversine_distance_km(
                latitude,
                longitude,
                cell.latitude,
                cell.longitude,
            )
            if distance <= self.search_radius_km:
                candidates.append(
                    (distance, cell.latitude, cell.longitude, cell)
                )
        if not candidates:
            raise NoValidWaveDataError(
                "No complete wave model cell exists within the configured radius"
            )

        raw_distance, _, _, selected = min(
            candidates,
            key=lambda item: (item[0], item[1], item[2]),
        )
        exact = raw_distance <= EXACT_GRID_CELL_TOLERANCE_KM
        warnings = [cycle_warning] if cycle_warning is not None else []
        if exact:
            quality = WaveQuality.EXACT_GRID_CELL
        else:
            quality = WaveQuality.NEAREST_VALID_OCEAN_CELL
            warnings.append(
                "Nearest complete wave model cell within the configured radius was used"
            )

        if cycle_reference is None:
            classification = WaveTimeClassification.UNKNOWN
            lead_hours = None
        else:
            classification = (
                WaveTimeClassification.ANALYSIS
                if selected_time <= cycle_reference
                else WaveTimeClassification.FORECAST
            )
            lead_hours = (selected_time - cycle_reference).total_seconds() / 3600

        assert selected.significant_wave_height_m is not None
        assert selected.mean_wave_period_s is not None
        assert selected.mean_wave_direction_from_deg is not None
        return WaveResponse(
            requested_location=SSTLocation(
                latitude=latitude,
                longitude=longitude,
            ),
            sampled_location=SSTLocation(
                latitude=selected.latitude,
                longitude=selected.longitude,
            ),
            sample_distance_km=round(raw_distance, 3),
            requested_time=query_time,
            valid_time=selected_time,
            forecast_reference_time=cycle_reference,
            forecast_lead_hours=lead_hours,
            time_classification=classification,
            significant_wave_height=WaveValue(
                value=round(selected.significant_wave_height_m, 3),
                unit="m",
            ),
            mean_wave_period=WaveValue(
                value=round(selected.mean_wave_period_s, 3),
                unit="s",
            ),
            mean_wave_direction_from=WaveValue(
                value=round(selected.mean_wave_direction_from_deg, 3),
                unit="degree",
            ),
            retrieved_at=retrieved_at,
            source=WaveSourceMetadata(
                product_id=COPERNICUS_WAVE_PRODUCT_ID,
                dataset_id=self.dataset_id,
                dataset_version=self.dataset_version,
            ),
            quality=quality,
            cache_status=WaveCacheStatus.REFRESHED,
            warnings=warnings,
        )

    async def get_waves(
        self,
        *,
        latitude: float,
        longitude: float,
        at: datetime | None = None,
    ) -> WaveResponse:
        query_time = _utc(at if at is not None else self._now())
        cycle_reference, cycle_warning = await self._cycle_reference()
        start_datetime, end_datetime = self._time_window(
            query_time,
            cycle_reference,
        )
        cache_base = self._cache_base(latitude, longitude, query_time)
        fresh_key = f"{cache_base}:fresh"
        last_success_key = f"{cache_base}:last_success"

        cached = await self._cached(
            fresh_key,
            WaveCacheStatus.FRESH,
            query_time,
        )
        if cached is not None:
            return cached

        lock = self._locks.setdefault(cache_base, asyncio.Lock())
        async with lock:
            cached = await self._cached(
                fresh_key,
                WaveCacheStatus.FRESH,
                query_time,
            )
            if cached is not None:
                return cached

            minimum_latitude, maximum_latitude, minimum_longitude, maximum_longitude = (
                self._bounds(latitude, longitude)
            )
            try:
                cells = await self.provider.fetch_cells(
                    dataset_id=self.dataset_id,
                    dataset_version=self.dataset_version,
                    height_variable=self.height_variable,
                    period_variable=self.period_variable,
                    direction_variable=self.direction_variable,
                    minimum_latitude=minimum_latitude,
                    maximum_latitude=maximum_latitude,
                    minimum_longitude=minimum_longitude,
                    maximum_longitude=maximum_longitude,
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                )
                response = self._normalize(
                    cells=cells,
                    latitude=latitude,
                    longitude=longitude,
                    query_time=query_time,
                    cycle_reference=cycle_reference,
                    cycle_warning=cycle_warning,
                    retrieved_at=_utc(self._now()),
                )
            except (
                NoValidWaveDataError,
                NoWaveTimeAvailableError,
                InvalidWaveResponseError,
            ):
                raise
            except WaveProviderError:
                stale = await self._cached(
                    last_success_key,
                    WaveCacheStatus.STALE,
                    query_time,
                    "Copernicus wave refresh failed; returning matching stale data",
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


class CopernicusWaveMarineSource:
    name = "waves"

    def __init__(self, service: CopernicusWaveService) -> None:
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
            response = await self.service.get_waves(
                latitude=latitude,
                longitude=longitude,
                at=at,
            )
        except WaveProviderError as exc:
            return SourceResult(
                source="Copernicus Marine",
                status=(
                    SourceStatus.INVALID
                    if isinstance(exc, InvalidWaveResponseError)
                    else SourceStatus.UNAVAILABLE
                ),
                error=wave_error_code(exc),
            )

        status = {
            WaveCacheStatus.FRESH: SourceStatus.CACHED,
            WaveCacheStatus.REFRESHED: SourceStatus.FRESH,
            WaveCacheStatus.STALE: SourceStatus.STALE,
        }[response.cache_status]
        return SourceResult(
            source="Copernicus Marine",
            status=status,
            data=response.model_dump(mode="json"),
            fetched_at=response.retrieved_at,
            cached=response.cache_status != WaveCacheStatus.REFRESHED,
        )
