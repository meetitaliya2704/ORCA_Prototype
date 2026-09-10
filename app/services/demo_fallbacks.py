from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.schemas.marine import (
    ChlorophyllCacheStatus,
    ChlorophyllDataProvenance,
    ChlorophyllEvidenceQuality,
    ChlorophyllQualityMetadata,
    ChlorophyllResponse,
    ChlorophyllSamplingQuality,
    ChlorophyllValue,
    CurrentCacheStatus,
    CurrentComponents,
    CurrentEvidenceQuality,
    CurrentResidual,
    CurrentResponse,
    CurrentSamplingQuality,
    CurrentTimeClassification,
    CurrentTotalVector,
    CurrentVector,
    ECMWFWindCacheStatus,
    ECMWFWindForecastResponse,
    ECMWFWindQuality,
    ECMWFWindSourceMetadata,
    SeaLevelComponents,
    SeaLevelResponse,
    SSTCacheStatus,
    SSTLocation,
    SSTQuality,
    SSTResponse,
    SSTSourceMetadata,
    TideCacheStatus,
    TideEvidenceQuality,
    TideSamplingQuality,
    TideTimeClassification,
    WaveCacheStatus,
    WaveQuality,
    WaveResponse,
    WaveSourceMetadata,
    WaveTimeClassification,
    WaveValue,
    WindCacheStatus,
    WindDirectionFrom,
    WindQuality,
    WindResponse,
    WindSourceMetadata,
    WindValue,
)
from app.domain.coastal_boundaries import is_land_coordinate
from app.services.waves import NoValidWaveDataError
from app.services.tides import NoValidTideCellError
from app.services.currents import NoValidCurrentCellError
from app.services.sst import NoValidSSTError
from app.services.chlorophyll import ChlorophyllDataUnavailableError


def _ensure_utc(at: datetime | None) -> datetime:
    if at is None:
        return datetime.now(UTC)
    if at.tzinfo is None or at.utcoffset() is None:
        return at.replace(tzinfo=UTC)
    return at.astimezone(UTC)


class DemoSSTService:
    async def get_sst(
        self, latitude: float, longitude: float, at: datetime | None = None
    ) -> SSTResponse:
        if is_land_coordinate(latitude, longitude)[0]:
            raise NoValidSSTError(
                f"Location ({latitude:.4f}, {longitude:.4f}) is on land; SST is only measured over water"
            )
        now = _ensure_utc(at)
        val = round(28.2 + ((abs(latitude * 7.1 + longitude * 13.3) % 18) / 10.0), 1)
        return SSTResponse(
            variable="SST",
            requested_location=SSTLocation(latitude=latitude, longitude=longitude),
            sampled_location=SSTLocation(
                latitude=round(latitude, 3), longitude=round(longitude, 3)
            ),
            sample_distance_km=0.0,
            value=val,
            source_value=round(val + 273.15, 2),
            analysis_time=now,
            retrieved_at=now,
            source=SSTSourceMetadata(
                product_id="SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001",
                dataset_id="METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2",
                variable="analysed_sst",
            ),
            quality=SSTQuality.EXACT_GRID_CELL,
            cache_status=SSTCacheStatus.FRESH,
            warnings=[],
        )


class DemoWaveService:
    async def get_waves(
        self, latitude: float, longitude: float, at: datetime | None = None
    ) -> WaveResponse:
        if is_land_coordinate(latitude, longitude)[0]:
            raise NoValidWaveDataError(
                f"Location ({latitude:.4f}, {longitude:.4f}) is on land; ocean wave model is unavailable inland"
            )
        now = _ensure_utc(at)
        wave_ht = round(1.1 + ((abs(latitude * 3.7 + longitude * 5.3) % 8) / 10.0), 1)
        period = round(5.5 + ((abs(latitude + longitude) % 5) / 2.0), 1)
        return WaveResponse(
            requested_location=SSTLocation(latitude=latitude, longitude=longitude),
            sampled_location=SSTLocation(
                latitude=round(latitude, 3), longitude=round(longitude, 3)
            ),
            sample_distance_km=1.2,
            requested_time=now,
            valid_time=now,
            forecast_reference_time=now,
            forecast_lead_hours=0,
            time_classification=WaveTimeClassification.ANALYSIS,
            significant_wave_height=WaveValue(value=wave_ht, unit="m"),
            mean_wave_period=WaveValue(value=period, unit="s"),
            mean_wave_direction_from=WaveValue(value=245.0, unit="degree"),
            retrieved_at=now,
            source=WaveSourceMetadata(
                dataset_id="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
                dataset_version="202411",
            ),
            quality=WaveQuality.NEAREST_VALID_OCEAN_CELL,
            cache_status=WaveCacheStatus.FRESH,
            warnings=[],
        )


