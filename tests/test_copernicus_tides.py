import asyncio
import json
import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clients.copernicus_tides import (
    InvalidTideResponseError,
    StaticGridAlignmentError,
    TideCell,
    TideSourceUnavailableError,
    TideStaticCell,
    TideTimeMetadata,
    decode_tide_value,
    select_surface_coordinate,
    validate_tide_metadata,
)
from app.main import app
from app.services.cache import MemoryJsonCache
from app.services.tides import (
    CopernicusTideService,
    InsufficientTideSeriesError,
    NoValidTideCellError,
    TideForecastOutOfHorizonError,
    detect_extrema,
    normalize_longitude,
)


NOW=datetime(2026,9,1,12,tzinfo=UTC)


def tide_cell(**changes):
    values=dict(latitude=18.0,longitude=70.5,depth_m=.494140625,valid_time=NOW,
        total_sea_level=.55,ocean_tide=.2,tide_loading=.04,invert_barometer=.05,
        sea_surface_height=.25,global_mean_steric_variation=.03,
        global_mean_mass_volume_variation=.02)
    values.update(changes); return TideCell(**values)


def static_cell(**changes):
    values=dict(latitude=18.0001,longitude=70.5001,mask=1,bathymetry_m=1452.251,mask_depth_m=.494)
    values.update(changes); return TideStaticCell(**values)


class FakeProvider:
    def __init__(self,cells=None,static=None,times=None,error=None):
        self.cells=cells or [tide_cell()]; self.static=static or [static_cell()]
        self.times=times or [NOW]; self.error=error
        self.time_calls=[]; self.dynamic_calls=[]; self.static_calls=[]
    async def available_times(self,**kwargs):
        self.time_calls.append(kwargs)
        if self.error: raise self.error
        return [item for item in self.times if kwargs["start_datetime"]<=item<=kwargs["end_datetime"]]
    async def fetch_dynamic(self,**kwargs):
        self.dynamic_calls.append(kwargs)
        if self.error: raise self.error
        return [cell for cell in self.cells if kwargs["start_datetime"]<=cell.valid_time<=kwargs["end_datetime"]]
    async def fetch_static(self,**kwargs):
        self.static_calls.append(kwargs)
        if self.error: raise self.error
        return self.static


class FakeResolver:
    def __init__(self,metadata=None): self.metadata=metadata; self.calls=[]
    async def resolve(self,**kwargs): self.calls.append(kwargs); return self.metadata


def service(provider=None,resolver=None,cache=None,**changes):
    options=dict(provider=provider or FakeProvider(),metadata_resolver=resolver or FakeResolver(),
        cache=cache or MemoryJsonCache(),dataset_id="cmems_mod_glo_phy_anfc_merged-sl_PT1H-i",
        dataset_version="202411",static_dataset_id="cmems_mod_glo_phy_anfc_0.083deg_static",
        static_dataset_version="202211",max_radius_km=10,static_alignment_tolerance_km=1,
        time_tolerance_hours=1,max_horizon_hours=240,decomposition_tolerance_m=.005,
        fresh_ttl_seconds=1800,stale_ttl_seconds=21600,static_ttl_seconds=604800,
        event_ttl_seconds=1800,availability_ttl_seconds=600,now=lambda:NOW)
    options.update(changes); return CopernicusTideService(**options)


def test_qualified_metadata_fixture_and_exact_variable_name():
    fixture=json.loads((Path(__file__).parent/"fixtures"/"copernicus_tides_metadata.json").read_text())
    assert "tide_loading" in fixture["variables"]
    assert "load_tide" not in fixture["variables"]
    validate_tide_metadata(fixture["variables"])
    with pytest.raises(InvalidTideResponseError): validate_tide_metadata({"load_tide":{}})


@pytest.mark.parametrize("value",[None,math.nan,math.inf,-math.inf,-9999,9.96921e36])
def test_missing_values_are_rejected(value): assert decode_tide_value(value) is None


def test_runtime_fill_range_and_negative_values():
    class Variable:
        attrs={"missing_value":-8888,"valid_range":[-10,10]}
        encoding={"_FillValue":-7777}
    assert decode_tide_value(-8888,Variable()) is None
    assert decode_tide_value(-7777,Variable()) is None
    assert decode_tide_value(11,Variable()) is None
    assert decode_tide_value(-1.25,Variable()) == -1.25


