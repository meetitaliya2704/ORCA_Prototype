from __future__ import annotations

from datetime import UTC, datetime
import pytest

from app.domain.risk_rules import (
    CorridorHazardEvaluation,
    evaluate_corridor_imd_hazards,
)
from app.schemas.assessment import AssessmentOutcome, OperationalLimits
from app.schemas.imd import (
    HazardFeatureProperties,
    HazardGeoJSONFeature,
    IMDCoastalBulletinItem,
    IMDCoastalBulletinResponse,
    IMDMarineHazardFeatureCollection,
    IMDWarnSeverity,
)
from app.schemas.pfz_journey import JourneyLocation, JourneyStatus, PFZJourneyRequest
from app.services.geospatial import (
    line_intersects_polygon,
    line_segment_intersects,
    point_in_polygon,
    point_to_segment_distance_km,
)
from app.services.pfz_journey import PFZJourneyService
from tests.test_pfz_api import nearest_service


# ==============================================================================
# 1. Pure Geometry Tests
# ==============================================================================

def test_point_in_polygon_ray_casting():
    # Square polygon in Arabian sea: [70, 18] to [72, 20]
    square = [
        [70.0, 18.0],
        [72.0, 18.0],
        [72.0, 20.0],
        [70.0, 20.0],
        [70.0, 18.0],
    ]
    # Inside
    assert point_in_polygon(71.0, 19.0, square) is True
    # Outside
    assert point_in_polygon(69.0, 19.0, square) is False
    assert point_in_polygon(71.0, 21.0, square) is False


def test_line_segment_intersects():
    # Crossing segments: (0, 0)->(2, 2) and (0, 2)->(2, 0)
    assert line_segment_intersects((0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0)) is True
    # Parallel non-intersecting
    assert line_segment_intersects((0.0, 0.0), (2.0, 0.0), (0.0, 1.0), (2.0, 1.0)) is False


def test_line_intersects_polygon():
    cone_geom = {
        "type": "Polygon",
        "coordinates": [
            [
                [85.0, 17.0],
                [88.0, 17.0],
                [88.0, 20.0],
                [85.0, 20.0],
                [85.0, 17.0],
            ]
        ],
    }
    # Corridor crossing through cone
    crossing_line = [(84.0, 18.5), (89.0, 18.5)]
    assert line_intersects_polygon(crossing_line, cone_geom) is True

    # Corridor completely outside cone
    clear_line = [(80.0, 15.0), (82.0, 16.0)]
    assert line_intersects_polygon(clear_line, cone_geom) is False


def test_point_to_segment_distance_km():
    # Segment along equator from lon 70 to 72 (lat 0)
    # Point at lon 71, lat 0.1 (approx 11.1 km north)
    dist = point_to_segment_distance_km(
        p_lon=71.0, p_lat=0.1,
        a_lon=70.0, a_lat=0.0,
        b_lon=72.0, b_lat=0.0,
    )
    assert 10.0 < dist < 12.0


# ==============================================================================
# 2. Corridor Hazard Veto Logic Tests
# ==============================================================================

def test_corridor_cyclone_cone_veto():
    cone_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [72.0, 18.0],
                    [74.0, 18.0],
                    [74.0, 20.0],
                    [72.0, 20.0],
                    [72.0, 18.0],
                ]
            ],
        },
        "properties": {
            "hazard_type": "cyclone_cone",
            "title": "Cyclone Vayu — Cone of Uncertainty",
            "severity": "DANGER",
        },
    }

    # Route from (71.0, 19.0) to (75.0, 19.0) passes right through the cone
    eval_veto = evaluate_corridor_imd_hazards(
        origin_lon=71.0, origin_lat=19.0,
        destination_lon=75.0, destination_lat=19.0,
        hazard_features=[cone_feature],
    )
    assert eval_veto.vetoed is True
    assert eval_veto.veto_code == "OFFICIAL_IMD_CYCLONE_WARNING"
    assert "Cyclone Vayu" in eval_veto.veto_message

    # Safe route completely south of the cone
    eval_safe = evaluate_corridor_imd_hazards(
        origin_lon=71.0, origin_lat=16.0,
        destination_lon=75.0, destination_lat=16.0,
        hazard_features=[cone_feature],
    )
    assert eval_safe.vetoed is False


def test_corridor_port_warning_proximity_veto():
    # Port with Danger Signal 3 at (72.85, 18.95) — Mumbai
    port_feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [72.85, 18.95]},
        "properties": {
            "hazard_type": "port_warning",
            "title": "Mumbai Port — LC3",
            "signal_number": 3,
            "severity": "ALERT",
        },
    }

    # Corridor passing within 10 km of Mumbai port
    eval_near = evaluate_corridor_imd_hazards(
        origin_lon=72.80, origin_lat=18.90,
        destination_lon=72.90, destination_lat=19.00,
        hazard_features=[port_feature],
        port_proximity_buffer_km=25.0,
    )
    assert eval_near.vetoed is True
    assert eval_near.veto_code == "OFFICIAL_IMD_PORT_WARNING"
    assert eval_near.distance_km < 25.0

    # Corridor far off-shore (> 50 km away)
    eval_far = evaluate_corridor_imd_hazards(
        origin_lon=71.50, origin_lat=18.90,
        destination_lon=71.60, destination_lat=19.00,
        hazard_features=[port_feature],
        port_proximity_buffer_km=25.0,
    )
    assert eval_far.vetoed is False


