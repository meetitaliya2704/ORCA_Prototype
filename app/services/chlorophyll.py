import asyncio
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.clients.copernicus_chlorophyll import (
    COPERNICUS_CHLOROPHYLL_PRODUCT_ID,
    ChlorophyllAuthenticationError,
    ChlorophyllDependencyMissingError,
    ChlorophyllFlagMetadata,
    ChlorophyllProvider,
    ChlorophyllProviderCell,
    ChlorophyllProviderError,
    ChlorophyllProviderResult,
    ChlorophyllSourceNotConfiguredError,
    ChlorophyllSourceUnavailableError,
    InvalidChlorophyllResponseError,
)
from app.schemas.marine import (
    ChlorophyllCacheStatus,
    ChlorophyllDataProvenance,
    ChlorophyllEvidenceQuality,
    ChlorophyllQualityMetadata,
    ChlorophyllResponse,
    ChlorophyllSamplingQuality,
    ChlorophyllValue,
    SSTLocation,
    SourceResult,
    SourceStatus,
)
from app.services.cache import JsonCache
from app.services.geospatial import haversine_distance_km


CHLOROPHYLL_ADAPTER_SCHEMA_VERSION = "1"
EXACT_GRID_CELL_TOLERANCE_KM = 0.001
FUTURE_CLOCK_SKEW = timedelta(minutes=5)

INTERPOLATION_WARNING = (
    "The selected chlorophyll value was produced using space-time interpolation."
)
HIGH_UNCERTAINTY_WARNING = (
    "The provider reports high chlorophyll uncertainty."
)
MISSING_UNCERTAINTY_WARNING = (
    "Chlorophyll uncertainty was unavailable for the selected cell."
)


class ChlorophyllDataUnavailableError(ChlorophyllProviderError):
    pass


class NoValidChlorophyllCellError(ChlorophyllProviderError):
    pass


class InvalidChlorophyllTimeError(ChlorophyllProviderError):
    pass


def chlorophyll_error_code(exc: Exception) -> str:
    if isinstance(exc, InvalidChlorophyllTimeError):
        return "INVALID_CHLOROPHYLL_TIME"
    if isinstance(exc, ChlorophyllDataUnavailableError):
        return "CHLOROPHYLL_DATA_UNAVAILABLE"
    if isinstance(exc, NoValidChlorophyllCellError):
        return "NO_VALID_CHLOROPHYLL_CELL"
    if isinstance(exc, InvalidChlorophyllResponseError):
        return "INVALID_CHLOROPHYLL_RESPONSE"
    if isinstance(exc, ChlorophyllDependencyMissingError):
        return "CHLOROPHYLL_DEPENDENCY_MISSING"
    if isinstance(exc, ChlorophyllAuthenticationError):
        return "CHLOROPHYLL_AUTHENTICATION_FAILED"
    if isinstance(exc, ChlorophyllSourceNotConfiguredError):
        return "CHLOROPHYLL_SOURCE_NOT_CONFIGURED"
    return "CHLOROPHYLL_SOURCE_UNAVAILABLE"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidChlorophyllTimeError(
            "Chlorophyll query time must be timezone-aware"
        )
    return value.astimezone(UTC)


def normalize_longitude(longitude: float) -> float:
    normalized = (longitude + 180.0) % 360.0 - 180.0
    return 0.0 if normalized == -0.0 else normalized


def _same_grid_cell(left: ChlorophyllProviderCell, right: ChlorophyllProviderCell) -> bool:
    return (
        left.latitude == right.latitude
        and normalize_longitude(left.longitude) == normalize_longitude(right.longitude)
    )


