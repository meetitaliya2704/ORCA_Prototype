from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta

from app.clients.copernicus_chlorophyll import (
    COPERNICUS_CHLOROPHYLL_PRODUCT_ID,
    ChlorophyllAuthenticationError,
    ChlorophyllDependencyMissingError,
    ChlorophyllFlagMetadata,
    ChlorophyllProvider,
    ChlorophyllProviderCell,
    ChlorophyllProviderResult,
    ChlorophyllSourceNotConfiguredError,
    ChlorophyllSourceUnavailableError,
    InvalidChlorophyllResponseError,
    parse_chlorophyll_flag_metadata,
)
from app.schemas.marine import (
    ChlorophyllCacheStatus,
    ChlorophyllSnapshotResponse,
    RefreshAcceptedResponse,
    RefreshJobResponse,
    RefreshTileReference,
    SSTSnapshotMetadata,
    SSTSnapshotStatus,
)
from app.services.chlorophyll import (
    ChlorophyllDataUnavailableError,
    CopernicusChlorophyllService,
    NoValidChlorophyllCellError,
    chlorophyll_error_code,
)
from app.snapshots.jobs import RefreshBlockedError, RefreshJobManager
from app.snapshots.models import (
    ChlorophyllRegionalCell,
    ChlorophyllRegionalPayload,
    RefreshFailureClassification,
    RefreshJobStatus,
    RegionalSnapshot,
    SnapshotIdentity,
    SnapshotMetadata,
    SnapshotState,
    TileKey,
)
from app.snapshots.store import InMemorySnapshotStore
from app.snapshots.tiling import coverage_contains, logical_coverage, padded_coverage, tile_for_coordinate


CHLOROPHYLL_SNAPSHOT_SCHEMA_VERSION = "chlorophyll-snapshot-v1"
CHLOROPHYLL_FLAG_POLICY_VERSION = "cmems-land-interpolated-bitmask-v1"
CHLOROPHYLL_UNIT_POLICY = "toolbox-decoded-mg-m3-no-rescale"


def classify_chlorophyll_refresh_failure(exc: Exception) -> RefreshFailureClassification:
    if isinstance(exc, (NoValidChlorophyllCellError, ChlorophyllDataUnavailableError)):
        return RefreshFailureClassification.REQUEST_RESULT
    if isinstance(
        exc,
        (
            ChlorophyllAuthenticationError,
            ChlorophyllDependencyMissingError,
            ChlorophyllSourceNotConfiguredError,
            InvalidChlorophyllResponseError,
            ValueError,
        ),
    ):
        return RefreshFailureClassification.NON_RETRYABLE
    if isinstance(exc, (ChlorophyllSourceUnavailableError, TimeoutError, ConnectionError)):
        return RefreshFailureClassification.RETRYABLE
    return RefreshFailureClassification.NON_RETRYABLE


