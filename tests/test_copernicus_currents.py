import asyncio
import math
import json
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clients.copernicus_currents import (
    CurrentAuthenticationError,
    CurrentCycleMetadata,
    CurrentProviderCell,
    CurrentSourceUnavailableError,
    decode_current_value,
    parse_current_reference,
)
from app.main import app
from app.clients.demo import DemoMarineSource
from app.services.cache import MemoryJsonCache
from app.services.currents import (
    CopernicusCurrentService,
    CurrentForecastOutOfHorizonError,
    CurrentTimeUnavailableError,
    NoValidCurrentCellError,
    current_speed_direction,
    normalize_longitude,
)
from app.services.marine import MarineConditionsService


NOW=datetime(2026,8,31,22,tzinfo=UTC)
T22=NOW; T23=NOW+timedelta(hours=1)


def cell(**changes):
    values=dict(latitude=18.0,longitude=70.5,depth_m=0.49402499198913574,
        valid_time=T22,sea_mask=1,bathymetry_m=100.0,
        uo=.0654296875,vo=-.0009765625,utide=-.0048828125,vtide=-.01953125,
        vsdx=.1396484375,vsdy=.01953125,utotal=.2001953125,vtotal=0.0)
    values.update(changes); return CurrentProviderCell(**values)


class FakeProvider:
    def __init__(self,cells=None,times=None,error=None):
        self.cells=cells or [cell()];self.times=times or [T22,T23];self.error=error
        self.time_calls=[];self.cell_calls=[]
    async def available_times(self,**kwargs):
        self.time_calls.append(kwargs)
        if self.error: raise self.error
        return self.times
    async def fetch_cells(self,**kwargs):
        self.cell_calls.append(kwargs)
        if self.error: raise self.error
        selected=kwargs["selected_time"]
        return [replace(c, valid_time=selected) for c in self.cells]


class FakeResolver:
    def __init__(self,reference=None,error=None): self.reference=reference;self.error=error;self.calls=[]
    async def resolve(self,**kwargs):
        self.calls.append(kwargs)
        if self.error: raise self.error
        return CurrentCycleMetadata(self.reference) if self.reference else None


def service(provider=None,resolver=None,cache=None,**overrides):
    options=dict(provider=provider or FakeProvider(),metadata_resolver=resolver or FakeResolver(),
        cache=cache or MemoryJsonCache(),dataset_id="cmems_mod_glo_phy_anfc_merged-uv_PT1H-i",
        dataset_version="202211",static_dataset_id="cmems_mod_glo_phy_anfc_0.083deg_static",
        static_dataset_version="202211",max_radius_km=15,calm_threshold_mps=.001,
        time_tolerance_hours=1,component_tolerance_mps=.002,fresh_ttl_seconds=1800,
        stale_ttl_seconds=21600,max_horizon_hours=240,now=lambda:NOW)
    options.update(overrides);return CopernicusCurrentService(**options)


@pytest.mark.parametrize(("u","v","degrees","compass"),[(0,1,0,"N"),(1,0,90,"E"),(0,-1,180,"S"),(-1,0,270,"W"),(1,1,45,"NE"),(-1,-1,225,"SW")])
def test_direction_is_oceanographic_toward(u,v,degrees,compass):
    speed,direction,label=current_speed_direction(u,v,.001)
    assert speed==pytest.approx(math.hypot(u,v));assert direction==pytest.approx(degrees);assert label==compass


def test_calm_current_has_no_arbitrary_direction():
    assert current_speed_direction(.0005,0,.001)==(.0005,None,"CALM")


@pytest.mark.parametrize("value",[None,math.nan,math.inf,-math.inf,9.96921e36,1e20])
def test_fill_and_non_finite_values_are_rejected(value): assert decode_current_value(value) is None


def test_variable_fill_missing_and_range_metadata_are_honored():
    class Variable:
        attrs={"missing_value":-9999,"valid_min":-5,"valid_max":5}
        encoding={"_FillValue":-32767}
    assert decode_current_value(-9999,Variable()) is None
    assert decode_current_value(-32767,Variable()) is None
    assert decode_current_value(6,Variable()) is None
    assert decode_current_value(1.25,Variable())==1.25


def test_cycle_filename_metadata_parser():
    result=parse_current_reference(["SMOC_20260901_R20260831.nc","bad.nc"])
    assert result and result.reference_time==datetime(2026,8,31,tzinfo=UTC)