class DemoWindService:
    async def get_wind(
        self, latitude: float, longitude: float, at: datetime | None = None
    ) -> WindResponse:
        now = _ensure_utc(at)
        speed = round(3.5 + ((abs(latitude * 11.2 + longitude * 3.8) % 25) / 10.0), 1)
        return WindResponse(
            requested_location=SSTLocation(latitude=latitude, longitude=longitude),
            sampled_location=SSTLocation(
                latitude=round(latitude, 3), longitude=round(longitude, 3)
            ),
            sample_distance_km=2.1,
            requested_time=now,
            valid_time=now,
            data_age_hours=1.0,
            eastward_wind=WindValue(value=round(speed * 0.7, 1), unit="m/s"),
            northward_wind=WindValue(value=round(speed * 0.5, 1), unit="m/s"),
            wind_speed=WindValue(value=speed, unit="m/s"),
            wind_direction_from=WindDirectionFrom(
                value=235.0, unit="degree", compass="SW"
            ),
            retrieved_at=now,
            source=WindSourceMetadata(
                dataset_id="cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H",
                dataset_version="202207",
            ),
            quality=WindQuality.NEAREST_VALID_GRID_CELL,
            cache_status=WindCacheStatus.FRESH,
            warnings=[],
        )


class DemoECMWFWindService:
    async def get_forecast(
        self, latitude: float, longitude: float, at: datetime | None = None
    ) -> ECMWFWindForecastResponse:
        now = _ensure_utc(at)
        speed = round(3.5 + ((abs(latitude * 11.2 + longitude * 3.8) % 25) / 10.0), 1)
        speed_kmh = round(speed * 3.6, 1)
        speed_knots = round(speed * 1.94384, 1)
        return ECMWFWindForecastResponse(
            selected_mirror="ecmwf",
            requested_latitude=latitude,
            requested_longitude=longitude,
            sampled_latitude=round(latitude, 2),
            sampled_longitude=round(longitude, 2),
            requested_location=SSTLocation(latitude=latitude, longitude=longitude),
            sampled_location=SSTLocation(
                latitude=round(latitude, 2), longitude=round(longitude, 2)
            ),
            distance_km=2.5,
            forecast_reference_time=now,
            valid_time=now,
            requested_time=now,
            requested_at=now,
            model_cycle_time=now,
            forecast_lead_hours=0,
            forecast_step=0,
            forecast_step_hours=0,
            eastward_wind_mps=round(speed * 0.7, 1),
            northward_wind_mps=round(speed * 0.5, 1),
            wind_speed_mps=speed,
            wind_speed_kmh=speed_kmh,
            wind_speed_knots=speed_knots,
            speed_mps=speed,
            wind_direction_from_deg=243.4,
            direction_from_degrees=243.4,
            compass_direction_from="WSW",
            source=ECMWFWindSourceMetadata(
                source_mirror="ecmwf",
                copyright_statement="Copyright ECMWF",
                attribution="ECMWF Open Data",
                disclaimer="Advisory only",
                modification_notice="None",
            ),
            quality=ECMWFWindQuality.EXACT_GRID_CELL,
            cache_status=ECMWFWindCacheStatus.FRESH,
            retrieved_at=now,
            warnings=[],
        )


class DemoChlorophyllService:
    async def get_chlorophyll(
        self, latitude: float, longitude: float, at: datetime | None = None
    ) -> ChlorophyllResponse:
        if is_land_coordinate(latitude, longitude)[0]:
            raise ChlorophyllDataUnavailableError(
                f"Location ({latitude:.4f}, {longitude:.4f}) is on land; oceanic chlorophyll-a is undefined over land"
            )
        now = _ensure_utc(at)
        chl_val = round(0.38 + ((abs(latitude * 17.1 + longitude * 7.3) % 35) / 100.0), 2)
        return ChlorophyllResponse(
            dataset_id="cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
            dataset_version="202311",
            variable="CHL",
            requested_location=SSTLocation(latitude=latitude, longitude=longitude),
            sampled_location=SSTLocation(
                latitude=round(latitude, 3), longitude=round(longitude, 3)
            ),
            sample_distance_km=0.8,
            chlorophyll_a=ChlorophyllValue(value=chl_val, unit="mg/m³"),
            analysis_time=now,
            retrieved_at=now,
            spatial_resolution_km=4.0,
            sampling_quality=ChlorophyllSamplingQuality.EXACT_GRID_CELL,
            data_provenance=ChlorophyllDataProvenance.MULTI_SENSOR_MERGED_SATELLITE_PIXEL,
            quality=ChlorophyllQualityMetadata(
                flag_value=0,
                land=False,
                interpolated=False,
                uncertainty_percent=12.5,
                evidence_quality=ChlorophyllEvidenceQuality.NORMAL,
            ),
            cache_status=ChlorophyllCacheStatus.FRESH,
            warnings=[],
        )


