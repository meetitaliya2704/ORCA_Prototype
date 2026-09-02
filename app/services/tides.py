from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.clients.copernicus_tides import (
    COPERNICUS_TIDE_PRODUCT_ID,
    STATIC_TIDE_VARIABLES,
    TIDE_VARIABLES,
    StaticGridAlignmentError,
    TideCell,
    TideMetadataResolver,
    TideProvider,
    TideProviderError,
    TideSourceUnavailableError,
    TideStaticCell,
)
from app.schemas.marine import (
    SSTLocation,
    SeaLevelComponents,
    SeaLevelEvent,
    SeaLevelEventsResponse,
    SeaLevelProviderWindow,
    SeaLevelRequestedWindow,
    SeaLevelResponse,
    SourceResult,
    SourceStatus,
    TideCacheStatus,
    TideEvidenceQuality,
    TideSamplingQuality,
    TideTimeClassification,
)
from app.services.cache import JsonCache
from app.services.geospatial import haversine_distance_km


TIDE_SCHEMA_VERSION = "d6-1-v1"
EVENT_ALGORITHM_VERSION = "local-extrema-quadratic-v1"
EXACT_CELL_TOLERANCE_KM = 0.001
UNKNOWN_TIME_WARNING = (
    "Authoritative cycle metadata was unavailable; analysis/forecast classification is unknown."
)


class InvalidTideTimeError(TideProviderError): pass
class TideDataUnavailableError(TideProviderError): pass
class TideForecastOutOfHorizonError(TideProviderError): pass
class TideTimeUnavailableError(TideProviderError): pass
class NoValidTideCellError(TideProviderError): pass
class InsufficientTideSeriesError(TideProviderError): pass


@dataclass(frozen=True)
class TideAvailabilitySnapshot:
    times: tuple[datetime, ...]
    queried_start: datetime
    queried_end: datetime
    retrieved_at: datetime

    @property
    def earliest(self) -> datetime | None:
        return self.times[0] if self.times else None

    @property
    def latest(self) -> datetime | None:
        return self.times[-1] if self.times else None


def normalize_longitude(value: float) -> float:
    return ((float(value) + 180.0) % 360.0) - 180.0


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _quadratic_event(
    previous: tuple[datetime, float], current: tuple[datetime, float],
    following: tuple[datetime, float], event_type: str, interpolate: bool,
) -> SeaLevelEvent:
    event = SeaLevelEvent(
        event_type=event_type, provider_sample_time=current[0],
        provider_sample_height_m=round(current[1], 6), time_is_interpolated=False,
    )
    if not interpolate:
        return event
    x0 = 0.0
    x1 = (current[0] - previous[0]).total_seconds()
    x2 = (following[0] - previous[0]).total_seconds()
    values = (x1, x2, previous[1], current[1], following[1])
    if not all(math.isfinite(item) for item in values) or not 0 < x1 < x2:
        return event
    slope_01 = (current[1] - previous[1]) / x1
    slope_12 = (following[1] - current[1]) / (x2 - x1)
    curvature = (slope_12 - slope_01) / x2
    if not math.isfinite(curvature) or abs(curvature) < 1e-18:
        return event
    if (event_type == "high" and curvature >= 0) or (event_type == "low" and curvature <= 0):
        return event
    linear = slope_01 - curvature * x1
    vertex = -linear / (2 * curvature)
    if not math.isfinite(vertex) or vertex < x0 or vertex > x2:
        return event
    height = curvature * vertex * vertex + linear * vertex + previous[1]
    if not math.isfinite(height):
        return event
    estimated = previous[0] + timedelta(seconds=vertex)
    if not previous[0] <= estimated <= following[0]:
        return event
    event.estimated_time = estimated
    event.estimated_height_m = round(height, 6)
    event.time_is_interpolated = True
    event.interpolation_method = "three_point_quadratic"
    return event