# ==============================================================================
# 3. End-to-End PFZJourneyService Corridor Veto Integration Test
# ==============================================================================

from tests.test_pfz_journey_service import journey_service, journey_request


class FakeIMDServiceWithCyclone:
    async def build_hazard_feature_collection(self):
        return IMDMarineHazardFeatureCollection(
            type="FeatureCollection",
            features=[
                HazardGeoJSONFeature(
                    type="Feature",
                    geometry={
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [68.0, 20.0],
                                [72.0, 20.0],
                                [72.0, 23.0],
                                [68.0, 23.0],
                                [68.0, 20.0],
                            ]
                        ],
                    },
                    properties=HazardFeatureProperties(
                        hazard_type="cyclone_cone",
                        title="Cyclone Test Cone",
                        severity=IMDWarnSeverity.DANGER,
                        details="Cone of uncertainty active",
                        issued_at=datetime.now(UTC),
                    ),
                )
            ],
            metadata={"source": "test"},
        )

    async def get_coastal_bulletins(self):
        return IMDCoastalBulletinResponse(
            issued_at=datetime.now(UTC),
            bulletins=[],
        ), "fresh"


class FakeIMDServiceWithPortWarning:
    async def build_hazard_feature_collection(self):
        return IMDMarineHazardFeatureCollection(
            type="FeatureCollection",
            features=[
                HazardGeoJSONFeature(
                    type="Feature",
                    geometry={
                        "type": "Point",
                        "coordinates": [69.65, 21.65],
                    },
                    properties=HazardFeatureProperties(
                        hazard_type="port_warning",
                        title="Porbandar Port — LC3",
                        signal_number=3,
                        severity=IMDWarnSeverity.ALERT,
                        details="Squally weather signal 3 hoisted",
                        issued_at=datetime.now(UTC),
                    ),
                )
            ],
            metadata={"source": "test"},
        )

    async def get_coastal_bulletins(self):
        return IMDCoastalBulletinResponse(
            issued_at=datetime.now(UTC),
            bulletins=[],
        ), "fresh"


class FakeIMDServiceWithFishermenWarning:
    async def build_hazard_feature_collection(self):
        return IMDMarineHazardFeatureCollection(
            type="FeatureCollection",
            features=[],
            metadata={"source": "test"},
        )

    async def get_coastal_bulletins(self):
        return IMDCoastalBulletinResponse(
            issued_at=datetime.now(UTC),
            bulletins=[
                IMDCoastalBulletinItem(
                    coastal_zone="Gujarat Coast",
                    wind_direction="SW",
                    wind_speed_knots_min=25,
                    wind_speed_knots_max=35,
                    wind_gusts_knots=45,
                    sea_condition="rough",
                    fishermen_warning=True,
                    advisory_text="Squally weather. Fishermen are advised NOT to venture into deep sea.",
                    valid_from=datetime.now(UTC),
                    valid_to=datetime.now(UTC),
                )
            ],
        ), "fresh"


@pytest.mark.asyncio
async def test_pfz_journey_vetoed_by_imd_cyclone():
    service, _, _ = await journey_service(origin_wave=1.0, destination_wave=1.0)
    service.imd_service = FakeIMDServiceWithCyclone()

    response = await service.run(journey_request())
    assert response.journey_status == JourneyStatus.PFZ_AVAILABLE_LIMIT_EXCEEDED
    assert any(r.code == "OFFICIAL_IMD_CYCLONE_WARNING" for r in response.reasons)
    assert any(r.code == "ROUTE_HAZARD_INTERSECTION" for r in response.reasons)
    assert response.limitations.official_warning_coverage == "imd_active"


@pytest.mark.asyncio
async def test_pfz_journey_vetoed_by_imd_port_warning():
    service, _, _ = await journey_service(origin_wave=1.0, destination_wave=1.0)
    service.imd_service = FakeIMDServiceWithPortWarning()

    response = await service.run(journey_request())
    assert response.journey_status == JourneyStatus.PFZ_AVAILABLE_LIMIT_EXCEEDED
    assert any(r.code == "OFFICIAL_IMD_PORT_WARNING" for r in response.reasons)
    assert any(r.code == "ROUTE_HAZARD_INTERSECTION" for r in response.reasons)
    assert response.limitations.official_warning_coverage == "imd_active"


@pytest.mark.asyncio
async def test_pfz_journey_vetoed_by_imd_fishermen_advisory():
    service, _, _ = await journey_service(origin_wave=1.0, destination_wave=1.0)
    service.imd_service = FakeIMDServiceWithFishermenWarning()

    response = await service.run(journey_request())
    assert response.journey_status == JourneyStatus.PFZ_AVAILABLE_LIMIT_EXCEEDED
    assert any(r.code == "OFFICIAL_IMD_FISHERMEN_WARNING" for r in response.reasons)
    assert response.limitations.official_warning_coverage == "imd_active"