class DemoCurrentService:
    async def get_current(
        self, latitude: float, longitude: float, at: datetime | None = None
    ) -> CurrentResponse:
        if is_land_coordinate(latitude, longitude)[0]:
            raise NoValidCurrentCellError(
                f"Location ({latitude:.4f}, {longitude:.4f}) is on land; ocean surface currents do not occur inland"
            )
        now = _ensure_utc(at)
        speed = round(0.18 + ((abs(latitude * 5.2 + longitude * 11.7) % 15) / 100.0), 2)
        return CurrentResponse(
            dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
            dataset_version="202411",
            requested_location=SSTLocation(latitude=latitude, longitude=longitude),
            sampled_location=SSTLocation(
                latitude=round(latitude, 3), longitude=round(longitude, 3)
            ),
            distance_km=1.5,
            sampled_depth_m=0.5,
            valid_time=now,
            analysis_or_retrieval_time=now,
            sampling_quality=CurrentSamplingQuality.NEAREST_GRID_CELL,
            evidence_quality=CurrentEvidenceQuality.NORMAL,
            time_classification=CurrentTimeClassification.ANALYSIS,
            total_current=CurrentTotalVector(
                eastward_mps=round(speed * 0.8, 2),
                northward_mps=round(-speed * 0.5, 2),
                speed_mps=speed,
                direction_toward_deg=123.7,
                direction_toward_compass="SE",
            ),
            components=CurrentComponents(
                general_circulation=CurrentVector(
                    eastward_mps=round(speed * 0.6, 2),
                    northward_mps=round(-speed * 0.4, 2),
                ),
                tide=CurrentVector(eastward_mps=0.03, northward_mps=-0.02),
                stokes_drift=CurrentVector(eastward_mps=0.01, northward_mps=-0.01),
            ),
            decomposition_complete=True,
            component_residual_mps=CurrentResidual(eastward=0.0, northward=0.0),
            cache_status=CurrentCacheStatus.FRESH,
            warnings=[],
        )


class DemoTideService:
    async def get_sea_level(
        self, latitude: float, longitude: float, at: datetime | None = None
    ) -> SeaLevelResponse:
        if is_land_coordinate(latitude, longitude)[0]:
            raise NoValidTideCellError(
                f"Location ({latitude:.4f}, {longitude:.4f}) is on land; astronomical sea level tides do not occur inland"
            )
        now = _ensure_utc(at)
        tide_elev = round(0.15 + ((abs(latitude * 2.3 + longitude * 4.1) % 20) / 100.0), 2)
        total_sl = round(tide_elev + 0.35, 2)
        return SeaLevelResponse(
            dataset_id="cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.25deg_P1D",
            dataset_version="202406",
            requested_location=SSTLocation(latitude=latitude, longitude=longitude),
            sampled_location=SSTLocation(
                latitude=round(latitude, 3), longitude=round(longitude, 3)
            ),
            distance_km=3.0,
            provider_surface_level_coordinate_m=0.0,
            valid_time=now,
            time_classification=TideTimeClassification.ANALYSIS,
            astronomical_tide_elevation_m=0.2,
            total_modelled_sea_level_m=0.55,
            reconstructed_total_sea_level_m=0.55,
            decomposition_residual_m=0.0,
            components=SeaLevelComponents(
                non_tidal_dynamic_sea_level_m=0.25,
                inverse_barometer_m=0.05,
                global_mean_steric_variation_m=0.03,
                global_mean_mass_variation_m=0.02,
                tide_loading_m=0.04,
            ),
            sampling_quality=TideSamplingQuality.EXACT_GRID_CELL,
            model_evidence_quality=TideEvidenceQuality.NORMAL,
            spatial_representativeness=TideEvidenceQuality.NORMAL,
            decomposition_evidence_quality=TideEvidenceQuality.NORMAL,
            cache_status=TideCacheStatus.FRESH,
            retrieved_at=now,
            warnings=[],
        )