class ChlorophyllSnapshotManager:
    def __init__(
        self,
        *,
        provider: ChlorophyllProvider,
        point_service: CopernicusChlorophyllService,
        store: InMemorySnapshotStore,
        jobs: RefreshJobManager,
        tile_size_degrees: float,
        wait_timeout_seconds: float,
        fresh_seconds: int,
        max_stale_seconds: int,
        refresh_check_seconds: int,
        schema_version: str = CHLOROPHYLL_SNAPSHOT_SCHEMA_VERSION,
        now=None,
    ) -> None:
        self.provider = provider
        self.point_service = point_service
        self.store = store
        self.jobs = jobs
        self.tile_size_degrees = tile_size_degrees
        self.wait_timeout_seconds = wait_timeout_seconds
        self.fresh_seconds = fresh_seconds
        self.max_stale_seconds = max_stale_seconds
        self.refresh_check_seconds = refresh_check_seconds
        self.schema_version = schema_version
        self._now = now or (lambda: datetime.now(UTC))
        canonical = {
            "source": "chlorophyll",
            "provider": "Copernicus Marine",
            "product": COPERNICUS_CHLOROPHYLL_PRODUCT_ID,
            "dataset": point_service.dataset_id,
            "dataset_version": point_service.dataset_version,
            "variables": [
                point_service.chlorophyll_variable,
                point_service.uncertainty_variable,
                point_service.flags_variable,
            ],
            "tile_size": tile_size_degrees,
            "tiling": "sst-tiles-v1",
            "fallback_radius_km": point_service.max_radius_km,
            "exact_grid_tolerance_km": point_service.exact_grid_tolerance_km,
            "freshness_hours": point_service.freshness_hours,
            "high_uncertainty_percent": point_service.high_uncertainty_percent,
            "uncertainty_policy": "missing-or-threshold-degrades-v1",
            "flag_policy": CHLOROPHYLL_FLAG_POLICY_VERSION,
            "unit_policy": CHLOROPHYLL_UNIT_POLICY,
            "schema": schema_version,
        }
        self.configuration_identity = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def tile(self, latitude: float, longitude: float) -> TileKey:
        return tile_for_coordinate(latitude, longitude, self.tile_size_degrees)

    def _store_key(self, tile: TileKey, requested_time: datetime) -> str:
        return (
            f"chlorophyll:snapshot:{self.configuration_identity}:"
            f"{tile.safe_id}:{requested_time.date().isoformat()}"
        )

    def _failure_gate_key(self, tile: TileKey) -> str:
        return f"chlorophyll:failure:{self.configuration_identity}:{tile.safe_id}"

    @staticmethod
    def _raise_failed(code: str | None, retry_after_seconds: int | None = None):
        errors = {
            "CHLOROPHYLL_DATA_UNAVAILABLE": ChlorophyllDataUnavailableError,
            "NO_VALID_CHLOROPHYLL_CELL": NoValidChlorophyllCellError,
            "CHLOROPHYLL_AUTHENTICATION_FAILED": ChlorophyllAuthenticationError,
            "CHLOROPHYLL_DEPENDENCY_MISSING": ChlorophyllDependencyMissingError,
            "CHLOROPHYLL_SOURCE_NOT_CONFIGURED": ChlorophyllSourceNotConfiguredError,
            "INVALID_CHLOROPHYLL_RESPONSE": InvalidChlorophyllResponseError,
        }
        error = errors.get(code, ChlorophyllSourceUnavailableError)(
            "Chlorophyll snapshot refresh failed"
        )
        if retry_after_seconds is not None:
            error.retry_after_seconds = retry_after_seconds
        raise error

    async def _refresh(
        self, *, tile: TileKey, requested_time: datetime, job_id: str
    ) -> RegionalSnapshot:
        bounds = padded_coverage(tile, self.point_service.max_radius_km)
        result = await self.provider.fetch_region(
            dataset_id=self.point_service.dataset_id,
            chlorophyll_variable=self.point_service.chlorophyll_variable,
            uncertainty_variable=self.point_service.uncertainty_variable,
            flags_variable=self.point_service.flags_variable,
            minimum_latitude=bounds.minimum_latitude,
            maximum_latitude=bounds.maximum_latitude,
            minimum_longitude=bounds.minimum_longitude,
            maximum_longitude=bounds.maximum_longitude,
            start_datetime=requested_time - timedelta(hours=self.point_service.freshness_hours),
            end_datetime=requested_time,
        )
        validated_flags = parse_chlorophyll_flag_metadata(
            tuple(result.flag_metadata.meaning_to_mask.values()),
            tuple(result.flag_metadata.meaning_to_mask.keys()),
        )
        if validated_flags.meaning_to_mask != result.flag_metadata.meaning_to_mask:
            raise InvalidChlorophyllResponseError(
                "Copernicus chlorophyll flag metadata is inconsistent"
            )
        eligible_times = {
            cell.analysis_time.astimezone(UTC)
            for cell in result.cells
            if cell.analysis_time.tzinfo is not None
            and cell.analysis_time.astimezone(UTC) <= requested_time
        }
        if not eligible_times:
            raise ChlorophyllDataUnavailableError(
                "No chlorophyll analysis exists within the freshness window"
            )
        valid_time = max(eligible_times)
        if requested_time - valid_time > timedelta(hours=self.point_service.freshness_hours):
            raise ChlorophyllDataUnavailableError(
                "Latest chlorophyll analysis exceeds ORCA's freshness policy"
            )
        cells = tuple(
            ChlorophyllRegionalCell(
                latitude=cell.latitude,
                longitude=cell.longitude,
                chlorophyll_mg_m3=cell.chlorophyll_mg_m3,
                uncertainty_percent=cell.uncertainty_percent,
                flag_value=cell.flag_value,
            )
            for cell in result.cells
            if cell.analysis_time.astimezone(UTC) == valid_time
        )
        if not cells:
            raise InvalidChlorophyllResponseError(
                "Copernicus chlorophyll regional field contained no selected-time cells"
            )
        latitudes = tuple(sorted({cell.latitude for cell in cells}))
        longitudes = tuple(sorted({cell.longitude for cell in cells}))
        payload = ChlorophyllRegionalPayload(
            latitudes=latitudes,
            longitudes=longitudes,
            cells=cells,
            provider_valid_time=valid_time,
            product_id=COPERNICUS_CHLOROPHYLL_PRODUCT_ID,
            dataset_id=self.point_service.dataset_id,
            dataset_version=self.point_service.dataset_version,
            chlorophyll_variable=self.point_service.chlorophyll_variable,
            uncertainty_variable=self.point_service.uncertainty_variable,
            flags_variable=self.point_service.flags_variable,
            meaning_to_mask=dict(result.flag_metadata.meaning_to_mask),
            raw_flag_meanings=result.flag_metadata.raw_flag_meanings,
            chlorophyll_valid_min=result.chlorophyll_valid_min,
            chlorophyll_valid_max=result.chlorophyll_valid_max,
            spatial_resolution_km=result.spatial_resolution_km,
        )
        now = self._now().astimezone(UTC)
        variables = (
            self.point_service.chlorophyll_variable,
            self.point_service.uncertainty_variable,
            self.point_service.flags_variable,
        )
        return RegionalSnapshot(
            metadata=SnapshotMetadata(
                identity=SnapshotIdentity(
                    source="chlorophyll",
                    product_id=COPERNICUS_CHLOROPHYLL_PRODUCT_ID,
                    dataset_id=self.point_service.dataset_id,
                    dataset_version=self.point_service.dataset_version,
                    variable=self.point_service.chlorophyll_variable,
                    variables=variables,
                    tile_id=tile.safe_id,
                    provider_valid_time=valid_time,
                    configuration_identity=self.configuration_identity,
                    schema_version=self.schema_version,
                ),
                logical_coverage=logical_coverage(tile),
                provider_request_coverage=bounds,
                retrieved_at=now,
                stored_at=now,
                fresh_until=now + timedelta(seconds=self.fresh_seconds),
                stale_until=now + timedelta(seconds=self.max_stale_seconds),
                last_successful_refresh_id=job_id,
            ),
            payload=payload,
        )

    async def queue(self, latitude: float, longitude: float, at: datetime | None = None):
        requested_time = self.point_service.query_time(at)
        tile = self.tile(latitude, longitude)
        key = self._store_key(tile, requested_time)

        async def factory(job_id: str) -> RegionalSnapshot:
            return await self._refresh(tile=tile, requested_time=requested_time, job_id=job_id)

        return await self.jobs.request(
            deduplication_key=key,
            failure_gate_key=self._failure_gate_key(tile),
            configuration_identity=self.configuration_identity,
            source="chlorophyll",
            tile_id=tile.safe_id,
            factory=factory,
            failure_classifier=classify_chlorophyll_refresh_failure,
            error_code_resolver=chlorophyll_error_code,
            failure_message="Chlorophyll snapshot refresh failed",
        )

    def _sample(
        self,
        snapshot: RegionalSnapshot,
        latitude: float,
        longitude: float,
        requested_time: datetime,
    ):
        if not coverage_contains(snapshot.metadata.logical_coverage, latitude, longitude):
            raise ValueError("coordinate is outside the snapshot logical tile")
        payload = ChlorophyllRegionalPayload.model_validate(snapshot.payload)
        metadata = ChlorophyllFlagMetadata(
            meaning_to_mask=dict(payload.meaning_to_mask),
            raw_flag_meanings=payload.raw_flag_meanings,
        )
        result = ChlorophyllProviderResult(
            cells=[
                ChlorophyllProviderCell(
                    latitude=cell.latitude,
                    longitude=cell.longitude,
                    analysis_time=payload.provider_valid_time,
                    chlorophyll_mg_m3=cell.chlorophyll_mg_m3,
                    uncertainty_percent=cell.uncertainty_percent,
                    flag_value=cell.flag_value,
                )
                for cell in payload.cells
            ],
            flag_metadata=metadata,
            chlorophyll_valid_min=payload.chlorophyll_valid_min,
            chlorophyll_valid_max=payload.chlorophyll_valid_max,
            spatial_resolution_km=payload.spatial_resolution_km,
        )
        return self.point_service.normalize_result(
            result=result,
            latitude=latitude,
            longitude=longitude,
            query_time=requested_time,
            retrieved_at=snapshot.metadata.retrieved_at,
        )

    def _response(
        self, snapshot: RegionalSnapshot, latitude: float, longitude: float,
        *, stale: bool, refresh_job_id: str | None = None,
        refresh_blocked_until: datetime | None = None, just_refreshed: bool = False,
        requested_time: datetime | None = None,
    ) -> ChlorophyllSnapshotResponse:
        base = self._sample(
            snapshot,
            latitude,
            longitude,
            requested_time or snapshot.metadata.identity.provider_valid_time,
        )
        warnings = list(base.warnings)
        if stale:
            warning = (
                "A newer Copernicus chlorophyll snapshot is being retrieved"
                if refresh_job_id is not None
                else "A newer chlorophyll snapshot could not be retrieved; the last successful snapshot is being used."
            )
            if warning not in warnings:
                warnings.append(warning)
        payload = ChlorophyllRegionalPayload.model_validate(snapshot.payload)
        return ChlorophyllSnapshotResponse.model_validate({
            **base.model_dump(mode="python"),
            "cache_status": (
                ChlorophyllCacheStatus.STALE if stale else
                ChlorophyllCacheStatus.REFRESHED if just_refreshed else
                ChlorophyllCacheStatus.FRESH
            ),
            "warnings": warnings,
            "snapshot": SSTSnapshotMetadata(
                status=(
                    SSTSnapshotStatus.STALE_REFRESHING
                    if stale and refresh_job_id is not None else
                    SSTSnapshotStatus.STALE if stale else SSTSnapshotStatus.FRESH
                ),
                snapshot_id=hashlib.sha256(
                    snapshot.metadata.identity.model_dump_json().encode()
                ).hexdigest()[:24],
                tile_id=snapshot.metadata.identity.tile_id,
                provider_valid_time=payload.provider_valid_time,
                refreshed_at=snapshot.metadata.retrieved_at,
                fresh_until=snapshot.metadata.fresh_until,
                stale_until=snapshot.metadata.stale_until,
                refresh_job_id=refresh_job_id,
                refresh_blocked_until=refresh_blocked_until,
            ),
        })

    async def get_chlorophyll(
        self, *, latitude: float, longitude: float, at: datetime | None = None,
        wait_for_refresh: bool = False,
    ) -> ChlorophyllSnapshotResponse | RefreshAcceptedResponse:
        requested_time = self.point_service.query_time(at)
        tile = self.tile(latitude, longitude)
        key = self._store_key(tile, requested_time)
        lookup = await self.store.get_latest(key)
        if lookup.snapshot is None:
            lookup = await self.store.get_latest_successful(
                source="chlorophyll",
                tile_id=tile.safe_id,
                configuration_identity=self.configuration_identity,
            )
            if lookup.snapshot is not None:
                valid = lookup.snapshot.metadata.identity.provider_valid_time
                if not (
                    requested_time - timedelta(hours=self.point_service.freshness_hours)
                    <= valid <= requested_time
                ):
                    lookup = lookup.model_copy(update={"snapshot": None, "state": SnapshotState.FAILED})
        if lookup.snapshot is not None and lookup.state == SnapshotState.FRESH:
            return self._response(
                lookup.snapshot, latitude, longitude, stale=False,
                requested_time=requested_time,
            )
        if lookup.snapshot is not None:
            try:
                job = await self.queue(latitude, longitude, requested_time)
            except RefreshBlockedError as exc:
                return self._response(
                    lookup.snapshot, latitude, longitude, stale=True,
                    refresh_blocked_until=exc.gate.blocked_until,
                    requested_time=requested_time,
                )
            if wait_for_refresh:
                completed = await self.jobs.wait(job.job_id, self.wait_timeout_seconds)
                if completed.state == RefreshJobStatus.SUCCEEDED:
                    refreshed = await self.store.get_latest(key)
                    if refreshed.snapshot is not None:
                        return self._response(
                            refreshed.snapshot, latitude, longitude,
                            stale=False, just_refreshed=True,
                            requested_time=requested_time,
                        )
            current = await self.jobs.get(job.job_id)
            if current.state == RefreshJobStatus.FAILED:
                gate = await self.jobs.failure_gate(self._failure_gate_key(tile))
                return self._response(
                    lookup.snapshot, latitude, longitude, stale=True,
                    refresh_blocked_until=gate.blocked_until if gate else None,
                    requested_time=requested_time,
                )
            return self._response(
                lookup.snapshot, latitude, longitude, stale=True,
                refresh_job_id=job.job_id,
                requested_time=requested_time,
            )
        try:
            job = await self.queue(latitude, longitude, requested_time)
        except RefreshBlockedError as exc:
            retry_after = max(
                1,
                math.ceil((exc.gate.blocked_until - self._now().astimezone(UTC)).total_seconds()),
            )
            self._raise_failed(
                exc.gate.error_code,
                retry_after if exc.gate.classification == RefreshFailureClassification.RETRYABLE else None,
            )
        if wait_for_refresh:
            completed = await self.jobs.wait(job.job_id, self.wait_timeout_seconds)
            if completed.state == RefreshJobStatus.SUCCEEDED:
                refreshed = await self.store.get_latest(key)
                if refreshed.snapshot is not None:
                    return self._response(
                        refreshed.snapshot, latitude, longitude,
                        stale=False, just_refreshed=True,
                        requested_time=requested_time,
                    )
            if completed.state == RefreshJobStatus.FAILED:
                self._raise_failed(completed.error_code, completed.retry_after_seconds)
        current = await self.jobs.get(job.job_id)
        if current.state == RefreshJobStatus.FAILED:
            self._raise_failed(current.error_code, current.retry_after_seconds)
        return RefreshAcceptedResponse(
            source="chlorophyll",
            job_id=job.job_id,
            tile=RefreshTileReference(id=tile.safe_id),
        )

    async def job_status(self, job_id: str) -> RefreshJobResponse:
        job = await self.jobs.get(job_id)
        if job.source != "chlorophyll":
            raise KeyError(job_id)
        lookup = await self.store.get_latest(job.deduplication_key)
        if lookup.snapshot is None:
            lookup = await self.store.get_latest_successful(
                source="chlorophyll",
                tile_id=job.tile_id,
                configuration_identity=self.configuration_identity,
            )
        return RefreshJobResponse(
            job_id=job.job_id,
            source="chlorophyll",
            tile_id=job.tile_id,
            state=job.state.value,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            attempt_count=job.attempt_count,
            snapshot_valid_time=job.snapshot_valid_time,
            error_code=job.error_code,
            message=job.message,
            retryable=job.retryable,
            next_retry_at=job.next_retry_at,
            retry_after_seconds=job.retry_after_seconds,
            snapshot_available=lookup.snapshot is not None,
        )

    async def schedule_if_due(self, latitude: float, longitude: float) -> str | None:
        requested = self.point_service.query_time(None)
        tile = self.tile(latitude, longitude)
        lookup = await self.store.get_latest(self._store_key(tile, requested))
        if lookup.snapshot is not None:
            age = (requested - lookup.snapshot.metadata.stored_at).total_seconds()
            if (
                age < self.refresh_check_seconds
                or requested.date() <= lookup.snapshot.metadata.identity.provider_valid_time.date()
            ):
                return None
        try:
            return (await self.queue(latitude, longitude, requested)).job_id
        except RefreshBlockedError:
            return None