@pytest.mark.asyncio
async def test_point_reconstruction_excludes_loading_and_unknown_time_metadata():
    result=await service().get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    assert result.sampling_quality=="nearest_grid_cell"
    assert result.reconstructed_total_sea_level_m==pytest.approx(.55)
    assert result.decomposition_residual_m==pytest.approx(0)
    assert result.components.tide_loading_m==pytest.approx(.04)
    assert result.time_classification=="unknown"
    assert result.forecast_reference_time is None


@pytest.mark.asyncio
async def test_authoritative_metadata_controls_classification():
    metadata=TideTimeMetadata("forecast",NOW-timedelta(hours=12),12)
    result=await service(resolver=FakeResolver(metadata)).get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    assert result.time_classification=="forecast"
    assert result.forecast_lead_hours==12


@pytest.mark.asyncio
async def test_past_future_and_selected_time_cache_boundaries():
    t22=NOW+timedelta(hours=10); t23=NOW+timedelta(hours=11)
    provider=FakeProvider(cells=[tide_cell(valid_time=t22),tide_cell(valid_time=t23)],times=[t22,t23])
    svc=service(provider)
    exact=await svc.get_sea_level(latitude=18.025,longitude=70.525,at=t22)
    after=await svc.get_sea_level(latitude=18.025,longitude=70.525,at=t22+timedelta(minutes=1))
    late=await svc.get_sea_level(latitude=18.025,longitude=70.525,at=t22+timedelta(minutes=59))
    next_exact=await svc.get_sea_level(latitude=18.025,longitude=70.525,at=t23)
    assert exact.valid_time==t22
    assert after.valid_time==late.valid_time==next_exact.valid_time==t23
    assert exact.valid_time!=after.valid_time


@pytest.mark.asyncio
async def test_horizon_is_rejected_before_provider_access():
    provider=FakeProvider()
    with pytest.raises(TideForecastOutOfHorizonError):
        await service(provider).get_sea_level(latitude=18.025,longitude=70.525,at=NOW+timedelta(hours=241))
    assert not provider.time_calls


@pytest.mark.asyncio
async def test_omitted_at_availability_cache_and_point_cache():
    clock=[0.0]; wall=[NOW+timedelta(minutes=20)]
    provider=FakeProvider(cells=[tide_cell(valid_time=NOW)],times=[NOW,NOW+timedelta(hours=1)])
    svc=service(provider,now=lambda:wall[0],monotonic=lambda:clock[0])
    first=await svc.get_sea_level(latitude=18.025,longitude=70.525)
    wall[0]+=timedelta(seconds=10)
    second=await svc.get_sea_level(latitude=18.025,longitude=70.525)
    assert first.cache_status=="refreshed" and second.cache_status=="fresh"
    assert len(provider.time_calls)==1
    assert len(provider.dynamic_calls)==1
    assert svc.availability_refresh_count==1
    assert svc.dynamic_field_refresh_count==1
    assert second.retrieved_at==first.retrieved_at


@pytest.mark.asyncio
async def test_availability_ttl_expiry_refreshes_once_without_field_reload():
    clock=[0.0]; wall=[NOW+timedelta(minutes=20)]
    provider=FakeProvider(cells=[tide_cell(valid_time=NOW)],times=[NOW,NOW+timedelta(hours=1)])
    svc=service(provider,now=lambda:wall[0],monotonic=lambda:clock[0],availability_ttl_seconds=10)
    await svc.get_sea_level(latitude=18.025,longitude=70.525)
    clock[0]=11
    await svc.get_sea_level(latitude=18.025,longitude=70.525)
    assert len(provider.time_calls)==2
    assert len(provider.dynamic_calls)==1


