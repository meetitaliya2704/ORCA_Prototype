from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.schemas.imd import (
    IMDCoastalBulletinResponse,
    IMDCycloneWarningResponse,
    IMDMarineHazardFeatureCollection,
    IMDPortWarningResponse,
    HazardGeoJSONFeature,
    HazardFeatureProperties,
    IMDWarnSeverity,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "imd"


def test_port_warnings_schema_validation():
    fixture_path = FIXTURES_DIR / "port_warnings_sample.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    response = IMDPortWarningResponse.model_validate(data)

    assert response.status == "success"
    assert response.bulletin_number == "PW-20260922-01"
    assert len(response.warnings) == 3

    veraval = next(w for w in response.warnings if w.port_name == "Veraval")
    assert veraval.signal_number == 3
    assert veraval.latitude == 20.9000
    assert veraval.longitude == 70.3667
    assert "squally" in veraval.signal_description.lower()


def test_coastal_bulletin_schema_validation():
    fixture_path = FIXTURES_DIR / "coastal_bulletin_sample.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    response = IMDCoastalBulletinResponse.model_validate(data)

    assert response.status == "success"
    assert len(response.bulletins) == 2

    gujarat = response.bulletins[0]
    assert gujarat.fishermen_warning is True
    assert gujarat.wind_gusts_knots == 45.0
    assert gujarat.sea_condition == "rough"

    konkan = response.bulletins[1]
    assert konkan.fishermen_warning is False


def test_cyclone_cou_schema_validation():
    fixture_path = FIXTURES_DIR / "cyclone_cou_sample.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    response = IMDCycloneWarningResponse.model_validate(data)

    assert response.cyclone_name == "BOB 02"
    assert response.current_intensity == "Deep Depression"
    assert response.cone_of_uncertainty is not None
    assert response.cone_of_uncertainty.geometry["type"] == "Polygon"
    assert len(response.forecast_track) == 2
    assert response.forecast_track[1].intensity == "Severe Cyclonic Storm"


def test_hazard_geojson_feature_collection():
    feature = HazardGeoJSONFeature(
        type="Feature",
        geometry={"type": "Point", "coordinates": [70.3667, 20.9000]},
        properties=HazardFeatureProperties(
            hazard_type="port_warning",
            title="Veraval Port Warning - Signal 3",
            severity=IMDWarnSeverity.ALERT,
            signal_number=3,
            details="Local Cautionary Signal No. III hoisted.",
            issued_at="2026-09-22T06:00:00Z",
        ),
    )
    collection = IMDMarineHazardFeatureCollection(
        type="FeatureCollection",
        features=[feature],
        metadata={"source": "India Meteorological Department (IMD)"},
    )

    dumped = collection.model_dump(mode="json")
    assert dumped["type"] == "FeatureCollection"
    assert len(dumped["features"]) == 1
    assert dumped["features"][0]["properties"]["hazard_type"] == "port_warning"
    assert dumped["features"][0]["properties"]["signal_number"] == 3