def test_qualified_current_metadata_fixture():
    fixture=json.loads((Path(__file__).parent/"fixtures"/"copernicus_currents_metadata.json").read_text(encoding="utf-8"))
    assert fixture["mask"] == {"standard_name":"sea_binary_mask","long_name":"Land-sea mask: 1 = sea ; 0 = land","sea":1,"land":0}
    assert fixture["decoded_fill_values_observed"] == [9.96921e36,1e20]


@pytest.mark.asyncio
async def test_open_ocean_nearest_grid_and_component_consistency():
    response=await service().get_current(latitude=18.025,longitude=70.525,at=T22)
    assert response.sampling_quality=="nearest_grid_cell"
    assert response.distance_km==pytest.approx(3.836,abs=.002)
    assert response.decomposition_complete is True
    assert response.component_residual_mps.northward==pytest.approx(.0009765625)
    assert response.evidence_quality=="normal"


@pytest.mark.asyncio
async def test_exact_and_coastal_fallback_quality():
    exact=cell(latitude=18.025,longitude=70.525)
    assert (await service(FakeProvider([exact])).get_current(latitude=18.025,longitude=70.525,at=T22)).sampling_quality=="exact_grid_cell"
    land=cell(latitude=20.5,longitude=72.91667,sea_mask=0,utotal=None,vtotal=None)
    water=cell(latitude=20.5,longitude=72.83334)
    response=await service(FakeProvider([land,water])).get_current(latitude=20.5,longitude=72.9,at=T22)
    assert response.sampling_quality=="nearest_valid_water_cell";assert response.distance_km==pytest.approx(6.943,abs=.01)


@pytest.mark.asyncio
async def test_radius_and_deterministic_tie_break():
    west=cell(latitude=0,longitude=-.05);east=cell(latitude=0,longitude=.05)
    response=await service(FakeProvider([east,west]),max_radius_km=10).get_current(latitude=0,longitude=0,at=T22)
    assert response.sampled_location.longitude==pytest.approx(-.05)
    with pytest.raises(NoValidCurrentCellError):
        await service(FakeProvider([cell(latitude=0,longitude=1)]),max_radius_km=10).get_current(latitude=0,longitude=0,at=T22)


@pytest.mark.asyncio
async def test_antimeridian_is_normalized_and_split():
    provider=FakeProvider([cell(latitude=0,longitude=-179.99)])
    response=await service(provider,max_radius_km=15).get_current(latitude=0,longitude=180,at=T22)
    assert response.requested_location.longitude==-180;assert len(provider.time_calls)==2


@pytest.mark.asyncio
async def test_missing_decomposition_preserves_authoritative_total():
    response=await service(FakeProvider([cell(vsdx=None,vsdy=None)])).get_current(latitude=18.025,longitude=70.525,at=T22)
    assert response.total_current.eastward_mps==pytest.approx(.200195)
    assert response.components.stokes_drift.eastward_mps is None
    assert response.decomposition_complete is False;assert response.evidence_quality=="degraded"


@pytest.mark.asyncio
async def test_large_component_residual_degrades_but_preserves_total():
    response=await service(FakeProvider([cell(utotal=1.0)])).get_current(latitude=18.025,longitude=70.525,at=T22)
    assert response.total_current.eastward_mps==1;assert response.evidence_quality=="degraded"


@pytest.mark.asyncio
async def test_time_selection_boundaries_do_not_collide():
    provider=FakeProvider()
    svc=service(provider)
    exact=await svc.get_current(latitude=18.025,longitude=70.525,at=T22)
    future_results=[]
    for minute in (1,59):
        result=await svc.get_current(latitude=18.025,longitude=70.525,at=T22+timedelta(minutes=minute))
        assert result.valid_time==T23
        future_results.append(result)
    at23=await svc.get_current(latitude=18.025,longitude=70.525,at=T23)
    assert exact.valid_time==T22;assert at23.valid_time==T23
    assert future_results[0].cache_status=="refreshed"
    assert future_results[1].cache_status=="fresh" and at23.cache_status=="fresh"


@pytest.mark.asyncio
async def test_tolerance_and_horizon_errors():
    with pytest.raises(CurrentTimeUnavailableError):
        await service(FakeProvider(times=[T23+timedelta(hours=2)])).get_current(latitude=0,longitude=0,at=T23)
    with pytest.raises(CurrentForecastOutOfHorizonError):
        await service().get_current(latitude=0,longitude=0,at=NOW+timedelta(hours=241))