def detect_extrema(
    samples: list[tuple[datetime, float | None]], *, start: datetime,
    end: datetime, interpolate: bool, minimum_consecutive: int = 3,
) -> list[SeaLevelEvent]:
    longest = run = 0
    previous_time: datetime | None = None
    for sample_time, value in samples:
        if value is not None and math.isfinite(value):
            if previous_time is not None and abs((sample_time-previous_time).total_seconds()-3600)>60:
                run = 0
            run += 1; longest = max(longest, run); previous_time = sample_time
        else:
            run = 0; previous_time = None
    if longest < minimum_consecutive:
        raise InsufficientTideSeriesError("Insufficient consecutive tide samples")
    result: list[SeaLevelEvent] = []
    for index in range(1, len(samples) - 1):
        previous, current, following = samples[index-1], samples[index], samples[index+1]
        if any(value is None or not math.isfinite(value) for _, value in (previous, current, following)):
            continue
        if abs((current[0]-previous[0]).total_seconds()-3600)>60 or abs((following[0]-current[0]).total_seconds()-3600)>60:
            continue
        assert previous[1] is not None and current[1] is not None and following[1] is not None
        event_type = None
        if previous[1] < current[1] >= following[1]: event_type = "high"
        elif previous[1] > current[1] <= following[1]: event_type = "low"
        if event_type is None:
            continue
        event = _quadratic_event(
            (previous[0], previous[1]), (current[0], current[1]),
            (following[0], following[1]), event_type, interpolate,
        )
        event_time = event.estimated_time if event.time_is_interpolated else event.provider_sample_time
        if start <= event_time <= end:
            result.append(event)
    result.sort(key=lambda item: item.estimated_time or item.provider_sample_time)
    return result