class CopernicusChlorophyllService:
    def __init__(
        self,
        *,
        provider: ChlorophyllProvider,
        cache: JsonCache,
        dataset_id: str,
        dataset_version: str,
        chlorophyll_variable: str,
        uncertainty_variable: str,
        flags_variable: str,
        max_radius_km: float,
        fresh_ttl_seconds: int,
        max_stale_seconds: int,
        freshness_hours: float,
        high_uncertainty_percent: float,
        exact_grid_tolerance_km: float = EXACT_GRID_CELL_TOLERANCE_KM,
        adapter_schema_version: str = CHLOROPHYLL_ADAPTER_SCHEMA_VERSION,
        now=None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.dataset_id = dataset_id
        self.dataset_version = dataset_version
        self.chlorophyll_variable = chlorophyll_variable
        self.uncertainty_variable = uncertainty_variable
        self.flags_variable = flags_variable
        self.max_radius_km = max_radius_km
        self.fresh_ttl_seconds = fresh_ttl_seconds
        self.max_stale_seconds = max_stale_seconds
        self.freshness_hours = freshness_hours
        self.high_uncertainty_percent = high_uncertainty_percent
        self.exact_grid_tolerance_km = exact_grid_tolerance_km
        self.adapter_schema_version = adapter_schema_version
        self._now = now or (lambda: datetime.now(UTC))
        self._locks: dict[str, asyncio.Lock] = {}

    def _cache_base(
        self,
        latitude: float,
        longitude: float,
        query_time: datetime,
    ) -> str:
        identity: dict[str, Any] = {
            "provider": "Copernicus Marine",
            "product_id": COPERNICUS_CHLOROPHYLL_PRODUCT_ID,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "chlorophyll_variable": self.chlorophyll_variable,
            "uncertainty_variable": self.uncertainty_variable,
            "flags_variable": self.flags_variable,
            "requested_latitude": f"{latitude:.6f}",
            "requested_longitude": f"{normalize_longitude(longitude):.6f}",
            "requested_utc_date": query_time.date().isoformat(),
            "maximum_sampling_radius_km": self.max_radius_km,
            "exact_grid_tolerance_km": self.exact_grid_tolerance_km,
            "freshness_hours": self.freshness_hours,
            "high_uncertainty_percent": self.high_uncertainty_percent,
            "fresh_ttl_seconds": self.fresh_ttl_seconds,
            "max_stale_seconds": self.max_stale_seconds,
            "adapter_schema_version": self.adapter_schema_version,
        }
        canonical = json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"chlorophyll:{self.adapter_schema_version}:{digest}"

    def _bounds(
        self,
        latitude: float,
        longitude: float,
    ) -> list[tuple[float, float, float, float]]:
        latitude_delta = self.max_radius_km / 111.195
        minimum_latitude = max(-90.0, latitude - latitude_delta)
        maximum_latitude = min(90.0, latitude + latitude_delta)
        cosine = abs(math.cos(math.radians(latitude)))
        longitude_delta = (
            180.0
            if cosine < 1e-12
            else min(180.0, self.max_radius_km / (111.195 * cosine))
        )
        if longitude_delta >= 180.0:
            return [(minimum_latitude, maximum_latitude, -180.0, 180.0)]

        centre = normalize_longitude(longitude)
        raw_minimum = centre - longitude_delta
        raw_maximum = centre + longitude_delta
        if raw_minimum < -180.0:
            return [
                (minimum_latitude, maximum_latitude, -180.0, raw_maximum),
                (
                    minimum_latitude,
                    maximum_latitude,
                    raw_minimum + 360.0,
                    180.0,
                ),
            ]
        if raw_maximum > 180.0:
            return [
                (minimum_latitude, maximum_latitude, raw_minimum, 180.0),
                (
                    minimum_latitude,
                    maximum_latitude,
                    -180.0,
                    raw_maximum - 360.0,
                ),
            ]
        return [
            (
                minimum_latitude,
                maximum_latitude,
                raw_minimum,
                raw_maximum,
            )
        ]

    async def _cached(
        self,
        key: str,
        status: ChlorophyllCacheStatus,
        *,
        query_time: datetime,
        warning: str | None = None,
    ) -> ChlorophyllResponse | None:
        value = await self.cache.get(key)
        if value is None:
            return None
        try:
            response = ChlorophyllResponse.model_validate(value)
        except Exception:
            return None
        if status == ChlorophyllCacheStatus.STALE:
            age = _utc(self._now()) - response.retrieved_at.astimezone(UTC)
            if age < timedelta(0) or age > timedelta(seconds=self.max_stale_seconds):
                return None
            analysis_age = query_time - response.analysis_time.astimezone(UTC)
            if analysis_age < timedelta(0) or analysis_age > timedelta(
                hours=self.freshness_hours
            ):
                return None
        warnings = [*response.warnings]
        if warning is not None and warning not in warnings:
            warnings.append(warning)
        return response.model_copy(
            update={"cache_status": status, "warnings": warnings}
        )

    @staticmethod
    def _metadata_matches(
        left: ChlorophyllFlagMetadata,
        right: ChlorophyllFlagMetadata,
    ) -> bool:
        return left.meaning_to_mask == right.meaning_to_mask

    async def _fetch_results(
        self,
        *,
        latitude: float,
        longitude: float,
        start_datetime: datetime,
        query_time: datetime,
    ) -> ChlorophyllProviderResult:
        results: list[ChlorophyllProviderResult] = []
        for minimum_latitude, maximum_latitude, minimum_longitude, maximum_longitude in self._bounds(
            latitude, longitude
        ):
            results.append(
                await self.provider.fetch_cells(
                    dataset_id=self.dataset_id,
                    chlorophyll_variable=self.chlorophyll_variable,
                    uncertainty_variable=self.uncertainty_variable,
                    flags_variable=self.flags_variable,
                    minimum_latitude=minimum_latitude,
                    maximum_latitude=maximum_latitude,
                    minimum_longitude=minimum_longitude,
                    maximum_longitude=maximum_longitude,
                    start_datetime=start_datetime,
                    end_datetime=query_time,
                )
            )
        if not results:
            raise InvalidChlorophyllResponseError(
                "Copernicus chlorophyll returned no bounded subsets"
            )
        first = results[0]
        for result in results[1:]:
            if (
                not self._metadata_matches(first.flag_metadata, result.flag_metadata)
                or first.chlorophyll_valid_min != result.chlorophyll_valid_min
                or first.chlorophyll_valid_max != result.chlorophyll_valid_max
            ):
                raise InvalidChlorophyllResponseError(
                    "Copernicus chlorophyll metadata changed across bounded subsets"
                )
        return ChlorophyllProviderResult(
            cells=[cell for result in results for cell in result.cells],
            flag_metadata=first.flag_metadata,
            chlorophyll_valid_min=first.chlorophyll_valid_min,
            chlorophyll_valid_max=first.chlorophyll_valid_max,
            spatial_resolution_km=first.spatial_resolution_km,
        )

    @staticmethod
    def _cell_is_water_and_valid(
        cell: ChlorophyllProviderCell,
        *,
        metadata: ChlorophyllFlagMetadata,
        valid_min: float,
        valid_max: float,
    ) -> bool:
        flag = cell.flag_value
        value = cell.chlorophyll_mg_m3
        if flag is None or flag & metadata.land_mask:
            return False
        return (
            value is not None
            and math.isfinite(value)
            and value not in (-999.0, -32768.0)
            and valid_min <= value <= valid_max
        )

    def _normalize(
        self,
        *,
        result: ChlorophyllProviderResult,
        latitude: float,
        longitude: float,
        start_datetime: datetime,
        query_time: datetime,
        retrieved_at: datetime,
    ) -> ChlorophyllResponse:
        normalized_cells: list[tuple[datetime, float, float, float, ChlorophyllProviderCell]] = []
        for cell in result.cells:
            try:
                analysis_time = _utc(cell.analysis_time)
            except InvalidChlorophyllTimeError as exc:
                raise InvalidChlorophyllResponseError(
                    "Copernicus chlorophyll returned a timezone-naive analysis time"
                ) from exc
            if not (
                math.isfinite(cell.latitude)
                and math.isfinite(cell.longitude)
                and -90.0 <= cell.latitude <= 90.0
            ):
                raise InvalidChlorophyllResponseError(
                    "Copernicus chlorophyll returned invalid coordinates"
                )
            if not start_datetime <= analysis_time <= query_time:
                continue
            normalized_longitude = normalize_longitude(cell.longitude)
            distance = haversine_distance_km(
                latitude,
                normalize_longitude(longitude),
                cell.latitude,
                normalized_longitude,
            )
            normalized_cells.append(
                (
                    analysis_time,
                    distance,
                    cell.latitude,
                    normalized_longitude,
                    cell,
                )
            )

        if not normalized_cells:
            raise ChlorophyllDataUnavailableError(
                "No chlorophyll analysis exists within the freshness window"
            )
        latest_time = max(item[0] for item in normalized_cells)
        if query_time - latest_time > timedelta(hours=self.freshness_hours):
            raise ChlorophyllDataUnavailableError(
                "Latest chlorophyll analysis exceeds ORCA's freshness policy"
            )
        latest = [item for item in normalized_cells if item[0] == latest_time]
        nearest_grid = min(latest, key=lambda item: (item[1], item[2], item[3]))
        eligible = [
            item
            for item in latest
            if item[1] <= self.max_radius_km
            and self._cell_is_water_and_valid(
                item[4],
                metadata=result.flag_metadata,
                valid_min=result.chlorophyll_valid_min,
                valid_max=result.chlorophyll_valid_max,
            )
        ]
        if not eligible:
            raise NoValidChlorophyllCellError(
                "No valid chlorophyll water cell exists within the configured radius"
            )
        selected_item = min(eligible, key=lambda item: (item[1], item[2], item[3]))
        _, raw_distance, selected_latitude, selected_longitude, selected = selected_item

        if raw_distance <= self.exact_grid_tolerance_km:
            sampling_quality = ChlorophyllSamplingQuality.EXACT_GRID_CELL
        elif _same_grid_cell(selected, nearest_grid[4]):
            sampling_quality = ChlorophyllSamplingQuality.NEAREST_GRID_CELL
        else:
            sampling_quality = ChlorophyllSamplingQuality.NEAREST_VALID_WATER_CELL

        flag = selected.flag_value
        value = selected.chlorophyll_mg_m3
        assert flag is not None and value is not None
        interpolated = bool(flag & result.flag_metadata.interpolated_mask)
        uncertainty = selected.uncertainty_percent
        if uncertainty is not None and (
            not math.isfinite(uncertainty) or uncertainty < 0
        ):
            uncertainty = None

        warnings: list[str] = []
        if sampling_quality == ChlorophyllSamplingQuality.NEAREST_VALID_WATER_CELL:
            if (
                nearest_grid[4].flag_value is not None
                and nearest_grid[4].flag_value & result.flag_metadata.land_mask
            ):
                warnings.append(
                    "The nearest provider grid cell was land; a valid water cell "
                    "within the configured radius was used."
                )
            else:
                warnings.append(
                    "The nearest provider grid cell was invalid; a valid water cell "
                    "within the configured radius was used."
                )
        if latest_time < query_time:
            warnings.append(
                "The latest daily chlorophyll analysis not later than the requested "
                "time was used."
            )
        if interpolated:
            warnings.append(INTERPOLATION_WARNING)
        high_uncertainty = (
            uncertainty is not None
            and uncertainty >= self.high_uncertainty_percent
        )
        if high_uncertainty:
            warnings.append(HIGH_UNCERTAINTY_WARNING)
        if uncertainty is None:
            warnings.append(MISSING_UNCERTAINTY_WARNING)
        evidence_quality = (
            ChlorophyllEvidenceQuality.DEGRADED
            if interpolated or high_uncertainty or uncertainty is None
            else ChlorophyllEvidenceQuality.NORMAL
        )

        return ChlorophyllResponse(
            dataset_id=self.dataset_id,
            dataset_version=self.dataset_version,
            variable=self.chlorophyll_variable,
            requested_location=SSTLocation(
                latitude=latitude,
                longitude=normalize_longitude(longitude),
            ),
            sampled_location=SSTLocation(
                latitude=selected_latitude,
                longitude=selected_longitude,
            ),
            sample_distance_km=round(raw_distance, 3),
            chlorophyll_a=ChlorophyllValue(value=round(value, 4)),
            analysis_time=latest_time,
            retrieved_at=retrieved_at,
            spatial_resolution_km=round(result.spatial_resolution_km, 6),
            sampling_quality=sampling_quality,
            data_provenance=(
                ChlorophyllDataProvenance.SPACE_TIME_INTERPOLATED_GAP_FILL
                if interpolated
                else ChlorophyllDataProvenance.MULTI_SENSOR_MERGED_SATELLITE_PIXEL
            ),
            quality=ChlorophyllQualityMetadata(
                flag_value=flag,
                interpolated=interpolated,
                uncertainty_percent=(
                    round(uncertainty, 2) if uncertainty is not None else None
                ),
                evidence_quality=evidence_quality,
            ),
            cache_status=ChlorophyllCacheStatus.REFRESHED,
            warnings=warnings,
        )

    async def get_chlorophyll(
        self,
        *,
        latitude: float,
        longitude: float,
        at: datetime | None = None,
    ) -> ChlorophyllResponse:
        now = _utc(self._now())
        query_time = _utc(at) if at is not None else now
        if at is not None and query_time > now + FUTURE_CLOCK_SKEW:
            raise InvalidChlorophyllTimeError(
                "Chlorophyll is an analysis product and does not provide forecasts"
            )
        start_datetime = query_time - timedelta(hours=self.freshness_hours)
        cache_base = self._cache_base(latitude, longitude, query_time)
        fresh_key = f"{cache_base}:fresh"
        last_success_key = f"{cache_base}:last_success"

        cached = await self._cached(
            fresh_key,
            ChlorophyllCacheStatus.FRESH,
            query_time=query_time,
        )
        if cached is not None:
            return cached

        lock = self._locks.setdefault(cache_base, asyncio.Lock())
        async with lock:
            cached = await self._cached(
                fresh_key,
                ChlorophyllCacheStatus.FRESH,
                query_time=query_time,
            )
            if cached is not None:
                return cached
            try:
                result = await self._fetch_results(
                    latitude=latitude,
                    longitude=longitude,
                    start_datetime=start_datetime,
                    query_time=query_time,
                )
                response = self._normalize(
                    result=result,
                    latitude=latitude,
                    longitude=longitude,
                    start_datetime=start_datetime,
                    query_time=query_time,
                    retrieved_at=_utc(self._now()),
                )
            except ChlorophyllSourceUnavailableError:
                stale = await self._cached(
                    last_success_key,
                    ChlorophyllCacheStatus.STALE,
                    query_time=query_time,
                    warning=(
                        "Copernicus chlorophyll refresh failed; returning matching "
                        "stale data"
                    ),
                )
                if stale is not None:
                    return stale
                raise

            serialized = response.model_dump(mode="json")
            await self.cache.set(fresh_key, serialized, self.fresh_ttl_seconds)
            await self.cache.set(
                last_success_key,
                serialized,
                self.max_stale_seconds,
            )
            return response


class CopernicusChlorophyllMarineSource:
    name = "chlorophyll"

    def __init__(self, service: CopernicusChlorophyllService) -> None:
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
            response = await self.service.get_chlorophyll(
                latitude=latitude,
                longitude=longitude,
                at=at,
            )
        except ChlorophyllProviderError as exc:
            return SourceResult(
                source="Copernicus Marine",
                status=(
                    SourceStatus.INVALID
                    if isinstance(exc, InvalidChlorophyllResponseError)
                    else SourceStatus.UNAVAILABLE
                ),
                error=chlorophyll_error_code(exc),
            )

        status = {
            ChlorophyllCacheStatus.FRESH: SourceStatus.CACHED,
            ChlorophyllCacheStatus.REFRESHED: SourceStatus.FRESH,
            ChlorophyllCacheStatus.STALE: SourceStatus.STALE,
        }[response.cache_status]
        return SourceResult(
            source="Copernicus Marine",
            status=status,
            data=response.model_dump(mode="json"),
            fetched_at=response.retrieved_at,
            cached=response.cache_status != ChlorophyllCacheStatus.REFRESHED,
        )

