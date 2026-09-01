import asyncio
import hashlib
import json
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.clients.copernicus_currents import (
    COPERNICUS_CURRENT_PRODUCT_ID,
    CURRENT_VARIABLES,
    CurrentAuthenticationError,
    CurrentDependencyMissingError,
    CurrentMetadataResolver,
    CurrentProvider,
    CurrentProviderCell,
    CurrentProviderError,
    CurrentSourceNotConfiguredError,
    CurrentSourceUnavailableError,
    InvalidCurrentResponseError,
)
from app.schemas.marine import (
    CurrentCacheStatus,
    CurrentComponents,
    CurrentEvidenceQuality,
    CurrentResidual,
    CurrentResponse,
    CurrentSamplingQuality,
    CurrentTimeClassification,
    CurrentTotalVector,
    CurrentVector,
    SSTLocation,
    SourceResult,
    SourceStatus,
)
from app.services.cache import JsonCache
from app.services.geospatial import haversine_distance_km


CURRENT_SCHEMA_VERSION = "d5-1-v1"
EXACT_CELL_TOLERANCE_KM = 0.001
UNKNOWN_TIME_WARNING = (
    "Authoritative cycle metadata was unavailable; analysis/forecast classification is unknown."
)


class InvalidCurrentTimeError(CurrentProviderError): pass
class CurrentDataUnavailableError(CurrentProviderError): pass
class NoValidCurrentCellError(CurrentProviderError): pass
class CurrentForecastOutOfHorizonError(CurrentProviderError): pass
class CurrentTimeUnavailableError(CurrentProviderError): pass


def normalize_longitude(value: float) -> float:
    normalized = ((float(value) + 180.0) % 360.0) - 180.0
    return -180.0 if normalized == 180.0 else normalized


