import asyncio
import logging
import math
from array import array
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.clients import ecmwf_wind as client_module
from app.clients.ecmwf_wind import (
    ECMWFCycleAvailability,
    ECMWFWindCorruptDownloadError,
    ECMWFWindField,
    ECMWFWindForecastOutOfRangeError,
    ECMWFWindSourceUnavailableError,
    ECMWFWindStepUnavailableError,
    ECMWFOpenDataWindProvider,
    InvalidECMWFWindResponseError,
    decode_ecmwf_wind_grib,
)
from app.schemas.marine import ECMWFWindCacheStatus, ECMWFWindFreshness
from app.schemas.marine import SourceResult, SourceStatus
from app.services.cache import MemoryJsonCache
from app.services.wind_forecast import (
    BoundedWindFieldCache,
    ECMWFWindForecastService,
    ECMWFWindMarineSource,
    ECMWFWindPastRequestError,
    TimeSelectingWindMarineSource,
    forecast_steps,
    normalize_longitude,
    select_forecast,
)


NOW = datetime(2026, 8, 30, 1, tzinfo=UTC)
CYCLE = datetime(2026, 8, 30, 0, tzinfo=UTC)


def availability() -> ECMWFCycleAvailability:
    return ECMWFCycleAvailability(CYCLE, CYCLE, "ecmwf", NOW)


def field(
    *,
    step: int = 24,
    source: str = "ecmwf",
    u: tuple[float, ...] = (1.0, 2.0, 3.0, 4.0),
    v: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0),
) -> ECMWFWindField:
    return ECMWFWindField(
        forecast_reference_time=CYCLE,
        forecast_step_hours=step,
        valid_time=CYCLE + timedelta(hours=step),
        ni=2,
        nj=2,
        latitude_first=0.25,
        longitude_first=70.5,
        latitude_increment=0.25,
        longitude_increment=0.25,
        latitude_scans_positive=False,
        longitude_scans_negative=False,
        u_values=array("d", u).tobytes(),
        v_values=array("d", v).tobytes(),
        source_mirror=source,
        retrieved_at=NOW,
        checksum_sha256="a" * 64,
    )


