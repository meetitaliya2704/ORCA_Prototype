from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta

from app.clients.copernicus_sst import (
    COPERNICUS_SST_PRODUCT_ID,
    InvalidSSTResponseError,
    SSTAuthenticationError,
    SSTProvider,
    SSTProviderCell,
    SSTSourceNotConfiguredError,
    SSTSourceUnavailableError,
)
from app.core.performance import performance_span
from app.schemas.marine import (
    RefreshAcceptedResponse,
    RefreshJobResponse,
    RefreshTileReference,
    SSTCacheStatus,
    SSTSnapshotMetadata,
    SSTSnapshotResponse,
    SSTSnapshotStatus,
)
from app.services.sst import (
    CopernicusSSTService,
    EXACT_GRID_CELL_TOLERANCE_KM,
    NoValidSSTError,
    _utc,
)
from app.snapshots.jobs import RefreshJobManager
from app.snapshots.jobs import RefreshBlockedError
from app.snapshots.models import (
    RefreshJobStatus,
    RegionalSnapshot,
    SnapshotIdentity,
    SnapshotMetadata,
    SnapshotState,
    SSTRegionalCell,
    SSTRegionalPayload,
    TileKey,
)
from app.snapshots.store import InMemorySnapshotStore
from app.snapshots.tiling import coverage_contains, logical_coverage, padded_coverage, tile_for_coordinate


SST_SNAPSHOT_SCHEMA_VERSION = "sst-snapshot-v1"
SST_TILING_VERSION = "sst-tiles-v1"
SST_CONVERSION_POLICY = "decoded-kelvin-minus-273.15-once"