@pytest.mark.asyncio
async def test_authoritative_and_unknown_classification():
    forecast=await service(resolver=FakeResolver(NOW-timedelta(hours=1))).get_current(latitude=18.025,longitude=70.525,at=T22)
    assert forecast.time_classification=="forecast";assert forecast.forecast_lead_hours==1
    unknown=await service().get_current(latitude=18.025,longitude=70.525,at=T22)
    assert unknown.time_classification=="unknown";assert unknown.forecast_reference_time is None


@pytest.mark.asyncio
async def test_fresh_cache_and_configuration_identity():
    cache=MemoryJsonCache();provider=FakeProvider();svc=service(provider,cache=cache)
    first=await svc.get_current(latitude=18.025,longitude=70.525,at=T22)
    second=await svc.get_current(latitude=18.025,longitude=70.525,at=T22)
    assert first.cache_status=="refreshed";assert second.cache_status=="fresh";assert len(provider.cell_calls)==1
    changed=service(provider,cache=cache,max_radius_km=14)
    assert (await changed.get_current(latitude=18.025,longitude=70.525,at=T22)).cache_status=="refreshed"


@pytest.mark.asyncio
async def test_single_flight_identical_misses():
    provider=FakeProvider();svc=service(provider)
    responses=await asyncio.gather(*[svc.get_current(latitude=18.025,longitude=70.525,at=T22) for _ in range(3)])
    assert len(provider.cell_calls)==1;assert {r.cache_status for r in responses}<={"refreshed","fresh"}


@pytest.mark.asyncio
async def test_matching_stale_only_for_source_unavailability():
    clock=[0.0]; cache=MemoryJsonCache(clock=lambda:clock[0]); provider=FakeProvider()
    svc=service(provider,cache=cache,monotonic=lambda:clock[0])
    assert (await svc.get_current(latitude=18.025,longitude=70.525,at=T22)).cache_status=="refreshed"
    clock[0]=1801;provider.error=CurrentSourceUnavailableError("safe")
    stale=await svc.get_current(latitude=18.025,longitude=70.525,at=T22)
    assert stale.cache_status=="stale"
    provider.error=CurrentAuthenticationError("secret detail must not escape")
    other=service(provider,cache=cache,monotonic=lambda:clock[0],max_radius_km=14)
    with pytest.raises(CurrentAuthenticationError):
        await other.get_current(latitude=18.025,longitude=70.525,at=T22)


def test_endpoint_schema_and_disabled_error():
    with TestClient(app) as client:
        app.state.current_service = None
        schema=client.get("/openapi.json").json();params=schema["paths"]["/v1/marine/currents"]["get"]["parameters"]
        assert {p["schema"]["type"] for p in params if p["name"] in {"latitude","longitude"}}=={"number"}
        response=client.get("/v1/marine/currents",params={"latitude":18.025,"longitude":70.525})
        assert response.status_code==503;assert response.json()["detail"]["code"]=="CURRENT_SOURCE_NOT_CONFIGURED"


@pytest.mark.parametrize(("latitude","longitude"),[(91,0),(-91,0),(0,181),(0,-181),("nan",0),(0,"inf")])
def test_endpoint_rejects_invalid_coordinates(latitude,longitude):
    with TestClient(app) as client: assert client.get("/v1/marine/currents",params={"latitude":latitude,"longitude":longitude}).status_code==422


def test_existing_wind_endpoint_remains_registered():
    with TestClient(app) as client:
        paths=client.get("/openapi.json").json()["paths"]
        assert "/v1/marine/wind" in paths and "/v1/marine/currents" in paths


def test_typed_current_endpoint_response_is_offline():
    with TestClient(app) as client:
        app.state.current_service=service()
        try:
            response=client.get("/v1/marine/currents",params={"latitude":18.025,"longitude":70.525,"at":T22.isoformat()})
        finally:
            app.state.current_service=None
    assert response.status_code==200
    assert response.json()["source_classification"]["observation"] is False
    assert response.json()["total_current"]["direction_toward_compass"]=="E"


@pytest.mark.asyncio
async def test_combined_conditions_preserve_other_source_when_current_fails():
    current_provider=FakeProvider(error=CurrentAuthenticationError("private"))
    from app.services.currents import CopernicusCurrentMarineSource
    combined=MarineConditionsService(
        client=None,cache=MemoryJsonCache(),  # type: ignore[arg-type]
        sources=[DemoMarineSource("sst","SST",28.0,"degC"),CopernicusCurrentMarineSource(service(current_provider))],
        cache_ttl=60,
    )
    response=await combined.get_conditions(18.025,70.525,T22)
    assert response.sources["sst"].status=="fresh"
    assert response.sources["currents"].status=="unavailable"
    assert "private" not in (response.sources["currents"].error or "")