def current_speed_direction(u: float, v: float, calm_threshold: float) -> tuple[float, float | None, str]:
    speed = math.hypot(u, v)
    if speed <= calm_threshold:
        return speed, None, "CALM"
    direction = (math.degrees(math.atan2(u, v)) + 360.0) % 360.0
    labels = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return speed, direction, labels[int((direction + 22.5) // 45) % 8]


class CopernicusCurrentService:
    def __init__(
        self, *, provider: CurrentProvider, metadata_resolver: CurrentMetadataResolver,
        cache: JsonCache, dataset_id: str, dataset_version: str,
        static_dataset_id: str, static_dataset_version: str,
        max_radius_km: float, calm_threshold_mps: float,
        time_tolerance_hours: float, component_tolerance_mps: float,
        fresh_ttl_seconds: int, stale_ttl_seconds: int,
        max_horizon_hours: int = 240, surface_depth_m: float = 0.49402499198913574,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.provider=provider; self.metadata_resolver=metadata_resolver; self.cache=cache
        self.dataset_id=dataset_id; self.dataset_version=dataset_version
        self.static_dataset_id=static_dataset_id; self.static_dataset_version=static_dataset_version
        self.max_radius_km=max_radius_km; self.calm_threshold_mps=calm_threshold_mps
        self.time_tolerance_hours=time_tolerance_hours; self.component_tolerance_mps=component_tolerance_mps
        self.fresh_ttl_seconds=fresh_ttl_seconds; self.stale_ttl_seconds=stale_ttl_seconds
        self.max_horizon_hours=max_horizon_hours; self.surface_depth_m=surface_depth_m
        self._now=now; self._monotonic=monotonic; self._locks: dict[str,asyncio.Lock]={}
        self._field_cache: dict[str,tuple[list[CurrentProviderCell],float]]={}
        self._selection_cache: dict[str, tuple[datetime, float]] = {}
        self._metadata_cache: dict[str, tuple[datetime | None, float]] = {}

    def _bounds(self, latitude: float, longitude: float) -> list[tuple[float,float,float,float]]:
        lat_delta=self.max_radius_km/111.195
        lon_delta=self.max_radius_km/max(111.195*math.cos(math.radians(latitude)),1e-6)
        lo=longitude-lon_delta; hi=longitude+lon_delta; min_lat=max(-90.0,latitude-lat_delta); max_lat=min(90.0,latitude+lat_delta)
        if lo < -180: return [(min_lat,max_lat,lo+360,180),(min_lat,max_lat,-180,hi)]
        if hi >= 180: return [(min_lat,max_lat,lo,180),(min_lat,max_lat,-180,hi-360)]
        return [(min_lat,max_lat,lo,hi)]

    def _identity(self, latitude: float, longitude: float, selected: datetime, reference: datetime | None) -> str:
        payload={
            "provider":"Copernicus Marine Service","product":COPERNICUS_CURRENT_PRODUCT_ID,
            "dataset":self.dataset_id,"version":self.dataset_version,
            "static_dataset":self.static_dataset_id,"static_version":self.static_dataset_version,
            "variables":list(CURRENT_VARIABLES),"selected_valid_time":selected.isoformat(),
            "latitude":f"{latitude:.6f}","longitude":f"{longitude:.6f}",
            "surface_depth":self.surface_depth_m,"depth_policy":"fixed_surface_level",
            "radius":self.max_radius_km,"exact_tolerance":EXACT_CELL_TOLERANCE_KM,
            "calm_threshold":self.calm_threshold_mps,"time_tolerance":self.time_tolerance_hours,
            "horizon_hours":self.max_horizon_hours,"component_tolerance":self.component_tolerance_mps,
            "reference_time":reference.isoformat() if reference else None,"schema":CURRENT_SCHEMA_VERSION,
        }
        canonical=json.dumps(payload,sort_keys=True,separators=(",",":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def _available_times(self, latitude: float, longitude: float, at: datetime) -> list[datetime]:
        values=[]; delta=timedelta(hours=self.time_tolerance_hours)
        for min_lat,max_lat,min_lon,max_lon in self._bounds(latitude,longitude):
            values.extend(await self.provider.available_times(
                dataset_id=self.dataset_id,dataset_version=self.dataset_version,
                minimum_latitude=min_lat,maximum_latitude=max_lat,
                minimum_longitude=min_lon,maximum_longitude=max_lon,
                start_datetime=at-delta,end_datetime=at+delta,surface_depth_m=self.surface_depth_m,
            ))
        return sorted(set(value.astimezone(UTC) for value in values))

    async def _select_time(self, latitude: float, longitude: float, at: datetime, now: datetime) -> datetime:
        if at > now + timedelta(hours=self.max_horizon_hours):
            raise CurrentForecastOutOfHorizonError("Requested current time exceeds the configured horizon")
        selection_key = f"{latitude:.6f}:{longitude:.6f}:{at.isoformat()}:{at > now}"
        cached = self._selection_cache.get(selection_key)
        if cached is not None and self._monotonic() < cached[1]:
            return cached[0]
        times=await self._available_times(latitude,longitude,at)
        if not times: raise CurrentTimeUnavailableError("No provider time is available")
        eligible=[value for value in times if value >= at] if at > now else [value for value in times if value <= at]
        if not eligible: raise CurrentTimeUnavailableError("No provider time satisfies the selection policy")
        selected=min(eligible) if at > now else max(eligible)
        if abs((selected-at).total_seconds()) > self.time_tolerance_hours*3600:
            raise CurrentTimeUnavailableError("Provider time exceeds the configured tolerance")
        self._selection_cache[selection_key] = (
            selected,
            self._monotonic() + self.stale_ttl_seconds,
        )
        return selected

    async def _field(self, selected: datetime, latitude: float, longitude: float) -> list[CurrentProviderCell]:
        bounds=self._bounds(latitude,longitude)
        field_key=json.dumps([
            self.dataset_id,self.dataset_version,self.static_dataset_id,
            self.static_dataset_version,list(CURRENT_VARIABLES),
            selected.isoformat(),self.surface_depth_m,bounds,
        ],separators=(",",":"))
        cached=self._field_cache.get(field_key)
        if cached and self._monotonic()<cached[1]: return cached[0]
        cells=[]
        for min_lat,max_lat,min_lon,max_lon in bounds:
            cells.extend(await self.provider.fetch_cells(
                dataset_id=self.dataset_id,dataset_version=self.dataset_version,
                static_dataset_id=self.static_dataset_id,static_dataset_version=self.static_dataset_version,
                minimum_latitude=min_lat,maximum_latitude=max_lat,
                minimum_longitude=min_lon,maximum_longitude=max_lon,
                selected_time=selected,surface_depth_m=self.surface_depth_m,
            ))
        self._field_cache[field_key]=(cells,self._monotonic()+self.fresh_ttl_seconds)
        return cells

    def _select_cell(self, cells: list[CurrentProviderCell], latitude: float, longitude: float, selected_time: datetime) -> tuple[CurrentProviderCell,float,CurrentSamplingQuality]:
        ranked=[]; all_ranked=[]
        for cell in cells:
            distance=haversine_distance_km(latitude,longitude,cell.latitude,normalize_longitude(cell.longitude))
            item=(distance,cell.latitude,normalize_longitude(cell.longitude),cell)
            all_ranked.append(item)
            if cell.valid_time == selected_time and cell.sea_mask==1 and cell.utotal is not None and cell.vtotal is not None and all(math.isfinite(v) for v in (cell.utotal,cell.vtotal)) and distance<=self.max_radius_km:
                ranked.append(item)
        if not ranked: raise NoValidCurrentCellError("No valid current cell exists within the radius")
        selected=min(ranked,key=lambda item:item[:3]); direct=min(all_ranked,key=lambda item:item[:3])
        if selected[0] <= EXACT_CELL_TOLERANCE_KM: quality=CurrentSamplingQuality.EXACT_GRID_CELL
        elif direct[3] is selected[3]: quality=CurrentSamplingQuality.NEAREST_GRID_CELL
        else: quality=CurrentSamplingQuality.NEAREST_VALID_WATER_CELL
        return selected[3],selected[0],quality

    def _build(self, cell: CurrentProviderCell, distance: float, quality: CurrentSamplingQuality, latitude: float, longitude: float, selected: datetime, reference: datetime | None, cache_status: CurrentCacheStatus, extra_warnings: list[str]) -> CurrentResponse:
        assert cell.utotal is not None and cell.vtotal is not None
        speed,direction,compass=current_speed_direction(cell.utotal,cell.vtotal,self.calm_threshold_mps)
        groups=((cell.uo,cell.vo),(cell.utide,cell.vtide),(cell.vsdx,cell.vsdy))
        complete=all(value is not None and math.isfinite(value) for pair in groups for value in pair)
        warnings=list(extra_warnings); residual_e=residual_n=None; evidence=CurrentEvidenceQuality.NORMAL
        if complete:
            residual_e=cell.utotal-(cell.uo+cell.utide+cell.vsdx)  # type: ignore[operator]
            residual_n=cell.vtotal-(cell.vo+cell.vtide+cell.vsdy)  # type: ignore[operator]
            if max(abs(residual_e),abs(residual_n))>self.component_tolerance_mps:
                evidence=CurrentEvidenceQuality.DEGRADED
                warnings.append("Provider total differs from the available component sum beyond ORCA's consistency tolerance.")
        else:
            evidence=CurrentEvidenceQuality.DEGRADED
            warnings.append("Provider total is valid, but one or more constituent current vectors are unavailable.")
        if quality==CurrentSamplingQuality.NEAREST_VALID_WATER_CELL:
            warnings.append("The nearest provider grid cell was land or invalid; the nearest valid water cell was used.")
        classification=CurrentTimeClassification.UNKNOWN; lead=None
        if reference is None:
            warnings.append(UNKNOWN_TIME_WARNING)
        elif selected>=reference:
            classification=CurrentTimeClassification.FORECAST; lead=(selected-reference).total_seconds()/3600
        elif selected<=reference-timedelta(hours=24):
            classification=CurrentTimeClassification.ANALYSIS
        else:
            reference=None; warnings.append("The resolved cycle does not authoritatively classify this valid time as analysis or forecast.")
        return CurrentResponse(
            dataset_id=self.dataset_id,dataset_version=self.dataset_version,
            requested_location=SSTLocation(latitude=latitude,longitude=longitude),
            sampled_location=SSTLocation(latitude=cell.latitude,longitude=normalize_longitude(cell.longitude)),
            distance_km=round(distance,3),sampled_depth_m=round(cell.depth_m,6),
            total_current=CurrentTotalVector(eastward_mps=round(cell.utotal,6),northward_mps=round(cell.vtotal,6),speed_mps=round(speed,6),direction_toward_deg=round(direction,3) if direction is not None else None,direction_toward_compass=compass),
            components=CurrentComponents(
                general_circulation=CurrentVector(eastward_mps=cell.uo,northward_mps=cell.vo),
                tide=CurrentVector(eastward_mps=cell.utide,northward_mps=cell.vtide),
                stokes_drift=CurrentVector(eastward_mps=cell.vsdx,northward_mps=cell.vsdy),
            ),decomposition_complete=complete,
            component_residual_mps=CurrentResidual(eastward=residual_e,northward=residual_n),
            time_classification=classification,valid_time=selected,
            forecast_reference_time=reference,forecast_lead_hours=lead,
            analysis_or_retrieval_time=self._now().astimezone(UTC),sampling_quality=quality,
            evidence_quality=evidence,cache_status=cache_status,warnings=list(dict.fromkeys(warnings)),
        )

    async def get_current(self, *, latitude: float, longitude: float, at: datetime | None = None) -> CurrentResponse:
        now=self._now().astimezone(UTC); longitude=normalize_longitude(longitude)
        requested=now if at is None else at
        if requested.tzinfo is None or requested.utcoffset() is None: raise InvalidCurrentTimeError("Current time must be timezone-aware")
        requested=requested.astimezone(UTC)
        selected=await self._select_time(latitude,longitude,requested,now)
        warnings=[]; reference=None
        metadata_key = f"{self.dataset_id}:{self.dataset_version}:{selected.isoformat()}"
        metadata_cached = self._metadata_cache.get(metadata_key)
        if metadata_cached is not None and self._monotonic() < metadata_cached[1]:
            reference = metadata_cached[0]
        else:
            try:
                metadata=await self.metadata_resolver.resolve(dataset_id=self.dataset_id,dataset_version=self.dataset_version,selected_time=selected)
                reference=metadata.reference_time.astimezone(UTC) if metadata else None
            except CurrentProviderError:
                warnings.append(UNKNOWN_TIME_WARNING)
            self._metadata_cache[metadata_key] = (
                reference,
                self._monotonic() + self.stale_ttl_seconds,
            )
        digest=self._identity(latitude,longitude,selected,reference); fresh_key=f"currents:point:fresh:{digest}"; stale_key=f"currents:point:last_success:{digest}"
        cached=await self.cache.get(fresh_key)
        if cached is not None:
            response=CurrentResponse.model_validate(cached); response.cache_status=CurrentCacheStatus.FRESH; return response
        lock=self._locks.setdefault(digest,asyncio.Lock())
        async with lock:
            cached=await self.cache.get(fresh_key)
            if cached is not None:
                response=CurrentResponse.model_validate(cached); response.cache_status=CurrentCacheStatus.FRESH; return response
            try:
                cells=await self._field(selected,latitude,longitude)
                cell,distance,quality=self._select_cell(cells,latitude,longitude,selected)
                response=self._build(cell,distance,quality,latitude,longitude,selected,reference,CurrentCacheStatus.REFRESHED,warnings)
                payload=response.model_dump(mode="json")
                await self.cache.set(fresh_key,payload,self.fresh_ttl_seconds); await self.cache.set(stale_key,payload,self.stale_ttl_seconds)
                return response
            except CurrentSourceUnavailableError as exc:
                stale=await self.cache.get(stale_key)
                if stale is not None:
                    response=CurrentResponse.model_validate(stale); response.cache_status=CurrentCacheStatus.STALE
                    response.warnings.append("Copernicus current refresh failed; matching cached data was returned.")
                    return response
                raise exc


class CopernicusCurrentMarineSource:
    name="currents"
    def __init__(self, service: CopernicusCurrentService): self.service=service
    async def fetch(self, client: httpx.AsyncClient, latitude: float, longitude: float, at: datetime | None = None) -> SourceResult:
        del client
        try:
            response=await self.service.get_current(latitude=latitude,longitude=longitude,at=at)
            status={CurrentCacheStatus.FRESH:SourceStatus.CACHED,CurrentCacheStatus.REFRESHED:SourceStatus.FRESH,CurrentCacheStatus.STALE:SourceStatus.STALE}[response.cache_status]
            return SourceResult(source=self.name,status=status,data=response.model_dump(mode="json"),fetched_at=response.analysis_or_retrieval_time,cached=response.cache_status!=CurrentCacheStatus.REFRESHED)
        except Exception as exc:
            return SourceResult(source=self.name,status=SourceStatus.UNAVAILABLE,error=type(exc).__name__)