class FakeProvider:
    def __init__(self, *, failures: dict[str, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.discovery_calls: list[str] = []
        self.retrieve_calls: list[str] = []
        self.result = field()

    async def discover_cycles(self, source: str) -> ECMWFCycleAvailability:
        self.discovery_calls.append(source)
        error = self.failures.get(f"discover:{source}")
        if error:
            raise error
        return availability()

    async def retrieve_field(
        self,
        source: str,
        forecast_reference_time: datetime,
        forecast_step_hours: int,
    ) -> ECMWFWindField:
        self.retrieve_calls.append(source)
        error = self.failures.get(f"retrieve:{source}")
        if error:
            raise error
        await asyncio.sleep(0)
        result = field(step=forecast_step_hours, source=source)
        return result


def service(
    provider: FakeProvider,
    *,
    clock=lambda: NOW,
    calm_threshold_mps: float = 0.001,
    max_horizon_hours: int = 360,
    max_stale_cycle_age_hours: float = 24,
) -> ECMWFWindForecastService:
    return ECMWFWindForecastService(
        provider=provider,
        point_cache=MemoryJsonCache(),
        field_cache=BoundedWindFieldCache(
            ttl_seconds=3600,
            max_entries=3,
            max_bytes=1024,
        ),
        primary_source="ecmwf",
        fallback_source="aws",
        cycle_cache_ttl_seconds=900,
        cycle_stale_ttl_seconds=3600,
        point_cache_ttl_seconds=3600,
        point_stale_ttl_seconds=21600,
        max_stale_cycle_age_hours=max_stale_cycle_age_hours,
        calm_threshold_mps=calm_threshold_mps,
        max_horizon_hours=max_horizon_hours,
        now=clock,
    )


def test_cycle_50r1_schedules_use_oper_hours() -> None:
    for hour in (0, 12):
        steps = forecast_steps(hour)
        assert steps[:49] == tuple(range(0, 145, 3))
        assert steps[49:] == tuple(range(150, 361, 6))
        assert max(steps) == 360
    for hour in (6, 18):
        assert forecast_steps(hour) == tuple(range(0, 145, 3))
    assert 147 not in forecast_steps(0)
    assert 363 not in forecast_steps(0)


@pytest.mark.parametrize("step", [144, 150, 360])
def test_long_cycle_boundaries_select_exact_steps(step: int) -> None:
    selected = select_forecast(CYCLE + timedelta(hours=step), availability())
    assert selected.forecast_step_hours == step
    assert selected.valid_time == CYCLE + timedelta(hours=step)


def test_configured_horizon_is_enforced_before_retrieval() -> None:
    with pytest.raises(ECMWFWindForecastOutOfRangeError):
        select_forecast(
            CYCLE + timedelta(hours=150),
            availability(),
            max_horizon_hours=144,
        )


def test_cycle_selection_exact_and_first_after() -> None:
    exact = select_forecast(CYCLE + timedelta(hours=24), availability())
    after = select_forecast(
        CYCLE + timedelta(hours=24, minutes=1), availability()
    )
    assert exact.valid_time == CYCLE + timedelta(hours=24)
    assert exact.forecast_reference_time + timedelta(
        hours=exact.forecast_step_hours
    ) == exact.valid_time
    assert after.valid_time == CYCLE + timedelta(hours=27)


def test_cycle_selection_uses_six_hour_steps_after_144() -> None:
    selected = select_forecast(
        CYCLE + timedelta(hours=145), availability()
    )
    assert selected.forecast_step_hours == 150
    assert selected.valid_time - (CYCLE + timedelta(hours=145)) == timedelta(hours=5)


def test_cycle_selection_rejects_beyond_360_hours() -> None:
    with pytest.raises(ECMWFWindForecastOutOfRangeError):
        select_forecast(CYCLE + timedelta(hours=361), availability())


@pytest.mark.parametrize(
    ("value", "expected"),
    [(180.0, -180.0), (-180.0, -180.0), (181.0, -179.0), (-181.0, 179.0)],
)
def test_longitude_normalization(value: float, expected: float) -> None:
    assert normalize_longitude(value) == expected


def test_field_cache_ttl_lru_byte_limit_and_corruption() -> None:
    current = [0.0]
    cache = BoundedWindFieldCache(
        ttl_seconds=10,
        max_entries=1,
        max_bytes=128,
        clock=lambda: current[0],
    )
    first = field()
    second = field(step=27)
    assert cache.set("first", first)
    assert cache.get("first") is first
    assert cache.set("second", second)
    assert cache.get("first") is None
    current[0] = 11
    assert cache.get("second") is None
    corrupt = replace(field(), u_values=b"bad")
    assert cache.set("bad", corrupt) is False


@pytest.mark.asyncio
async def test_service_selects_nearest_and_derives_direction_from() -> None:
    response = await service(FakeProvider()).get_forecast(
        latitude=0.0,
        longitude=70.5,
        at=CYCLE + timedelta(hours=24),
    )
    assert response.sampled_location.latitude == 0.0
    assert response.sampled_location.longitude == 70.5
    assert response.eastward_wind_mps == 3.0
    assert response.wind_speed_mps == 3.0
    assert response.wind_direction_from_deg == 270.0
    assert response.compass_direction_from == "W"
    assert response.classification == "forecast"
    assert response.source.provider == "ECMWF"
    assert response.provider == "ECMWF"
    assert response.selected_mirror == "ecmwf"
    assert response.source_classification == "numerical_forecast"
    assert response.requested_latitude == 0.0
    assert response.requested_longitude == 70.5
    assert response.speed_mps == response.wind_speed_mps
    assert response.direction_from_degrees == response.wind_direction_from_deg
    assert response.requested_at == response.requested_time
    assert response.forecast_step == response.forecast_lead_hours
    assert "uncertainty increases with lead time" in response.notice


@pytest.mark.asyncio
async def test_calm_forecast_has_no_direction() -> None:
    provider = FakeProvider()
    provider.result = field(u=(0.0,) * 4, v=(0.0,) * 4)

    async def calm(*args, **kwargs):
        del args, kwargs
        return provider.result

    provider.retrieve_field = calm
    response = await service(provider).get_forecast(
        latitude=0.0,
        longitude=70.5,
        at=CYCLE + timedelta(hours=24),
    )
    assert response.wind_speed_mps == 0
    assert response.wind_direction_from_deg is None
    assert response.compass_direction_from is None


@pytest.mark.asyncio
async def test_configurable_calm_threshold_suppresses_direction() -> None:
    provider = FakeProvider()

    async def nearly_calm(*args, **kwargs):
        del args, kwargs
        return field(u=(0.0005,) * 4, v=(0.0,) * 4)

    provider.retrieve_field = nearly_calm
    response = await service(provider, calm_threshold_mps=0.001).get_forecast(
        latitude=0.0,
        longitude=70.5,
        at=CYCLE + timedelta(hours=24),
    )
    assert response.speed_mps == 0.0005
    assert response.direction_from_degrees is None
    assert response.compass_direction_from is None


@pytest.mark.asyncio
async def test_midpoint_tie_and_nonfinite_cells_are_deterministic() -> None:
    provider = FakeProvider()

    async def custom(*args, **kwargs):
        del args, kwargs
        return replace(
            field(u=(1.0, 2.0, math.nan, math.inf), v=(0.0,) * 4),
            latitude_first=0.0,
        )

    provider.retrieve_field = custom
    response = await service(provider).get_forecast(
        latitude=0.0,
        longitude=70.625,
        at=CYCLE + timedelta(hours=24),
    )
    assert response.sampled_longitude == 70.5
    assert response.eastward_wind_mps == 1.0


@pytest.mark.asyncio
async def test_antimeridian_sampling_treats_180_as_minus_180() -> None:
    provider = FakeProvider()

    async def dateline(*args, **kwargs):
        del args, kwargs
        return replace(
            field(u=(1.0, 2.0, 3.0, 4.0), v=(0.0,) * 4),
            latitude_first=0.25,
            longitude_first=179.75,
        )

    provider.retrieve_field = dateline
    response = await service(provider).get_forecast(
        latitude=0.25,
        longitude=180.0,
        at=CYCLE + timedelta(hours=24),
    )
    assert response.requested_longitude == -180.0
    assert response.sampled_longitude == -180.0
    assert response.eastward_wind_mps == 2.0


@pytest.mark.asyncio
async def test_primary_transient_failure_uses_one_fallback() -> None:
    provider = FakeProvider(
        failures={
            "retrieve:ecmwf": ECMWFWindSourceUnavailableError("private URL")
        }
    )
    response = await service(provider).get_forecast(
        latitude=0.0,
        longitude=70.5,
        at=CYCLE + timedelta(hours=24),
    )
    assert provider.retrieve_calls == ["ecmwf", "aws"]
    assert response.source.source_mirror == "aws"


@pytest.mark.asyncio
async def test_corrupt_primary_does_not_fail_over() -> None:
    provider = FakeProvider(
        failures={"retrieve:ecmwf": ECMWFWindCorruptDownloadError("private")}
    )
    with pytest.raises(InvalidECMWFWindResponseError):
        await service(provider).get_forecast(
            latitude=0.0,
            longitude=70.5,
            at=CYCLE + timedelta(hours=24),
        )
    assert provider.retrieve_calls == ["ecmwf"]


@pytest.mark.asyncio
async def test_cycle_discovery_uses_one_fallback() -> None:
    provider = FakeProvider(
        failures={
            "discover:ecmwf": ECMWFWindSourceUnavailableError("private URL")
        }
    )
    await service(provider).get_forecast(
        latitude=0.0,
        longitude=70.5,
        at=CYCLE + timedelta(hours=24),
    )
    assert provider.discovery_calls == ["ecmwf", "aws"]


@pytest.mark.asyncio
async def test_successful_primary_prevents_fallback() -> None:
    provider = FakeProvider()
    await service(provider).get_forecast(
        latitude=0.0,
        longitude=70.5,
        at=CYCLE + timedelta(hours=24),
    )
    assert provider.retrieve_calls == ["ecmwf"]


@pytest.mark.asyncio
async def test_invalid_forecast_times_do_not_attempt_mirror_failover() -> None:
    provider = FakeProvider()
    subject = service(provider)
    with pytest.raises(ECMWFWindForecastOutOfRangeError):
        await subject.get_forecast(
            latitude=0.0,
            longitude=70.5,
            at=CYCLE + timedelta(hours=361),
        )
    assert provider.discovery_calls == ["ecmwf"]
    assert provider.retrieve_calls == []


@pytest.mark.asyncio
async def test_unavailable_step_does_not_attempt_mirror_failover() -> None:
    provider = FakeProvider(
        failures={
            "retrieve:ecmwf": ECMWFWindStepUnavailableError("not published")
        }
    )
    with pytest.raises(ECMWFWindStepUnavailableError):
        await service(provider).get_forecast(
            latitude=0.0,
            longitude=70.5,
            at=CYCLE + timedelta(hours=24),
        )
    assert provider.retrieve_calls == ["ecmwf"]


@pytest.mark.asyncio
async def test_non_future_request_does_not_discover_or_retrieve() -> None:
    provider = FakeProvider()
    with pytest.raises(ECMWFWindPastRequestError, match="future forecast times only"):
        await service(provider).get_forecast(
            latitude=0.0,
            longitude=70.5,
            at=NOW,
        )
    assert provider.discovery_calls == []
    assert provider.retrieve_calls == []


@pytest.mark.asyncio
async def test_same_field_is_reused_across_coordinates() -> None:
    provider = FakeProvider()
    subject = service(provider)
    await subject.get_forecast(
        latitude=0.0, longitude=70.5, at=CYCLE + timedelta(hours=24)
    )
    await subject.get_forecast(
        latitude=0.2, longitude=70.7, at=CYCLE + timedelta(hours=24)
    )
    assert provider.retrieve_calls == ["ecmwf"]


@pytest.mark.asyncio
async def test_point_cache_does_not_cross_coordinates_or_times() -> None:
    provider = FakeProvider()
    subject = service(provider)
    first = await subject.get_forecast(
        latitude=0.0, longitude=70.5, at=CYCLE + timedelta(hours=24)
    )
    coordinate = await subject.get_forecast(
        latitude=0.25, longitude=70.75, at=CYCLE + timedelta(hours=24)
    )
    later = await subject.get_forecast(
        latitude=0.0, longitude=70.5, at=CYCLE + timedelta(hours=27)
    )
    assert first.requested_location != coordinate.requested_location
    assert later.valid_time != first.valid_time
    assert provider.retrieve_calls == ["ecmwf", "ecmwf"]


@pytest.mark.asyncio
async def test_point_cache_and_single_flight() -> None:
    provider = FakeProvider()
    subject = service(provider)
    arguments = {
        "latitude": 0.0,
        "longitude": 70.5,
        "at": CYCLE + timedelta(hours=24),
    }
    first, second = await asyncio.gather(
        subject.get_forecast(**arguments),
        subject.get_forecast(**arguments),
    )
    third = await subject.get_forecast(**arguments)
    assert provider.retrieve_calls == ["ecmwf"]
    assert {first.cache_status, second.cache_status} == {
        ECMWFWindCacheStatus.REFRESHED,
        ECMWFWindCacheStatus.FRESH,
    }
    assert third.cache_status == ECMWFWindCacheStatus.FRESH


@pytest.mark.asyncio
async def test_matching_stale_fallback_preserves_cycle() -> None:
    provider = FakeProvider()
    subject = service(provider)
    arguments = {
        "latitude": 0.0,
        "longitude": 70.5,
        "at": CYCLE + timedelta(hours=24),
    }
    first = await subject.get_forecast(**arguments)
    base = subject._point_base(
        select_forecast(arguments["at"], availability()), 0.0, 70.5
    )
    subject.field_cache.delete(subject._field_key(select_forecast(arguments["at"], availability())))
    await subject.point_cache.set(f"{base}:fresh", {}, 1)
    provider.failures["retrieve:ecmwf"] = ECMWFWindSourceUnavailableError("x")
    provider.failures["retrieve:aws"] = ECMWFWindSourceUnavailableError("y")
    stale = await subject.get_forecast(**arguments)
    assert stale.cache_status == ECMWFWindCacheStatus.STALE
    assert stale.freshness == ECMWFWindFreshness.STALE_CYCLE
    assert stale.valid_time == first.valid_time


class FakeEccodes:
    def __init__(self, messages: list[dict[str, object]]) -> None:
        self.messages = messages
        self.index = 0
        self.released: list[dict[str, object]] = []

    def codes_grib_new_from_file(self, stream):
        del stream
        if self.index >= len(self.messages):
            return None
        message = self.messages[self.index]
        self.index += 1
        return message

    def codes_get_long(self, handle, key):
        return int(handle[key])

    def codes_get_double(self, handle, key):
        return float(handle[key])

    def codes_get_string(self, handle, key):
        return str(handle[key])

    def codes_get_values(self, handle):
        return handle["values"]

    def codes_release(self, handle):
        self.released.append(handle)


def grib_message(short_name: str, values=(1.0, -9999.0, 2.0, 3.0)):
    return {
        "shortName": short_name,
        "edition": 2,
        "gridType": "regular_ll",
        "dataType": "fc",
        "units": "m s**-1",
        "Ni": 2,
        "Nj": 2,
        "endStep": 24,
        "dataDate": 20260830,
        "dataTime": 0,
        "validityDate": 20260831,
        "validityTime": 0,
        "jPointsAreConsecutive": 0,
        "alternativeRowScanning": 0,
        "missingValue": -9999.0,
        "latitudeOfFirstGridPointInDegrees": 0.25,
        "longitudeOfFirstGridPointInDegrees": 70.5,
        "jDirectionIncrementInDegrees": 0.25,
        "iDirectionIncrementInDegrees": 0.25,
        "jScansPositively": 0,
        "iScansNegatively": 0,
        "values": values,
    }


def test_direct_decoder_is_order_independent_and_metadata_driven(
    monkeypatch, tmp_path: Path
) -> None:
    fake = FakeEccodes([grib_message("10v"), grib_message("10u")])
    monkeypatch.setattr(client_module, "_load_eccodes", lambda: fake)
    target = tmp_path / "tiny.grib2"
    target.write_bytes(b"synthetic")
    decoded = decode_ecmwf_wind_grib(target, "ecmwf", 24, NOW)
    assert decoded.forecast_reference_time + timedelta(hours=24) == decoded.valid_time
    assert math.isnan(memoryview(decoded.u_values).cast("d")[1])
    assert len(fake.released) == 2


def test_direct_decoder_rejects_duplicate_components_and_releases_handles(
    monkeypatch, tmp_path: Path
) -> None:
    fake = FakeEccodes([grib_message("10u"), grib_message("10u")])
    monkeypatch.setattr(client_module, "_load_eccodes", lambda: fake)
    target = tmp_path / "tiny.grib2"
    target.write_bytes(b"synthetic")
    with pytest.raises(ECMWFWindCorruptDownloadError):
        decode_ecmwf_wind_grib(target, "ecmwf", 24, NOW)
    assert len(fake.released) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        {"endStep": 27},
        {"Ni": 3},
        {"iDirectionIncrementInDegrees": 0.5},
        {"validityTime": 300},
    ],
)
def test_direct_decoder_rejects_conflicting_or_invalid_metadata(
    monkeypatch, tmp_path: Path, mutation: dict[str, object]
) -> None:
    second = grib_message("10v")
    second.update(mutation)
    fake = FakeEccodes([grib_message("10u"), second])
    monkeypatch.setattr(client_module, "_load_eccodes", lambda: fake)
    target = tmp_path / "tiny.grib2"
    target.write_bytes(b"synthetic")
    with pytest.raises(ECMWFWindCorruptDownloadError):
        decode_ecmwf_wind_grib(target, "ecmwf", 24, NOW)
    assert len(fake.released) == 2