class CopernicusTideService:
    def __init__(
        self, *, provider: TideProvider, metadata_resolver: TideMetadataResolver,
        cache: JsonCache, dataset_id: str, dataset_version: str,
        static_dataset_id: str, static_dataset_version: str,
        static_dataset_part: str = "bathy", max_radius_km: float = 10.0,
        static_alignment_tolerance_km: float = 1.0,
        time_tolerance_hours: float = 1.0, max_horizon_hours: int = 240,
        decomposition_tolerance_m: float = 0.005,
        fresh_ttl_seconds: int = 1800, stale_ttl_seconds: int = 21600,
        static_ttl_seconds: int = 604800, metadata_ttl_seconds: int = 3600,
        metadata_unavailable_ttl_seconds: int = 600, event_ttl_seconds: int = 1800,
        availability_ttl_seconds: int = 600,
        minimum_consecutive_samples: int = 3, surface_depth_m: float = 0.494140625,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.provider=provider; self.metadata_resolver=metadata_resolver; self.cache=cache
        self.dataset_id=dataset_id; self.dataset_version=dataset_version
        self.static_dataset_id=static_dataset_id; self.static_dataset_version=static_dataset_version
        self.static_dataset_part=static_dataset_part; self.max_radius_km=max_radius_km
        self.static_alignment_tolerance_km=static_alignment_tolerance_km
        self.time_tolerance_hours=time_tolerance_hours; self.max_horizon_hours=max_horizon_hours
        self.decomposition_tolerance_m=decomposition_tolerance_m
        self.fresh_ttl_seconds=fresh_ttl_seconds; self.stale_ttl_seconds=stale_ttl_seconds
        self.static_ttl_seconds=static_ttl_seconds; self.metadata_ttl_seconds=metadata_ttl_seconds
        self.metadata_unavailable_ttl_seconds=metadata_unavailable_ttl_seconds
        self.availability_ttl_seconds=availability_ttl_seconds
        self.event_ttl_seconds=event_ttl_seconds; self.minimum_consecutive_samples=minimum_consecutive_samples
        self.surface_depth_m=surface_depth_m; self._now=now; self._monotonic=monotonic
        self._locks: dict[str,asyncio.Lock]={}; self._static_locks: dict[str,asyncio.Lock]={}
        self._field_locks: dict[str,asyncio.Lock]={}
        self._static_cache: dict[str,tuple[list[TideStaticCell],float]]={}
        self._field_cache: dict[str,tuple[list[TideCell],float]]={}
        self._metadata_cache: dict[str,tuple[Any,float]]={}
        self._availability_cache: dict[str,tuple[TideAvailabilitySnapshot,float]]={}
        self._availability_locks: dict[str,asyncio.Lock]={}
        self.availability_refresh_count=0
        self.dynamic_field_refresh_count=0

    def _bounds(self, latitude: float, longitude: float) -> list[tuple[float,float,float,float]]:
        lat_delta=self.max_radius_km/111.195
        lon_delta=self.max_radius_km/max(111.195*abs(math.cos(math.radians(latitude))),1e-6)
        lo=longitude-lon_delta; hi=longitude+lon_delta
        low_lat=max(-90.0,latitude-lat_delta); high_lat=min(90.0,latitude+lat_delta)
        if lo < -180: return [(low_lat,high_lat,lo+360,180),(low_lat,high_lat,-180,hi)]
        if hi >= 180: return [(low_lat,high_lat,lo,180),(low_lat,high_lat,-180,hi-360)]
        return [(low_lat,high_lat,lo,hi)]

    async def _fetch_times(self, latitude: float, longitude: float, start: datetime, end: datetime) -> list[datetime]:
        values=[]
        for min_lat,max_lat,min_lon,max_lon in self._bounds(latitude,longitude):
            values.extend(await self.provider.available_times(
                dataset_id=self.dataset_id,dataset_version=self.dataset_version,
                minimum_latitude=min_lat,maximum_latitude=max_lat,
                minimum_longitude=min_lon,maximum_longitude=max_lon,
                start_datetime=start,end_datetime=end,surface_depth_m=self.surface_depth_m,
            ))
        return sorted(set(value.astimezone(UTC) for value in values))

    def _availability_identity(self) -> str:
        resolver_identity=f"{type(self.provider).__module__}.{type(self.provider).__qualname__}"
        return "tides:availability:"+_digest({
            "product":COPERNICUS_TIDE_PRODUCT_ID,"dataset":self.dataset_id,
            "version":self.dataset_version,"variables":list(TIDE_VARIABLES),
            "resolver":resolver_identity,"schema":TIDE_SCHEMA_VERSION,
        })

    async def _availability(
        self, *, latitude:float, longitude:float, query_start:datetime,
        query_end:datetime, required_start:datetime, required_end:datetime,
        strict_padding:bool=False,
    ) -> TideAvailabilitySnapshot:
        key=self._availability_identity()
        def covers(snapshot:TideAvailabilitySnapshot) -> bool:
            if strict_padding:
                return (
                    snapshot.queried_start<=query_start
                    and snapshot.queried_end>=query_end
                    and any(value<required_start for value in snapshot.times)
                    and any(value>required_end for value in snapshot.times)
                )
            return snapshot.queried_start<=required_start<=snapshot.queried_end and snapshot.queried_start<=required_end<=snapshot.queried_end
        cached=self._availability_cache.get(key)
        if cached and self._monotonic()<cached[1] and covers(cached[0]): return cached[0]
        lock=self._availability_locks.setdefault(key,asyncio.Lock())
        async with lock:
            cached=self._availability_cache.get(key)
            if cached and self._monotonic()<cached[1] and covers(cached[0]): return cached[0]
            times=await self._fetch_times(latitude,longitude,query_start,query_end)
            snapshot=TideAvailabilitySnapshot(tuple(times),query_start,query_end,self._now().astimezone(UTC))
            self.availability_refresh_count+=1
            self._availability_cache[key]=(snapshot,self._monotonic()+self.availability_ttl_seconds)
            return snapshot

    async def _select_time(self, latitude: float, longitude: float, requested: datetime, now: datetime) -> datetime:
        if requested > now + timedelta(hours=self.max_horizon_hours):
            raise TideForecastOutOfHorizonError("Requested time exceeds provider horizon")
        delta=timedelta(hours=self.time_tolerance_hours)
        snapshot=await self._availability(
            latitude=latitude,longitude=longitude,query_start=requested-delta,
            query_end=requested+delta,required_start=requested,required_end=requested,
        )
        times=list(snapshot.times)
        eligible=[item for item in times if item >= requested] if requested > now else [item for item in times if item <= requested]
        if not eligible: raise TideTimeUnavailableError("No provider timestamp satisfies the request")
        selected=min(eligible) if requested > now else max(eligible)
        if abs((selected-requested).total_seconds()) > delta.total_seconds():
            raise TideTimeUnavailableError("Selected provider timestamp exceeds tolerance")
        return selected

    async def _static(self, bounds: list[tuple[float,float,float,float]]) -> list[TideStaticCell]:
        identity="tides:static:"+_digest([self.static_dataset_id,self.static_dataset_version,self.static_dataset_part,list(STATIC_TIDE_VARIABLES),bounds,"shallowest",self.static_alignment_tolerance_km,TIDE_SCHEMA_VERSION])
        cached=self._static_cache.get(identity)
        if cached and self._monotonic()<cached[1]: return cached[0]
        lock=self._static_locks.setdefault(identity,asyncio.Lock())
        async with lock:
            cached=self._static_cache.get(identity)
            if cached and self._monotonic()<cached[1]: return cached[0]
            cells=[]
            for min_lat,max_lat,min_lon,max_lon in bounds:
                cells.extend(await self.provider.fetch_static(
                    dataset_id=self.static_dataset_id,dataset_version=self.static_dataset_version,
                    dataset_part=self.static_dataset_part,minimum_latitude=min_lat,
                    maximum_latitude=max_lat,minimum_longitude=min_lon,maximum_longitude=max_lon,
                    static_surface_depth_m=0.49402499198913574,
                ))
            if not cells: raise TideDataUnavailableError("Static mask contained no cells")
            self._static_cache[identity]=(cells,self._monotonic()+self.static_ttl_seconds)
            return cells

    async def _field(self, bounds: list[tuple[float,float,float,float]], start: datetime, end: datetime) -> list[TideCell]:
        identity="tides:field:"+_digest([COPERNICUS_TIDE_PRODUCT_ID,self.dataset_id,self.dataset_version,list(TIDE_VARIABLES),start.isoformat(),end.isoformat(),bounds,self.surface_depth_m,TIDE_SCHEMA_VERSION])
        cached=self._field_cache.get(identity)
        if cached and self._monotonic()<cached[1]: return cached[0]
        lock=self._field_locks.setdefault(identity,asyncio.Lock())
        async with lock:
            cached=self._field_cache.get(identity)
            if cached and self._monotonic()<cached[1]: return cached[0]
            cells=[]
            for min_lat,max_lat,min_lon,max_lon in bounds:
                cells.extend(await self.provider.fetch_dynamic(
                    dataset_id=self.dataset_id,dataset_version=self.dataset_version,
                    minimum_latitude=min_lat,maximum_latitude=max_lat,
                    minimum_longitude=min_lon,maximum_longitude=max_lon,
                    start_datetime=start,end_datetime=end,surface_depth_m=self.surface_depth_m,
                ))
            if not cells: raise TideDataUnavailableError("Provider returned no sea-level fields")
            self.dynamic_field_refresh_count+=1
            self._field_cache[identity]=(cells,self._monotonic()+self.fresh_ttl_seconds)
            return cells

    def _align_static(self, cell: TideCell, static: list[TideStaticCell]) -> TideStaticCell:
        ranked=sorted((haversine_distance_km(cell.latitude,normalize_longitude(cell.longitude),item.latitude,normalize_longitude(item.longitude)),item.latitude,normalize_longitude(item.longitude),item) for item in static)
        if not ranked or ranked[0][0] > self.static_alignment_tolerance_km:
            raise StaticGridAlignmentError("Dynamic and static grids cannot be aligned")
        if len(ranked)>1 and math.isclose(ranked[0][0],ranked[1][0],abs_tol=1e-12) and ranked[0][1:3]==ranked[1][1:3]:
            raise StaticGridAlignmentError("Static grid alignment is ambiguous")
        return ranked[0][3]

    @staticmethod
    def _valid(cell: TideCell) -> bool:
        return all(value is not None and math.isfinite(value) for value in (
            cell.total_sea_level,cell.ocean_tide,cell.tide_loading,cell.invert_barometer,
            cell.sea_surface_height,cell.global_mean_steric_variation,
            cell.global_mean_mass_volume_variation,
        ))

    def _select_cell(self, cells: list[TideCell], static: list[TideStaticCell], latitude: float, longitude: float, valid_time: datetime) -> tuple[TideCell,TideStaticCell,float,TideSamplingQuality]:
        at_time=[cell for cell in cells if cell.valid_time==valid_time]
        if not at_time: raise NoValidTideCellError("No dynamic cells exist at selected time")
        direct=min(at_time,key=lambda cell:(haversine_distance_km(latitude,longitude,cell.latitude,normalize_longitude(cell.longitude)),cell.latitude,normalize_longitude(cell.longitude)))
        candidates=[]
        for cell in at_time:
            distance=haversine_distance_km(latitude,longitude,cell.latitude,normalize_longitude(cell.longitude))
            if distance>self.max_radius_km or not self._valid(cell): continue
            aligned=self._align_static(cell,static)
            if aligned.mask != 1: continue
            candidates.append((distance,cell.latitude,normalize_longitude(cell.longitude),cell,aligned))
        if not candidates: raise NoValidTideCellError("No valid sea-level water cell exists within the radius")
        chosen=min(candidates,key=lambda item:item[:3]); distance,_,_,cell,aligned=chosen
        direct_valid=False
        try:
            direct_static=self._align_static(direct,static)
            direct_valid=self._valid(direct) and direct_static.mask==1
        except StaticGridAlignmentError:
            direct_valid=False
        if distance<=EXACT_CELL_TOLERANCE_KM: quality=TideSamplingQuality.EXACT_GRID_CELL
        elif cell is direct and direct_valid: quality=TideSamplingQuality.NEAREST_GRID_CELL
        else: quality=TideSamplingQuality.NEAREST_VALID_WATER_CELL
        return cell,aligned,distance,quality

    async def _metadata(self, selected: datetime) -> tuple[TideTimeClassification,datetime|None,float|None,list[str]]:
        key=f"tides:cycle:{self.dataset_id}:{self.dataset_version}:{selected.isoformat()}"
        cached=self._metadata_cache.get(key)
        if cached and self._monotonic()<cached[1]: metadata=cached[0]
        else:
            try: metadata=await self.metadata_resolver.resolve(dataset_id=self.dataset_id,dataset_version=self.dataset_version,selected_time=selected)
            except TideProviderError: metadata=None
            ttl=self.metadata_ttl_seconds if metadata else self.metadata_unavailable_ttl_seconds
            self._metadata_cache[key]=(metadata,self._monotonic()+ttl)
        if metadata is None or metadata.classification not in {"analysis","forecast"}:
            return TideTimeClassification.UNKNOWN,None,None,[UNKNOWN_TIME_WARNING]
        classification=TideTimeClassification(metadata.classification)
        if classification==TideTimeClassification.FORECAST and (metadata.reference_time is None or metadata.lead_hours is None):
            return TideTimeClassification.UNKNOWN,None,None,[UNKNOWN_TIME_WARNING]
        return classification,metadata.reference_time,metadata.lead_hours,[]

    def _point_identity(self, latitude: float, longitude: float, selected: datetime, reference: datetime|None) -> str:
        return _digest({"provider":"Copernicus Marine Service","product":COPERNICUS_TIDE_PRODUCT_ID,"dataset":self.dataset_id,"version":self.dataset_version,"static":self.static_dataset_id,"static_version":self.static_dataset_version,"static_part":self.static_dataset_part,"variables":list(TIDE_VARIABLES),"lat":f"{latitude:.6f}","lon":f"{longitude:.6f}","selected":selected.isoformat(),"reference":reference.isoformat() if reference else None,"radius":self.max_radius_km,"alignment":self.static_alignment_tolerance_km,"time_tolerance":self.time_tolerance_hours,"horizon":self.max_horizon_hours,"decomposition_tolerance":self.decomposition_tolerance_m,"depth":self.surface_depth_m,"schema":TIDE_SCHEMA_VERSION})

    def _build_point(self, cell:TideCell,static:TideStaticCell,distance:float,quality:TideSamplingQuality,latitude:float,longitude:float,classification:TideTimeClassification,reference:datetime|None,lead:float|None,cache_status:TideCacheStatus,warnings:list[str]) -> SeaLevelResponse:
        assert all(value is not None for value in (cell.total_sea_level,cell.ocean_tide,cell.tide_loading,cell.invert_barometer,cell.sea_surface_height,cell.global_mean_steric_variation,cell.global_mean_mass_volume_variation))
        reconstructed=cell.ocean_tide+cell.invert_barometer+cell.sea_surface_height+cell.global_mean_steric_variation+cell.global_mean_mass_volume_variation  # type: ignore[operator]
        residual=cell.total_sea_level-reconstructed  # type: ignore[operator]
        decomposition=TideEvidenceQuality.NORMAL
        if abs(residual)>self.decomposition_tolerance_m:
            decomposition=TideEvidenceQuality.DEGRADED
            warnings.append("Provider total differs from the documented component reconstruction beyond ORCA's tolerance.")
        spatial=TideEvidenceQuality.NORMAL
        if quality==TideSamplingQuality.NEAREST_VALID_WATER_CELL:
            spatial=TideEvidenceQuality.DEGRADED
            warnings.append("The nearest provider cell was land or invalid; the nearest valid water cell was used.")
        return SeaLevelResponse(
            dataset_id=self.dataset_id,dataset_version=self.dataset_version,
            requested_location=SSTLocation(latitude=latitude,longitude=longitude),
            sampled_location=SSTLocation(latitude=cell.latitude,longitude=normalize_longitude(cell.longitude)),
            distance_km=round(distance,3),bathymetry_m=round(static.bathymetry_m,3) if static.bathymetry_m is not None else None,
            provider_surface_level_coordinate_m=round(cell.depth_m,6),valid_time=cell.valid_time,
            time_classification=classification,forecast_reference_time=reference,forecast_lead_hours=lead,
            astronomical_tide_elevation_m=round(cell.ocean_tide,6),total_modelled_sea_level_m=round(cell.total_sea_level,6),
            components=SeaLevelComponents(non_tidal_dynamic_sea_level_m=round(cell.sea_surface_height,6),inverse_barometer_m=round(cell.invert_barometer,6),global_mean_steric_variation_m=round(cell.global_mean_steric_variation,6),global_mean_mass_variation_m=round(cell.global_mean_mass_volume_variation,6),tide_loading_m=round(cell.tide_loading,6)),
            reconstructed_total_sea_level_m=round(reconstructed,6),decomposition_residual_m=round(residual,6),
            sampling_quality=quality,model_evidence_quality=TideEvidenceQuality.NORMAL,
            spatial_representativeness=spatial,decomposition_evidence_quality=decomposition,
            cache_status=cache_status,retrieved_at=self._now().astimezone(UTC),warnings=list(dict.fromkeys(warnings)),
        )

    async def get_sea_level(self, *, latitude:float, longitude:float, at:datetime|None=None) -> SeaLevelResponse:
        now=self._now().astimezone(UTC); requested=now if at is None else at
        if requested.tzinfo is None or requested.utcoffset() is None: raise InvalidTideTimeError("Sea-level time must be timezone-aware")
        requested=requested.astimezone(UTC); longitude=normalize_longitude(longitude)
        selected=await self._select_time(latitude,longitude,requested,now)
        classification,reference,lead,warnings=await self._metadata(selected)
        identity=self._point_identity(latitude,longitude,selected,reference)
        fresh_key=f"tides:point:{identity}"; stale_key=f"tides:stale:{identity}"
        cached=await self.cache.get(fresh_key)
        if cached is not None:
            response=SeaLevelResponse.model_validate(cached); response.cache_status=TideCacheStatus.FRESH; return response
        lock=self._locks.setdefault(identity,asyncio.Lock())
        async with lock:
            cached=await self.cache.get(fresh_key)
            if cached is not None:
                response=SeaLevelResponse.model_validate(cached); response.cache_status=TideCacheStatus.FRESH; return response
            bounds=self._bounds(latitude,longitude)
            try:
                static,cells=await asyncio.gather(self._static(bounds),self._field(bounds,selected,selected))
                cell,static_cell,distance,quality=self._select_cell(cells,static,latitude,longitude,selected)
                response=self._build_point(cell,static_cell,distance,quality,latitude,longitude,classification,reference,lead,TideCacheStatus.REFRESHED,warnings)
                payload=response.model_dump(mode="json")
                await self.cache.set(fresh_key,payload,self.fresh_ttl_seconds); await self.cache.set(stale_key,payload,self.stale_ttl_seconds)
                return response
            except TideSourceUnavailableError:
                stale=await self.cache.get(stale_key)
                if stale is not None:
                    response=SeaLevelResponse.model_validate(stale); response.cache_status=TideCacheStatus.STALE
                    response.warnings.append("Copernicus sea-level refresh failed; exactly matching cached data was returned.")
                    return response
                raise

    def _event_identity(self, latitude:float,longitude:float,start:datetime,end:datetime,hours:int,interpolate:bool) -> str:
        return _digest({"lat":f"{latitude:.6f}","lon":f"{longitude:.6f}","start":start.isoformat(),"end":end.isoformat(),"hours":hours,"dataset":self.dataset_id,"version":self.dataset_version,"variables":list(TIDE_VARIABLES),"radius":self.max_radius_km,"static":self.static_dataset_id,"static_version":self.static_dataset_version,"alignment":self.static_alignment_tolerance_km,"minimum_samples":self.minimum_consecutive_samples,"event_algorithm":EVENT_ALGORITHM_VERSION,"interpolate":interpolate,"uncertainty_minutes":60,"schema":TIDE_SCHEMA_VERSION})

    async def get_events(self, *, latitude:float,longitude:float,start:datetime|None=None,hours:int=48,interpolate:bool=True) -> SeaLevelEventsResponse:
        now=self._now().astimezone(UTC); requested=now if start is None else start
        if requested.tzinfo is None or requested.utcoffset() is None: raise InvalidTideTimeError("Event start must be timezone-aware")
        if hours<24 or hours>72: raise InvalidTideTimeError("Event duration must be between 24 and 72 hours")
        requested=requested.astimezone(UTC); end=requested+timedelta(hours=hours)
        if end>now+timedelta(hours=self.max_horizon_hours): raise TideForecastOutOfHorizonError("Event window exceeds provider horizon")
        longitude=normalize_longitude(longitude); identity=self._event_identity(latitude,longitude,requested,end,hours,interpolate)
        key=f"tides:events:{identity}"; cached=await self.cache.get(key)
        if cached is not None:
            response=SeaLevelEventsResponse.model_validate(cached); response.cache_status=TideCacheStatus.FRESH; return response
        lock=self._locks.setdefault("events:"+identity,asyncio.Lock())
        async with lock:
            cached=await self.cache.get(key)
            if cached is not None:
                response=SeaLevelEventsResponse.model_validate(cached); response.cache_status=TideCacheStatus.FRESH; return response
            bounds=self._bounds(latitude,longitude); tolerance=timedelta(hours=self.time_tolerance_hours)
            snapshot=await self._availability(
                latitude=latitude,longitude=longitude,query_start=requested-tolerance,
                query_end=end+tolerance,required_start=requested,required_end=end,
                strict_padding=True,
            )
            left=[value for value in snapshot.times if value<requested]
            inside=[value for value in snapshot.times if requested<=value<=end]
            right=[value for value in snapshot.times if value>end]
            if not left or not right:
                raise InsufficientTideSeriesError("Both provider padding neighbours are required")
            provider_start=max(left); provider_end=min(right)
            provider_times=[provider_start,*inside,provider_end]
            if not (provider_start<requested and provider_end>end):
                raise InsufficientTideSeriesError("Provider padding does not surround the requested interval")
            static,cells=await asyncio.gather(self._static(bounds),self._field(bounds,provider_start,provider_end))
            returned_times={cell.valid_time for cell in cells}
            if any(value not in returned_times for value in provider_times):
                raise InsufficientTideSeriesError("Provider response omitted required timestamps")
            times=provider_times
            if len(times)<self.minimum_consecutive_samples: raise InsufficientTideSeriesError("Insufficient provider timestamps")
            # Select one spatial cell using the first time with a complete pair, then keep that coordinate for the series.
            selected_cell=selected_static=None; distance=0.0; quality=TideSamplingQuality.NEAREST_GRID_CELL
            for value in times:
                try:
                    selected_cell,selected_static,distance,quality=self._select_cell(cells,static,latitude,longitude,value); break
                except NoValidTideCellError: continue
            if selected_cell is None or selected_static is None: raise NoValidTideCellError("No valid series location exists")
            coordinate_cells={cell.valid_time:cell for cell in cells if math.isclose(cell.latitude,selected_cell.latitude,abs_tol=1e-9) and math.isclose(normalize_longitude(cell.longitude),normalize_longitude(selected_cell.longitude),abs_tol=1e-9)}
            tide_samples=[(value,coordinate_cells[value].ocean_tide if value in coordinate_cells else None) for value in times]
            total_samples=[(value,coordinate_cells[value].total_sea_level if value in coordinate_cells else None) for value in times]
            tide_events=detect_extrema(tide_samples,start=requested,end=end,interpolate=interpolate,minimum_consecutive=self.minimum_consecutive_samples)
            total_extrema=detect_extrema(total_samples,start=requested,end=end,interpolate=interpolate,minimum_consecutive=self.minimum_consecutive_samples)
            warnings=[]
            spatial=TideEvidenceQuality.DEGRADED if quality==TideSamplingQuality.NEAREST_VALID_WATER_CELL else TideEvidenceQuality.NORMAL
            if spatial==TideEvidenceQuality.DEGRADED: warnings.append("The nearest provider cell was land or invalid; events use a nearby valid water cell.")
            warnings.append("Interpolated event times remain uncertain by at least the provider's 60-minute cadence.")
            response=SeaLevelEventsResponse(
                dataset_id=self.dataset_id,dataset_version=self.dataset_version,
                requested_location=SSTLocation(latitude=latitude,longitude=longitude),sampled_location=SSTLocation(latitude=selected_cell.latitude,longitude=normalize_longitude(selected_cell.longitude)),distance_km=round(distance,3),bathymetry_m=round(selected_static.bathymetry_m,3) if selected_static.bathymetry_m is not None else None,provider_surface_level_coordinate_m=round(selected_cell.depth_m,6),requested_window=SeaLevelRequestedWindow(start=requested,end=end,duration_hours=hours),provider_window=SeaLevelProviderWindow(start=provider_start,end=provider_end,sample_count=len(times)),astronomical_tide_events=tide_events,total_sea_level_extrema=total_extrema,sampling_quality=quality,spatial_representativeness=spatial,cache_status=TideCacheStatus.REFRESHED,retrieved_at=self._now().astimezone(UTC),warnings=warnings,
            )
            await self.cache.set(key,response.model_dump(mode="json"),self.event_ttl_seconds)
            return response


class CopernicusTideMarineSource:
    name="sea_level"
    def __init__(self, service:CopernicusTideService): self.service=service
    async def fetch(self, client:httpx.AsyncClient,latitude:float,longitude:float,at:datetime|None=None) -> SourceResult:
        del client
        try:
            response=await self.service.get_sea_level(latitude=latitude,longitude=longitude,at=at)
            status={TideCacheStatus.FRESH:SourceStatus.CACHED,TideCacheStatus.REFRESHED:SourceStatus.FRESH,TideCacheStatus.STALE:SourceStatus.STALE}[response.cache_status]
            return SourceResult(source=self.name,status=status,data=response.model_dump(mode="json"),fetched_at=response.retrieved_at,cached=response.cache_status!=TideCacheStatus.REFRESHED)
        except Exception as exc:
            return SourceResult(source=self.name,status=SourceStatus.UNAVAILABLE,error=type(exc).__name__)
