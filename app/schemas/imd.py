from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class IMDWarnSeverity(str, Enum):
    INFO = "INFO"
    WATCH = "WATCH"
    ALERT = "ALERT"
    WARNING = "WARNING"
    DANGER = "DANGER"


# ---------------------------------------------------------------------------
# 1. Port Warnings (/api/v1/portwarning)
# ---------------------------------------------------------------------------

class IMDPortWarningItem(BaseModel):
    port_id: str | int = Field(..., description="Unique port code or ID")
    port_name: str = Field(..., description="Name of the coastal port (e.g. Kandla, Veraval, Paradip)")
    state: str = Field(..., description="Maritime state (e.g. Gujarat, Odisha)")
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    signal_number: int = Field(..., ge=0, le=11, description="Official port danger signal 1 to 11 (0 if no signal hoisted)")
    signal_type: str = Field(..., description="e.g. 'Local Cautionary', 'Squally Weather', 'Danger', 'Great Danger'")
    signal_description: str = Field(default="", description="Text explanation of the hoisted signal")
    issue_time: datetime = Field(..., description="Timestamp of issue")
    valid_until: datetime | None = Field(default=None, description="Expiration/validity of the port signal")


class IMDPortWarningResponse(BaseModel):
    status: Literal["success", "error"] = "success"
    bulletin_number: str | None = None
    issued_at: datetime
    warnings: list[IMDPortWarningItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 2. Coastal & Fishermen Bulletins (/api/v1/coastalbulletin, /api/v1/seabulletin)
# ---------------------------------------------------------------------------

class SeaState(str, Enum):
    SMOOTH = "smooth"
    SLIGHT = "slight"
    MODERATE = "moderate"
    ROUGH = "rough"
    VERY_ROUGH = "very_rough"
    HIGH = "high"
    VERY_HIGH = "very_high"
    PHENOMENAL = "phenomenal"


class IMDCoastalBulletinItem(BaseModel):
    coastal_zone: str = Field(..., description="e.g. 'North Gujarat Coast', 'Konkan-Goa', 'South Tamil Nadu'")
    wind_direction: str | None = None
    wind_speed_knots_min: float | None = Field(default=None, ge=0)
    wind_speed_knots_max: float | None = Field(default=None, ge=0)
    wind_gusts_knots: float | None = Field(default=None, ge=0)
    sea_condition: SeaState | str | None = None
    fishermen_warning: bool = Field(
        default=False, 
        description="True if fishermen are advised NOT to venture into deep sea"
    )
    advisory_text: str = Field(..., description="Official advice / warning message text")
    valid_from: datetime
    valid_to: datetime


class IMDCoastalBulletinResponse(BaseModel):
    status: Literal["success", "error"] = "success"
    bulletin_number: str | None = None
    issued_at: datetime
    bulletins: list[IMDCoastalBulletinItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 3. Cyclone Track & Cone of Uncertainty (/api/v1/cyclone_cou, /api/v1/cyclone_track)
# ---------------------------------------------------------------------------

class CycloneIntensity(str, Enum):
    DEPRESSION = "Depression"
    DEEP_DEPRESSION = "Deep Depression"
    CYCLONIC_STORM = "Cyclonic Storm"
    SEVERE_CYCLONIC_STORM = "Severe Cyclonic Storm"
    VERY_SEVERE_CYCLONIC_STORM = "Very Severe Cyclonic Storm"
    EXTREMELY_SEVERE_CYCLONIC_STORM = "Extremely Severe Cyclonic Storm"
    SUPER_CYCLONIC_STORM = "Super Cyclonic Storm"


class IMDCycloneTrackPoint(BaseModel):
    forecast_hour: int = Field(..., ge=0, description="0 for current/observed, +6, +12, etc.")
    valid_time: datetime
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    intensity: CycloneIntensity | str
    max_sustained_wind_knots: float = Field(..., ge=0)
    estimated_central_pressure_hpa: float | None = None


class IMDCycloneConeGeoJSON(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any] = Field(..., description="Polygon or MultiPolygon GeoJSON geometry representing Cone of Uncertainty")
    properties: dict[str, Any] = Field(default_factory=dict)


class IMDCycloneWarningResponse(BaseModel):
    status: Literal["success", "error"] = "success"
    cyclone_name: str = Field(..., description="Storm designation e.g. 'ASNA', 'BIPARJOY', 'BOB 01'")
    basin: Literal["Arabian Sea", "Bay of Bengal", "North Indian Ocean"] = "North Indian Ocean"
    bulletin_number: str
    current_intensity: CycloneIntensity | str
    current_position: IMDCycloneTrackPoint | None = None
    forecast_track: list[IMDCycloneTrackPoint] = Field(default_factory=list)
    cone_of_uncertainty: IMDCycloneConeGeoJSON | None = None


# ---------------------------------------------------------------------------
# 4. MapLibre GeoJSON Hazard Layer Aggregation
# ---------------------------------------------------------------------------

class HazardFeatureProperties(BaseModel):
    hazard_type: Literal["cyclone_cone", "cyclone_track", "port_warning", "coastal_warning"]
    title: str
    severity: IMDWarnSeverity
    signal_number: int | None = None
    details: str
    issued_at: datetime
    valid_until: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class HazardGeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any] = Field(..., description="GeoJSON Point, LineString, or Polygon")
    properties: HazardFeatureProperties


class IMDMarineHazardFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[HazardGeoJSONFeature] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