@pytest.mark.asyncio
async def test_provider_uses_oper_only_and_cleans_temporary_directory(
    caplog,
) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def retrieve(self, **kwargs):
            logging.getLogger("multiurl.http").warning(
                "https://signed.invalid/object?token=secret"
            )
            captured.update(kwargs)
            Path(kwargs["target"]).write_bytes(b"small")

    def decoder(path, source, step, retrieved_at):
        captured["temporary_parent"] = path.parent
        return field(step=step, source=source)

    provider = ECMWFOpenDataWindProvider(
        model="ifs",
        resolution="0p25",
        u_parameter="10u",
        v_parameter="10v",
        maximum_retries=2,
        retry_initial_seconds=1,
        retry_max_seconds=8,
        total_timeout_seconds=10,
        max_download_bytes=1024,
        client_factory=lambda source: FakeClient(),
        decoder=decoder,
        now=lambda: NOW,
    )
    result = await provider.retrieve_field("ecmwf", CYCLE, 24)
    assert result.valid_time == CYCLE + timedelta(hours=24)
    assert captured["stream"] == "oper"
    assert captured["type"] == "fc"
    assert captured["param"] == ["10u", "10v"]
    assert "scda" not in captured.values()
    assert not captured["temporary_parent"].exists()
    assert "signed.invalid" not in caplog.text
    assert "token=secret" not in caplog.text