@pytest.mark.asyncio
async def test_availability_single_flight_and_explicit_coverage():
    times=[NOW,NOW+timedelta(hours=1)]
    cells=[tide_cell(valid_time=value) for value in times]
    provider=FakeProvider(cells=cells,times=times); svc=service(provider)
    await asyncio.gather(*(svc.get_sea_level(latitude=18.025,longitude=70.525) for _ in range(5)))
    assert len(provider.time_calls)==1
    await svc.get_sea_level(latitude=18.025,longitude=70.525,at=NOW+timedelta(minutes=30))
    assert len(provider.time_calls)==1
    provider.times.append(NOW+timedelta(hours=2)); provider.cells.append(tide_cell(valid_time=NOW+timedelta(hours=2)))
    await svc.get_sea_level(latitude=18.025,longitude=70.525,at=NOW+timedelta(hours=2))
    assert len(provider.time_calls)==2


@pytest.mark.asyncio
async def test_failed_availability_refresh_is_not_cached():
    provider=FakeProvider(error=TideSourceUnavailableError("offline")); svc=service(provider)
    with pytest.raises(TideSourceUnavailableError):
        await svc.get_sea_level(latitude=18.025,longitude=70.525)
    assert svc._availability_cache=={}
    assert svc.availability_refresh_count==0


def test_availability_configuration_identity_and_namespaces_are_isolated():
    first=service(); second=service(dataset_version="209901")
    assert first._availability_identity()!=second._availability_identity()
    assert first._availability_identity().startswith("tides:availability:")
    assert not first._availability_identity().startswith("tides:point:")


@pytest.mark.asyncio
async def test_residual_degrades_only_decomposition_evidence():
    result=await service(FakeProvider([tide_cell(total_sea_level=.6)])).get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    assert result.total_modelled_sea_level_m==.6
    assert result.model_evidence_quality=="normal"
    assert result.spatial_representativeness=="normal"
    assert result.decomposition_evidence_quality=="degraded"


@pytest.mark.asyncio
async def test_exact_nearest_and_coastal_quality():
    exact=tide_cell(latitude=18.025,longitude=70.525)
    exact_static=static_cell(latitude=18.025,longitude=70.525)
    result=await service(FakeProvider([exact],[exact_static])).get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    assert result.sampling_quality=="exact_grid_cell"
    land=tide_cell(latitude=20.5,longitude=72.91667)
    water=tide_cell(latitude=20.5,longitude=72.83334)
    masks=[static_cell(latitude=20.5001,longitude=72.9167,mask=0),static_cell(latitude=20.5001,longitude=72.8334,mask=1)]
    result=await service(FakeProvider([land,water],masks)).get_sea_level(latitude=20.5,longitude=72.9,at=NOW)
    assert result.sampling_quality=="nearest_valid_water_cell"
    assert result.spatial_representativeness=="degraded"


@pytest.mark.asyncio
async def test_static_alignment_and_radius_are_enforced():
    with pytest.raises(StaticGridAlignmentError):
        await service(FakeProvider([tide_cell()],[static_cell(latitude=18.1)]),static_alignment_tolerance_km=1).get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    with pytest.raises(NoValidTideCellError):
        await service(FakeProvider([tide_cell(latitude=18.5)],[static_cell(latitude=18.5)]),max_radius_km=10).get_sea_level(latitude=18.025,longitude=70.525,at=NOW)


@pytest.mark.asyncio
async def test_midpoint_tie_break_and_antimeridian():
    west=tide_cell(latitude=0,longitude=-.05); east=tide_cell(latitude=0,longitude=.05)
    statics=[static_cell(latitude=0,longitude=-.05),static_cell(latitude=0,longitude=.05)]
    result=await service(FakeProvider([east,west],statics)).get_sea_level(latitude=0,longitude=0,at=NOW)
    assert result.sampled_location.longitude==pytest.approx(-.05)
    assert normalize_longitude(180)==-180


@pytest.mark.asyncio
async def test_cache_and_static_cache_reuse():
    provider=FakeProvider(); svc=service(provider)
    first=await svc.get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    second=await svc.get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    assert first.cache_status=="refreshed" and second.cache_status=="fresh"
    assert len(provider.dynamic_calls)==1 and len(provider.static_calls)==1