class SSTSnapshotManager:
    def __init__(
        self,
        *,
        provider: SSTProvider,
        point_service: CopernicusSSTService,
        store: InMemorySnapshotStore,
        jobs: RefreshJobManager,
        tile_size_degrees: float,
        wait_timeout_seconds: float,
        fresh_seconds: int,
        max_stale_seconds: int,
        refresh_check_seconds: int,
        lookback_days: int,
        dataset_version: str = "provider-current",
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
        self.lookback_days = lookback_days
        self.dataset_version = dataset_version
        self._now = now or (lambda: datetime.now(UTC))
        canonical = {
            "source": "copernicus_sst",
            "product": COPERNICUS_SST_PRODUCT_ID,
            "dataset": point_service.dataset_id,
            "dataset_version": dataset_version,
            "variable": point_service.variable,
            "fallback_radius_km": point_service.search_radius_km,
            "coordinate_tolerance_km": EXACT_GRID_CELL_TOLERANCE_KM,
            "lookback_days": lookback_days,
            "conversion": SST_CONVERSION_POLICY,
            "tile_size": tile_size_degrees,
            "tiling": SST_TILING_VERSION,
            "schema": SST_SNAPSHOT_SCHEMA_VERSION,
        }
        self.configuration_identity = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def tile(self, latitude: float, longitude: float) -> TileKey:
        return tile_for_coordinate(latitude, longitude, self.tile_size_degrees)

    def _store_key(self, tile: TileKey, requested_time: datetime) -> str:
        return (
            f"sst:snapshot:{self.configuration_identity}:"
            f"{tile.safe_id}:{requested_time.date().isoformat()}"
        )

    def _failure_gate_key(self, tile: TileKey) -> str:
        return f"sst:failure:{self.configuration_identity}:{tile.safe_id}"

    @staticmethod
    def _raise_failed(code: str | None, retry_after_seconds: int | None = None):
        errors = {
            "NO_VALID_SST": NoValidSSTError,
            "SST_AUTHENTICATION_FAILED": SSTAuthenticationError,
            "SST_SOURCE_NOT_CONFIGURED": SSTSourceNotConfiguredError,
            "INVALID_SST_RESPONSE": InvalidSSTResponseError,
        }
        error_type = errors.get(code, SSTSourceUnavailableError)
        error = error_type("SST snapshot refresh failed")
        if retry_after_seconds is not None:
            error.retry_after_seconds = retry_after_seconds
        raise error

    async def _refresh(
        self, *, tile: TileKey, requested_time: datetime, store_key: str, job_id: str
    ) -> RegionalSnapshot:
        bounds = padded_coverage(tile, self.point_service.search_radius_km)
        field = await self.provider.fetch_region(
            dataset_id=self.point_service.dataset_id,
            variable=self.point_service.variable,
            minimum_latitude=bounds.minimum_latitude,
            maximum_latitude=bounds.maximum_latitude,
            minimum_longitude=bounds.minimum_longitude,
            maximum_longitude=bounds.maximum_longitude,
            start_datetime=requested_time - timedelta(days=self.lookback_days),
            end_datetime=requested_time,
        )
        cells = tuple(
            SSTRegionalCell(
                latitude=cell.latitude,
                longitude=cell.longitude,
                value_celsius=(
                    cell.value_kelvin - 273.15
                    if cell.value_kelvin is not None and math.isfinite(cell.value_kelvin)
                    else None
                ),
                source_value_kelvin=(
                    cell.value_kelvin
                    if cell.value_kelvin is not None and math.isfinite(cell.value_kelvin)
                    else None
                ),
            )
            for cell in field.cells
        )
        now = _utc(self._now())
        payload = SSTRegionalPayload(
            latitudes=field.latitudes,
            longitudes=field.longitudes,
            cells=cells,
            provider_valid_time=_utc(field.analysis_time),
            product_id=COPERNICUS_SST_PRODUCT_ID,
            dataset_id=self.point_service.dataset_id,
            dataset_version=self.dataset_version,
            variable=self.point_service.variable,
        )
        identity = SnapshotIdentity(
            source="sst",
            product_id=COPERNICUS_SST_PRODUCT_ID,
            dataset_id=self.point_service.dataset_id,
            dataset_version=self.dataset_version,
            variable=self.point_service.variable,
            tile_id=tile.safe_id,
            provider_valid_time=payload.provider_valid_time,
            configuration_identity=self.configuration_identity,
        )
        return RegionalSnapshot(
            metadata=SnapshotMetadata(
                identity=identity,
                logical_coverage=logical_coverage(tile),
                provider_request_coverage=bounds,
                retrieved_at=now,
                stored_at=now,
                fresh_until=now + timedelta(seconds=self.fresh_seconds),
                stale_until=now + timedelta(seconds=self.max_stale_seconds),
                last_successful_refresh_id=job_id,
                provider_warnings=field.warnings,
            ),
            payload=payload,
        )

    async def queue(
        self, latitude: float, longitude: float, at: datetime | None = None,
        *, retry_failed: bool = False,
    ):
        requested_time = _utc(at if at is not None else self._now())
        tile = self.tile(latitude, longitude)
        key = self._store_key(tile, requested_time)

        async def factory(job_id: str) -> RegionalSnapshot:
            return await self._refresh(
                tile=tile, requested_time=requested_time, store_key=key, job_id=job_id
            )

        return await self.jobs.request(
            deduplication_key=key,
            failure_gate_key=self._failure_gate_key(tile),
            configuration_identity=self.configuration_identity,
            source="sst",
            tile_id=tile.safe_id,
            factory=factory,
            retry_failed=retry_failed,
        )

    def _sample(self, snapshot: RegionalSnapshot, latitude: float, longitude: float):
        if not coverage_contains(snapshot.metadata.logical_coverage, latitude, longitude):
            raise ValueError("coordinate is outside the snapshot logical tile")
        cells = [
            SSTProviderCell(
                latitude=cell.latitude,
                longitude=cell.longitude,
                analysis_time=snapshot.payload.provider_valid_time,
                value_kelvin=cell.source_value_kelvin,
            )
            for cell in snapshot.payload.cells
        ]
        with performance_span("snapshot.sampling"):
            return self.point_service.normalize_cells(
                cells=cells,
                latitude=latitude,
                longitude=longitude,
                start_datetime=snapshot.payload.provider_valid_time,
                query_time=snapshot.payload.provider_valid_time,
                retrieved_at=snapshot.metadata.retrieved_at,
            )

    def _response(
        self, snapshot: RegionalSnapshot, latitude: float, longitude: float,
        *, stale: bool, refresh_job_id: str | None = None,
        refresh_blocked_until: datetime | None = None,
        just_refreshed: bool = False,
    ) -> SSTSnapshotResponse:
        base = self._sample(snapshot, latitude, longitude)
        warnings = [*base.warnings, *snapshot.metadata.provider_warnings]
        if stale:
            warning = (
                "A newer SST snapshot could not be retrieved; the last successful "
                "snapshot is being used."
                if refresh_job_id is None
                else "A newer Copernicus SST snapshot is being retrieved"
            )
            if warning not in warnings:
                warnings.append(warning)
        return SSTSnapshotResponse.model_validate({
            **base.model_dump(mode="python"),
            "cache_status": (
                SSTCacheStatus.STALE if stale else
                SSTCacheStatus.REFRESHED if just_refreshed else SSTCacheStatus.FRESH
            ),
            "warnings": warnings,
            "snapshot": SSTSnapshotMetadata(
                status=(
                    SSTSnapshotStatus.STALE_REFRESHING
                    if stale and refresh_job_id is not None
                    else SSTSnapshotStatus.STALE
                    if stale
                    else SSTSnapshotStatus.FRESH
                ),
                snapshot_id=hashlib.sha256(
                    snapshot.metadata.identity.model_dump_json().encode()
                ).hexdigest()[:24],
                tile_id=snapshot.metadata.identity.tile_id,
                provider_valid_time=snapshot.payload.provider_valid_time,
                refreshed_at=snapshot.metadata.retrieved_at,
                fresh_until=snapshot.metadata.fresh_until,
                stale_until=snapshot.metadata.stale_until,
                refresh_job_id=refresh_job_id,
                refresh_blocked_until=refresh_blocked_until,
            ),
        })

    async def get_sst(
        self, *, latitude: float, longitude: float, at: datetime | None = None,
        wait_for_refresh: bool = False,
    ) -> SSTSnapshotResponse | RefreshAcceptedResponse:
        requested_time = _utc(at if at is not None else self._now())
        tile = self.tile(latitude, longitude)
        key = self._store_key(tile, requested_time)
        lookup = await self.store.get_latest(key)
        if lookup.snapshot is None:
            lookup = await self.store.get_latest_successful(
                source="sst",
                tile_id=tile.safe_id,
                configuration_identity=self.configuration_identity,
            )
            if lookup.snapshot is not None and not (
                requested_time - timedelta(days=self.lookback_days)
                <= lookup.snapshot.payload.provider_valid_time
                <= requested_time
            ):
                lookup = lookup.model_copy(update={"snapshot": None, "state": SnapshotState.FAILED})
        if lookup.snapshot is not None and lookup.state == SnapshotState.FRESH:
            return self._response(lookup.snapshot, latitude, longitude, stale=False)
        if lookup.snapshot is not None and lookup.state in {
            SnapshotState.STALE, SnapshotState.STALE_REFRESHING
        }:
            gate_key = self._failure_gate_key(tile)
            try:
                job = await self.queue(latitude, longitude, requested_time)
            except RefreshBlockedError as exc:
                return self._response(
                    lookup.snapshot,
                    latitude,
                    longitude,
                    stale=True,
                    refresh_blocked_until=exc.gate.blocked_until,
                )
            if wait_for_refresh:
                completed = await self.jobs.wait(job.job_id, self.wait_timeout_seconds)
                if completed.state == RefreshJobStatus.SUCCEEDED:
                    refreshed = await self.store.get_latest(key)
                    if refreshed.snapshot is not None:
                        return self._response(
                            refreshed.snapshot,
                            latitude,
                            longitude,
                            stale=False,
                            just_refreshed=True,
                        )
            current = await self.jobs.get(job.job_id)
            if current.state == RefreshJobStatus.FAILED:
                gate = await self.jobs.failure_gate(gate_key)
                return self._response(
                    lookup.snapshot,
                    latitude,
                    longitude,
                    stale=True,
                    refresh_blocked_until=(gate.blocked_until if gate else None),
                )
            return self._response(
                lookup.snapshot, latitude, longitude, stale=True, refresh_job_id=job.job_id
            )
        try:
            job = await self.queue(latitude, longitude, requested_time)
        except RefreshBlockedError as exc:
            retry_after = max(
                1,
                math.ceil(
                    (exc.gate.blocked_until - _utc(self._now())).total_seconds()
                ),
            )
            self._raise_failed(
                exc.gate.error_code,
                retry_after if exc.gate.classification.value == "retryable" else None,
            )
        if wait_for_refresh:
            completed = await self.jobs.wait(job.job_id, self.wait_timeout_seconds)
            if completed.state == RefreshJobStatus.SUCCEEDED:
                refreshed = await self.store.get_latest(key)
                if refreshed.snapshot is not None:
                    return self._response(
                        refreshed.snapshot, latitude, longitude,
                        stale=False, just_refreshed=True,
                    )
            if completed.state == RefreshJobStatus.FAILED:
                self._raise_failed(completed.error_code, completed.retry_after_seconds)
        current = await self.jobs.get(job.job_id)
        if current.state == RefreshJobStatus.FAILED:
            self._raise_failed(current.error_code, current.retry_after_seconds)
        return RefreshAcceptedResponse(
            job_id=job.job_id,
            tile=RefreshTileReference(id=tile.safe_id),
        )

    async def job_status(self, job_id: str) -> RefreshJobResponse:
        job = await self.jobs.get(job_id)
        lookup = await self.store.get_latest(job.deduplication_key)
        if lookup.snapshot is None:
            lookup = await self.store.get_latest_successful(
                source="sst",
                tile_id=job.tile_id,
                configuration_identity=self.configuration_identity,
            )
        return RefreshJobResponse(
            job_id=job.job_id,
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
        requested = _utc(self._now())
        tile = self.tile(latitude, longitude)
        key = self._store_key(tile, requested)
        lookup = await self.store.get_latest(key)
        if lookup.snapshot is not None:
            age = (requested - lookup.snapshot.metadata.stored_at).total_seconds()
            if (
                age < self.refresh_check_seconds
                or requested.date() <= lookup.snapshot.payload.provider_valid_time.date()
            ):
                return None
        try:
            return (await self.queue(latitude, longitude, requested)).job_id
        except RefreshBlockedError:
            return None