def test_official_client_retry_configuration_is_bounded(monkeypatch) -> None:
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(client_module, "_load_client_class", lambda: FakeClient)
    provider = ECMWFOpenDataWindProvider(
        model="ifs",
        resolution="0p25",
        u_parameter="10u",
        v_parameter="10v",
        maximum_retries=2,
        retry_initial_seconds=1,
        retry_max_seconds=8,
        total_timeout_seconds=60,
        max_download_bytes=10_485_760,
    )
    provider._make_client("ecmwf")
    assert captured["maximum_retries"] == 2
    assert captured["retry_after"] == (1, 8, 2)
    assert captured["use_server_retry_after"] is False
    assert captured["source"] == "ecmwf"


@pytest.mark.asyncio
async def test_provider_maps_missing_step_without_exposing_or_retrying_mirror() -> None:
    class Response:
        status_code = 404

    class MissingStep(Exception):
        response = Response()

    class FakeClient:
        def retrieve(self, **kwargs):
            del kwargs
            raise MissingStep("signed provider URL")

    provider = ECMWFOpenDataWindProvider(
        model="ifs",
        resolution="0p25",
        u_parameter="10u",
        v_parameter="10v",
        maximum_retries=2,
        retry_initial_seconds=1,
        retry_max_seconds=8,
        total_timeout_seconds=10,
        max_download_bytes=1024,
        client_factory=lambda source: FakeClient(),
        now=lambda: NOW,
    )
    with pytest.raises(ECMWFWindStepUnavailableError) as caught:
        await provider.retrieve_field("ecmwf", CYCLE, 24)
    assert "signed provider URL" not in str(caught.value)