@pytest.mark.asyncio
async def test_static_cache_expiry_and_configuration_identity():
    clock=[0.0]; provider=FakeProvider(); svc=service(provider,monotonic=lambda:clock[0],static_ttl_seconds=10)
    await svc.get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    # Expire normalized/field data as well, then verify the independent static TTL.
    clock[0]=11; svc._field_cache.clear()
    for key in list(svc.cache._values): svc.cache._values.pop(key)
    await svc.get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    assert len(provider.static_calls)==2
    other=service(provider,static_alignment_tolerance_km=.5)
    await other.get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    assert len(provider.static_calls)==3


def test_surface_coordinate_selection_and_static_request_depth():
    assert select_surface_coordinate([.8,.494140625,.6],.494140625)==pytest.approx(.494140625)
    with pytest.raises(InvalidTideResponseError): select_surface_coordinate([],.494140625)
    with pytest.raises(InvalidTideResponseError): select_surface_coordinate([10,20],.494140625)


@pytest.mark.asyncio
async def test_static_request_uses_exact_surface_coordinate_not_zero_range():
    provider=FakeProvider(); await service(provider).get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    request=provider.static_calls[0]
    assert request["static_surface_depth_m"]==pytest.approx(.49402499198913574)
    assert request["static_surface_depth_m"]>0


@pytest.mark.asyncio
async def test_stale_only_for_source_unavailability():
    cache=MemoryJsonCache(); provider=FakeProvider(); svc=service(provider,cache=cache,fresh_ttl_seconds=1)
    first=await svc.get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    # Remove only the fresh normalized record while preserving last-success.
    fresh=next(key for key in cache._values if key.startswith("tides:point:"))
    cache._values.pop(fresh)
    provider.error=TideSourceUnavailableError("offline"); svc._field_cache.clear()
    stale=await svc.get_sea_level(latitude=18.025,longitude=70.525,at=NOW)
    assert first.cache_status=="refreshed" and stale.cache_status=="stale"


@pytest.mark.asyncio
async def test_single_flight_identical_misses():
    provider=FakeProvider(); svc=service(provider)
    values=await asyncio.gather(*(svc.get_sea_level(latitude=18.025,longitude=70.525,at=NOW) for _ in range(5)))
    assert len(provider.dynamic_calls)==1
    assert {item.cache_status for item in values}<={"refreshed","fresh"}


def sine_samples(start=NOW,hours=26,missing=None):
    result=[]
    for index in range(-1,hours+2):
        value=math.cos(index*math.pi/6)
        result.append((start+timedelta(hours=index),None if index==missing else value))
    return result


def test_event_detection_separates_high_low_and_interpolates():
    events=detect_extrema(sine_samples(),start=NOW,end=NOW+timedelta(hours=24),interpolate=True)
    assert events and {event.event_type for event in events}=={"high","low"}
    assert all(event.timing_uncertainty_minutes_at_least==60 for event in events)
    assert events==sorted(events,key=lambda item:item.estimated_time or item.provider_sample_time)


def test_plateau_not_duplicated_and_interpolation_can_be_disabled():
    values=[(NOW+timedelta(hours=i),v) for i,v in enumerate([0,1,1,0])]
    events=detect_extrema(values,start=NOW,end=NOW+timedelta(hours=3),interpolate=False)
    assert len(events)==1 and events[0].time_is_interpolated is False