class FakeAnalysisSource:
    name = "wind"

    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, client, latitude, longitude, at=None):
        del client, latitude, longitude, at
        self.calls += 1
        return SourceResult(source="Copernicus Marine", status=SourceStatus.FRESH)


@pytest.mark.asyncio
async def test_combined_wind_selects_analysis_for_recent_and_ecmwf_for_future() -> None:
    analysis = FakeAnalysisSource()
    provider = FakeProvider()
    forecast_service = service(provider)
    source = TimeSelectingWindMarineSource(
        analysis,
        ECMWFWindMarineSource(forecast_service),
        now=lambda: NOW,
    )
    recent = await source.fetch(None, 0.0, 70.5, NOW)
    future = await source.fetch(None, 0.0, 70.5, CYCLE + timedelta(hours=24))
    assert recent.source == "Copernicus Marine"
    assert future.source == "ECMWF"
    assert future.data["classification"] == "forecast"
    assert analysis.calls == 1


@pytest.mark.asyncio
async def test_combined_future_failure_never_substitutes_analysis() -> None:
    analysis = FakeAnalysisSource()
    provider = FakeProvider(
        failures={
            "retrieve:ecmwf": ECMWFWindSourceUnavailableError("secret"),
            "retrieve:aws": ECMWFWindSourceUnavailableError("secret"),
        }
    )
    source = TimeSelectingWindMarineSource(
        analysis,
        ECMWFWindMarineSource(service(provider)),
        now=lambda: NOW,
    )
    result = await source.fetch(None, 0.0, 70.5, CYCLE + timedelta(hours=24))
    assert result.source == "ECMWF"
    assert result.status == SourceStatus.UNAVAILABLE
    assert result.error == "ECMWF_SOURCE_UNAVAILABLE"
    assert analysis.calls == 0