def test_missing_samples_break_continuity_and_insufficient_errors():
    with pytest.raises(InsufficientTideSeriesError):
        detect_extrema([(NOW,None),(NOW+timedelta(hours=1),1.0),(NOW+timedelta(hours=2),None)],start=NOW,end=NOW+timedelta(hours=2),interpolate=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("hours",[24,48,72])
async def test_event_windows_and_cache(hours):
    times=[NOW+timedelta(hours=i) for i in range(-1,hours+2)]
    cells=[tide_cell(valid_time=value,ocean_tide=math.cos(i*math.pi/6),total_sea_level=.2+math.cos(i*math.pi/6)) for i,value in enumerate(times,start=-1)]
    provider=FakeProvider(cells=cells,times=times); svc=service(provider)
    result=await svc.get_events(latitude=18.025,longitude=70.525,start=NOW,hours=hours)
    assert result.astronomical_tide_events
    assert result.total_sea_level_extrema
    assert not hasattr(result,"tide_events")
    assert result.requested_window.start==NOW
    assert result.requested_window.end==NOW+timedelta(hours=hours)
    assert result.requested_window.duration_hours==hours
    assert result.provider_window.start==NOW-timedelta(hours=1)
    assert result.provider_window.end==NOW+timedelta(hours=hours+1)
    assert result.provider_window.sample_count==hours+3
    assert result.provider_window.has_left_padding is True
    assert result.provider_window.has_right_padding is True
    cached=await svc.get_events(latitude=18.025,longitude=70.525,start=NOW,hours=hours)
    assert cached.cache_status=="fresh"
    assert len(provider.static_calls)==1


@pytest.mark.asyncio
async def test_non_hour_aligned_event_window_uses_strict_surrounding_times():
    start=NOW+timedelta(minutes=30); hours=24
    times=[NOW+timedelta(hours=i) for i in range(0,27)]
    cells=[tide_cell(valid_time=value,ocean_tide=math.cos(i*math.pi/6),total_sea_level=.2+math.cos(i*math.pi/6)) for i,value in enumerate(times)]
    result=await service(FakeProvider(cells=cells,times=times)).get_events(latitude=18.025,longitude=70.525,start=start,hours=hours)
    assert result.requested_window.start==start
    assert result.requested_window.end==start+timedelta(hours=24)
    assert result.provider_window.start==NOW
    assert result.provider_window.end==NOW+timedelta(hours=25)
    assert result.provider_window.start<result.requested_window.start
    assert result.provider_window.end>result.requested_window.end
    assert result.provider_window.sample_count==26


@pytest.mark.asyncio
@pytest.mark.parametrize("missing",["left","right"])
async def test_event_window_requires_both_padding_neighbours(missing):
    times=[NOW+timedelta(hours=i) for i in range(-1,26)]
    if missing=="left": times=[value for value in times if value>=NOW]
    else: times=[value for value in times if value<=NOW+timedelta(hours=24)]
    cells=[tide_cell(valid_time=value) for value in times]
    with pytest.raises(InsufficientTideSeriesError):
        await service(FakeProvider(cells=cells,times=times)).get_events(latitude=18.025,longitude=70.525,start=NOW,hours=24)


def test_boundary_events_are_inclusive_and_padded_events_are_excluded():
    samples=[
        (NOW-timedelta(hours=1),0.0),(NOW,1.0),(NOW+timedelta(hours=1),0.0),
        (NOW+timedelta(hours=23),0.0),(NOW+timedelta(hours=24),-1.0),
        (NOW+timedelta(hours=25),0.0),
    ]
    events=detect_extrema(samples,start=NOW,end=NOW+timedelta(hours=24),interpolate=False)
    assert [event.provider_sample_time for event in events]==[NOW,NOW+timedelta(hours=24)]
    outside=[(NOW-timedelta(hours=2),0.0),(NOW-timedelta(hours=1),1.0),(NOW,0.0),(NOW+timedelta(hours=1),1.0)]
    assert all(event.provider_sample_time>=NOW for event in detect_extrema(outside,start=NOW,end=NOW+timedelta(hours=1),interpolate=False))


def test_event_cache_identity_includes_exact_end():
    svc=service(); start=NOW
    first=svc._event_identity(18.025,70.525,start,start+timedelta(hours=48),48,True)
    shifted=start+timedelta(microseconds=1)
    second=svc._event_identity(18.025,70.525,shifted,shifted+timedelta(hours=48),48,True)
    assert first!=second


def test_endpoint_openapi_decimal_and_typed_not_configured_errors():
    with TestClient(app) as client:
        app.state.tide_service = None
        document=client.get("/openapi.json").json()
        for path in ("/v1/marine/sea-level","/v1/marine/sea-level/events"):
            params={item["name"]:item for item in document["paths"][path]["get"]["parameters"]}
            assert params["latitude"]["schema"]["type"]=="number"
            assert params["longitude"]["schema"]["type"]=="number"
        response=client.get("/v1/marine/sea-level",params={"latitude":18.025,"longitude":70.525})
        assert response.status_code==503
        assert response.json()["detail"]["code"]=="TIDE_SOURCE_NOT_CONFIGURED"
        assert client.get("/v1/marine/sea-level",params={"latitude":"nan","longitude":70}).status_code==422
